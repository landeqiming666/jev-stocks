use super::{security, BridgeState, CoreStatus};
pub use crate::platform::ExternalOpenError;
use crate::platform::Platform;

pub fn open_external_with(
    url: &str,
    opener: impl FnOnce(&str) -> Result<(), ExternalOpenError>,
) -> Result<(), String> {
    security::validate_url(url).map_err(|error| error.message)?;
    opener(url).map_err(|error| error.to_string())
}

pub fn core_status_snapshot(state: &BridgeState) -> CoreStatus {
    super::status(state)
}

#[tauri::command]
pub fn core_status(state: tauri::State<'_, BridgeState>) -> CoreStatus {
    core_status_snapshot(&state)
}

#[tauri::command]
pub async fn rpc_send(line: String, state: tauri::State<'_, BridgeState>) -> Result<(), String> {
    let shared = state.shared.clone();
    tauri::async_runtime::spawn_blocking(move || super::send_shared(&shared, &line))
        .await
        .map_err(rpc_task_error_message)?
        .map_err(|e| e.message)
}

fn rpc_task_error_message(error: tauri::Error) -> String {
    match error {
        tauri::Error::JoinError(join) if join.is_panic() => {
            "核心请求任务异常终止，请稍后重试。".to_string()
        }
        tauri::Error::JoinError(join) if join.is_cancelled() => {
            "核心请求任务已取消，请稍后重试。".to_string()
        }
        _ => "核心请求任务未能完成，请稍后重试。".to_string(),
    }
}
#[tauri::command]
pub async fn open_external<R: tauri::Runtime>(
    url: String,
    _app: tauri::AppHandle<R>,
) -> Result<(), String> {
    security::validate_url(&url).map_err(|e| e.message)?;
    tauri::async_runtime::spawn_blocking(move || {
        open_external_with(&url, |url| crate::platform::current().open_external(url))
    })
    .await
    .map_err(|error| match error {
        tauri::Error::JoinError(join) if join.is_panic() => {
            "无法打开链接：外链任务异常终止。".to_string()
        }
        tauri::Error::JoinError(join) if join.is_cancelled() => {
            "无法打开链接：外链任务被取消。".to_string()
        }
        _ => "无法打开链接：外链任务未能完成。".to_string(),
    })?
}

#[cfg(test)]
mod tests {
    #[test]
    fn rpc_task_panic_returns_fixed_message_without_request_or_panic_body() {
        let error =
            tauri::async_runtime::block_on(tauri::async_runtime::spawn_blocking(|| -> () {
                std::panic::resume_unwind(Box::new(
                    r#"request={"id":"r-private","params":{"token":"test-secret"}}"#.to_string(),
                ));
            }))
            .unwrap_err();
        let message = super::rpc_task_error_message(error);
        assert_eq!(message, "核心请求任务异常终止，请稍后重试。");
        for private in ["r-private", "test-secret", "params", "token"] {
            assert!(!message.contains(private));
        }
    }
}
