use super::{BridgeError, BridgeErrorCode};

pub const MAX_LINE_BYTES: usize = 1_048_576;
pub const CSP_POLICY: &str = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src ipc: http://ipc.localhost; object-src 'none'; base-uri 'none'; frame-ancestors 'none'";

pub fn csp() -> &'static str {
    CSP_POLICY
}
pub fn secure_context<R: tauri::Runtime>(mut context: tauri::Context<R>) -> tauri::Context<R> {
    let security = &mut context.config_mut().app.security;
    security.csp = Some(tauri::utils::config::Csp::Policy(CSP_POLICY.into()));
    security.dev_csp = Some(tauri::utils::config::Csp::Policy(CSP_POLICY.into()));
    context
}
pub fn validate_url(url: &str) -> Result<tauri::Url, BridgeError> {
    let parsed =
        tauri::Url::parse(url).map_err(|_| BridgeError::new(BridgeErrorCode::InvalidUrl))?;
    let authority = url
        .split_once("://")
        .map(|(_, s)| s.split(['/', '?', '#']).next().unwrap_or(""));
    if parsed.scheme() != "https"
        || parsed.host_str().is_none_or(str::is_empty)
        || authority.is_none_or(str::is_empty)
    {
        return Err(BridgeError::new(BridgeErrorCode::InvalidUrl));
    }
    Ok(parsed)
}
pub fn validate_line(line: &str) -> Result<(), BridgeError> {
    if line.len() > MAX_LINE_BYTES {
        return Err(BridgeError::new(BridgeErrorCode::LineTooLarge));
    }
    if line.contains(['\r', '\n']) {
        return Err(BridgeError::new(BridgeErrorCode::WriteFailed));
    }
    // rs- 名称空间只属于监督器，前端不能伪造它的请求。
    if serde_json::from_str::<serde_json::Value>(line)
        .ok()
        .and_then(|v| {
            v.get("id")
                .and_then(|id| id.as_str())
                .map(|id| id.starts_with("rs-"))
        })
        .unwrap_or(false)
    {
        return Err(BridgeError::new(BridgeErrorCode::WriteFailed));
    }
    Ok(())
}
