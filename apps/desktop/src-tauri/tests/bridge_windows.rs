#![cfg(windows)]

#[path = "../src/bridge/windows.rs"]
mod bridge_probe;

use bridge_probe::{Fixture, FixtureProcess};
use sentinel_lib::bridge::process::Timings;
use sentinel_lib::bridge::security::MAX_LINE_BYTES;
use sentinel_lib::bridge::{self, BridgeErrorCode, BridgeEvent, BridgeState, CoreState};
use serde_json::{json, Value};
use std::fs;
use std::sync::mpsc::{self, Receiver};
use std::time::{Duration, Instant};

const START_TIMEOUT: Duration = Duration::from_secs(30);
const IO_TIMEOUT: Duration = Duration::from_secs(5);

const FAKE_CORE: &str = r#"
"""Controlled W-02 subprocess for testing NDJSON on Windows."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import threading


def encode(message):
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def notification(method, params):
    return {"jsonrpc": "2.0", "method": method, "params": params}


def response(request_id, **outcome):
    return {"jsonrpc": "2.0", "id": request_id, **outcome}


def record(path, value):
    with path.open("ab") as stream:
        stream.write(encode(value) + b"\n")


def run(args):
    import os

    version = "0.0.0-fixture"
    data_dir = args.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    record(data_dir / "starts.jsonl", {"pid": os.getpid()})
    ending = b"\r\n" if args.output_eol == "crlf" else b"\n"

    def send(message):
        sys.stdout.buffer.write(encode(message) + ending)
        sys.stdout.buffer.flush()

    descendant = None
    pending = set()
    workers = []
    state_lock = threading.Lock()
    stopping = threading.Event()

    def finish_slow(request_id):
        if stopping.wait(2):
            return
        with state_lock:
            if request_id in pending:
                pending.remove(request_id)
                send(response(request_id, result={"ok": True}))
            send(notification("fixture.slowFinished", {"id": request_id}))

    bootstrap = {
        "protocolVersion": "1.0",
        "appVersion": version,
        "dbSchemaVersion": 0,
        "platform": "windows",
        "engine": {
            "requested": "auto",
            "active": None,
            "modelId": "fixture-model",
            "jevdbAvailable": False,
        },
        "markets": ["us"],
        "configured": {"jevKey": False, "secEmail": False},
        "demoDataLoaded": False,
        "offline": True,
        "now": "2026-01-01T00:00:00Z",
    }

    send(notification("app.ready", {"version": version, "migrationsApplied": 0}))
    try:
        for raw in sys.stdin.buffer:
            payload = raw.removesuffix(b"\n").removesuffix(b"\r")
            request = json.loads(payload.decode("utf-8"))
            method = request["method"]
            request_id = request.get("id")
            params = request.get("params", {})
            record(data_dir / "requests.jsonl", {
                "id": request_id, "method": method, "bytes": len(payload),
            })
            with state_lock:
                if method == "app.bootstrap":
                    send(response(request_id, result=bootstrap))
                elif method == "app.ping":
                    send(response(request_id, result={"ok": True, "uptimeMs": 0}))
                elif method == "fixture.echo":
                    send(response(request_id, result=params))
                elif method == "fixture.measure":
                    send(response(request_id, result={"bytes": len(payload)}))
                elif method == "fixture.spawnChild":
                    python = getattr(sys, "_base_executable", sys.executable)
                    descendant = subprocess.Popen(
                        [python, "-c", "import time; time.sleep(30)"],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    send(response(request_id, result={"pid": descendant.pid}))
                elif method == "fixture.slow":
                    pending.add(request_id)
                    worker = threading.Thread(target=finish_slow, args=(request_id,))
                    workers.append(worker)
                    worker.start()
                    send(notification("fixture.slowStarted", {"id": request_id}))
                elif method == "$/cancel" and params["id"] in pending:
                    cancelled_id = params["id"]
                    pending.remove(cancelled_id)
                    send(response(cancelled_id, error={
                        "code": "CANCELLED",
                        "message": "请求已取消",
                        "data": {"retryable": False},
                    }))
                elif method == "fixture.crash":
                    print("fixture crash: exit 7", file=sys.stderr, flush=True)
                    os._exit(7)
                elif method == "app.shutdown":
                    if args.ignore_shutdown:
                        continue
                    send(response(request_id, result={"ok": True}))
                    return 0
    finally:
        stopping.set()
        for worker in workers:
            worker.join()
        if descendant is not None and descendant.poll() is None:
            descendant.kill()
            descendant.wait(timeout=3)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--parent-pid", type=int)
    parser.add_argument("--resource-dir", type=Path)
    parser.add_argument("--log-level")
    parser.add_argument("--ignore-shutdown", action="store_true")
    parser.add_argument("--output-eol", choices=("lf", "crlf"), default="lf")
    raise SystemExit(run(parser.parse_args()))
"#;

struct Probe {
    bridge: BridgeState,
    events: Receiver<BridgeEvent>,
    fixture: Fixture,
}

impl Probe {
    fn start(args: &[&str]) -> Self {
        let fixture = Fixture::new();
        let (tx, events) = mpsc::channel();
        let timings = Timings {
            startup_timeout: START_TIMEOUT,
            shutdown_grace: Duration::from_millis(200),
            restart_delays: [20, 40, 80].map(Duration::from_millis),
            ..Timings::default()
        };
        let bridge = BridgeState::start(fixture.config(FAKE_CORE, args), timings, move |event| {
            let _ = tx.send(event);
        })
        .expect("start actual C-02 supervisor with controlled Windows core");
        let probe = Self {
            bridge,
            events,
            fixture,
        };
        probe.ready(0);
        probe
    }

    fn event_before(&self, deadline: Instant) -> BridgeEvent {
        let remaining = deadline.saturating_duration_since(Instant::now());
        assert!(!remaining.is_zero(), "bridge event deadline expired");
        self.events.recv_timeout(remaining).expect("bridge event")
    }

    fn expect_status(&self, expected: CoreState, attempt: u8, timeout: Duration) {
        let deadline = Instant::now() + timeout;
        loop {
            if let BridgeEvent::Status(status) = self.event_before(deadline) {
                assert_eq!((status.state, status.attempt), (expected, attempt));
                return;
            }
        }
    }

    fn line(&self, timeout: Duration) -> String {
        let deadline = Instant::now() + timeout;
        loop {
            if let BridgeEvent::Message(line) = self.event_before(deadline) {
                return line;
            }
        }
    }

    fn message(&self) -> Value {
        serde_json::from_str(&self.line(IO_TIMEOUT)).expect("JSON-RPC object")
    }

    fn ready(&self, attempt: u8) {
        self.expect_status(CoreState::Starting, attempt, START_TIMEOUT);
        self.expect_status(CoreState::Ready, 0, START_TIMEOUT);
        let ready = self.message();
        assert_eq!(ready["jsonrpc"], "2.0");
        assert_eq!(ready["method"], "app.ready");
        assert!(ready.get("id").is_none());
    }

    fn send(&self, id: &str, method: &str, params: Value) {
        let request = json!({"jsonrpc":"2.0", "id":id, "method":method, "params":params});
        bridge::send_line(&self.bridge, &request.to_string()).expect("write bridge request");
    }

    fn records(&self, file: &str) -> Vec<Value> {
        fs::read_to_string(self.fixture.data_dir.join(file))
            .expect("fixture record")
            .lines()
            .map(|line| serde_json::from_str(line).expect("fixture JSON record"))
            .collect()
    }

    fn process(&self) -> FixtureProcess {
        let starts = self.records("starts.jsonl");
        let pid = starts.last().expect("current fixture startup")["pid"]
            .as_u64()
            .and_then(|pid| u32::try_from(pid).ok())
            .expect("fixture PID");
        FixtureProcess::open(pid).expect("retain fixture process handle")
    }
}

#[test]
fn test_bridge_startup_handshake_and_bootstrap() {
    let probe = Probe::start(&[]);
    let process = probe.process();
    probe.send("r-bootstrap", "app.bootstrap", json!({}));
    let response = probe.message();
    assert_eq!(response["id"], "r-bootstrap");
    assert_eq!(response["result"]["protocolVersion"], "1.0");
    assert_eq!(response["result"]["platform"], "windows");
    bridge::shutdown(&probe.bridge).expect("graceful bridge shutdown");
    assert_eq!(process.exit_code(IO_TIMEOUT).unwrap(), Some(0));
    assert!(probe.records("requests.jsonl").iter().any(|request| {
        request["method"] == "app.shutdown"
            && request["id"]
                .as_str()
                .is_some_and(|id| id.starts_with("rs-shutdown-"))
    }));
}

#[test]
fn test_bridge_preserves_utf8_chinese_around_newlines() {
    let probe = Probe::start(&["--output-eol", "crlf"]);
    let params = json!({"text":"投资逻辑哨兵\r\n第二行\n最后一行"});
    probe.send("r-echo", "fixture.echo", params.clone());
    let expected = format!(r#"{{"jsonrpc":"2.0","id":"r-echo","result":{params}}}"#);
    assert_eq!(probe.line(IO_TIMEOUT).as_bytes(), expected.as_bytes());
}

fn sized_request(id: &str, bytes: usize) -> String {
    let mut value = json!({
        "jsonrpc":"2.0", "id":id, "method":"fixture.measure", "params":{"text":"投资逻辑哨兵"},
    });
    let padding = bytes - value.to_string().len();
    value["params"]["text"] = json!(format!("投资逻辑哨兵{}", "x".repeat(padding)));
    let line = value.to_string();
    assert_eq!(line.len(), bytes);
    line
}

#[test]
fn test_bridge_rejects_line_over_1mb() {
    let probe = Probe::start(&[]);
    for (id, bytes) in [("r-limit", MAX_LINE_BYTES), ("r-over", MAX_LINE_BYTES + 1)] {
        let error = bridge::send_line(&probe.bridge, &sized_request(id, bytes)).unwrap_err();
        assert_eq!(error.code, BridgeErrorCode::LineTooLarge);
    }
    let line = sized_request("r-allowed", MAX_LINE_BYTES - 1);
    bridge::send_line(&probe.bridge, &line).expect("1 MiB including appended LF");
    let response = probe.message();
    assert_eq!(response["id"], "r-allowed");
    assert_eq!(response["result"]["bytes"], MAX_LINE_BYTES - 1);
    let requests = probe.records("requests.jsonl");
    assert!(requests
        .iter()
        .all(|request| { request["id"] != "r-limit" && request["id"] != "r-over" }));
    assert!(requests.iter().any(|request| request["id"] == "r-allowed"));
}

#[test]
fn test_bridge_forwards_cancel_response_within_200ms() {
    let probe = Probe::start(&["--output-eol", "crlf"]);
    probe.send("r-slow", "fixture.slow", json!({}));
    assert_eq!(probe.message()["method"], "fixture.slowStarted");
    let cancel = json!({"jsonrpc":"2.0", "method":"$/cancel", "params":{"id":"r-slow"}});
    let started = Instant::now();
    bridge::send_line(&probe.bridge, &cancel.to_string()).expect("send cancellation");
    let response = probe.message();
    let elapsed = started.elapsed();
    assert_eq!(response["id"], "r-slow");
    assert_eq!(response["error"]["code"], "CANCELLED");
    assert!(
        elapsed <= Duration::from_millis(200),
        "cancel took {elapsed:?}"
    );
    assert_eq!(
        probe.message(),
        json!({
            "jsonrpc":"2.0", "method":"fixture.slowFinished", "params":{"id":"r-slow"},
        })
    );
    eprintln!("Windows bridge cancel: {elapsed:?}");
}

#[test]
fn test_bridge_reports_child_exit() {
    let probe = Probe::start(&[]);
    let exited = probe.process();
    probe.send("r-crash", "fixture.crash", json!({}));
    assert_eq!(exited.exit_code(IO_TIMEOUT).unwrap(), Some(7));
    // The status event carries state and attempt only. The held OS handle
    // verifies the crash code independently of the bridge event.
    probe.expect_status(CoreState::Restarting, 1, IO_TIMEOUT);
    probe.ready(1);
}

#[test]
fn test_bridge_restarts_after_crash() {
    let probe = Probe::start(&[]);
    for attempt in 1..=3 {
        probe.send("r-crash", "fixture.crash", json!({}));
        probe.expect_status(CoreState::Restarting, attempt, IO_TIMEOUT);
        probe.ready(attempt);
        assert_eq!(
            probe.records("starts.jsonl").len(),
            usize::from(attempt) + 1
        );
    }
    probe.send("r-last-crash", "fixture.crash", json!({}));
    probe.expect_status(CoreState::Failed, 3, IO_TIMEOUT);
    assert_eq!(bridge::status(&probe.bridge).state, CoreState::Failed);
    bridge::shutdown(&probe.bridge).unwrap();
    assert_eq!(probe.records("starts.jsonl").len(), 4);
}

#[test]
fn test_bridge_stops_without_orphan() {
    let probe = Probe::start(&["--ignore-shutdown"]);
    let parent = probe.process();
    probe.send("r-spawn", "fixture.spawnChild", json!({}));
    let response = probe.message();
    assert_eq!(response["id"], "r-spawn");
    let pid = u32::try_from(response["result"]["pid"].as_u64().unwrap()).unwrap();
    let child = FixtureProcess::open(pid).expect("retain descendant handle before shutdown");
    assert_eq!(parent.exit_code(Duration::ZERO).unwrap(), None);
    assert_eq!(child.exit_code(Duration::ZERO).unwrap(), None);

    let started = Instant::now();
    bridge::shutdown(&probe.bridge).expect("forced bridge shutdown");
    let remaining = || Duration::from_secs(3).saturating_sub(started.elapsed());
    assert!(parent.exit_code(remaining()).unwrap().is_some());
    assert!(child.exit_code(remaining()).unwrap().is_some());
    assert!(started.elapsed() <= Duration::from_secs(3));
    assert!(probe
        .records("requests.jsonl")
        .iter()
        .any(|request| request["method"] == "app.shutdown"));
}
