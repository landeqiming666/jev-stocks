use tauri::{Manager, Runtime, WebviewWindowBuilder};

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ExternalOpenError {
    Io {
        kind: std::io::ErrorKind,
        raw_os_error: Option<i32>,
    },
    Exited(Option<i32>),
}

impl From<std::io::Error> for ExternalOpenError {
    fn from(error: std::io::Error) -> Self {
        // 系统或注入的错误正文可能携带完整 URL，只保留结构化原因。
        Self::Io {
            kind: error.kind(),
            raw_os_error: error.raw_os_error(),
        }
    }
}

impl std::fmt::Display for ExternalOpenError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io { kind, raw_os_error } => {
                write!(f, "无法打开链接：系统调用失败（{kind:?}")?;
                if let Some(code) = raw_os_error {
                    write!(f, "，系统错误码 {code}")?;
                }
                f.write_str("）。")
            }
            Self::Exited(Some(code)) => {
                write!(f, "无法打开链接：系统打开程序退出，状态码 {code}。")
            }
            Self::Exited(None) => f.write_str("无法打开链接：系统打开程序被信号终止。"),
        }
    }
}

impl std::error::Error for ExternalOpenError {}

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
    fn open_external(&self, _url: &str) -> Result<(), ExternalOpenError> {
        Err(std::io::Error::from(std::io::ErrorKind::Unsupported).into())
    }
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
