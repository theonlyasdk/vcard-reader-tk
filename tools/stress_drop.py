"""Stress: launch app, hammer it with drops, close it, repeat.

Watches for 'Fatal Python error' (GIL/thread-state crashes in the
subclassed window procedure). Exits nonzero on any failure.
Usage: python stress_drop.py [cycles]
"""
import ctypes
import struct
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

WM_DROPFILES = 0x0233
WM_CLOSE = 0x0010
CYCLES = int(sys.argv[1]) if len(sys.argv) > 1 else 10
ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "vcard_reader.py"
VCF = ROOT / "tests" / "data" / "vcard30.vcf"

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.EnumWindows.argtypes = (
    ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM),
    wintypes.LPARAM,
)
user32.EnumWindows.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = (
    wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user32.GetWindowRect.restype = wintypes.BOOL
user32.SendMessageW.argtypes = (
    wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM)
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.PostMessageW.argtypes = (
    wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM)
user32.PostMessageW.restype = wintypes.BOOL
kernel32.GlobalAlloc.argtypes = (ctypes.c_uint, ctypes.c_size_t)
kernel32.GlobalAlloc.restype = wintypes.HANDLE
kernel32.GlobalLock.argtypes = (wintypes.HANDLE,)
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = (wintypes.HANDLE,)
kernel32.GlobalUnlock.restype = wintypes.BOOL


@ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
def _enum_cb(hwnd, _lparam):
    if user32.IsWindowVisible(hwnd):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        _enum_cb.found.append((hwnd, owner.value))
    return True


def find_window(pid, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        _enum_cb.found = []
        user32.EnumWindows(_enum_cb, 0)
        for hwnd, owner in _enum_cb.found:
            if owner == pid:
                return hwnd
        time.sleep(0.5)
    return None


def send_drop(hwnd, paths):
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    x = (rect.left + rect.right) // 2
    y = (rect.top + rect.bottom) // 2
    payload = "\0".join(paths).encode("utf-16-le") + b"\0\0\0\0"
    blob = struct.pack("<IiiII", 20, x, y, 0, 1) + payload
    handle = kernel32.GlobalAlloc(0x0002 | 0x2000, len(blob))
    addr = kernel32.GlobalLock(handle)
    ctypes.memmove(addr, blob, len(blob))
    kernel32.GlobalUnlock(handle)
    user32.SendMessageW(hwnd, WM_DROPFILES, handle, 0)


failures = 0
for cycle in range(1, CYCLES + 1):
    err_path = Path(f"stress-{cycle}.log")
    with open(err_path, "w") as err:
        proc = subprocess.Popen(
            [sys.executable, str(APP)],
            stdout=subprocess.DEVNULL, stderr=err, cwd=str(ROOT),
            creationflags=0x08000000)  # CREATE_NO_WINDOW
    hwnd = find_window(proc.pid)
    if hwnd is None:
        print(f"[{cycle}] no window; killing", flush=True)
        proc.kill()
        failures += 1
        continue
    for _ in range(3):
        send_drop(hwnd, [str(VCF)])
        time.sleep(0.3)
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        print(f"[{cycle}] hung; killing", flush=True)
        proc.kill()
        failures += 1
        continue
    err_text = err_path.read_text(errors="replace")
    err_path.unlink(missing_ok=True)
    if "Fatal Python error" in err_text or "PyEval_RestoreThread" in err_text:
        print(f"[{cycle}] FATAL ERROR REPRODUCED", flush=True)
        print(err_text[-2000:], flush=True)
        failures += 1
    else:
        print(f"[{cycle}] clean exit={proc.returncode}", flush=True)
    if proc.returncode not in (0,):
        failures += 1

print("FAILURES:" + str(failures), flush=True)
sys.exit(1 if failures else 0)
