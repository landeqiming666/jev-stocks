use std::os::unix::process::CommandExt;
use tauri::{Manager, Runtime, WebviewWindowBuilder};

use super::{ExternalOpenError, Platform};

pub struct MacOs;

fn open_external_command(url: &str) -> std::process::Command {
    let mut command = std::process::Command::new("/usr/bin/open");
    command
        .arg(url)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());
    command
}

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

    fn prepare_core_command(&self, cmd: &mut std::process::Command) {
        // The core and its descendants need a group separate from the desktop app.
        cmd.process_group(0);
    }

    fn kill_process_tree(&self, child: &mut std::process::Child) {
        let _ = std::process::Command::new("/bin/kill")
            .args(["-KILL", "--", &format!("-{}", child.id())])
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status();
        let _ = child.kill();
    }

    fn open_external(&self, url: &str) -> Result<(), ExternalOpenError> {
        let status = open_external_command(url).status()?;
        if status.success() {
            Ok(())
        } else {
            Err(ExternalOpenError::Exited(status.code()))
        }
    }
}

#[cfg(test)]
mod tests {
    use std::io::{BufRead, BufReader};
    use std::process::{Child, Command, Stdio};
    use std::time::{Duration, Instant};

    use super::{open_external_command, MacOs, Platform};

    #[test]
    fn external_open_command_uses_executable_open_with_one_complete_url_argument() {
        use std::os::unix::fs::PermissionsExt;

        let url = "https://example.com/a%20b?q=%22value%22&literal=$(touch%20test);x=1#part";
        let command = open_external_command(url);
        assert_eq!(command.get_program(), "/usr/bin/open");
        assert_eq!(
            command.get_args().collect::<Vec<_>>(),
            vec![std::ffi::OsStr::new(url)]
        );
        let metadata = std::fs::metadata(command.get_program()).unwrap();
        assert!(metadata.is_file());
        assert_ne!(metadata.permissions().mode() & 0o111, 0);
    }

    struct OwnedCore(Child);

    impl Drop for OwnedCore {
        fn drop(&mut self) {
            MacOs.kill_process_tree(&mut self.0);
            let _ = self.0.wait();
        }
    }

    #[test]
    fn killing_prepared_core_terminates_its_sleeping_descendant() {
        let mut command = Command::new("/bin/sh");
        command
            .args(["-c", "sleep 60 & echo $!; wait"])
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        MacOs.prepare_core_command(&mut command);
        let mut core = OwnedCore(command.spawn().expect("spawn test core"));
        let mut line = String::new();
        BufReader::new(core.0.stdout.take().expect("test stdout"))
            .read_line(&mut line)
            .expect("read descendant pid");
        let descendant: u32 = line.trim().parse().expect("descendant pid");
        MacOs.kill_process_tree(&mut core.0);
        core.0.wait().expect("reap test core");
        let deadline = Instant::now() + Duration::from_secs(3);
        loop {
            let output = Command::new("/bin/ps")
                .args(["-o", "stat=", "-p", &descendant.to_string()])
                .output()
                .expect("inspect test descendant");
            let state = String::from_utf8_lossy(&output.stdout);
            if state.trim().is_empty() || state.trim().starts_with('Z') {
                break;
            }
            assert!(
                Instant::now() < deadline,
                "descendant still running: {state}"
            );
            std::thread::sleep(Duration::from_millis(10));
        }
    }
}
