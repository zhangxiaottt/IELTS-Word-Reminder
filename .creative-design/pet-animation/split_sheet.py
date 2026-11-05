# -*- coding: utf-8 -*-
"""把精灵表切分成单帧素材并落进 assets/pets/

切分规则：2048x2048 原图 → 2 行 4 列，每格 512x1024。
第一行第 2 格（左腿交叉到右腿前）姿态错误，弃用。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from process_pet_frame import (  # noqa: E402
    build_bg_mask, apply_alpha, keep_largest, normalize,
)
from PIL import Image  # noqa: E402

SRC = os.path.join(HERE, "sheet_raw.png")
OUT = r"D:\Projects\IELTS-Word-Reminder\assets\pets"

# 按切格顺序命名（None 表示弃用）
NAMES = [
    "walk_base",     # r0c0 站姿双脚并拢
    None,            # r0c1 左腿交叉到右腿前，弃用
    "walk_right",    # r0c2 右腿前迈
    "blink_closed",  # r0c3 正面闭眼（眨眼备选）
    "idle_wave",     # r1c0 挥手
    "idle_hips",     # r1c1 双手叉腰
    "idle_giggle",   # r1c2 捧脸大笑
    "idle_relax",    # r1c3 闭眼放松
]


def main() -> None:
    im = Image.open(SRC).convert("RGBA")
    W, H = im.size
    cw, ch = W // 4, H // 2
    for idx, name in enumerate(NAMES):
        if name is None:
            continue
        r, c = divmod(idx, 4)
        cell = im.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))
        bg = build_bg_mask(cell)
        apply_alpha(cell, bg)
        cell = keep_largest(cell)
        cell = normalize(cell)
        out = os.path.join(OUT, name + ".png")
        cell.save(out)
        bbox = cell.getchannel("A").getbbox()
        print(name, "->", out, "bbox", bbox)


if __name__ == "__main__":
    main()
