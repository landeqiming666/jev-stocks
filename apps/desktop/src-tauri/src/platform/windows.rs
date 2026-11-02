use tauri::{Manager, Runtime, WebviewWindowBuilder};

use super::Platform;

/// 占位实现：W-01 接手并补齐 Windows 平台行为。
pub struct Windows;

impl Platform for Windows {
    fn name(&self) -> &'static str {
        "windows"
    }

    fn init_script(&self) -> String {
        r#"if (document.documentElement) { document.documentElement.dataset.platform = "windows"; }
document.addEventListener("DOMContentLoaded", function () { document.documentElement.dataset.platform = "windows"; });"#
            .to_string()
    }

    fn configure_window<'a, R: Runtime, M: Manager<R>>(
        &self,
        builder: WebviewWindowBuilder<'a, R, M>,
    ) -> WebviewWindowBuilder<'a, R, M> {
        builder
    }

    fn prepare_core_command(&self, _cmd: &mut std::process::Command) {}

    fn kill_process_tree(&self, child: &mut std::process::Child) {
        let _ = child.kill();
    }
}
