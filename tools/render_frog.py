# -*- coding: utf-8 -*-
"""
参数化写实树蛙渲染器 —— 生成桌面宠物所需的全部姿态素材。
输出 (assets/frog/):
  frog_idle.png    待机(睁眼)
  frog_blink.png   眨眼(闭眼)
  frog_puffed.png  鼓腮(鸣囊鼓起)
  frog_jump.png    腾空(后肢蹬直)
  shadow.png       接触阴影
  frog.ico         应用图标

渲染策略: 640 逻辑坐标绘制 + 2x 超采样 -> 640x640 RGBA。
所有姿态共用同一套身体几何, 保证帧间一致(比 AI 逐帧生成更稳)。
"""
import math
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageChops

SS = 2                       # 超采样倍数
C = 640                      # 画布逻辑尺寸
W = C * SS

random.seed(20260927)
np.random.seed(20260927)

# ---------------- 基础色板 (真实树蛙) ----------------
DORSUM_DARK = (70, 112, 40)
DORSUM_MID = (98, 150, 58)
DORSUM_LIGHT = (130, 180, 72)
FLANK_YELLOW = (158, 194, 88)
BELLY_CREAM = (230, 226, 194)
STRIPE_DARK = (56, 86, 32)
LIMB_DARK = (84, 130, 50)
EYE_AMBER_OUT = (168, 116, 38)
EYE_AMBER_IN = (226, 176, 70)
EYE_PUPIL = (16, 14, 9)


