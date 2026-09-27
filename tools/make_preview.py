# -*- coding: utf-8 -*-
"""生成 README 用的预览图: 四个姿态并排放在柔和渐变背景上 (docs/preview.png)。"""
import os
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs", "preview.png"))
SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "frog"))

FRAMES = [
    ("frog_idle.png", "待机 · 呼吸"),
    ("frog_blink.png", "随机眨眼"),
    ("frog_puffed.png", "鼓腮鸣囊"),
    ("frog_jump.png", "跳跃腾空"),
]

TH = 340          # 每帧显示高度
GAP = 70
PAD_X = 90
PAD_TOP = 70
LABEL_H = 70
W = PAD_X * 2 + TH * len(FRAMES) + GAP * (len(FRAMES) - 1)
H = PAD_TOP + TH + LABEL_H + 60


def main():
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    # 垂直渐变背景 (淡绿 -> 米白)
    top = (232, 244, 226)
    bottom = (250, 250, 244)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))

    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 30)
    x = PAD_X
    for name, label in FRAMES:
        src = Image.open(os.path.join(SRC, name)).convert("RGBA")
        bbox = src.getbbox()
        src = src.crop(bbox)
        w = int(src.width * TH / src.height)
        src = src.resize((w, TH), Image.LANCZOS)
        img.paste(src, (x + (TH - w) // 2, PAD_TOP), src)
        tw = d.textlength(label, font=font)
        d.text((x + (TH - tw) / 2, PAD_TOP + TH + 26), label, fill=(58, 84, 48), font=font)
        x += TH + GAP

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img.save(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
