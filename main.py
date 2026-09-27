# -*- coding: utf-8 -*-
"""FrogPet 入口: 单实例互斥、日志、首次安装(复制到 LOCALAPPDATA + 开机自启)、
全局热键 Ctrl+Alt+Q (唯一退出方式)、主窗口。"""
import ctypes
import logging
import sys

import paths

ERROR_ALREADY_EXISTS = 183
_MUTEX_HOLD = None


def setup_logging():
    try:
        import os
        os.makedirs(paths.appdata_dir(), exist_ok=True)
        lf = paths.log_file()
        if os.path.isfile(lf) and os.path.getsize(lf) > 256 * 1024:
            os.remove(lf)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            handlers=[logging.FileHandler(lf, encoding="utf-8")],
        )
    except Exception:
        logging.basicConfig(level=logging.INFO)


def acquire_single_instance() -> bool:
    global _MUTEX_HOLD
    k32 = ctypes.windll.kernel32
    k32.CreateMutexW.restype = ctypes.c_void_p
    _MUTEX_HOLD = k32.CreateMutexW(None, False, "Local\\FrogPet.SingleInstance")
    return k32.GetLastError() != ERROR_ALREADY_EXISTS


def main():
    setup_logging()
    log = logging.getLogger("frogpet")

    if not acquire_single_instance():
        log.info("another FrogPet instance is running, exit")
        return 0

    if paths.is_frozen():
        import autostart
        if autostart.install_and_relaunch():
            log.info("handed over to installed copy, exit")
            return 0

    from PySide6.QtWidgets import QApplication
    from config import Config
    from hotkey import GlobalHotkey
    from pet_window import HotkeyBridge, PetWindow

    app = QApplication(sys.argv)
    app.setApplicationName("FrogPet")
    app.setQuitOnLastWindowClosed(True)

    cfg = Config.load()
    win = PetWindow(cfg)
    bridge = HotkeyBridge()
    bridge.triggered.connect(
        lambda kind: app.quit() if kind == "quit" else win.on_hotkey(kind))
    hk = GlobalHotkey(bridge.triggered.emit)
    hk.start()
    app.aboutToQuit.connect(hk.stop)

    win.start()
    log.info("FrogPet started (frozen=%s, size=%d)", paths.is_frozen(), cfg.size)
    return app.exec()


def _excepthook(tp, val, tb):
    logging.getLogger("frogpet").critical("unhandled exception", exc_info=(tp, val, tb))


if __name__ == "__main__":
    sys.excepthook = _excepthook
    sys.exit(main())
