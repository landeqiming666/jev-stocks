use super::{security, BridgeState};

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
    Err("外链打开接口尚未接入，请复制链接到浏览器。".into())
}
