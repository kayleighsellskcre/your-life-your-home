"""Generate the fine-grain oak texture behind the site header: static/img/oak-slab.jpg
Soft, matte, low-contrast straight grain (no knots) in a muted warm tan.
Run:  python scripts/make_wood.py
"""
import numpy as np
from PIL import Image
from pathlib import Path

W, H = 2400, 320


def noise(w, h, gx, gy, seed):
    r = np.random.default_rng(seed)
    g = r.random((gy + 3, gx + 3)).astype(np.float32)
    ox, oy = w // gx + 1, h // gy + 1
    img = Image.fromarray((g * 255).astype(np.uint8)).resize((w + 2 * ox, h + 2 * oy), Image.BICUBIC)
    return np.asarray(img, dtype=np.float32)[oy:oy + h, ox:ox + w] / 255


def fbm(w, h, gx, gy, seed, octaves=4):
    out, amp, tot = 0, 1.0, 0
    for i in range(octaves):
        out = out + amp * noise(w, h, gx * 2 ** i, gy * 2 ** i, seed + i)
        tot += amp
        amp *= 0.5
    return out / tot


y, x = np.mgrid[0:H, 0:W].astype(np.float32)

# very gentle drift so the lines are not ruler-straight
f = y + 26 * (fbm(W, H, 3, 2, 100) - 0.5) + 9 * (fbm(W, H, 9, 4, 120) - 0.5)

# fine grain lines stretched along the length of the board, at several scales
y2 = np.clip((f).astype(np.int32), 0, H - 1)
g1 = noise(W, H, 8, 150, 41)[y2, np.arange(W)[None, :].repeat(H, 0)]          # long soft streaks
g2 = noise(W, H, 30, 320, 43)[y2, np.arange(W)[None, :].repeat(H, 0)]         # fine lines
g3 = noise(W, H, 160, 320, 47)        # tiny pores
sway = fbm(W, H, 4, 2, 7)
lines = 0.5 + 0.5 * np.sin(f * 0.34 + 5 * sway)
cloud = fbm(W, H, 5, 3, 77)
tone = 0.28 * g1 + 0.18 * g2 + 0.10 * g3 + 0.10 * lines + 0.34 * cloud

# muted, warm, slightly greyed tan (matte, not orange)
light = np.array([196, 163, 123], np.float32)
dark = np.array([170, 136, 98], np.float32)
t = np.clip((tone - tone.mean()) * 2.6 + 0.5, 0, 1)
col = light[None, None] * (1 - t[..., None]) + dark[None, None] * t[..., None]

# soft sheen: a broad, faint light band across the board
sheen = 0.5 + 0.5 * np.cos((x / W - 0.35) * 2.2)
col *= (0.97 + 0.05 * sheen)[..., None]
col *= (1.02 - 0.05 * (y / H))[..., None]

Image.fromarray(np.clip(col, 0, 255).astype(np.uint8)).save(
    Path(__file__).resolve().parent.parent / "static" / "img" / "oak-slab.jpg", quality=84, optimize=True)
print("ok")
