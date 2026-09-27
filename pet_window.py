# -*- coding: utf-8 -*-
"""桌面宠物主窗口: 无边框透明置顶、不抢焦点、不进任务栏/Alt-Tab。
透明区域鼠标穿透, 点到蛙身可点击/拖拽。唯一退出方式: 全局热键 Ctrl+Alt+Q。
脚下有随身小池塘(岸边/水面/荷叶/石子/涟漪), 起跳落地会溅起水花。"""
import ctypes
import logging
import math
import os
import random
import time

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetricsF, QGuiApplication,
                           QPainter, QPainterPath, QPen, QRadialGradient, QPixmap)
from PySide6.QtWidgets import QWidget

from animation import (FOOT_Y, SRC, Sprites, clamp01, ease_in_out, ease_out,
                       lerp, triangle)
import paths

try:
    import winsound
except ImportError:
    winsound = None

log = logging.getLogger("frogpet")

# ---- Win32 常量 ----
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010

_user32 = ctypes.windll.user32

BUBBLES = ["呱~", "呱呱~", "干嘛~", "别戳我~", "哼~", "咕~咕~", "(歪头看你)", "呱!"]
DRAG_BUBBLES = ["拖我干嘛~", "哇——", "飞起来啦~", "(手脚乱蹬)"]
HOTKEY_HINT = "按 Ctrl+Alt+Q 可让我休息"


class HotkeyBridge(QObject):
    """跨线程热键回调 -> 主线程信号。"""
    triggered = Signal(str)


