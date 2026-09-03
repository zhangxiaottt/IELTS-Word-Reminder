# -*- coding: utf-8 -*-
"""桌面小宠模块 - DesktopPet

在悬浮复习面板周围活动的小型 Q 版角色（桌宠）：
- 透明、无边框、置顶小窗，显示透明背景的角色 PNG（平面/2D 设计）
- 简单动画：上下轻微浮动 + 左右来回游走，活动范围限于面板周围
- 面板移动/缩放时自动跟随重新定位
- 单击跳跃反应；右键菜单可回到面板旁
"""
import math
import random

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QMenu, QVBoxLayout,
)

from .utils import get_asset_path

# 角色图路径（透明 PNG，位于 assets/pets/）
PET_SPRITE = "pets/pet_1.png"


class DesktopPet(QWidget):
    """桌面小宠"""

    TICK_MS = 33          # 动画刷新间隔（毫秒）
    DISPLAY_H = 120       # 角色显示高度（像素，高分屏自动按比例放大）
    BOB_AMP = 6           # 上下浮动幅度（像素）
    BOB_SPEED = 0.16      # 浮动角速度
    WANDER_STEP = 1.2     # 每帧向目标游走的步长（像素）
    HOP_POWER = 26        # 单击跳跃力度（像素）
    WANDER_RANGE = 40     # 相对锚点的最大水平游走距离（像素）

    def __init__(self, config, panel, parent: QWidget = None):
        """初始化桌宠

        Args:
            config: ConfigManager 实例
            panel: FloatPanel 实例（桌宠跟随它移动）
        """
        super().__init__(
            parent,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,
        )
        self._config = config
        self._panel = panel

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)  # 不抢输入焦点
        self.setWindowTitle("雅思小宠")

        # 加载角色图
        self._pixmap = QPixmap(get_asset_path(PET_SPRITE))
        self._build_ui()

        # 动画状态
        self._t = 0              # 时间步计数
        self._wander = 0.0       # 当前水平偏移（相对锚点）
        self._target_dx = 0      # 目标水平偏移
        self._hop = 0            # 跳跃高度（逐帧衰减）
        self._base_pos = (0, 0)  # 锚点：面板下缘居中

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self.TICK_MS)

        self._wander_timer = QTimer(self)
        self._wander_timer.timeout.connect(self._pick_target)
        self._wander_timer.start(random.randint(2500, 5000))

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        """构建界面：单张角色图"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel(self)
        if not self._pixmap.isNull():
            w = int(self._pixmap.width() * self.DISPLAY_H / self._pixmap.height())
            pm = self._pixmap.scaled(
                w, self.DISPLAY_H, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self._label.setPixmap(pm)
            self.setFixedSize(pm.width(), pm.height())
        else:
            self.setFixedSize(80, 80)
        layout.addWidget(self._label)

    # ------------------------------------------------------------------ #
    # 定位 / 动画
    # ------------------------------------------------------------------ #
    def _screen(self):
        """当前屏幕（回退到主屏）"""
        s = self.screen()
        return s if s else QApplication.primaryScreen()

    def anchor(self) -> None:
        """根据面板当前几何重新计算锚点（面板下缘居中）并归位"""
        if not self._panel.isVisible():
            self.hide()
            return
        g = self._panel.geometry()
        self._base_pos = (
            g.x() + (g.width() - self.width()) // 2,
            g.y() + g.height() + 8,
        )
        self._wander = 0.0
        self._target_dx = 0
        self._apply_position(force=True)

    def _allowed_region(self) -> tuple:
        """活动范围：面板四周扩展区域（左上角语义），并夹在屏幕可用区域内

        返回 (left, right, top, bottom)，表示桌宠左上角允许的坐标范围。
        """
        g = self._panel.geometry()
        left = g.x() - 40
        right = g.x() + g.width() + 40
        top = g.y() - 40
        bottom = g.y() + g.height() + 60
        scr = self._screen()
        if scr is not None:
            ag = scr.availableGeometry()
            # 屏幕边界按桌宠尺寸夹紧，保证整只小宠可见
            left = max(left, ag.x())
            right = min(right, ag.x() + ag.width() - self.width())
            top = max(top, ag.y())
            bottom = min(bottom, ag.y() + ag.height() - self.height())
        if right < left:
            right = left
        if bottom < top:
            bottom = top
        return left, right, top, bottom

    def _pick_target(self) -> None:
        """随机选取下一个游走目标（水平偏移相对锚点）"""
        ax, _ = self._base_pos
        left, right, _, _ = self._allowed_region()
        self._target_dx = random.randint(
            max(left - ax, -self.WANDER_RANGE),
            min(right - ax, self.WANDER_RANGE),
        )
        self._wander_timer.start(random.randint(2500, 5000))

    def _tick(self) -> None:
        """动画主循环：浮动 + 游走 + 跳跃衰减"""
        self._t += 1
        if not self.isVisible() or not self._panel.isVisible():
            return
        # 上下浮动（正弦）
        bob = int(math.sin(self._t * self.BOB_SPEED) * self.BOB_AMP)
        # 左右游走：逐步逼近目标偏移
        dx = self._wander
        if abs(self._target_dx - dx) <= self.WANDER_STEP:
            self._wander = float(self._target_dx)
        else:
            self._wander += self.WANDER_STEP if self._target_dx > dx else -self.WANDER_STEP
        # 跳跃衰减
        if self._hop > 0:
            self._hop -= 1.5
            if self._hop < 0:
                self._hop = 0
        self._apply_position()

    def _apply_position(self, force: bool = False) -> None:
        """根据锚点 + 偏移计算并设置位置（夹在活动范围内）"""
        x = self._base_pos[0] + int(round(self._wander))
        y = self._base_pos[1] + int(round(
            math.sin(self._t * self.BOB_SPEED) * self.BOB_AMP
        )) - int(self._hop)
        left, right, top, bottom = self._allowed_region()
        x = max(left, min(right, x))
        y = max(top, min(bottom, y))
        if force or self.pos().x() != x or self.pos().y() != y:
            self.move(x, y)

    # ------------------------------------------------------------------ #
    # 交互
    # ------------------------------------------------------------------ #
    def mousePressEvent(self, event) -> None:
        """左键单击：跳跃反应"""
        if event.button() == Qt.LeftButton:
            self._hop = self.HOP_POWER
            event.accept()
            return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:
        """右键菜单：回到面板旁 / 隐藏"""
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #FFFFFF; border: 1px solid #E0E0E0; }"
            "QMenu::item { padding: 6px 22px; color: #333333; }"
            "QMenu::item:selected { background: #EAF3FC; color: #4A90E2; }"
        )
        act_back = menu.addAction("回到面板旁")
        act_hide = menu.addAction("隐藏小宠")
        chosen = menu.exec(event.globalPos())
        if chosen == act_back:
            self.anchor()
        elif chosen == act_hide:
            self.hide()
