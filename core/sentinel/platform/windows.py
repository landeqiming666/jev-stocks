"""Windows 平台实现。"""

from __future__ import annotations

import csv
import ctypes
import msvcrt
import os
import re
import stat
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path
from typing import Literal

from . import AlreadyRunning

# 共享类型检查也会发现这个仅供 Windows 使用的模块。
assert sys.platform == "win32"

_SYNCHRONIZE = 0x00100000
_ERROR_ACCESS_DENIED = 5
_ERROR_INVALID_PARAMETER = 87
_WAIT_TIMEOUT = 258
_WAIT_FAILED = 0xFFFFFFFF
_SDDL_REVISION_1 = 1
_DACL_SECURITY_INFORMATION = 0x00000004
_PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
_kernel32.WaitForSingleObject.restype = wintypes.DWORD
_kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
_kernel32.CloseHandle.restype = wintypes.BOOL
_kernel32.LocalFree.argtypes = (wintypes.HLOCAL,)
_kernel32.LocalFree.restype = wintypes.HLOCAL

_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
_advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = (
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.POINTER(wintypes.ULONG),
)
_advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
_advapi32.SetFileSecurityW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p)
_advapi32.SetFileSecurityW.restype = wintypes.BOOL


def name() -> Literal["macos", "windows"]:
    return "windows"


def default_data_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "Sentinel"


def is_process_alive(pid: int) -> bool:
    if not 0 < pid <= 0xFFFFFFFF:
        return False
    process = _kernel32.OpenProcess(_SYNCHRONIZE, False, pid)
    if not process:
        error = ctypes.get_last_error()
        if error == _ERROR_ACCESS_DENIED:
            return True
        if error == _ERROR_INVALID_PARAMETER:
            return False
        raise ctypes.WinError(error)
    try:
        # 等待进程对象可区分尚未退出和确实返回退出码 259 的进程。
        wait: int = _kernel32.WaitForSingleObject(process, 0)
        if wait == _WAIT_FAILED:
            raise ctypes.WinError(ctypes.get_last_error())
        return wait == _WAIT_TIMEOUT
    finally:
        _kernel32.CloseHandle(process)


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        fd = handle.fileno()
        handle.seek(0)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise AlreadyRunning("另一个核心进程正在使用这份数据") from exc
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


def _current_user_sid() -> str:
    try:
        whoami = Path(os.environ["SYSTEMROOT"]) / "System32" / "whoami.exe"
        result = subprocess.run(
            [str(whoami), "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=10,
        )
        _, sid = next(csv.reader(result.stdout.decode("oem").splitlines()))
    except (
        KeyError,
        OSError,
        subprocess.SubprocessError,
        csv.Error,
        StopIteration,
        ValueError,
    ) as exc:
        raise OSError("无法获取当前用户") from exc
    if not re.fullmatch(r"S-1(?:-[0-9]+){2,}", sid):
        raise OSError("无法获取当前用户")
    return sid


def harden_permissions(path: Path) -> None:
    directory = stat.S_ISDIR(path.stat().st_mode)
    inheritance = "OICI" if directory else ""
    sid = _current_user_sid()
    # D:P 关闭继承，整份 DACL 只保留当前用户的完全控制。
    sddl = f"D:P(A;{inheritance};FA;;;{sid})"
    descriptor = ctypes.c_void_p()
    if not _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, _SDDL_REVISION_1, ctypes.byref(descriptor), None
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        # SetFileSecurityW 只更改目标；目录 ACE 可供新建子项继承。
        security_info = _DACL_SECURITY_INFORMATION | _PROTECTED_DACL_SECURITY_INFORMATION
        if not _advapi32.SetFileSecurityW(str(path), security_info, descriptor):
            error = ctypes.get_last_error()
            raise OSError(0, ctypes.FormatError(error).strip(), path, error)
    finally:
        _kernel32.LocalFree(descriptor)
