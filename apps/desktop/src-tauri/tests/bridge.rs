use sentinel_lib::bridge::commands::{open_external_with, ExternalOpenError};
use sentinel_lib::bridge::{process::*, security::*, *};
use std::{path::PathBuf, sync::mpsc, time::Duration};

fn config(mode: &str) -> CoreConfig {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..");
    CoreConfig {
        argv: vec![
            root.join("core/.venv/bin/python").to_string_lossy().into(),
            "-u".into(),
            "-c".into(),
            FAKE.into(),
            mode.into(),
        ],
        working_dir: root.clone(),
        data_dir: std::env::temp_dir().join("sentinel bridge data"),
        resource_dir: root.join("resources"),
        parent_pid: std::process::id(),
        log_level: "debug".into(),
    }
}

#[test]
fn test_development_repository_root_is_resolved_from_manifest_not_process_cwd() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .unwrap();
    assert!(root.join("core/pyproject.toml").is_file());
    assert_eq!(development_repository_root().unwrap(), root);
}
const FAKE: &str = r#"
import sys, json, os, time, subprocess
mode = sys.argv[1]
def emit(obj): print(json.dumps(obj), flush=True)
if mode == 'orphan':
    descendant = subprocess.Popen(['sh','-c','exec sleep 10'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
if mode != 'startup': emit({'jsonrpc':'2.0','method':'app.ready','params':{'pid':os.getpid(), 'descendant':descendant.pid if mode == 'orphan' else None}})
if mode == 'crash': sys.exit(2)
if mode == 'eof': os.close(1); time.sleep(10)
if mode == 'closed': os.close(0); time.sleep(10)
if mode == 'blocked': time.sleep(10)
if mode == 'flood':
    print('x' * 1048577, flush=True)
    print('x' * 1048576, flush=True)
    print('after-flood', flush=True)
for line in sys.stdin:
    req = json.loads(line); method = req.get('method'); rid = req.get('id')
    if method == 'app.ping':
        if mode == 'hang': emit({'method':'test.ping','params':{'pid':os.getpid()}})
        if mode in ('hang','startup','orphan'): continue
        emit({'result':{'ok': True}, 'id':rid, 'jsonrpc':'2.0'})
        emit({'id':'rs-unknown','result':{'ok':True}})
    elif method == 'app.shutdown':
        if mode in ('hang','startup','orphan'): continue
        if mode == 'graceful':
            with open(os.path.join(sys.argv[3], 'shutdown-received'), 'w') as f: f.write('ok')
        emit({'result':{'ok': True}, 'jsonrpc':'2.0','id':rid}); break
    else:
        if mode == 'frame':
            emit({'jsonrpc':'2.0','id':rid,'result':{'frameBytes':len(line.encode('utf-8'))}})
        else:
            emit({'jsonrpc':'2.0','id':rid,'result':{'argv':sys.argv[2:], 'utf8':os.getenv('PYTHONUTF8'), 'encoding':os.getenv('PYTHONIOENCODING')}})
"#;
fn fast() -> Timings {
    Timings {
        heartbeat_interval: Duration::from_millis(30),
        heartbeat_timeout: Duration::from_millis(15),
        startup_timeout: Duration::from_millis(80),
        shutdown_grace: Duration::from_millis(30),
        restart_delays: [
            Duration::from_millis(10),
            Duration::from_millis(20),
            Duration::from_millis(40),
        ],
        write_timeout: Duration::from_millis(100),
    }
}
fn start(mode: &str) -> (BridgeState, mpsc::Receiver<BridgeEvent>) {
    let (tx, rx) = mpsc::channel();
    (
        BridgeState::start(config(mode), fast(), move |event| {
            let _ = tx.send(event);
        })
        .unwrap(),
        rx,
    )
}
fn ready(rx: &mpsc::Receiver<BridgeEvent>) -> serde_json::Value {
    loop {
        if let BridgeEvent::Message(line) = rx.recv_timeout(Duration::from_secs(3)).unwrap() {
            let v: serde_json::Value = serde_json::from_str(&line).unwrap();
            if v["method"] == "app.ready" {
                return v["params"].clone();
            }
        }
    }
}
fn message(rx: &mpsc::Receiver<BridgeEvent>) -> String {
    loop {
        if let BridgeEvent::Message(s) = rx.recv_timeout(Duration::from_secs(3)).unwrap() {
            return s;
        }
    }
}
#[test]
fn test_parse_core_command_uses_whitespace() {
    let a = parse_core_command("uv\trun --project core python -m sentinel").unwrap();
    assert_eq!(a.len(), 7);
    assert_eq!(a[0], "uv");
    assert_eq!(parse_core_command("python\u{a0}arg").unwrap().len(), 1);
}
#[test]
fn test_empty_core_command_is_rejected() {
    for cmd in ["", " \t", "python 'x'", "python \"x\""] {
        assert_eq!(
            parse_core_command(cmd).unwrap_err().code,
            BridgeErrorCode::SpawnFailed
        );
    }
}
#[test]
fn test_build_args_contains_data_and_parent() {
    let mut c = config("healthy");
    c.data_dir = "/tmp/a b".into();
    c.parent_pid = 42;
    let cmd = build_command(&c).unwrap();
    let args: Vec<_> = cmd
        .get_args()
        .map(|v| v.to_string_lossy().into_owned())
        .collect();
    assert!(args.windows(2).any(|a| a == ["--data-dir", "/tmp/a b"]));
    assert!(args.windows(2).any(|a| a == ["--parent-pid", "42"]));
}

#[test]
fn test_build_command_uses_explicit_working_directory() {
    let mut c = config("healthy");
    c.working_dir = std::env::temp_dir().join("sentinel repository root with spaces");
    let cmd = build_command(&c).unwrap();
    assert_eq!(cmd.get_current_dir(), Some(c.working_dir.as_path()));
}
#[test]
fn test_rpc_send_rejects_over_one_mib() {
    assert_eq!(
        send_line(&BridgeState::default(), &"x".repeat(MAX_LINE_BYTES + 1))
            .unwrap_err()
            .code,
        BridgeErrorCode::LineTooLarge
    );
}
#[test]
fn test_rpc_send_rejects_before_ready() {
    assert_eq!(
        send_line(&BridgeState::default(), "{}").unwrap_err().code,
        BridgeErrorCode::NotReady
    );
}
#[test]
fn test_rs_response_is_not_forwarded() {
    let (state, rx) = start("healthy");
    ready(&rx);
    send_line(&state, r#"{"jsonrpc":"2.0","id":"r-1","method":"test"}"#).unwrap();
    let v: serde_json::Value = serde_json::from_str(&message(&rx)).unwrap();
    assert_eq!(v["id"], "r-1");
    assert_eq!(v["result"]["utf8"], "1");
    assert_eq!(v["result"]["encoding"], "utf-8");
    for _ in 0..5 {
        if let Ok(BridgeEvent::Message(s)) = rx.recv_timeout(Duration::from_millis(35)) {
            panic!("leaked: {s}");
        }
    }
    assert_eq!(status(&state).state, CoreState::Ready);
    shutdown(&state).unwrap();
}
#[test]
fn test_restart_delays_are_one_two_four_seconds() {
    assert_eq!(
        Timings::default().restart_delays,
        [
            Duration::from_secs(1),
            Duration::from_secs(2),
            Duration::from_secs(4)
        ]
    );
}
#[test]
fn test_open_external_rejects_http_and_file() {
    for url in [
        "http://a",
        "file:///x",
        "javascript:alert(1)",
        "https://",
        "https:///",
        "https://?x",
        "https://#x",
    ] {
        assert_eq!(
            validate_url(url).unwrap_err().code,
            BridgeErrorCode::InvalidUrl
        );
    }
    assert!(validate_url("https://example.com/a").is_ok());
}
#[test]
fn test_csp_forbids_eval_and_remote_scripts() {
    let context = sentinel_lib::runtime_context();
    assert_eq!(
        context
            .config()
            .app
            .security
            .csp
            .as_ref()
            .unwrap()
            .to_string(),
        csp()
    );
    assert_eq!(
        context
            .config()
            .app
            .security
            .dev_csp
            .as_ref()
            .unwrap()
            .to_string(),
        csp()
    );
    assert!(!csp().contains("unsafe-eval"));
    assert!(!csp().contains("https:"));
}
#[test]
fn test_actual_io_and_newline_injection() {
    let (state, rx) = start("healthy");
    ready(&rx);
    for line in ["{}\n{}", "{}\r{}"] {
        assert_eq!(
            send_line(&state, line).unwrap_err().code,
            BridgeErrorCode::WriteFailed
        );
    }
    send_line(&state, r#"{"id":"r-data","method":"test"}"#).unwrap();
    let v: serde_json::Value = serde_json::from_str(&message(&rx)).unwrap();
    let args = v["result"]["argv"].as_array().unwrap();
    assert_eq!(args[0], "--data-dir");
    assert_eq!(
        args[1],
        config("healthy").data_dir.to_string_lossy().as_ref()
    );
    assert_eq!(args[2], "--parent-pid");
    assert_eq!(args[4], "--resource-dir");
    assert_eq!(args[6], "--log-level");
    assert_eq!(args[7], "debug");
    shutdown(&state).unwrap();
    assert_eq!(status(&state).state, CoreState::Failed);
    assert_eq!(
        send_line(&state, "{}").unwrap_err().code,
        BridgeErrorCode::NotReady
    );
}
#[test]
fn test_stdout_oversize_discards_whole_line_then_recovers() {
    let (state, rx) = start("flood");
    ready(&rx);
    assert_eq!(message(&rx).len(), MAX_LINE_BYTES);
    assert_eq!(message(&rx), "after-flood");
    shutdown(&state).unwrap();
}
fn failed(mode: &str) {
    let (state, rx) = start(mode);
    let mut attempts = Vec::new();
    let mut ping_count = 0;
    let mut backoff = None;
    loop {
        match rx.recv_timeout(Duration::from_secs(3)).unwrap() {
            BridgeEvent::Status(s) => {
                if s.state == CoreState::Restarting {
                    attempts.push(s.attempt);
                    backoff = Some((std::time::Instant::now(), s.attempt));
                }
                if s.state == CoreState::Starting {
                    if let Some((time, attempt)) = backoff.take() {
                        assert!(
                            time.elapsed()
                                >= fast().restart_delays[usize::from(attempt - 1)]
                                    - Duration::from_millis(2)
                        );
                    }
                }
                if s.state == CoreState::Failed {
                    break;
                }
            }
            BridgeEvent::Message(line) => {
                if line.contains("test.ping") {
                    ping_count += 1;
                }
            }
        }
    }
    assert_eq!(attempts, [1, 2, 3]);
    assert_eq!(status(&state).attempt, 3);
    if mode == "hang" {
        assert_eq!(ping_count, 12);
    }
    shutdown(&state).unwrap();
}
#[test]
fn test_eof_ready_crashes_have_bounded_restart_budget() {
    failed("crash");
    failed("eof");
}
#[test]
fn test_heartbeat_hang_restarts_after_three_timeouts() {
    failed("hang");
}
#[test]
fn test_startup_timeout_restarts_without_ready() {
    failed("startup");
}
#[test]
fn test_stdin_write_failure_triggers_recovery() {
    let (state, rx) = start("closed");
    ready(&rx);
    assert_eq!(
        send_line(&state, "{}").unwrap_err().code,
        BridgeErrorCode::WriteFailed
    );
    loop {
        if let BridgeEvent::Status(s) = rx.recv_timeout(Duration::from_secs(3)).unwrap() {
            if s.state == CoreState::Restarting {
                break;
            }
        }
    }
    shutdown(&state).unwrap();
    assert_eq!(status(&state).state, CoreState::Failed);
}
#[test]
fn test_blocked_stdin_does_not_block_shutdown_and_releases_writer() {
    let (state, rx) = start("blocked");
    ready(&rx);
    std::thread::scope(|scope| {
        let writer = scope.spawn(|| send_line(&state, &"x".repeat(MAX_LINE_BYTES - 1)));
        assert!(writer.join().unwrap().is_err());
    });
    shutdown(&state).unwrap();
}
#[test]
fn test_shutdown_during_backoff_prevents_respawn() {
    let (state, rx) = start("crash");
    loop {
        if let BridgeEvent::Status(s) = rx.recv_timeout(Duration::from_secs(3)).unwrap() {
            if s.state == CoreState::Restarting {
                break;
            }
        }
    }
    shutdown(&state).unwrap();
    for event in rx.try_iter() {
        if let BridgeEvent::Status(s) = event {
            assert_ne!(s.state, CoreState::Starting);
        }
    }
}
#[test]
fn test_graceful_and_forced_shutdown_reap_child() {
    for mode in ["graceful", "hang"] {
        let mut cfg = config(mode);
        cfg.data_dir =
            std::env::temp_dir().join(format!("sentinel-bridge-{}-{mode}", std::process::id()));
        std::fs::create_dir_all(&cfg.data_dir).unwrap();
        let marker = cfg.data_dir.join("shutdown-received");
        let (tx, rx) = mpsc::channel();
        let state = BridgeState::start(cfg, fast(), move |e| {
            let _ = tx.send(e);
        })
        .unwrap();
        ready(&rx);
        shutdown(&state).unwrap();
        assert_eq!(status(&state).state, CoreState::Failed);
        assert_eq!(marker.exists(), mode == "graceful");
        std::fs::remove_dir_all(marker.parent().unwrap()).unwrap();
    }
}

#[cfg(unix)]
#[test]
fn test_process_reaping_and_orphan_cleanup() {
    for mode in ["healthy", "hang", "orphan"] {
        let (state, rx) = start(mode);
        let params = ready(&rx);
        let pid = params["pid"].as_u64().unwrap().to_string();
        shutdown(&state).unwrap();
        let alive = |pid: &str| {
            !std::process::Command::new("ps")
                .args(["-p", pid, "-o", "stat="])
                .output()
                .unwrap()
                .stdout
                .is_empty()
        };
        assert!(!alive(&pid), "direct child was not reaped");
        if let Some(pid) = params["descendant"].as_u64() {
            let pid = pid.to_string();
            let stat = std::process::Command::new("ps")
                .args(["-p", &pid, "-o", "stat="])
                .output()
                .unwrap()
                .stdout;
            let stat = String::from_utf8(stat).unwrap();
            let orphaned = !stat.trim().is_empty() && !stat.trim().starts_with('Z');
            // 即使上游平台层失败，也清理测试自己创建的后代。
            if orphaned {
                std::process::Command::new("kill")
                    .args(["-KILL", &pid])
                    .status()
                    .unwrap();
            }
            assert!(
                !orphaned,
                "Platform::kill_process_tree left a living descendant"
            );
        }
    }
}

#[test]
fn test_spawn_failure_reports_failed_without_child() {
    let mut cfg = config("healthy");
    cfg.argv = vec!["sentinel-test-missing-executable".into()];
    let (tx, rx) = mpsc::channel();
    let result = BridgeState::start(cfg, fast(), move |e| {
        let _ = tx.send(e);
    });
    assert!(matches!(
        result,
        Err(BridgeError {
            code: BridgeErrorCode::SpawnFailed,
            ..
        })
    ));
    let statuses: Vec<_> = rx
        .try_iter()
        .filter_map(|e| {
            if let BridgeEvent::Status(s) = e {
                Some(s.state)
            } else {
                None
            }
        })
        .collect();
    assert_eq!(statuses, [CoreState::Starting, CoreState::Failed]);
}

fn padded_request(raw_bytes: usize) -> String {
    let mut request = serde_json::json!({"jsonrpc":"2.0", "id":"r-frame", "method":"test.echo", "params":{"padding":""}});
    let padding = raw_bytes - request.to_string().len();
    request["params"]["padding"] = "x".repeat(padding).into();
    let line = request.to_string();
    assert_eq!(line.len(), raw_bytes);
    line
}

#[test]
fn test_rpc_frame_limit_includes_writer_lf_and_rejects_raw_max() {
    let (state, rx) = start("frame");
    ready(&rx);
    send_line(&state, &padded_request(MAX_LINE_BYTES - 1)).unwrap();
    let response: serde_json::Value = serde_json::from_str(&message(&rx)).unwrap();
    assert_eq!(response["result"]["frameBytes"], MAX_LINE_BYTES);
    assert_eq!(
        send_line(&state, &padded_request(MAX_LINE_BYTES))
            .unwrap_err()
            .code,
        BridgeErrorCode::LineTooLarge
    );
    send_line(
        &state,
        "{\"id\":\"r-after\",\"method\":\"test.echo\",\"params\":{}}",
    )
    .unwrap();
    let response: serde_json::Value = serde_json::from_str(&message(&rx)).unwrap();
    assert_eq!(response["id"], "r-after");
    shutdown(&state).unwrap();
}

#[test]
fn test_rpc_frame_matches_actual_c01_parse_request_and_serialize() {
    const CORE_PROTOCOL: &str = r#"
import json, os, sys
from sentinel.rpc.protocol import MAX_LINE_BYTES, LineTooLarge, parse_request, serialize
def emit(message):
    sys.stdout.buffer.write(serialize(message)); sys.stdout.buffer.flush()
emit({'jsonrpc':'2.0','method':'app.ready','params':{'pid':os.getpid()}})
for frame in sys.stdin.buffer:
    request = parse_request(frame)
    if request.method in ('app.ping', 'app.shutdown'):
        result = {'ok':True}
    else:
        serialized = serialize(json.loads(frame))
        assert serialized == frame
        assert parse_request(serialized).id == request.id
        oversized = json.loads(frame)
        oversized['params']['padding'] += 'x'
        oversized = serialize(oversized)
        assert len(oversized) == MAX_LINE_BYTES + 1
        try:
            parse_request(oversized)
        except LineTooLarge:
            pass
        else:
            raise AssertionError('C-01 accepted an oversized frame')
        result = {'frameBytes':len(frame),'serializedBytes':len(serialized),'oversizedRejected':True}
    emit({'jsonrpc':'2.0','id':request.id,'result':result})
    if request.method == 'app.shutdown': break
"#;
    let mut cfg = config("frame");
    cfg.argv = vec![
        cfg.argv[0].clone(),
        "-u".into(),
        "-c".into(),
        CORE_PROTOCOL.into(),
    ];
    let mut timings = fast();
    timings.startup_timeout = Duration::from_secs(3);
    timings.heartbeat_interval = Duration::from_secs(1);
    timings.write_timeout = Duration::from_secs(1);
    let (tx, rx) = mpsc::channel();
    let state = BridgeState::start(cfg, timings, move |event| {
        let _ = tx.send(event);
    })
    .unwrap();
    ready(&rx);
    send_line(&state, &padded_request(MAX_LINE_BYTES - 1)).unwrap();
    let response: serde_json::Value = serde_json::from_str(&message(&rx)).unwrap();
    assert_eq!(response["result"]["frameBytes"], MAX_LINE_BYTES);
    assert_eq!(response["result"]["serializedBytes"], MAX_LINE_BYTES);
    assert_eq!(response["result"]["oversizedRejected"], true);
    shutdown(&state).unwrap();
}

struct FakeOpener {
    calls: std::cell::RefCell<Vec<Vec<String>>>,
    failure: Option<ExternalOpenError>,
}
impl FakeOpener {
    fn open(&self, url: &str) -> Result<(), ExternalOpenError> {
        let mut command = std::process::Command::new("fake-opener");
        command.arg(url);
        assert_eq!(command.get_program(), "fake-opener");
        self.calls.borrow_mut().push(
            command
                .get_args()
                .map(|arg| arg.to_string_lossy().into_owned())
                .collect(),
        );
        self.failure.clone().map_or(Ok(()), Err)
    }
}

#[test]
fn test_open_external_valid_url_is_one_exact_argv_without_shell() {
    let opener = FakeOpener {
        calls: Default::default(),
        failure: None,
    };
    let url = "https://example.com/a%20b?q=%22quoted%22&literal=$(touch%20test);x=1#part";
    open_external_with(url, |url| opener.open(url)).unwrap();
    assert_eq!(*opener.calls.borrow(), vec![vec![url.to_owned()]]);
}

#[test]
fn test_open_external_invalid_url_never_calls_opener() {
    let opener = FakeOpener {
        calls: Default::default(),
        failure: None,
    };
    for url in [
        "http://example.com",
        "file:///x",
        "javascript:alert(1)",
        "https://",
        "https:///",
        "https://?q",
        "https://#fragment",
    ] {
        assert!(open_external_with(url, |url| opener.open(url)).is_err());
    }
    assert!(opener.calls.borrow().is_empty());
}

#[test]
fn test_open_external_failure_preserves_cause_without_url_or_credentials() {
    let url = "https://test-user:test-password@example.com/private?token=test-secret";
    let failures = [
        (
            ExternalOpenError::from(std::io::Error::new(
                std::io::ErrorKind::PermissionDenied,
                format!("denied {url}"),
            )),
            "PermissionDenied",
        ),
        (
            ExternalOpenError::from(std::io::Error::from_raw_os_error(13)),
            "13",
        ),
        (ExternalOpenError::Exited(Some(27)), "27"),
    ];
    for (failure, expected) in failures {
        let opener = FakeOpener {
            calls: Default::default(),
            failure: Some(failure),
        };
        let error = open_external_with(url, |url| opener.open(url)).unwrap_err();
        assert!(error.contains(expected), "{error}");
        for private in [
            url,
            "test-user",
            "test-password",
            "test-secret",
            "example.com",
        ] {
            assert!(!error.contains(private));
            assert!(!format!("{:?}", opener.failure).contains(private));
        }
        assert_eq!(opener.calls.borrow().len(), 1);
    }
}
