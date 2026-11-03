pub mod commands;
pub mod process;
pub mod security;

pub use security::csp;
use std::sync::{mpsc, Arc, Mutex};
use std::thread::JoinHandle;
use tauri::{Emitter, Manager};

#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "lowercase")]
pub enum CoreState {
    Starting,
    Ready,
    Restarting,
    Failed,
}
#[derive(Clone, Debug, serde::Serialize)]
pub struct CoreStatus {
    pub state: CoreState,
    pub attempt: u8,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BridgeErrorCode {
    NotReady,
    LineTooLarge,
    InvalidUrl,
    SpawnFailed,
    WriteFailed,
    Timeout,
}
#[derive(Clone, Debug)]
pub struct BridgeError {
    pub code: BridgeErrorCode,
    pub message: String,
}
impl BridgeError {
    pub(crate) fn new(code: BridgeErrorCode) -> Self {
        let message = match code {
            BridgeErrorCode::NotReady => "核心进程尚未就绪，请稍后重试。",
            BridgeErrorCode::LineTooLarge => "请求超过 1 MB，无法发送。",
            BridgeErrorCode::InvalidUrl => "只允许打开 https 链接。",
            BridgeErrorCode::SpawnFailed => "核心进程无法启动，请查看日志。",
            BridgeErrorCode::WriteFailed => "核心进程已断开，正在重启。",
            BridgeErrorCode::Timeout => "核心进程响应超时，请稍后重试。",
        };
        Self {
            code,
            message: message.into(),
        }
    }
}
impl std::fmt::Display for BridgeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}
impl std::error::Error for BridgeError {}
#[derive(Clone, Debug)]
pub enum BridgeEvent {
    Status(CoreStatus),
    Message(String),
}
pub(crate) struct View {
    status: CoreStatus,
    closing: bool,
    generation: u64,
    writer: Option<mpsc::SyncSender<process::Write>>,
}
pub(crate) struct Shared {
    view: Mutex<View>,
    events: mpsc::SyncSender<process::Event>,
    sink: Box<dyn Fn(BridgeEvent) + Send + Sync>,
    timings: process::Timings,
}
pub struct BridgeState {
    pub(crate) shared: Arc<Shared>,
    worker: Mutex<Option<JoinHandle<()>>>,
}
impl Default for BridgeState {
    fn default() -> Self {
        let (events, _) = mpsc::sync_channel(64);
        Self::new(events, process::Timings::default(), |_| {})
    }
}
impl BridgeState {
    fn new(
        events: mpsc::SyncSender<process::Event>,
        timings: process::Timings,
        sink: impl Fn(BridgeEvent) + Send + Sync + 'static,
    ) -> Self {
        Self {
            shared: Arc::new(Shared {
                view: Mutex::new(View {
                    status: CoreStatus {
                        state: CoreState::Starting,
                        attempt: 0,
                    },
                    closing: false,
                    generation: 0,
                    writer: None,
                }),
                events,
                sink: Box::new(sink),
                timings,
            }),
            worker: Mutex::new(None),
        }
    }
    pub fn start(
        config: process::CoreConfig,
        timings: process::Timings,
        sink: impl Fn(BridgeEvent) + Send + Sync + 'static,
    ) -> Result<Self, BridgeError> {
        let (events, rx) = mpsc::sync_channel(64);
        let state = Self::new(events, timings, sink);
        transition(&state.shared, CoreState::Starting, 0);
        let child = match process::build_command(&config).and_then(|mut cmd| {
            cmd.spawn()
                .map_err(|_| BridgeError::new(BridgeErrorCode::SpawnFailed))
        }) {
            Ok(child) => child,
            Err(_) => {
                transition(&state.shared, CoreState::Failed, 0);
                return Err(BridgeError::new(BridgeErrorCode::SpawnFailed));
            }
        };
        let shared = state.shared.clone();
        *state.worker.lock().unwrap_or_else(|e| e.into_inner()) =
            Some(std::thread::spawn(move || {
                process::supervise(shared, rx, config, child)
            }));
        Ok(state)
    }
}
impl Drop for BridgeState {
    fn drop(&mut self) {
        let _ = shutdown(self);
    }
}
pub fn status(state: &BridgeState) -> CoreStatus {
    state
        .shared
        .view
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .status
        .clone()
}
pub fn send_line(state: &BridgeState, line: &str) -> Result<(), BridgeError> {
    send_shared(&state.shared, line)
}
fn send_shared(shared: &Arc<Shared>, line: &str) -> Result<(), BridgeError> {
    security::validate_line(line)?;
    let view = shared.view.lock().unwrap_or_else(|e| e.into_inner());
    if view.closing || view.status.state != CoreState::Ready {
        return Err(BridgeError::new(BridgeErrorCode::NotReady));
    }
    if view.writer.is_none() {
        return Err(BridgeError::new(BridgeErrorCode::NotReady));
    }
    let generation = view.generation;
    let (tx, rx) = mpsc::channel();
    let queued = view.writer.as_ref().is_some_and(|writer| {
        writer
            .try_send(process::Write {
                line: line.into(),
                reply: Some(tx),
            })
            .is_ok()
    });
    drop(view);
    if queued {
        if let Ok(result) = rx.recv_timeout(shared.timings.write_timeout) {
            return result;
        }
    }
    let _ = shared.events.try_send(process::Event::Fault(generation));
    Err(BridgeError::new(BridgeErrorCode::WriteFailed))
}
pub fn shutdown(state: &BridgeState) -> Result<(), BridgeError> {
    state
        .shared
        .view
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .closing = true;
    let _ = state.shared.events.try_send(process::Event::Wake);
    let mut worker = state.worker.lock().unwrap_or_else(|e| e.into_inner());
    if let Some(handle) = worker.take() {
        handle
            .join()
            .map_err(|_| BridgeError::new(BridgeErrorCode::Timeout))?;
    }
    Ok(())
}
pub(crate) fn transition(shared: &Shared, state: CoreState, attempt: u8) {
    let status = CoreStatus { state, attempt };
    shared.view.lock().unwrap_or_else(|e| e.into_inner()).status = status.clone();
    (shared.sink)(BridgeEvent::Status(status));
}
fn emit_core_event<R: tauri::Runtime>(app: &tauri::AppHandle<R>, event: BridgeEvent) {
    let result = match event {
        BridgeEvent::Status(status) => app.emit("core://status", status),
        BridgeEvent::Message(line) => app.emit("core://message", line),
    };
    if result.is_err() {
        eprintln!("{{\"level\":\"warn\",\"module\":\"bridge\",\"error_code\":\"EMIT_FAILED\"}}");
    }
}

fn start_state<R: tauri::Runtime>(app: &tauri::AppHandle<R>) -> BridgeState {
    let handle = app.clone();
    let started = process::CoreConfig::from_app(app).and_then(|config| {
        BridgeState::start(config, process::Timings::default(), move |event| {
            emit_core_event(&handle, event);
        })
    });
    started.unwrap_or_else(|_| {
        let state = BridgeState::default();
        transition(&state.shared, CoreState::Failed, 0);
        let _ = app.emit("core://status", status(&state));
        state
    })
}

fn on_ready<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
    app.manage(start_state(app));
}

fn on_exit<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
    if let Some(state) = app.try_state::<BridgeState>() {
        let _ = shutdown(&state);
    }
}

pub fn install<R: tauri::Runtime>(builder: tauri::Builder<R>) -> tauri::Builder<R> {
    let plugin = tauri::plugin::Builder::<R>::new("core-bridge")
        .on_event(|app, event| match event {
            tauri::RunEvent::Ready => on_ready(app),
            tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit => on_exit(app),
            _ => {}
        })
        .build();
    builder
        .invoke_handler(tauri::generate_handler![
            commands::rpc_send,
            commands::core_status,
            commands::open_external
        ])
        .plugin(plugin)
}
