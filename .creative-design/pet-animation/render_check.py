# -*- coding: utf-8 -*-
"""离屏渲染检查：把行走 4 拍与待机状态分别 grab 成图，用于人工核对

不启动真实界面、不写配置，只在 offscreen 平台下渲染角色窗口。
用法：python render_check.py <输出目录>
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = r"D:\Projects\IELTS-Word-Reminder"
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402
from src.desktop_pet import DesktopPet  # noqa: E402


class _StubConfig:
    """最小配置桩（小宠只在初始化时读少量项）"""

    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return default


class _StubPanel(QWidget):
    """面板桩：提供几何与可见性，让 anchor/位置计算可用"""

    def __init__(self):
        super().__init__()
        self.setGeometry(100, 600, 320, 120)

    def isVisible(self):
        return True


def main(out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    app = QApplication(sys.argv[:1])
    pet = DesktopPet(_StubConfig(), _StubPanel())
    pet.show()
    pet._base_pos = (200, 200)

    # 待机帧
    pet._state = "idle"
    pet._pixmap = pet._open_pixmap
    pet._apply_position(force=True)
    pet.grab().save(os.path.join(out_dir, "shot_idle.png"))

    # 4 个随机 idle pose
    for i, pm in enumerate(pet._idle_pixmaps):
        pet._pixmap = pm
        pet._apply_position(force=True)
        pet.repaint()
        pet.grab().save(os.path.join(out_dir, "shot_pose_%d.png" % i))

    # 行走 6 拍：逐拍取图（WALK_ORDER 长度）
    pet._state = "walk"
    pet._walk_idx = -1
    n = len(pet.WALK_ORDER)
    for i in range(n):
        pet._advance_walk()
        pet._frame_elapsed = pet.WALK_FRAME_MS * 0.5
        pet._apply_position(force=True)
        pet.repaint()
        pet.grab().save(os.path.join(out_dir, "shot_walk_%d.png" % i))

    print("OK 输出目录:", out_dir)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "tmp_render"))
