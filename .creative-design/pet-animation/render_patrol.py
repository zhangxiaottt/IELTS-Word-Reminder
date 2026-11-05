# -*- coding: utf-8 -*-
"""巡逻模式离屏验证：侧身站姿/迈步、朝右/朝左"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = r"D:\Projects\IELTS-Word-Reminder"
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402
from src.desktop_pet import DesktopPet  # noqa: E402


class _Cfg:
    def get(self, k, d=None):
        return d


class _Panel(QWidget):
    def __init__(self):
        super().__init__()
        self.setGeometry(100, 100, 320, 120)

    def isVisible(self):
        return True


def main(out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    app = QApplication(sys.argv[:1])
    pet = DesktopPet(_Cfg(), _Panel())
    pet.show()
    pet.start_patrol()

    # 朝右：侧身站姿 + 侧身迈步
    pet._face = 1
    pet._pixmap = pet._side_frames["stand"]
    pet._apply_position(force=True)
    pet.repaint()
    pet.grab().save(os.path.join(out_dir, "patrol_r_stand.png"))

    pet._pixmap = pet._side_frames["walk"]
    pet._apply_position(force=True)
    pet.repaint()
    pet.grab().save(os.path.join(out_dir, "patrol_r_walk.png"))

    # 朝左：同一批源帧，paintEvent 按 _face=-1 自动水平翻转
    pet._face = -1
    pet._pixmap = pet._side_frames["stand"]
    pet._apply_position(force=True)
    pet.repaint()
    pet.grab().save(os.path.join(out_dir, "patrol_l_stand.png"))

    pet._pixmap = pet._side_frames["walk"]
    pet._apply_position(force=True)
    pet.repaint()
    pet.grab().save(os.path.join(out_dir, "patrol_l_walk.png"))

    print("OK", out_dir)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "tmp_patrol"))
