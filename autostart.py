# -*- coding: utf-8 -*-
"""开机自启 (HKCU\\...\\CurrentVersion\\Run) 与首次安装逻辑。
只写 HKCU, 不需要管理员权限; 卸载脚本或本模块均可移除。"""
import logging
import os
import shutil
import subprocess
import sys

import paths
from config import Config

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "FrogPet"


def _reg():
    import winreg
    return winreg


def enable(exe_path: str) -> bool:
    """写入/更新自启项。"""
    try:
        winreg = _reg()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, VALUE_NAME, 0, winreg.REG_SZ,
                              f'"{os.path.normpath(exe_path)}"')
        return True
    except Exception as e:
        logging.getLogger("frogpet").error("autostart enable failed: %s", e)
        return False


def disable() -> bool:
    try:
        winreg = _reg()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, VALUE_NAME)
        return True
    except FileNotFoundError:
        return True
    except Exception as e:
        logging.getLogger("frogpet").error("autostart disable failed: %s", e)
        return False


def is_enabled() -> bool:
    try:
        winreg = _reg()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_QUERY_VALUE) as k:
            winreg.QueryValueEx(k, VALUE_NAME)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def install_and_relaunch() -> bool:
    """首次运行: 复制自身到 %LOCALAPPDATA%\\FrogPet, 写自启, 重启新进程。
    返回 True 表示已移交(当前进程应退出)。"""
    log = logging.getLogger("frogpet")
    target = paths.target_exe()
    current = os.path.abspath(sys.executable)
    if os.path.normpath(current) == os.path.normpath(target):
        enable(target)          # 已在正式位置, 确保自启项存在
        Config.write_default()
        return False
    try:
        os.makedirs(paths.appdata_dir(), exist_ok=True)
        shutil.copy2(current, target)
        Config.write_default()
        enable(target)
    except Exception as e:
        log.error("install to appdata failed (%s), fallback: autostart current exe", e)
        enable(current)         # 复制失败(如被杀软拦截)也保证能自启
        return False
    log.info("installed to %s, relaunching", target)
    try:
        subprocess.Popen([target], cwd=paths.appdata_dir(),
                         creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                         close_fds=True)
        return True
    except Exception as e:
        log.error("relaunch failed: %s", e)
        return False
