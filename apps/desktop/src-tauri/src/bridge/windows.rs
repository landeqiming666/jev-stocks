//! Windows bridge test fixtures, compiled through tests/bridge_windows.rs.

use sentinel_lib::bridge::process::CoreConfig;
use std::fs;
use std::io;
use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle, RawHandle};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

static FIXTURE_COUNTER: AtomicU64 = AtomicU64::new(0);

pub struct Fixture {
    root: PathBuf,
    pub data_dir: PathBuf,
}

impl Fixture {
    pub fn new() -> Self {
        let temp = fs::canonicalize(std::env::temp_dir()).expect("absolute temp directory");
        let root = loop {
            let id = FIXTURE_COUNTER.fetch_add(1, Ordering::Relaxed);
            let path = temp.join(format!("sentinel-bridge-{}-{id} 桥 接", std::process::id()));
            match fs::create_dir(&path) {
                Ok(()) => break path,
                Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
                Err(error) => panic!("create owned bridge fixture: {error}"),
            }
        };
        Self {
            data_dir: root.join("核心 数据"),
            root,
        }
    }

    pub fn config(&self, script_body: &str, fixture_args: &[&str]) -> CoreConfig {
        let script = self.root.join("假 核心.py");
        fs::write(&script, script_body).expect("write fixture source");
        let python = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../../core/.venv/Scripts/python.exe")
            .canonicalize()
            .expect("run scripts/setup.ps1 to prepare project Python");
        let path_arg = |path: &Path| path.to_str().expect("UTF-8 Windows path").to_owned();
        let mut argv = vec![path_arg(&python), path_arg(&script)];
        argv.extend(fixture_args.iter().map(|arg| (*arg).to_owned()));
        CoreConfig {
            argv,
            working_dir: self.root.clone(),
            data_dir: self.data_dir.clone(),
            resource_dir: self.root.clone(),
            parent_pid: std::process::id(),
            log_level: "info".into(),
        }
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}

const PROCESS_TERMINATE: u32 = 0x0001;
const PROCESS_QUERY_LIMITED_INFORMATION: u32 = 0x1000;
const SYNCHRONIZE: u32 = 0x0010_0000;
const WAIT_OBJECT_0: u32 = 0;
const WAIT_TIMEOUT: u32 = 258;

#[link(name = "kernel32")]
unsafe extern "system" {
    fn OpenProcess(access: u32, inherit: i32, pid: u32) -> RawHandle;
    fn WaitForSingleObject(handle: RawHandle, timeout_ms: u32) -> u32;
    fn GetExitCodeProcess(handle: RawHandle, code: *mut u32) -> i32;
    fn TerminateProcess(handle: RawHandle, code: u32) -> i32;
}

/// Construct only from a PID published by the test's own live fixture.
pub struct FixtureProcess(OwnedHandle);

impl FixtureProcess {
    pub fn open(pid: u32) -> io::Result<Self> {
        let access = PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE;
        // SAFETY: OpenProcess returns an owned handle or NULL.
        let handle = unsafe { OpenProcess(access, 0, pid) };
        if handle.is_null() {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: the non-NULL handle is valid and transferred exactly once.
        Ok(Self(unsafe { OwnedHandle::from_raw_handle(handle) }))
    }

    pub fn exit_code(&self, timeout: Duration) -> io::Result<Option<u32>> {
        let timeout_ms = u32::try_from(timeout.as_millis()).unwrap_or(u32::MAX - 1);
        let handle = self.0.as_raw_handle();
        // SAFETY: the handle is valid for wait and query until self is dropped.
        match unsafe { WaitForSingleObject(handle, timeout_ms) } {
            WAIT_OBJECT_0 => {
                let mut code = 0;
                // SAFETY: code is a writable DWORD and the handle grants query.
                if unsafe { GetExitCodeProcess(handle, &mut code) } == 0 {
                    return Err(io::Error::last_os_error());
                }
                Ok(Some(code))
            }
            WAIT_TIMEOUT => Ok(None),
            _ => Err(io::Error::last_os_error()),
        }
    }
}

impl Drop for FixtureProcess {
    fn drop(&mut self) {
        if matches!(self.exit_code(Duration::ZERO), Ok(None)) {
            // A failing test still reaps its own process through the held handle.
            // SAFETY: the handle belongs to this fixture and grants termination.
            unsafe { TerminateProcess(self.0.as_raw_handle(), 1) };
            let _ = self.exit_code(Duration::from_secs(3));
        }
    }
}