def chain(draw, pts, widths, color):
    """沿折线画渐变宽度圆链, 形成有机肢体。坐标: 逻辑640。"""
    n = len(pts)
    for i in range(n - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        w1, w2 = widths[i], widths[i + 1]
        d = math.hypot(x2 - x1, y2 - y1)
        steps = max(2, int(d / max(2.0, min(w1, w2) * 0.35)))
        for s in range(steps + 1):
            t = s / steps
            x, y = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            r = (w1 + (w2 - w1) * t) / 2
            draw.ellipse([x - r, y - r, x + r, y + r], fill=color)


def toes(draw, origin, tips, base_w):
    """脚趾 + 末端吸盘。"""
    for tip in tips:
        chain(draw, [origin, tip], [base_w, base_w * 0.62, base_w * 0.45], 255)
        r = base_w * 0.5
        draw.ellipse([tip[0] - r, tip[1] - r, tip[0] + r, tip[1] + r], fill=255)


def mirror_pt(p):
    """水平镜像一个点: 只翻转 x。"""
    return (640 - p[0], p[1])


def mirror_limbs(items):
    """镜像肢体列表。元素 either [点,...] (链) 或 (原点, [趾尖,...])。"""
    out = []
    for item in items:
        if isinstance(item[0], tuple) and isinstance(item[1], list):
            origin, tips = item
            out.append((mirror_pt(origin), [mirror_pt(t) for t in tips]))
        else:
            out.append([mirror_pt(p) for p in item])
    return out


def geo(pose):
    """各姿态的几何参数 (逻辑坐标), 左右镜像齐全。"""
    if pose == "sit":
        left = dict(
            body=(320, 398, 202, 184), head=(320, 308, 186, 132),
            eye_bumps=[(244, 216), (396, 216)], eye_bump_r=54,
            thigh=[(152, 428, 72, 104, -0.32)],
            shanks=[[(148, 478), (184, 548)]],
            back_feet=[((188, 552), [(104, 588), (140, 602), (178, 606), (214, 594)])],
            arms=[[(200, 470), (184, 530), (176, 558)]],
            arm_toes=[((176, 558), [(140, 590), (168, 600), (200, 602)])],
            arm_w=[30, 24, 20], shank_w=[46, 34], toe_w=18, arm_toe_w=12,
        )
    else:  # air
        left = dict(
            body=(320, 372, 188, 206), head=(320, 278, 176, 130),
            eye_bumps=[(246, 194), (394, 194)], eye_bump_r=52,
            thigh=[],
            shanks=[[(172, 436), (136, 512), (174, 566)]],
            back_feet=[((178, 572), [(146, 600), (180, 608), (210, 598)])],
            arms=[[(196, 446), (170, 516), (160, 556)]],
            arm_toes=[((160, 556), [(118, 584), (146, 598), (180, 602), (208, 588)])],
            arm_w=[30, 24, 20], shank_w=[44, 34, 26], toe_w=15, arm_toe_w=13,
        )
    g = dict(left)
    for key in ("shanks", "back_feet", "arms", "arm_toes"):
        g[key] = left[key] + mirror_limbs(left[key])
    if left["thigh"]:
        g["thigh"] = left["thigh"] + [(640 - cx, cy, rx, ry, -ang) for cx, cy, rx, ry, ang in left["thigh"]]
    return g


def build_masks(pose):
    """返回 (mask_all, mask_body, mask_limb), SS 尺寸 L 图。
    mask_body: 躯干+头+眼凸+大腿; mask_limb: 小腿/脚/前臂/趾。"""
    g = geo(pose)
    m_all = Image.new("L", (C, C), 0)
    m_body = Image.new("L", (C, C), 0)
    m_limb = Image.new("L", (C, C), 0)
    da, db, dl = ImageDraw.Draw(m_all), ImageDraw.Draw(m_body), ImageDraw.Draw(m_limb)

    bx, by, brx, bry = g["body"]
    da.ellipse([bx - brx, by - bry, bx + brx, by + bry], fill=255)
    db.ellipse([bx - brx, by - bry, bx + brx, by + bry], fill=255)
    hx, hy, hrx, hry = g["head"]
    da.ellipse([hx - hrx, hy - hry, hx + hrx, hy + hry], fill=255)
    db.ellipse([hx - hrx, hy - hry, hx + hrx, hy + hry], fill=255)
    for cx, cy in g["eye_bumps"]:
        r = g["eye_bump_r"]
        da.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
        db.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)

    for cx, cy, rx, ry, ang in g["thigh"]:
        tmp = Image.new("L", (C, C), 0)
        td = ImageDraw.Draw(tmp)
        td.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=255)
        tmp = tmp.rotate(math.degrees(ang), center=(cx, cy), resample=Image.BILINEAR)
        for target in (m_all, m_body):
            target.paste(255, (0, 0), tmp)
        da = ImageDraw.Draw(m_all)

    for seg in g["shanks"]:
        chain(dl, seg, g["shank_w"], 255)
    for seg in g["arms"]:
        chain(dl, seg, g["arm_w"], 255)
    for org, tips in g["back_feet"]:
        toes(dl, org, tips, g["toe_w"])
    for org, tips in g["arm_toes"]:
        toes(dl, org, tips, g["arm_toe_w"])

    m_all = ImageChops.lighter(m_all, m_limb)
    m_all = m_all.resize((W, W), Image.LANCZOS).filter(ImageFilter.GaussianBlur(2.5 * SS))
    m_body = m_body.resize((W, W), Image.LANCZOS).filter(ImageFilter.GaussianBlur(2.5 * SS))
    m_limb = m_limb.resize((W, W), Image.LANCZOS).filter(ImageFilter.GaussianBlur(2 * SS))
    return m_all, m_body, m_limb


def radial_map(size, cx, cy, radius):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    return np.clip(np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / radius, 0, 2.0)


def base_gradient(mask_np):
    h, w = mask_np.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32) / SS
    vt = np.clip(yy / C, 0, 1)
    c_dark = np.array(DORSUM_DARK, np.float32)
    c_mid = np.array(DORSUM_MID, np.float32)
    c_light = np.array(DORSUM_LIGHT, np.float32)
    col = np.where(vt[..., None] < 0.40,
                   c_dark + (c_mid - c_dark) * (vt[..., None] / 0.40),
                   c_mid + (c_light - c_mid) * ((vt[..., None] - 0.40) / 0.60))
    d = radial_map(w, 320 * SS, 295 * SS, 330 * SS)          # 头胸受光
    col *= (1.0 + 0.20 * np.clip(1 - d, 0, 1))[..., None]
    flank = np.clip((np.abs(xx - 320) - 118) / 150, 0, 1) * np.clip(vt * 1.5, 0, 1)
    c_flank = np.array(FLANK_YELLOW, np.float32)
    col = col * (1 - flank[..., None] * 0.5) + c_flank * flank[..., None] * 0.5
    return col


