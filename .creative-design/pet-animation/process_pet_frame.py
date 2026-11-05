# -*- coding: utf-8 -*-
"""道具素材处理：白底角色图 → 透明 PNG，并统一缩放/脚底对齐

用途：把 AI 生成的桌宠动作帧处理成与既有帧（pet_1.png / walk_3.png）同规格的透明素材。
- 白底（含浅灰投影）从四边洪泛去除，只删与边缘连通的近白像素
- 只保留最大连通主体，清理抠图残留噪点
- 缩放到与原帧一致的人物高度，并对齐脚底 y、水平中心
"""
import sys
from collections import deque

from PIL import Image

# 目标规格（与原素材一致）
CANVAS = 1024
TARGET_BBOX = (241, 65, 780, 974)   # 原 pet_1.png 的人物包围盒
TARGET_FOOT_Y = 974                 # 脚底基线
TARGET_CX = (241 + 780) / 2.0       # 水平中心


def near_white(px):
    """近白判定：高亮度且低饱和（覆盖纯白背景与浅灰投影）"""
    r, g, b = px[0], px[1], px[2]
    if r > 228 and g > 228 and b > 228:
        return True
    # 浅灰投影：灰度接近、明度偏高
    mx, mn = max(r, g, b), min(r, g, b)
    return mx > 215 and (mx - mn) < 16


def build_bg_mask(im):
    """从四边洪泛标记与边缘连通的近白像素"""
    w, h = im.size
    px = im.load()
    bg = bytearray(w * h)

    def mark(x, y):
        if bg[y * w + x]:
            return
        if not near_white(px[x, y]):
            return
        bg[y * w + x] = 1
        dq.append((x, y))

    dq = deque()
    for x in range(w):
        mark(x, 0)
        mark(x, h - 1)
    for y in range(h):
        mark(0, y)
        mark(w - 1, y)

    while dq:
        x, y = dq.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h:
                mark(nx, ny)
    return bg


def apply_alpha(im, bg):
    w, h = im.size
    px = im.load()
    for y in range(h):
        row = y * w
        for x in range(w):
            if bg[row + x]:
                px[x, y] = (0, 0, 0, 0)


def keep_largest(im):
    """只保留最大连通不透明块"""
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    opaque = bytearray(w * h)
    for y in range(h):
        row = y * w
        for x in range(w):
            if px[x, y][3] > 0:
                opaque[row + x] = 1

    seen = bytearray(w * h)
    best = []
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if opaque[i] and not seen[i]:
                comp = []
                dq = deque([(x, y)])
                seen[i] = 1
                while dq:
                    cx, cy = dq.popleft()
                    comp.append((cx, cy))
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if 0 <= nx < w and 0 <= ny < h:
                            j = ny * w + nx
                            if opaque[j] and not seen[j]:
                                seen[j] = 1
                                dq.append((nx, ny))
                if len(comp) > len(best):
                    best = comp

    keep = set(best)
    for y in range(h):
        row = y * w
        for x in range(w):
            if opaque[row + x] and (x, y) not in keep:
                px[x, y] = (0, 0, 0, 0)
    return im


def normalize(im):
    """缩放到人物高度=909，脚底对齐 TARGET_FOOT_Y，水平中心对齐"""
    im = im.convert("RGBA")
    bbox = im.getchannel("A").getbbox()
    if not bbox:
        return im
    x0, y0, x1, y1 = bbox
    src_h = y1 - y0
    src_cx = (x0 + x1) / 2.0
    tgt_h = TARGET_BBOX[3] - TARGET_BBOX[1]
    scale = tgt_h / float(src_h)
    new_w = max(1, int(round(im.width * scale)))
    new_h = max(1, int(round(im.height * scale)))
    im = im.resize((new_w, new_h), Image.LANCZOS)

    bbox = im.getchannel("A").getbbox()
    x0, y0, x1, y1 = bbox
    tmp = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    # 目标：bbox 底边 = TARGET_FOOT_Y，bbox 水平中心 = TARGET_CX
    dx = int(round(TARGET_CX - (x0 + x1) / 2.0))
    dy = int(round(TARGET_FOOT_Y - y1))
    tmp.paste(im, (dx, dy), im)
    return tmp


def main(src, dst):
    im = Image.open(src).convert("RGBA")
    bg = build_bg_mask(im)
    apply_alpha(im, bg)
    im = keep_largest(im)
    im = normalize(im)
    im.save(dst, "PNG")
    bbox = im.getchannel("A").getbbox()
    print("OK ->", dst, "size", im.size, "bbox", bbox)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("用法: python process_pet_frame.py <输入> <输出>")
    main(sys.argv[1], sys.argv[2])
