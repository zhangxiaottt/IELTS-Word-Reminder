# -*- coding: utf-8 -*-
"""一次性工具：把 Q 版少女贴纸图从纯粉色背景抠成透明 PNG

原理（适用于纯色背景 + 白色描边的贴纸图）：
1. 用 HSV 判断像素是否为「粉色背景」（色相在品红/粉区间且饱和度、明度足够）
2. 从图像四边做洪泛填充，只删除「与边缘连通的粉色」
   —— 人物身上的粉色（如鞋子）被白色描边包围，不与边缘连通，得以保留
3. 其余像素设为不透明
"""
import os
import sys

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QImage, QPixmap, QColor
from collections import deque

# 默认输入/输出（可用命令行参数覆盖：python make_pet_png.py <输入> <输出>）
BASE = r"D:\Projects\IELTS-Word-Reminder\assets\pets"
SRC = BASE + r"\pet_1_raw.jpg"
DST = BASE + r"\pet_1.png"

# 粉色背景判定阈值（HSV：h 色相 0-359，s/v 0-255）
H_MIN = 280      # 品红/粉/红 色相下界
S_MIN = 80       # 饱和度下界
V_MIN = 90       # 明度下界


def load(src):
    img = QImage(src)
    if img.isNull():
        raise RuntimeError("cannot load image: " + src)
    return img.convertToFormat(QImage.Format_ARGB32)


def is_pink(img, x, y):
    c = QColor(img.pixel(x, y))
    h, s, v, _ = c.getHsv()
    if h < 0:          # 无色相（灰/白）不算背景
        return False
    return h >= H_MIN and s >= S_MIN and v >= V_MIN


def flood_from_border(img):
    """从四边连通粉色做洪泛填充，返回「背景像素」布尔表"""
    w, h = img.width(), img.height()
    pink = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            if is_pink(img, x, y):
                pink[y * w + x] = 1

    bg = bytearray(w * h)
    dq = deque()

    def seed(x, y):
        if 0 <= x < w and 0 <= y < h and pink[y * w + x] and not bg[y * w + x]:
            bg[y * w + x] = 1
            dq.append((x, y))

    for x in range(w):
        seed(x, 0)
        seed(x, h - 1)
    for y in range(h):
        seed(0, y)
        seed(w - 1, y)

    while dq:
        x, y = dq.popleft()
        for nx, ny in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
            if 0 <= nx < w and 0 <= ny < h and pink[ny * w + nx] and not bg[ny * w + nx]:
                bg[ny * w + nx] = 1
                dq.append((nx, ny))
    return bg


def apply_alpha(img, bg):
    """背景像素置为全透明（用 QColor.fromRgba 保留 alpha，避免 QColor(QRgb) 忽略 alpha 的坑）"""
    w, h = img.width(), img.height()
    for y in range(h):
        for x in range(w):
            if bg[y * w + x]:
                c = QColor.fromRgba(img.pixel(x, y))
                c.setAlpha(0)
                img.setPixelColor(x, y, c)
    return img


def keep_largest_component(img):
    """只保留最大连通的不透明区域（去除抠底后残留的孤立噪点/色块）

    抠掉与边缘连通的背景后，主体人物是最大的连通块；
    背景中残留的白色噪点等会成为与人物不相连的孤立小岛，直接清除。
    """
    w, h = img.width(), img.height()
    opaque = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            if QColor.fromRgba(img.pixel(x, y)).alpha() > 0:
                opaque[y * w + x] = 1

    seen = bytearray(w * h)
    best = []
    for y in range(h):
        for x in range(w):
            if opaque[y * w + x] and not seen[y * w + x]:
                comp = []
                dq = deque()
                seen[y * w + x] = 1
                dq.append((x, y))
                while dq:
                    cx, cy = dq.popleft()
                    comp.append((cx, cy))
                    for nx, ny in ((cx+1, cy), (cx-1, cy), (cx, cy+1), (cx, cy-1)):
                        if (0 <= nx < w and 0 <= ny < h
                                and opaque[ny * w + nx] and not seen[ny * w + nx]):
                            seen[ny * w + nx] = 1
                            dq.append((nx, ny))
                if len(comp) > len(best):
                    best = comp
    # 把非最大分量的像素设为透明
    best_set = set(best)
    for (x, y) in best_set:
        pass
    for y in range(h):
        for x in range(w):
            if opaque[y * w + x] and (x, y) not in best_set:
                c = QColor.fromRgba(img.pixel(x, y))
                c.setAlpha(0)
                img.setPixelColor(x, y, c)
    return len(best)


def main():
    img = load(SRC)
    bg = flood_from_border(img)
    # 统计去掉多少像素
    removed = sum(bg) * 1.0 / (img.width() * img.height()) * 100
    apply_alpha(img, bg)
    # 只保留最大连通区域（清除背景残留噪点）
    keep = keep_largest_component(img)
    # 保存前再把非背景像素设成不透明（去掉残留的半透明杂边）
    for y in range(img.height()):
        for x in range(img.width()):
            c = QColor.fromRgba(img.pixel(x, y))
            if c.alpha() > 0:
                c.setAlpha(255)
                img.setPixelColor(x, y, c)
    ok = img.save(DST, "PNG")
    if not ok:
        raise RuntimeError("save failed")
    print("OK saved: {} (bg removed {:.1f}%, keep px {})".format(DST, removed, keep))


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        SRC = sys.argv[1]
        DST = sys.argv[2]
    main()
