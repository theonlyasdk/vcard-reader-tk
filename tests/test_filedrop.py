"""Native drop test: synthesize WM_DROPFILES and check the callback fires.

Builds a real HDROP in global memory and SendMessages it to the window,
exercising the same path Explorer uses. Windows-only; skipped headless.
"""

import ctypes
import struct
import sys
import tkinter as tk
import unittest
from ctypes import wintypes

from ui.file_drop import WM_DROPFILES, enable_file_drop

GMEM_MOVEABLE = 0x0002


@unittest.skipUnless(sys.platform.startswith("win"), "Windows only")
class TestFileDrop(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"no display: {exc}")
        self.addCleanup(self._close)
        # Mapped (offscreen) so hit-testing sees real geometry.
        self.root.geometry("+32000+32000")
        self.root.deiconify()
        self.root.update()
        self.got = []
        if not enable_file_drop(self.root, self.got.extend):
            self.skipTest("drop target unavailable")
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SendMessageW.argtypes = (
            wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM)
        user32.SendMessageW.restype = ctypes.c_ssize_t
        self._user32 = user32
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GlobalAlloc.argtypes = (ctypes.c_uint, ctypes.c_size_t)
        kernel32.GlobalAlloc.restype = wintypes.HANDLE
        kernel32.GlobalLock.argtypes = (wintypes.HANDLE,)
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = (wintypes.HANDLE,)
        kernel32.GlobalUnlock.restype = wintypes.BOOL
        self._kernel32 = kernel32

    def _close(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _send_drop(self, paths, x, y):
        payload = "\0".join(paths).encode("utf-16-le") + b"\0\0\0\0"
        header = struct.pack("<IiiII", 20, x, y, 0, 1)
        blob = header + payload
        handle = self._kernel32.GlobalAlloc(GMEM_MOVEABLE, len(blob))
        self.assertTrue(handle, "GlobalAlloc failed")
        addr = self._kernel32.GlobalLock(handle)
        ctypes.memmove(addr, blob, len(blob))
        self._kernel32.GlobalUnlock(handle)
        # The handler releases the handle via DragFinish; do not touch it after.
        self._user32.SendMessageW(self.root.winfo_id(), WM_DROPFILES, handle, 0)
        self.root.update()

    def _center(self):
        return (self.root.winfo_rootx() + self.root.winfo_width() // 2,
                self.root.winfo_rooty() + self.root.winfo_height() // 2)

    def test_drop_inside_window_fires(self):
        self._send_drop(["C:\\tmp\\a.vcf", "C:\\tmp\\b.vcf"], *self._center())
        self._drain_poll()
        self.assertEqual(self.got, ["C:\\tmp\\a.vcf", "C:\\tmp\\b.vcf"])

    def test_drop_outside_window_ignored(self):
        self._send_drop(["C:\\tmp\\a.vcf"], 0, 0)
        self._drain_poll()
        self.assertEqual(self.got, [])

    def _drain_poll(self):
        # Delivery now goes through a 100 ms event-loop poll, not after(0).
        import time
        deadline = time.time() + 5
        while not self.got and time.time() < deadline:
            time.sleep(0.15)
            self.root.update()
        self.root.update()


if __name__ == "__main__":
    unittest.main()
