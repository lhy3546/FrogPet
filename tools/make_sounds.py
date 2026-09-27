# -*- coding: utf-8 -*-
"""合成三段轻柔的青蛙"呱"声 (assets/sounds/croak1-3.wav)。
谐波脉冲串 + 共鸣峰 + 幅度包络, 峰值 0.22, 音量轻柔不刺耳。"""
import os
import wave
import numpy as np

SR = 44100
PEAK = 0.22


def env_ad(n, attack, decay_tau):
    t = np.arange(n) / SR
    e = np.minimum(t / max(attack, 1e-4), 1.0)
    e *= np.exp(-np.maximum(t - attack, 0) / decay_tau)
    return e


def croak(f0_start, f0_end, dur, formant, am_hz=0.0, am_depth=0.0):
    n = int(SR * dur)
    t = np.arange(n) / SR
    f0 = np.linspace(f0_start, f0_end, n)
    phase = 2 * np.pi * np.cumsum(f0) / SR
    sig = np.zeros(n)
    for k in range(1, 10):
        amp = 1.0 / k ** 1.4
        # 共鸣峰: 靠近 formant 的谐波增强
        fk = f0 * k
        boost = np.exp(-((fk - formant) / (formant * 0.55)) ** 2) * 2.2
        sig += amp * (1 + boost) * np.sin(phase * k)
    # 气息噪声
    rng = np.random.default_rng(7)
    sig += rng.normal(0, 0.05, n) * env_ad(n, 0.01, dur * 0.4)
    if am_hz > 0:
        sig *= 1 - am_depth * (0.5 - 0.5 * np.cos(2 * np.pi * am_hz * t))
    sig *= env_ad(n, 0.012, dur * 0.38)
    return sig


def splash():
    """轻柔的落水"扑通": 短噪声脉冲 + 下滑正弦, 峰值更低。"""
    n = int(SR * 0.22)
    t = np.arange(n) / SR
    rng = np.random.default_rng(11)
    noise = rng.normal(0, 1, n)
    # 简易低通: 一阶滑动
    k = 24
    noise = np.convolve(noise, np.ones(k) / k, mode="same")
    noise *= env_ad(n, 0.004, 0.045)
    f0 = np.linspace(880, 260, n)
    blip = np.sin(2 * np.pi * np.cumsum(f0) / SR) * env_ad(n, 0.006, 0.055) * 0.8
    sig = noise * 0.7 + blip
    return sig


def save(path, sig):
    sig = sig / (np.abs(sig).max() + 1e-9) * PEAK
    pcm = (sig * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print("wrote", path)


def main():
    out = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "sounds"))
    os.makedirs(out, exist_ok=True)
    gap = np.zeros(int(SR * 0.11))

    save(os.path.join(out, "croak1.wav"), croak(150, 118, 0.17, 620))
    save(os.path.join(out, "croak2.wav"),
         np.concatenate([croak(140, 125, 0.13, 680), gap, croak(150, 112, 0.16, 600)]))
    save(os.path.join(out, "croak3.wav"), croak(125, 96, 0.30, 520, am_hz=27, am_depth=0.5))
    s = splash()
    s = s / (np.abs(s).max() + 1e-9) * (PEAK * 0.75)
    pcm = (s * 32767).astype(np.int16)
    with wave.open(os.path.join(out, "splash.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print("wrote", os.path.join(out, "splash.wav"))


if __name__ == "__main__":
    main()
