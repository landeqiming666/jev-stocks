use tauri::{Manager, Runtime, WebviewWindowBuilder};

#[allow(dead_code)] // C-02 才会调用 name / prepare_core_command / kill_process_tree。
pub trait Platform: Sync {
    fn name(&self) -> &'static str;
    fn init_script(&self) -> String;
    fn configure_window<'a, R: Runtime, M: Manager<R>>(
        &self,
        builder: WebviewWindowBuilder<'a, R, M>,
    ) -> WebviewWindowBuilder<'a, R, M>;
    fn prepare_core_command(&self, cmd: &mut std::process::Command);
    fn kill_process_tree(&self, child: &mut std::process::Child);
}

#[cfg(target_os = "macos")]
mod macos;
#[cfg(windows)]
mod windows;

#[cfg(target_os = "macos")]
pub fn current() -> impl Platform {
    macos::MacOs
}

#[cfg(windows)]
pub fn current() -> impl Platform {
    windows::Windows
}

#[cfg(not(any(target_os = "macos", windows)))]
compile_error!("不支持的平台：只支持 macOS 与 Windows");