def draw_eye(layer, cx, cy, r, closed):
    """眼睛: 金铜虹膜 + 水平瞳孔 + 高光。坐标为 SS 空间。closed 画闭合眼睑。"""
    d = ImageDraw.Draw(layer)
    if closed:
        for rr, col in [(r + 5, (122, 168, 76)), (r, (114, 158, 70))]:
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=col + (255,))
        d.arc([cx - r * 0.78, cy - r * 0.5, cx + r * 0.78, cy + r * 0.8],
              start=18, end=162, fill=(66, 100, 38, 180), width=int(2.8 * SS))
        return
    d.ellipse([cx - r - 3 * SS, cy - r - 3 * SS, cx + r + 3 * SS, cy + r + 3 * SS],
              fill=(44, 70, 26, 100))
    steps = 6
    for i in range(steps):
        t = i / (steps - 1)
        rr = r * (1 - 0.58 * t)
        col = tuple(int(EYE_AMBER_OUT[j] + (EYE_AMBER_IN[j] - EYE_AMBER_OUT[j]) * t) for j in range(3))
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=col + (255,))
    rng = random.Random(7)
    for _ in range(14):
        a = rng.uniform(0, math.tau)
        x0, y0 = cx + math.cos(a) * r * 0.5, cy + math.sin(a) * r * 0.5
        x1, y1 = cx + math.cos(a) * r * 0.9, cy + math.sin(a) * r * 0.9
        d.line([x0, y0, x1, y1], fill=(116, 76, 26, 70), width=SS)
    pw, ph = r * 0.52, r * 0.24
    d.ellipse([cx - pw, cy - ph, cx + pw, cy + ph], fill=EYE_PUPIL + (255,))
    d.ellipse([cx - pw * 0.55, cy - ph * 1.7, cx - pw * 0.05, cy - ph * 0.1],
              fill=(255, 255, 250, 235))
    d.ellipse([cx + pw * 0.25, cy + ph * 0.4, cx + pw * 0.55, cy + ph * 1.3],
              fill=(255, 252, 235, 100))
    d.arc([cx - r, cy - r, cx + r, cy + r], start=195, end=345,
          fill=(60, 94, 34, 150), width=int(2.2 * SS))


