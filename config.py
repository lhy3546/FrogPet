# -*- coding: utf-8 -*-
"""配置: 从 %LOCALAPPDATA%\\FrogPet\\config.json 读取, 不存在则写默认值。"""
import json
import logging
import os

import paths

DEFAULTS = {
    "size": 170,            # 青蛙显示高度(px), 建议 120~220
    "jump_min": 2.0,        # 跳跃间隔下限(秒)
    "jump_max": 6.0,        # 跳跃间隔上限(秒)
    "sound": True,          # 点击是否发声
    "bubbles": True,        # 是否显示气泡文字
    "multi_screen": True,   # 是否允许跳到其他显示器
    "shadow": True,         # 是否绘制接触阴影
    "pond": True,           # 是否显示脚下小池塘与落水水花
}


class Config:
    def __init__(self, data: dict):
        self.size = _clamp(int(data.get("size", 170)), 80, 400)
        self.jump_min = _clamp(float(data.get("jump_min", 2.0)), 0.8, 60.0)
        self.jump_max = _clamp(float(data.get("jump_max", 6.0)), self.jump_min, 120.0)
        self.sound = bool(data.get("sound", True))
        self.bubbles = bool(data.get("bubbles", True))
        self.multi_screen = bool(data.get("multi_screen", True))
        self.shadow = bool(data.get("shadow", True))
        self.pond = bool(data.get("pond", True))

    @classmethod
    def load(cls) -> "Config":
        path = paths.config_file()
        data = dict(DEFAULTS)
        try:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    data.update(loaded)
        except Exception as e:  # 配置损坏时用默认值
            logging.getLogger("frogpet").warning("config load failed: %s", e)
        return cls(data)

    @staticmethod
    def write_default() -> None:
        try:
            os.makedirs(paths.appdata_dir(), exist_ok=True)
            with open(paths.config_file(), "w", encoding="utf-8") as f:
                json.dump(DEFAULTS, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.getLogger("frogpet").warning("config write failed: %s", e)


def _clamp(v, lo, hi):
    try:
        return max(lo, min(hi, v))
    except (TypeError, ValueError):
        return lo
