use super::{
    security::MAX_LINE_BYTES, transition, BridgeError, BridgeErrorCode, BridgeEvent, CoreState,
    Shared,
};
use crate::platform::Platform;
use std::{
    collections::HashMap,
    io::{BufRead, BufReader, Read, Write as IoWrite},
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{mpsc, Arc},
    thread,
    time::{Duration, Instant},
};
use tauri::Manager;

pub const CORE_HEARTBEAT_INTERVAL: Duration = Duration::from_secs(5);
pub const CORE_HEARTBEAT_TIMEOUT: Duration = Duration::from_secs(2);
pub const CORE_MAX_RESTARTS: u8 = 3;
pub const RESTART_DELAYS_MS: [u64; 3] = [1000, 2000, 4000];
pub const SHUTDOWN_GRACE: Duration = Duration::from_secs(3);
pub const DEFAULT_CORE_CMD: &str = "uv run --project core python -m sentinel";
#[derive(Clone)]
pub struct Timings {
    pub heartbeat_interval: Duration,
    pub heartbeat_timeout: Duration,
    pub startup_timeout: Duration,
    pub shutdown_grace: Duration,
    pub restart_delays: [Duration; 3],
    pub write_timeout: Duration,
}
impl Default for Timings {
    fn default() -> Self {
        Self {
            heartbeat_interval: CORE_HEARTBEAT_INTERVAL,
            heartbeat_timeout: CORE_HEARTBEAT_TIMEOUT,
            startup_timeout: Duration::from_secs(60),
            shutdown_grace: SHUTDOWN_GRACE,
            restart_delays: RESTART_DELAYS_MS.map(Duration::from_millis),
            write_timeout: CORE_HEARTBEAT_TIMEOUT,
        }
    }
}
pub struct CoreConfig {
    pub argv: Vec<String>,
    pub data_dir: PathBuf,
    pub resource_dir: PathBuf,
    pub parent_pid: u32,
    pub log_level: String,
}
impl CoreConfig {
    pub fn from_app<R: tauri::Runtime>(app: &tauri::AppHandle<R>) -> Result<Self, BridgeError> {
        let cmd = std::env::var("SENTINEL_CORE_CMD").unwrap_or_else(|_| DEFAULT_CORE_CMD.into());
        let data_dir = std::env::var_os("SENTINEL_DATA_DIR")
            .map(PathBuf::from)
            .map(Ok)
            .unwrap_or_else(|| app.path().app_data_dir())
            .map_err(|_| BridgeError::new(BridgeErrorCode::SpawnFailed))?;
        let resource_dir = app
            .path()
            .resource_dir()
            .map_err(|_| BridgeError::new(BridgeErrorCode::SpawnFailed))?;
        Ok(Self {
            argv: parse_core_command(&cmd)?,
            data_dir,
            resource_dir,
            parent_pid: std::process::id(),
            log_level: std::env::var("SENTINEL_LOG_LEVEL").unwrap_or_else(|_| "info".into()),
        })
    }
}
pub fn parse_core_command(cmd: &str) -> Result<Vec<String>, BridgeError> {
    let argv: Vec<String> = cmd.split_ascii_whitespace().map(str::to_owned).collect();
    if argv.is_empty() || cmd.contains(['\'', '"']) {
        return Err(BridgeError::new(BridgeErrorCode::SpawnFailed));
    }
    Ok(argv)
}
pub fn build_command(config: &CoreConfig) -> Result<Command, BridgeError> {
    let executable = config
        .argv
        .first()
        .filter(|v| !v.is_empty())
        .ok_or_else(|| BridgeError::new(BridgeErrorCode::SpawnFailed))?;
    let mut cmd = Command::new(executable);
    cmd.args(&config.argv[1..])
        .arg("--data-dir")
        .arg(&config.data_dir)
        .arg("--parent-pid")
        .arg(config.parent_pid.to_string())
        .arg("--resource-dir")
        .arg(&config.resource_dir)
        .arg("--log-level")
        .arg(&config.log_level)
        .env("PYTHONUTF8", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    crate::platform::current().prepare_core_command(&mut cmd);
    Ok(cmd)
}
pub(crate) struct Write {
    pub line: String,
    pub reply: Option<mpsc::Sender<Result<(), BridgeError>>>,
}
pub(crate) enum Event {
    Line(u64, String),
    Fault(u64),
    Wake,
}
fn read_lines(reader: impl Read, mut line: impl FnMut(String)) {
    let mut reader = BufReader::new(reader);
    let mut bytes = Vec::new();
    let mut oversized = false;
    while let Ok(buf) = reader.fill_buf() {
        if buf.is_empty() {
            if !oversized && !bytes.is_empty() {
                if let Ok(s) = String::from_utf8(bytes) {
                    line(s);
                }
            }
            break;
        }
        let end = buf.iter().position(|b| *b == b'\n');
        let n = end.map_or(buf.len(), |n| n + 1);
        let content = end.unwrap_or(n);
        if !oversized {
            if bytes.len() + content > MAX_LINE_BYTES {
                bytes.clear();
                oversized = true;
            } else {
                bytes.extend_from_slice(&buf[..content]);
            }
        }
        reader.consume(n);
        if end.is_some() {
            if !oversized {
                if bytes.last() == Some(&b'\r') {
                    bytes.pop();
                }
                if !bytes.is_empty() {
                    if let Ok(s) = String::from_utf8(std::mem::take(&mut bytes)) {
                        line(s);
                    }
                }
            } else {
                eprintln!("{{\"level\":\"warn\",\"module\":\"bridge\",\"error_code\":\"LINE_TOO_LARGE\"}}");
            }
            bytes.clear();
            oversized = false;
        }
    }
}
fn attach(shared: &Arc<Shared>, child: &mut Child, generation: u64) -> Vec<thread::JoinHandle<()>> {
    let mut handles = Vec::new();
    let (tx, rx) = mpsc::sync_channel::<Write>(32);
    let mut stdin = child.stdin.take().expect("piped stdin");
    let events = shared.events.clone();
    let weak = Arc::downgrade(shared);
    handles.push(thread::spawn(move || {
        let mut broken = false;
        for request in rx {
            let cancelled = request.reply.is_some()
                && weak.upgrade().is_none_or(|shared| {
                    let view = shared.view.lock().unwrap_or_else(|e| e.into_inner());
                    view.closing || view.generation != generation || view.writer.is_none()
                });
            let result = if broken || cancelled {
                Err(BridgeError::new(BridgeErrorCode::Timeout))
            } else {
                stdin
                    .write_all(request.line.as_bytes())
                    .and_then(|_| stdin.write_all(b"\n"))
                    .and_then(|_| stdin.flush())
                    .map_err(|_| BridgeError::new(BridgeErrorCode::WriteFailed))
            };
            if result.is_err() {
                broken = true;
                let _ = events.try_send(Event::Fault(generation));
            }
            if let Some(reply) = request.reply {
                let _ = reply.send(result);
            }
        }
    }));
    let stdout = child.stdout.take().expect("piped stdout");
    let events = shared.events.clone();
    handles.push(thread::spawn(move || {
        read_lines(stdout, |line| {
            let _ = events.send(Event::Line(generation, line));
        });
        let _ = events.send(Event::Fault(generation));
    }));
    let mut stderr = child.stderr.take().expect("piped stderr");
    handles.push(thread::spawn(move || {
        let _ = std::io::copy(&mut stderr, &mut std::io::sink());
    }));
    let mut view = shared.view.lock().unwrap_or_else(|e| e.into_inner());
    view.writer = Some(tx);
    view.generation = generation;
    handles
}
fn internal(shared: &Shared, id: &str, method: &str) -> bool {
    let line =
        serde_json::json!({"jsonrpc":"2.0", "id":id, "method":method, "params":{}}).to_string();
    shared
        .view
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .writer
        .as_ref()
        .is_some_and(|w| w.try_send(Write { line, reply: None }).is_ok())
}
fn closing(shared: &Shared) -> bool {
    shared
        .view
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .closing
}
pub(crate) fn supervise(
    shared: Arc<Shared>,
    rx: mpsc::Receiver<Event>,
    config: CoreConfig,
    mut child: Child,
) {
    let mut attempt = 0;
    let mut serial = 0u64;
    let mut generation = 0;
    loop {
        let handles = attach(&shared, &mut child, generation);
        let started = Instant::now();
        let mut heartbeat = started + shared.timings.heartbeat_interval;
        let mut ready = false;
        let mut misses = 0;
        let mut pending = HashMap::<String, Instant>::new();
        let mut stop_deadline = None;
        loop {
            let now = Instant::now();
            if closing(&shared) && stop_deadline.is_none() {
                serial += 1;
                let id = format!("rs-shutdown-{serial}");
                internal(&shared, &id, "app.shutdown");
                pending.clear();
                pending.insert(id, now + shared.timings.shutdown_grace);
                stop_deadline = Some(now + shared.timings.shutdown_grace);
            }
            match child.try_wait() {
                Ok(None) => {}
                _ => break,
            }
            if stop_deadline.is_some_and(|d| now >= d) {
                break;
            }
            if stop_deadline.is_none() {
                if !ready && now.duration_since(started) >= shared.timings.startup_timeout {
                    break;
                }
                let expired: Vec<_> = pending
                    .iter()
                    .filter(|(_, d)| now >= **d)
                    .map(|(id, _)| id.clone())
                    .collect();
                for id in expired {
                    pending.remove(&id);
                    misses += 1;
                }
                if misses >= 3 {
                    break;
                }
                if now >= heartbeat && pending.is_empty() {
                    serial += 1;
                    let id = format!("rs-ping-{serial}");
                    if !internal(&shared, &id, "app.ping") {
                        break;
                    }
                    pending.insert(id, now + shared.timings.heartbeat_timeout);
                    heartbeat = now + shared.timings.heartbeat_interval;
                }
            }
            match rx.recv_timeout(Duration::from_millis(5)) {
                Ok(Event::Fault(g)) if g == generation => break,
                Ok(Event::Line(g, line)) if g == generation => {
                    if let Ok(value) = serde_json::from_str::<serde_json::Value>(&line) {
                        if let Some(id) = value
                            .get("id")
                            .and_then(|v| v.as_str())
                            .filter(|id| id.starts_with("rs-"))
                        {
                            if pending.remove(id).is_some() && id.starts_with("rs-ping-") {
                                if value.get("error").is_none()
                                    && value.pointer("/result/ok").and_then(|v| v.as_bool())
                                        == Some(true)
                                {
                                    misses = 0;
                                    if !ready && stop_deadline.is_none() && !closing(&shared) {
                                        ready = true;
                                        transition(&shared, CoreState::Ready, 0);
                                    }
                                } else {
                                    misses += 1;
                                }
                            }
                            continue;
                        }
                        if !ready
                            && value.get("id").is_none()
                            && value.get("method").and_then(|v| v.as_str()) == Some("app.ready")
                            && stop_deadline.is_none()
                            && !closing(&shared)
                        {
                            ready = true;
                            transition(&shared, CoreState::Ready, 0);
                        }
                    }
                    if !closing(&shared) {
                        (shared.sink)(BridgeEvent::Message(line));
                    }
                }
                Err(mpsc::RecvTimeoutError::Disconnected) => break,
                _ => {}
            }
        }
        shared.view.lock().unwrap_or_else(|e| e.into_inner()).writer = None;
        pending.clear();
        crate::platform::current().kill_process_tree(&mut child);
        let _ = child.wait();
        // 排空有界队列使读线程退出；有后代继承管道时由 Platform 清理。
        let drained = Instant::now() + shared.timings.shutdown_grace;
        while handles.iter().any(|h| !h.is_finished()) && Instant::now() < drained {
            let _ = rx.recv_timeout(Duration::from_millis(5));
        }
        for handle in handles {
            if handle.is_finished() {
                let _ = handle.join();
            } else {
                eprintln!("{{\"level\":\"error\",\"module\":\"bridge\",\"error_code\":\"PIPE_NOT_CLOSED\"}}");
            }
        }
        if closing(&shared) || attempt >= CORE_MAX_RESTARTS {
            break;
        }
        let next = loop {
            if closing(&shared) || attempt >= CORE_MAX_RESTARTS {
                break None;
            }
            attempt += 1;
            transition(&shared, CoreState::Restarting, attempt);
            let deadline = Instant::now() + shared.timings.restart_delays[usize::from(attempt - 1)];
            while !closing(&shared) && Instant::now() < deadline {
                let _ = rx.recv_timeout(Duration::from_millis(5));
            }
            // 关闭与 spawn 共用锁：关闭标记一旦设置，就不可能再生成核心进程。
            let view = shared.view.lock().unwrap_or_else(|e| e.into_inner());
            if view.closing {
                break None;
            }
            let spawned = build_command(&config).and_then(|mut cmd| {
                cmd.spawn()
                    .map_err(|_| BridgeError::new(BridgeErrorCode::SpawnFailed))
            });
            drop(view);
            if let Ok(next) = spawned {
                break Some(next);
            }
        };
        let Some(next) = next else {
            break;
        };
        child = next;
        generation += 1;
        transition(&shared, CoreState::Starting, attempt);
    }
    transition(&shared, CoreState::Failed, attempt);
}
