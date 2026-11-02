use tauri::{Manager, Runtime, WebviewWindowBuilder};

use super::Platform;

pub struct MacOs;

impl Platform for MacOs {
    fn name(&self) -> &'static str {
        "macos"
    }

    fn init_script(&self) -> String {
        r#"if (document.documentElement) { document.documentElement.dataset.platform = "macos"; }
document.addEventListener("DOMContentLoaded", function () { document.documentElement.dataset.platform = "macos"; });"#
            .to_string()
    }

    fn configure_window<'a, R: Runtime, M: Manager<R>>(
        &self,
        builder: WebviewWindowBuilder<'a, R, M>,
    ) -> WebviewWindowBuilder<'a, R, M> {
        builder
            .title_bar_style(tauri::TitleBarStyle::Overlay)
            .hidden_title(true)
    }

    fn prepare_core_command(&self, _cmd: &mut std::process::Command) {}

    fn kill_process_tree(&self, child: &mut std::process::Child) {
        let _ = child.kill();
    }
}
