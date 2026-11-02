use super::{security, BridgeState};
pub use crate::platform::ExternalOpenError;
use crate::platform::Platform;

pub fn open_external_with(
    url: &str,
    opener: impl FnOnce(&str) -> Result<(), ExternalOpenError>,
) -> Result<(), String> {
    security::validate_url(url).map_err(|error| error.message)?;
    opener(url).map_err(|error| error.to_string())
}

#[tauri::command]
pub async fn rpc_send(line: String, state: tauri::State<'_, BridgeState>) -> Result<(), String> {
    let shared = state.shared.clone();
    tauri::async_runtime::spawn_blocking(move || super::send_shared(&shared, &line))
        .await
        .map_err(|e| e.to_string())?
        .map_err(|e| e.message)
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
