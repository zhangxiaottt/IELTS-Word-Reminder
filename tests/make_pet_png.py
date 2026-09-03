# -*- coding: utf-8 -*-
"""一次性工具：把 Q 版少女贴纸图从纯粉色背景抠成透明 PNG

原理（适用于纯色背景 + 白色描边的贴纸图）：
1. 用 HSV 判断像素是否为「粉色背景」（色相在品红/粉区间且饱和度、明度足够）
2. 从图像四边做洪泛填充，只删除「与边缘连通的粉色」
   —— 人物身上的粉色（如鞋子）被白色描边包围，不与边缘连通，得以保留
3. 其余像素设为不透明
"""
import os

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QImage, QPixmap, QColor
from collections import deque

SRC = r"D:\Projects\IELTS-Word-Reminder\assets\pets\pet_1_raw.jpg"
DST = r"D:\Projects\IELTS-Word-Reminder\assets\pets\pet_1.png"

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


def main():
    img = load(SRC)
    bg = flood_from_border(img)
    # 统计去掉多少像素
    removed = sum(bg) * 1.0 / (img.width() * img.height()) * 100
    apply_alpha(img, bg)
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
    print("OK saved: {} (bg removed {:.1f}%)".format(DST, removed))


if __name__ == "__main__":
    main()