class PetWindow(QWidget):
    TICK_MS = 30

    ST_IDLE, ST_CROUCH, ST_JUMP, ST_LAND, ST_INTERACT, ST_DRAG = range(6)

    def __init__(self, cfg):
        super().__init__(None,
                         Qt.WindowType.Window |
                         Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.Tool |
                         Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self.cfg = cfg
        self.sprites = Sprites(cfg.size)
        # 窗口比蛙身大: 顶部留气泡, 底部留池塘+跳跃弧线的地面空间
        self.win_w = int(cfg.size * 2.4)
        self.win_h = int(cfg.size * 3.0)
        self.feet_win = QPointF(self.win_w / 2, self.win_h * 0.58)

        self.resize(self.win_w, self.win_h)
        self.setMouseTracking(False)

        # 状态机
        self.state = self.ST_IDLE
        self.t0 = time.monotonic()          # 当前状态起始
        self.fx = 0.0                        # 脚底世界坐标 (逻辑全局 px)
        self.fy = 0.0
        self.face_left = random.random() < 0.5
        self.next_jump = self._after(2.0, 4.0)
        self.next_blink = self._after(1.0, 3.0)
        self.next_puff = self._after(5.0, 11.0)
        self.next_ripple = self._after(1.2, 2.6)
        self.blink_t0 = -9.0
        self.puff_t0 = -9.0
        # 跳跃参数
        self.jump_T = 0.4
        self.jump_A = (0.0, 0.0)
        self.jump_B = (0.0, 0.0)
        self.jump_h = 60.0
        self.jump_dist = 0.0
        # 交互
        self.interact_kind = ""
        self.interact_until = 0.0
        self.click_cooldown = 0.0
        self.look_side = 1
        self.hop_landed = True
        # 拖拽
        self.press_active = False
        self.drag_active = False
        self.press_gp = QPointF(0, 0)
        self.grab_dx = 0.0
        self.grab_dy = 0.0
        # 水花粒子 (窗口局部坐标)
        self.droplets = []      # {x,y,vx,vy,r,age,life}
        self.rings = []         # {cx,cy,r0,r1,age,life,a0,delay,flash}
        # 气泡
        self.bubble_text = ""
        self.bubble_t0 = -9.0
        self.intro_pending = True

        # 命中/穿透 (None=未初始化, 首帧必须落到确定状态)
        self._hit_active = None
        self._tick_count = 0
        self._last_now = time.monotonic()

        self.timer = QTimer(self)
        self.timer.setInterval(self.TICK_MS)
        self.timer.timeout.connect(self._tick)

        self._place_initially()

    # ---------------- 生命周期 ----------------
    def start(self):
        self.show()
        QTimer.singleShot(0, self._apply_native_flags)
        self.timer.start()
        log.info("pet window shown at (%d, %d)", self.x(), self.y())

    def _apply_native_flags(self):
        try:
            hwnd = int(self.winId())
            style = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            _user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                                   style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE |
                                   WS_EX_TRANSPARENT)   # 默认全穿透, 命中循环按需放开
            self._raise_topmost()
        except Exception as e:
            log.warning("native flags failed: %s", e)

    def _raise_topmost(self):
        hwnd = int(self.winId())
        _user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                             SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    # ---------------- 工具 ----------------
    def _after(self, lo: float, hi: float) -> float:
        return time.monotonic() + random.uniform(lo, hi)

    def _screens_geo(self):
        return [s.availableGeometry() for s in QGuiApplication.screens()]

    def _screen_at(self, x: float, y: float):
        for g in self._screens_geo():
            if g.contains(QPointF(x, y).toPoint()):
                return g
        return QGuiApplication.primaryScreen().availableGeometry()

    def _place_initially(self):
        c = QCursor.pos()
        geo = self._screen_at(c.x(), c.y())
        m = self.cfg.size * 1.2
        area = geo.adjusted(int(m), int(m), -int(m), -int(m))
        self.fx = random.uniform(area.left(), area.right())
        self.fy = random.uniform(area.top() + geo.height() * 0.15, area.bottom())
        self._move_window_to(self.fx, self.fy)

    def _move_window_to(self, fx: float, fy: float):
        self.fx, self.fy = fx, fy
        self.move(int(fx - self.win_w / 2), int(fy - self.win_h * 0.58))

    # ---------------- 状态机 ----------------
    def _tick(self):
        now = time.monotonic()
        dt = min(0.1, now - self._last_now)
        self._last_now = now
        self._tick_count += 1
        if self._tick_count % 120 == 0:
            try:
                self._raise_topmost()
            except Exception:
                pass

        self._update_particles(dt)

        if self.state == self.ST_IDLE:
            self._tick_idle(now)
        elif self.state == self.ST_CROUCH:
            self._tick_crouch(now)
        elif self.state == self.ST_JUMP:
            self._tick_jump(now)
        elif self.state == self.ST_LAND:
            self._tick_land(now)
        elif self.state == self.ST_INTERACT:
            self._tick_interact(now)
        # ST_DRAG: 位置由 mouseMoveEvent 驱动, 粒子/气泡照常更新

        if self.intro_pending and now > self.t0 + 0.9 and self.state != self.ST_DRAG:
            self.intro_pending = False
            self.show_bubble("呱~ 我来啦")

        self._update_click_through()
        self.update()

    def _tick_idle(self, now):
        if now >= self.next_jump:
            self._plan_jump(now)
            return
        if now >= self.next_blink:
            self.blink_t0 = now
            self.next_blink = self._after(2.2, 6.0)
        if now >= self.next_puff:
            self.puff_t0 = now
            self.next_puff = self._after(7.0, 15.0)
        if self.cfg.pond and now >= self.next_ripple:
            self._spawn_ambient_ripple()
            self.next_ripple = self._after(1.4, 3.2)
        self._move_window_to(self.fx, self.fy)

    def _plan_jump(self, now):
        geos = self._screens_geo()
        cur = self._screen_at(self.fx, self.fy)
        m = self.cfg.size * 0.95
        target = None
        if self.cfg.multi_screen and len(geos) > 1 and random.random() < 0.15:
            others = [g for g in geos if g != cur]
            if others:
                og = random.choice(others)
                pt = self._random_point_in(og, m)
                if self._path_on_screen(self.fx, self.fy, pt[0], pt[1], geos):
                    target = pt
        if target is None:
            max_d = max(140.0, self.cfg.size * 2.1)
            for _ in range(10):
                ang = random.uniform(0, 2 * math.pi)
                dist = random.uniform(0.3, 1.0) * max_d
                tx = self.fx + math.cos(ang) * dist
                ty = self.fy + math.sin(ang) * dist * 0.55
                if cur.adjusted(int(m), int(m), -int(m), -int(m)) \
                        .contains(int(tx), int(ty)) and math.hypot(tx - self.fx, ty - self.fy) > 60:
                    target = (tx, ty)
                    break
            if target is None:
                c = cur.center()
                target = (c.x() + random.uniform(-100, 100), c.y() + random.uniform(-60, 60))
        self.jump_A = (self.fx, self.fy)
        self.jump_B = target
        self.jump_dist = math.hypot(target[0] - self.fx, target[1] - self.fy)
        if abs(target[0] - self.fx) > 8:
            self.face_left = target[0] < self.fx
        self.jump_h = min(self.jump_dist * 0.32 + 24.0, self.cfg.size * 0.7)
        self.jump_T = clamp_jump_t(0.34 + self.jump_dist / 1200.0)
        self.state = self.ST_CROUCH
        self.t0 = now
        self._move_window_to(self.fx, self.fy)

    def _tick_crouch(self, now):
        if (now - self.t0) >= 0.16:
            self.state = self.ST_JUMP
            self.t0 = now
            if self.cfg.pond:
                self._spawn_splash("takeoff")

    def _tick_jump(self, now):
        p = (now - self.t0) / self.jump_T
        if p >= 1.0:
            self.state = self.ST_LAND
            self.t0 = now
            self._move_window_to(self.jump_B[0], self.jump_B[1])
            if self.cfg.pond:
                self._spawn_splash("land")
                self._play_splash(0.8)
            return
        t = ease_in_out(p)
        x = lerp(self.jump_A[0], self.jump_B[0], t)
        y = lerp(self.jump_A[1], self.jump_B[1], t) - self.jump_h * 4 * p * (1 - p)
        self._move_window_to(x, y)

    def _tick_land(self, now):
        if (now - self.t0) >= 0.15:
            self.state = self.ST_IDLE
            self.t0 = now
            self.next_jump = self._after(self.cfg.jump_min, self.cfg.jump_max)
            self._move_window_to(self.fx, self.fy)

    def _tick_interact(self, now):
        if self.interact_kind in ("hop", "hop_bubble"):
            T = 0.42
            p = clamp01((now - self.t0) / T)
            if p >= 1.0 and not self.hop_landed:
                self.hop_landed = True
                if self.cfg.pond:
                    self._spawn_splash("land")
                    self._play_splash(0.6)
        if now >= self.interact_until:
            self.state = self.ST_IDLE
            self.t0 = now
            self.next_jump = self._after(self.cfg.jump_min, self.cfg.jump_max)
            self.click_cooldown = now + 0.25
            self._move_window_to(self.fx, self.fy)

    # ---------------- 水花与涟漪 ----------------
    def _pond_cy_local(self, ground_dy: float) -> float:
        """池塘中心在窗口内的 y 坐标。"""
        return self.feet_win.y() + ground_dy + self.cfg.size * 0.16

    def _spawn_splash(self, kind: str):
        """kind: takeoff(小) / land(大)。窗口局部坐标。"""
        size = self.cfg.size
        cx = self.feet_win.x() + random.uniform(-0.05, 0.05) * size
        cy = self._pond_cy_local(0.0)
        if kind == "land":
            n, pw, ph = 9, 1.1, 1.5
            self.rings.append(dict(cx=cx, cy=cy, r0=size * 0.05, r1=size * 0.44,
                                   age=0.0, life=0.55, a0=150, delay=0.0, flash=True))
            self.rings.append(dict(cx=cx, cy=cy, r0=size * 0.04, r1=size * 0.40,
                                   age=0.0, life=0.7, a0=110, delay=0.12, flash=False))
        else:
            n, pw, ph = 4, 0.7, 1.0
        for _ in range(n):
            self.droplets.append(dict(
                x=cx + random.uniform(-0.12, 0.12) * size,
                y=cy + random.uniform(-2, 4),
                vx=random.uniform(-1.0, 1.0) * size * pw,
                vy=-random.uniform(0.7, 1.5) * size * ph,
                r=size * random.uniform(0.012, 0.026),
                age=0.0, life=random.uniform(0.35, 0.65)))
        if kind == "land":
            self.rings.append(dict(cx=cx, cy=cy, r0=size * 0.04, r1=size * 0.34,
                                   age=0.0, life=0.6, a0=110, delay=0.24, flash=False))

    def _spawn_ambient_ripple(self):
        size = self.cfg.size
        cx = self.feet_win.x() + random.uniform(-0.45, 0.45) * size
        cy = self._pond_cy_local(0.0) + random.uniform(-0.08, 0.10) * size
        self.rings.append(dict(cx=cx, cy=cy, r0=size * 0.03, r1=size * 0.14,
                               age=0.0, life=1.1, a0=70, delay=0.0, flash=False))

    def _update_particles(self, dt: float):
        if dt <= 0:
            return
        for d in self.droplets:
            d["x"] += d["vx"] * dt
            d["y"] += d["vy"] * dt
            d["vy"] += self.cfg.size * 9.0 * dt      # 重力
            d["age"] += dt
        self.droplets = [d for d in self.droplets if d["age"] < d["life"]]
        for r in self.rings:
            if r["delay"] > 0:
                r["delay"] -= dt
            else:
                r["age"] += dt
        self.rings = [r for r in self.rings if r["age"] < r["life"]]

    def _play_splash(self, prob: float):
        if not self.cfg.sound or winsound is None or random.random() > prob:
            return
        path = paths.asset_path("sounds", "splash.wav")
        if os.path.isfile(path):
            try:
                winsound.PlaySound(path, winsound.SND_FILENAME |
                                   winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            except Exception as e:
                log.warning("play splash failed: %s", e)

    def _ground_dy(self, now: float) -> float:
        """地面(池塘)相对脚底当前在窗口内的偏移: 跳到空中时地面在下方。"""
        if self.state == self.ST_JUMP:
            p = ease_in_out(clamp01((now - self.t0) / self.jump_T))
            return lerp(self.jump_A[1], self.jump_B[1], p) - self.fy
        if self.state == self.ST_INTERACT and self.interact_kind in ("hop", "hop_bubble"):
            p = clamp01((now - self.t0) / 0.42)
            return self.jump_h * 4 * p * (1 - p)
        return 0.0

    # ---------------- 鼠标: 点击回应 / 拖拽 ----------------
    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self.state in (self.ST_JUMP, self.ST_CROUCH) or self.press_active:
            return
        gp = self.mapToGlobal(event.position().toPoint())
        self.press_active = True
        self.drag_active = False
        self.press_gp = QPointF(gp)
        self.grab_dx = self.fx - gp.x()          # 保持抓取点相对蛙身不动
        self.grab_dy = self.fy - gp.y()
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if not self.press_active:
            return
        gp = self.mapToGlobal(event.position().toPoint())
        if not self.drag_active:
            if abs(gp.x() - self.press_gp.x()) + abs(gp.y() - self.press_gp.y()) < 8:
                return
            self.drag_active = True
            was = self.state
            self.state = self.ST_DRAG
            if was == self.ST_INTERACT:
                self.click_cooldown = time.monotonic() + 0.2
            self.look_side = 1 if gp.x() >= self.fx else -1
            if random.random() < 0.35:
                self.show_bubble(random.choice(DRAG_BUBBLES))
            log.info("drag started at (%d, %d)", int(self.fx), int(self.fy))
        self._move_window_to(gp.x() + self.grab_dx, gp.y() + self.grab_dy)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.press_active:
            return
        self.press_active = False
        self.drag_active = False
        self.unsetCursor()
        now = time.monotonic()
        if self.state == self.ST_DRAG:
            # 松手落地: 收进当前屏幕范围 + 落地缓冲 + 水花
            geo = self._screen_at(self.fx, self.fy)
            m = self.cfg.size * 0.9
            a = geo.adjusted(int(m), int(m), -int(m), -int(m))
            nx = min(max(self.fx, a.left()), a.right())
            ny = min(max(self.fy, a.top()), a.bottom())
            self._move_window_to(nx, ny)
            self.state = self.ST_LAND
            self.t0 = now
            self.next_jump = self._after(self.cfg.jump_min, self.cfg.jump_max)
            log.info("drag dropped at (%d, %d)", int(self.fx), int(self.fy))
            if self.cfg.pond:
                self._spawn_splash("land")
                self._play_splash(0.9)
            return
        # 未移动 -> 视为点击, 触发回应
        if now < self.click_cooldown or self.state == self.ST_JUMP:
            return
        self._start_interact(now)

    def _start_interact(self, now: float):
        gp = QCursor.pos()
        self.look_side = 1 if gp.x() >= self.fx else -1
        self.face_left = self.look_side < 0
        kind = random.choices(
            ["bubble", "croak", "hop", "hop_bubble"],
            weights=[35, 25, 25, 15])[0]
        log.info("interact: %s at (%d, %d)", kind, int(self.fx), int(self.fy))
        self.interact_kind = kind
        self.interact_until = now + random.uniform(1.2, 1.8)
        self.click_cooldown = now + 0.5
        self.state = self.ST_INTERACT
        self.t0 = now
        if kind in ("hop", "hop_bubble"):
            self.hop_landed = False
            self.jump_A = (self.fx, self.fy)
            dx = -self.look_side * self.cfg.size * random.uniform(0.15, 0.35)
            self.jump_B = (self.fx + dx, self.fy)
            self.jump_h = self.cfg.size * random.uniform(0.35, 0.5)
            if abs(dx) > 6:
                self.face_left = dx < 0
            if kind == "hop_bubble" or random.random() < 0.5:
                self.show_bubble(random.choice(BUBBLES))
            self._play_croak(0.6)
            if self.cfg.pond:
                self._spawn_splash("takeoff")
        elif kind == "croak":
            self.puff_t0 = now
            self.show_bubble(random.choice(BUBBLES))
            self._play_croak(1.0)
        else:  # bubble
            self.puff_t0 = now
            self.show_bubble(random.choice(BUBBLES))
        self._move_window_to(self.fx, self.fy)

    def show_bubble(self, text: str):
        if not self.cfg.bubbles:
            return
        self.bubble_text = text
        self.bubble_t0 = time.monotonic()

    def _play_croak(self, prob: float):
        if not self.cfg.sound or winsound is None or random.random() > prob:
            return
        path = paths.asset_path("sounds", f"croak{random.randint(1, 3)}.wav")
        if os.path.isfile(path):
            try:
                winsound.PlaySound(path, winsound.SND_FILENAME |
                                   winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            except Exception as e:
                log.warning("play sound failed: %s", e)

    def on_hotkey(self, kind: str):
        if kind == "error":
            self.show_bubble("热键被占用啦")
        # "quit" 由 main 直接退出应用

    # ---------------- 穿透控制 ----------------
    def _current_alpha_at(self, lx: float, ly: float) -> int:
        """把窗口局部坐标逆变换回姿态源图, 采样 alpha (取各层最大值)。"""
        s = self.sprites.scale
        sy, sx = self._squash(time.monotonic())
        dx = lx - self.feet_win.x()
        dy = ly - self.feet_win.y()
        if abs(sx) < 1e-3 or abs(sy) < 1e-3:
            return 0
        px = dx / sx + SRC * s / 2
        py = dy / sy + FOOT_Y * s
        names = ["jump", "idle"] if self.state in (self.ST_JUMP, self.ST_CROUCH) else ["idle"]
        best = 0
        for name in names:
            img = self.sprites.img_flip[name] if self.face_left else self.sprites.img[name]
            ix = int(img.width() - px) if self.face_left else int(px)
            iy = int(py)
            if 0 <= ix < img.width() and 0 <= iy < img.height():
                best = max(best, img.pixelColor(ix, iy).alpha())
        return best

    def _update_click_through(self):
        if self.press_active:
            hit = True                     # 拖拽期间保持可接收鼠标事件
        else:
            try:
                gp = QCursor.pos()
                lp = self.mapFromGlobal(gp)
                hit = self._current_alpha_at(lp.x(), lp.y()) > 12
            except Exception:
                return
        if hit != self._hit_active:
            self._hit_active = hit
            try:
                hwnd = int(self.winId())
                style = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                if hit:
                    style &= ~WS_EX_TRANSPARENT
                    self.setCursor(Qt.CursorShape.PointingHandCursor)
                else:
                    style |= WS_EX_TRANSPARENT
                    self.unsetCursor()
                _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            except Exception as e:
                log.warning("toggle click-through failed: %s", e)

    # ---------------- 姿态数值 ----------------
    def _squash(self, now):
        """返回 (sy, sx) 当前挤压/拉伸。"""
        if self.state == self.ST_IDLE:
            ph = (now * 1000 % 2600) / 2600.0
            sy = 1 + 0.014 * math.sin(2 * math.pi * ph)
            sx = 1 - 0.010 * math.sin(2 * math.pi * ph)
            return sy, sx
        if self.state == self.ST_CROUCH:
            p = ease_out((now - self.t0) / 0.16)
            return lerp(1, 0.90, p), lerp(1, 1.06, p)
        if self.state == self.ST_JUMP:
            p = clamp01((now - self.t0) / self.jump_T)
            if p < 0.45:
                return lerp(0.90, 1.07, ease_out(p / 0.45)), lerp(1.06, 0.97, ease_out(p / 0.45))
            return lerp(1.07, 1.0, ease_in_out((p - 0.45) / 0.55)), lerp(0.97, 1.0, ease_in_out((p - 0.45) / 0.55))
        if self.state == self.ST_LAND:
            p = ease_out((now - self.t0) / 0.15)
            return lerp(0.86, 1.0, p), lerp(1.08, 1.0, p)
        if self.state == self.ST_DRAG:
            ph = now * 2.0
            return 1 + 0.012 * math.sin(ph), 1 - 0.008 * math.sin(ph)
        # INTERACT
        if self.interact_kind in ("hop", "hop_bubble"):
            p = clamp01((now - self.t0) / 0.42)
            if p < 0.4:
                return lerp(1.0, 1.08, ease_out(p / 0.4)), lerp(1.0, 0.95, ease_out(p / 0.4))
            return lerp(1.08, 1.0, ease_in_out((p - 0.4) / 0.6)), lerp(0.95, 1.0, ease_in_out((p - 0.4) / 0.6))
        ph = clamp01((now - self.t0) / 1.2)
        env = math.sin(math.pi * ph)
        return 1 + 0.012 * env, 1 - 0.008 * env

    def _blink_alpha(self, now):
        if self.state != self.ST_IDLE:
            return 0.0
        return triangle((now - self.blink_t0) / 0.22) if now - self.blink_t0 < 0.22 else 0.0

    def _puff_alpha(self, now):
        if self.state == self.ST_INTERACT and self.interact_kind in ("bubble", "croak"):
            p = (now - self.t0) / 0.8
            return math.sin(math.pi * clamp01(p)) * 0.9
        if self.state != self.ST_IDLE:
            return 0.0
        p = (now - self.puff_t0) / 1.1
        if p < 0 or p > 1:
            return 0.0
        return math.sin(math.pi * p)

    def _look_rot(self, now):
        if self.state == self.ST_DRAG:
            return math.sin(now * 2.2) * 3.0     # 悬挂时轻轻晃
        if self.state == self.ST_INTERACT and self.interact_kind in ("bubble", "croak"):
            ph = clamp01((now - self.t0) / 1.2)
            return -self.look_side * 6.0 * math.sin(math.pi * ph)
        return 0.0

    # ---------------- 绘制 ----------------
    def paintEvent(self, event):
        now = time.monotonic()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        sy, sx = self._squash(now)
        s = self.sprites.scale
        dy = self._ground_dy(now)

        if self.cfg.pond:
            self._paint_pond(p, now, dy)

        # 接触阴影: 跳跃时留在地面并缩小
        if self.cfg.shadow:
            sh = self.sprites.shadow_pm(340 * s * max(0.55, 1 - min(0.45, abs(dy) / (self.cfg.size * 1.2))))
            if not sh.isNull():
                p.setOpacity(0.35 * max(0.3, 1 - abs(dy) / (self.cfg.size * 1.6)))
                gy = self.feet_win.y() + dy + 6 * s
                p.drawPixmap(QPointF(self.feet_win.x() - sh.width() / 2, gy - sh.height() / 2), sh)
                p.setOpacity(1.0)

        # 姿态帧 (支持两层交叉淡化)
        base_name, mix_name, mix = self._pose_mix(now)
        p.save()
        p.translate(self.feet_win)
        rot = self._look_rot(now)
        if rot:
            p.rotate(rot)
        p.scale(sx, sy)
        pm_a = self.sprites.pm_flip[base_name] if self.face_left else self.sprites.pm[base_name]
        p.drawPixmap(QPointF(-SRC * s / 2, -FOOT_Y * s), pm_a)
        if mix_name and mix > 0.01:
            pm_b = self.sprites.pm_flip[mix_name] if self.face_left else self.sprites.pm[mix_name]
            p.setOpacity(mix)
            p.drawPixmap(QPointF(-SRC * s / 2, -FOOT_Y * s), pm_b)
            p.setOpacity(1.0)
        ba = self._blink_alpha(now)
        if ba > 0.01:
            pm_bl = self.sprites.pm_flip["blink"] if self.face_left else self.sprites.pm["blink"]
            p.setOpacity(ba)
            p.drawPixmap(QPointF(-SRC * s / 2, -FOOT_Y * s), pm_bl)
            p.setOpacity(1.0)
        pa = self._puff_alpha(now)
        if pa > 0.01:
            pm_pu = self.sprites.pm_flip["puffed"] if self.face_left else self.sprites.pm["puffed"]
            p.setOpacity(pa)
            p.drawPixmap(QPointF(-SRC * s / 2, -FOOT_Y * s), pm_pu)
            p.setOpacity(1.0)
        p.restore()

        # 水珠画在青蛙前面 (向观众飞溅)
        self._paint_droplets(p)
        self._paint_bubble(p, now)
        p.end()

    def _pose_mix(self, now):
        if self.state == self.ST_INTERACT and self.interact_kind in ("hop", "hop_bubble"):
            p = clamp01((now - self.t0) / 0.42)
            if p < 0.30:
                return "idle", "jump", ease_out(p / 0.30)
            if p > 0.70:
                return "jump", "idle", ease_in_out((p - 0.70) / 0.30)
            return "jump", None, 0.0
        if self.state == self.ST_CROUCH:
            p = clamp01((now - self.t0) / 0.16)
            return "idle", "jump", ease_out(p)
        if self.state == self.ST_JUMP:
            p = clamp01((now - self.t0) / self.jump_T)
            if p < 0.30:
                return "idle", "jump", ease_out(p / 0.30)
            if p > 0.72:
                return "jump", "idle", ease_in_out((p - 0.72) / 0.28)
            return "jump", None, 0.0
        return "idle", None, 0.0

    # ---------------- 池塘 ----------------
    def _paint_pond(self, p: QPainter, now: float, dy: float):
        size = self.cfg.size
        cx = self.feet_win.x()
        cy = self._pond_cy_local(dy)
        w = size * 1.55
        h = w * 0.34

        p.setPen(Qt.PenStyle.NoPen)
        # 岸边
        p.setBrush(QColor(56, 88, 60, 150))
        p.drawEllipse(QPointF(cx, cy), w / 2 + 3 * size * 0.02, h / 2 + 3 * size * 0.02)
        p.setBrush(QColor(96, 132, 74, 170))
        p.drawEllipse(QPointF(cx, cy), w / 2 - size * 0.015, h / 2 - size * 0.012)
        # 水面
        grad = QRadialGradient(cx, cy - h * 0.18, w * 0.55)
        grad.setColorAt(0.0, QColor(158, 216, 190, 235))
        grad.setColorAt(0.6, QColor(94, 172, 146, 228))
        grad.setColorAt(1.0, QColor(56, 116, 98, 215))
        p.setBrush(grad)
        p.drawEllipse(QPointF(cx, cy), w / 2 - size * 0.05, h / 2 - size * 0.035)
        # 上缘反光
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(235, 252, 245, 60), max(1.5, size * 0.012)))
        p.drawArc(QRectF(cx - w / 2 + size * 0.10, cy - h / 2 + size * 0.03,
                         w - size * 0.20, h - size * 0.05), 15 * 16, 150 * 16)
        # 石子
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(148, 152, 132, 220))
        p.drawEllipse(QPointF(cx + w * 0.30, cy + h * 0.10), w * 0.055, h * 0.20)
        p.drawEllipse(QPointF(cx + w * 0.36, cy + h * 0.02), w * 0.04, h * 0.15)
        p.setBrush(QColor(230, 232, 214, 90))
        p.drawEllipse(QPointF(cx + w * 0.288, cy + h * 0.04), w * 0.02, h * 0.07)
        # 荷叶 (带缺口)
        lx, ly = cx - w * 0.30, cy - h * 0.06
        lr = w * 0.13
        p.setBrush(QColor(100, 164, 80, 240))
        p.drawEllipse(QPointF(lx, ly), lr, lr * 0.42)
        p.setBrush(QColor(84, 146, 104, 235))       # 缺口楔形用附近水色
        p.setBrush(QColor(96, 176, 148, 235))
        notch = QPainterPath()
        notch.moveTo(lx, ly)
        notch.lineTo(lx + lr * 1.2, ly - lr * 0.18)
        notch.lineTo(lx + lr * 0.9, ly + lr * 0.42)
        notch.closeSubpath()
        p.drawPath(notch)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(52, 96, 44, 130), max(1.0, size * 0.007)))
        p.drawEllipse(QPointF(lx, ly), lr, lr * 0.42)

        # 水面涟漪圈
        for r in self.rings:
            if r["delay"] > 0:
                continue
            t = clamp01(r["age"] / r["life"])
            rr = lerp(r["r0"], r["r1"], ease_out(t))
            alpha = r["a0"] * (1 - t)
            if r.get("flash"):
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(240, 252, 248, int(alpha * 0.8)))
                p.drawEllipse(QPointF(r["cx"], r["cy"]), rr, rr * 0.36)
            else:
                p.setPen(QPen(QColor(238, 252, 247, int(alpha)), max(1.2, size * 0.010)))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(r["cx"], r["cy"]), rr, rr * 0.36)

    def _paint_droplets(self, p: QPainter):
        if not self.droplets:
            return
        p.setPen(Qt.PenStyle.NoPen)
        for d in self.droplets:
            t = clamp01(d["age"] / d["life"])
            alpha = int(235 * (1 - t) + 20)
            p.setBrush(QColor(232, 250, 244, alpha))
            p.drawEllipse(QPointF(d["x"], d["y"]), d["r"], d["r"] * 1.25)
            p.setBrush(QColor(255, 255, 255, min(200, alpha)))
            p.drawEllipse(QPointF(d["x"] - d["r"] * 0.25, d["y"] - d["r"] * 0.3),
                          d["r"] * 0.35, d["r"] * 0.35)

    # ---------------- 气泡 ----------------
    def _paint_bubble(self, p: QPainter, now):
        life = 1.7
        dt = now - self.bubble_t0
        if self.bubble_text and 0 <= dt <= life:
            alpha = 1.0
            if dt < 0.15:
                alpha = dt / 0.15
            elif dt > life - 0.3:
                alpha = max(0.0, (life - dt) / 0.3)
            s = self.sprites.scale
            font = QFont("Microsoft YaHei UI")
            font.setPixelSize(max(13, int(self.cfg.size * 0.105)))
            font.setWeight(QFont.Weight.DemiBold)
            fm = QFontMetricsF(font)
            tw = fm.horizontalAdvance(self.bubble_text)
            pad_x, pad_y = 12, 8
            bw, bh = tw + pad_x * 2, fm.height() + pad_y * 2
            bx = self.feet_win.x() - bw / 2
            by = self.feet_win.y() - (FOOT_Y - 150) * s - bh - 14
            bx = max(4, min(bx, self.win_w - bw - 4))
            path = QPainterPath()
            path.addRoundedRect(QRectF(bx, by, bw, bh), 10, 10)
            tail = QPainterPath()
            tail.moveTo(self.feet_win.x() - 7, by + bh - 1)
            tail.lineTo(self.feet_win.x() + 7, by + bh - 1)
            tail.lineTo(self.feet_win.x(), by + bh + 9)
            tail.closeSubpath()
            p.setOpacity(alpha)
            p.setPen(QColor(120, 150, 88, 210))
            p.setBrush(QColor(255, 255, 252, 236))
            p.drawPath(path.united(tail))
            p.setPen(QColor(52, 72, 40))
            p.setFont(font)
            p.drawText(QRectF(bx, by, bw, bh), Qt.AlignmentFlag.AlignCenter, self.bubble_text)
            p.setOpacity(1.0)


def clamp_jump_t(t: float) -> float:
    return max(0.32, min(0.58, t))