def render(pose="sit", closed=False, puff=0.0):
    mask_all, mask_body, mask_limb = build_masks(pose)
    ma = np.asarray(mask_all, np.float32) / 255.0
    mb = np.asarray(mask_body, np.float32) / 255.0
    ml = np.asarray(mask_limb, np.float32) / 255.0
    W_, H_ = mask_all.size
    yy, xx = np.mgrid[0:H_, 0:W_].astype(np.float32) / SS
    vt = np.clip(yy / C, 0, 1)

    # ================= 肢体层 (先画, 位于身体之下) =================
    c_limb_a = np.array(LIMB_DARK, np.float32)
    c_limb_b = np.array((116, 162, 70), np.float32)
    col_limb = c_limb_a + (c_limb_b - c_limb_a) * vt[..., None]

    # ================= 身体层 =================
    col_body = base_gradient(mb)

    # 腹部/喉部米白 (仅身体区域)
    belly = np.exp(-(((xx - 320) / 150) ** 2 + ((yy - (514 if pose == "sit" else 492)) / 96) ** 2))
    throat_r = 84 + 60 * puff
    throat = np.exp(-(((xx - 320) / throat_r) ** 2 +
                      ((yy - (470 + 26 * puff if pose == "sit" else 446)) / (56 + 34 * puff)) ** 2))
    cream = np.clip(np.maximum(belly, throat * (0.9 + 0.3 * puff)), 0, 1) * mb
    c_cream = np.array(BELLY_CREAM, np.float32)
    col_body = col_body * (1 - cream[..., None]) + c_cream * cream[..., None]

    # 鸣囊: 明确的球形隆起 + 边缘阴影
    if puff > 0.02:
        sac = np.exp(-(((xx - 320) / (96 + 14 * puff)) ** 2 +
                       ((yy - (492 + 14 * puff)) / (64 + 12 * puff)) ** 2))
        sac_hi = np.exp(-(((xx - 320) / 46) ** 2 + ((yy - (478 + 10 * puff)) / 28) ** 2))
        c_sac = np.array((246, 240, 202), np.float32)
        col_body = col_body * (1 - sac[..., None] * 0.92) + c_sac * sac[..., None] * 0.92
        col_body += (sac_hi * 40 * puff)[..., None]

    # 体侧条纹 + 背斑
    stripe = np.zeros((H_, W_), np.float32)
    for sgn in (-1, 1):
        px = 320 + sgn * (172 if pose == "sit" else 162)
        ds = np.exp(-(((xx - px) / 32) ** 2 + ((yy - (336 if pose == "sit" else 306)) / 185) ** 2))
        stripe = np.maximum(stripe, ds)
    stripe *= np.clip((yy - 230) / 150, 0, 1) * mb * 0.45
    col_body = col_body * (1 - stripe[..., None]) + np.array(STRIPE_DARK, np.float32) * stripe[..., None]
    rng = random.Random(42)
    spots = np.zeros((H_, W_), np.float32)
    for _ in range(9):
        sx, sy = rng.uniform(250, 390), rng.uniform(260, 390)
        sr = rng.uniform(13, 26)
        spots += np.exp(-(((xx - sx) / sr) ** 2 + ((yy - sy) / (sr * 0.8)) ** 2))
    spots = np.clip(spots, 0, 1) * mb * np.clip((370 - yy) / 130, 0, 1) * 0.35
    col_body = col_body * (1 - spots[..., None] * 0.55) + \
        np.array(STRIPE_DARK, np.float32) * spots[..., None] * 0.55

    # 湿润高光斑 (身体受光面)
    spec = Image.new("L", (W_, W_), 0)
    sd = ImageDraw.Draw(spec)
    hi = [(300, 244, 46, 18), (398, 246, 38, 16), (270, 308, 28, 13), (384, 318, 24, 11),
          (320, 202, 50, 15)] if pose == "sit" else \
         [(302, 218, 46, 18), (394, 220, 38, 16), (272, 280, 28, 13), (382, 290, 24, 11), (320, 176, 50, 15)]
    for x, y, rx, ry in hi:
        sd.ellipse([(x - rx) * SS, (y - ry) * SS, (x + rx) * SS, (y + ry) * SS], fill=60)
    spec = spec.filter(ImageFilter.GaussianBlur(6 * SS))
    col_body += ((np.asarray(spec, np.float32) / 255.0 * mb) * 52)[..., None] * np.array([1, 1, 0.92])

    # ================= 合成: 肢体在下, 身体覆盖其上 =================
    ab = mb[..., None]
    col = col_limb * (1 - ab) + col_body * ab

    # ---- 全局皮肤颗粒 ----
    noise = np.random.normal(0, 1, (H_, W_)).astype(np.float32)
    noise_img = Image.fromarray(((noise * 0.5 + 0.5) * 255).clip(0, 255).astype(np.uint8))
    fine = np.asarray(noise_img.filter(ImageFilter.GaussianBlur(0.6 * SS)), np.float32) / 255.0 - 0.5
    grain = np.asarray(noise_img.filter(ImageFilter.GaussianBlur(2.2 * SS)), np.float32) / 255.0 - 0.5
    col += ((fine * 8 + grain * 5)[..., None]) * ma[..., None]
    dots = np.zeros((H_, W_), np.float32)
    for _ in range(2400):
        dx, dy = rng.uniform(130, 510), rng.uniform(190, 560)
        dr = rng.uniform(1.4, 3.2)
        dots += np.exp(-(((xx - dx) / dr) ** 2 + ((yy - dy) / dr) ** 2)) * rng.choice((-1, 1)) * rng.uniform(0.5, 1.0)
    dots = np.asarray(Image.fromarray(((dots * 40 + 128)).clip(0, 255).astype(np.uint8))
                      .filter(ImageFilter.GaussianBlur(0.8 * SS)), np.float32) / 255.0 - 0.5
    col += (dots * 22)[..., None] * ma[..., None]

    # ---- 底缘 AO / 肢体下段加重 ----
    m_up = np.asarray(mask_all.transform((W_, W_), Image.AFFINE, (1, 0, 0, 0, 1, -5 * SS),
                                         resample=Image.BILINEAR), np.float32) / 255.0
    col -= (np.clip(ma - m_up, 0, 1) * 24)[..., None]
    limb_low = ml * np.clip((yy - 430) / 170, 0, 1)
    col -= (limb_low * 14)[..., None]

    # ---- 顶缘轮廓光 ----
    m_dn = np.asarray(mask_all.transform((W_, W_), Image.AFFINE, (1, 0, 0, 0, 1, 6 * SS),
                                         resample=Image.BILINEAR), np.float32) / 255.0
    rim = np.clip(ma - m_dn, 0, 1) * np.clip((320 - yy) * 0.01 + 0.55, 0, 1)
    rim = np.asarray(Image.fromarray((rim * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.5 * SS)),
                     np.float32) / 255.0
    col += (rim * 46)[..., None] * np.array([1.05, 1.1, 0.85])

    rgba = np.dstack([col.clip(0, 255).astype(np.uint8), (ma * 255).astype(np.uint8)])
    layer = Image.fromarray(rgba, "RGBA")

    # ---- 眼睛 / 鼻孔 / 嘴 ----
    eye_y = 220 if pose == "sit" else 198
    er = 34
    draw_eye(layer, 244 * SS, eye_y * SS, er * SS, closed)
    draw_eye(layer, 396 * SS, eye_y * SS, er * SS, closed)
    d = ImageDraw.Draw(layer)
    for nx, ny in [(306, 268), (334, 268)]:
        if pose == "air":
            ny -= 22
        d.ellipse([(nx - 3) * SS, (ny - 3) * SS, (nx + 3) * SS, (ny + 3) * SS],
                  fill=(40, 62, 24, 170))
    y_off = 0 if pose == "sit" else -22
    d.arc([208 * SS, (322 + y_off) * SS, 432 * SS, (402 + y_off) * SS],
          start=24, end=156, fill=(58, 88, 32, 80), width=int(2.2 * SS))

    return layer.resize((C, C), Image.LANCZOS)


def make_shadow():
    s = Image.new("RGBA", (480, 160), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    d.ellipse([70, 40, 410, 120], fill=(10, 16, 6, 80))
    return s.filter(ImageFilter.GaussianBlur(16))


def main():
    import os
    out = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "frog"))
    os.makedirs(out, exist_ok=True)
    idle = render("sit", closed=False, puff=0.0)
    idle.save(os.path.join(out, "frog_idle.png"))
    render("sit", closed=True).save(os.path.join(out, "frog_blink.png"))
    render("sit", puff=1.0).save(os.path.join(out, "frog_puffed.png"))
    render("air").save(os.path.join(out, "frog_jump.png"))
    make_shadow().save(os.path.join(out, "shadow.png"))

    icon_src = idle.crop(idle.getbbox())
    side = max(icon_src.size)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(icon_src, ((side - icon_src.width) // 2, (side - icon_src.height) // 2))
    sq.save(os.path.join(out, "frog_icon_src.png"))
    sq.resize((256, 256), Image.LANCZOS).save(
        os.path.join(out, "frog.ico"),
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("assets written to", out)


if __name__ == "__main__":
    main()
