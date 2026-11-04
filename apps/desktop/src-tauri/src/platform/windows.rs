use std::os::windows::process::CommandExt;
use std::process::{Child, Command, Stdio};

use tauri::{Manager, Runtime, WebviewWindowBuilder};

use super::Platform;

const CREATE_NO_WINDOW: u32 = 0x0800_0000;

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
        builder.decorations(true)
    }

    fn prepare_core_command(&self, cmd: &mut Command) {
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    fn kill_process_tree(&self, child: &mut Child) {
        if let Ok(Some(_)) = child.try_wait() {
            return;
        }

        // 开发模式中的 uv 会再启动 Python，先按根 PID 结束整棵树。
        let _ = Command::new("taskkill.exe")
            .args(["/PID", &child.id().to_string(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();

        // taskkill 无法启动或结束根进程时，仍用 Child 句柄尝试结束并等待。
        let _ = child.kill();
        let _ = child.wait();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn init_script_sets_windows_platform() {
        let script = Windows.init_script();
        assert!(script.contains(r#"document.documentElement.dataset.platform = "windows""#));
        assert!(script.contains("DOMContentLoaded"));
    }
}
