# -*- coding: utf-8 -*-
"""全局热键 Ctrl+Alt+Q (唯一正常退出方式)。
用 Win32 RegisterHotKey + GetMessage 线程实现, 不依赖第三方库,
无论焦点在哪个程序都会触发。"""
import ctypes
import logging
import threading

log = logging.getLogger("frogpet")

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
HOTKEY_ID = 0xB00B          # 任意唯一 id
VK_Q = 0x51

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class GlobalHotkey:
    def __init__(self, callback):
        """callback: 热键触发时在热键线程中调用 (应当线程安全, 如 Qt 信号 emit)。"""
        self._callback = callback
        self._thread: threading.Thread | None = None
        self._thread_id = 0

    def start(self) -> bool:
        self._thread = threading.Thread(target=self._run, name="FrogPetHotkey", daemon=True)
        self._thread.start()
        return True

    def _run(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_ALT, VK_Q):
            err = kernel32.GetLastError()
            log.error("RegisterHotKey failed, err=%s (Ctrl+Alt+Q 可能被占用)", err)
            self._callback("error")
            return
        log.info("global hotkey Ctrl+Alt+Q registered")
        import ctypes.wintypes as wt
        msg = wt.MSG()
        while True:
            r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r <= 0:          # WM_QUIT 或错误
                break
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                try:
                    self._callback("quit")
                except Exception as e:
                    log.exception("hotkey callback error: %s", e)
        user32.UnregisterHotKey(None, HOTKEY_ID)
        log.info("hotkey thread exited")

    def stop(self):
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
