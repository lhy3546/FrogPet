# -*- coding: utf-8 -*-
"""路径工具: 兼容 PyInstaller --onefile (sys._MEIPASS) 与源码运行。"""
import os
import sys


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def app_root() -> str:
    """资源根目录 (打包后为解包临时目录, 源码运行为本文件所在目录)。"""
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def asset_path(*parts: str) -> str:
    return os.path.join(app_root(), "assets", *parts)


def appdata_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "FrogPet")


def log_file() -> str:
    return os.path.join(appdata_dir(), "log.txt")


def config_file() -> str:
    return os.path.join(appdata_dir(), "config.json")


def target_exe() -> str:
    """安装后的正式 exe 路径。"""
    return os.path.join(appdata_dir(), "FrogPet.exe")
