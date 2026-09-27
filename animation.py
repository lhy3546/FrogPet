# -*- coding: utf-8 -*-
"""素材加载与动画数值工具。"""
import math
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap, QTransform

import paths

# 素材源图 (640x640) 内的几何关键点
SRC = 640
FOOT_Y = 608          # 脚底基准线
HEAD_Y = 150          # 头顶
BODY_W = 480          # 身体可见宽度


def clamp01(v: float) -> float:
    return 0.0 if v < 0 else (1.0 if v > 1 else v)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ease_out(t: float) -> float:
    t = clamp01(t)
    return 1 - (1 - t) ** 3


def ease_in(t: float) -> float:
    t = clamp01(t)
    return t ** 3


def ease_in_out(t: float) -> float:
    t = clamp01(t)
    return t * t * (3 - 2 * t)


def triangle(t: float) -> float:
    """0→1→0 三角波 (眨眼包络)。"""
    t = clamp01(t)
    return t / 0.38 if t < 0.38 else 1 - (t - 0.38) / 0.62


class Sprites:
    """加载四帧姿态并缓存镜像、命中检测用的 alpha 图。"""

    POSES = ("idle", "blink", "puffed", "jump")

    def __init__(self, size: int):
        self.size = size
        self.scale = size / float(FOOT_Y - HEAD_Y)
        self.pm: dict[str, QPixmap] = {}
        self.pm_flip: dict[str, QPixmap] = {}
        self.img: dict[str, QImage] = {}
        self.img_flip: dict[str, QImage] = {}
        w = int(SRC * self.scale)
        for name in self.POSES:
            path = paths.asset_path("frog", f"frog_{name}.png")
            if not os.path.isfile(path):     # 素材缺失时退回 idle
                path = paths.asset_path("frog", "frog_idle.png")
            src = QPixmap(path)
            pm = src.scaled(w, w, Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
            flip = pm.transformed(QTransform().scale(-1.0, 1.0))
            self.pm[name] = pm
            self.pm_flip[name] = flip
            self.img[name] = pm.toImage()
            self.img_flip[name] = flip.toImage()
        sh_path = paths.asset_path("frog", "shadow.png")
        self.shadow = QPixmap(sh_path) if os.path.isfile(sh_path) else QPixmap()

    def shadow_pm(self, width: float) -> QPixmap:
        if self.shadow.isNull():
            return QPixmap()
        return self.shadow.scaled(int(width), int(width * 0.33),
                                  Qt.AspectRatioMode.IgnoreAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
