# -*- coding: utf-8 -*-
"""离屏录制行走动画 GIF：跑真实定时器，按 33ms 采帧

用于人工核对换帧、起伏与重心摆动的连贯度，不启动可见界面。
用法：python render_gif.py <输出gif> [时长秒]
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = r"D:\Projects\IELTS-Word-Reminder"
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402
from PIL import Image  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from src.desktop_pet import DesktopPet  # noqa: E402


class _StubConfig:
    def get(self, key, default=None):
        return default


class _StubPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setGeometry(100, 600, 320, 120)

    def isVisible(self):
        return True


def main(out_path: str, seconds: float = 2.0) -> None:
    app = QApplication(sys.argv[:1])
    pet = DesktopPet(_StubConfig(), _StubPanel())
    pet.show()
    pet._base_pos = (200, 200)
    # 强制持续行走：给一个 2 秒内走不到的远目标
    pet._target_dx = 240
    pet._state = "walk"
    pet._walk_idx = 1
    pet._pixmap = pet._walk_frames[pet.WALK_ORDER[1]]
    pet._frame_elapsed = 0.0
    pet._walk_timer.start()

    frames = []
    t0 = time.perf_counter()
    next_at = 0.0
    step = 0.033
    while True:
        elapsed = time.perf_counter() - t0
        if elapsed >= seconds:
            break
        app.processEvents()
        if elapsed >= next_at:
            img = pet.grab().toImage()
            frames.append(img)
            next_at += step
        time.sleep(0.004)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    pil_frames = []
    bg = Image.new("RGBA", (pet.width(), pet.height()), (250, 246, 248, 255))
    for img in frames:
        qimg = img.convertToFormat(QImage.Format.Format_ARGB32)
        w, h = qimg.width(), qimg.height()
        buf = qimg.constBits().tobytes()
        layer = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)
        merged = bg.copy()
        merged.paste(layer, (0, 0), layer)
        pil_frames.append(merged.convert("P", palette=Image.ADAPTIVE, colors=128))

    pil_frames[0].save(
        out_path, save_all=True, append_images=pil_frames[1:],
        duration=33, loop=0, optimize=False,
    )
    print("OK", out_path, "frames", len(pil_frames))


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "tmp_walk.gif")
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
    main(out, secs)
