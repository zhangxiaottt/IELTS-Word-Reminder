# -*- coding: utf-8 -*-
"""桌面小宠模块 - DesktopPet

一只 Q 版双马尾少女（粉色系，与面板背景预设同角色）：
- 默认站在「悬浮面板正下方」（水平居中、贴住下缘），随面板移动/缩放自动跟随
- 支持鼠标拖拽到屏幕任意位置，松开后在该处附近自由活动（自由模式）
- 简单动画（全部平面/2D，无旋转，避免"模子不动"的割裂感）：
    * 上下轻微浮动 + 左右游走（正弦，平滑连贯）
    * 轻微「呼吸」：脚底固定、身体微微收放（替代生硬的整体倾斜）
    * 定时「眨眼」（睁眼帧 ↔ 闭眼帧切换，多帧动画）
    * 点击「跳跃」反应 + 头顶弹出带小尾巴的圆角气泡说出当前单词词义
- 右键菜单：回到面板内 / 隐藏小宠
- 窗口按角色像素生成掩码：透明区域可穿透点击到下层面板
"""
import math
import random

from PySide6.QtCore import Qt, QTimer, QRect, QRectF, QPointF, QPropertyAnimation
from PySide6.QtGui import (
    QPixmap, QPainter, QRegion, QColor, QPen, QFont,
    QPainterPath, QPolygonF,
)
from PySide6.QtWidgets import QApplication, QWidget, QMenu

from .utils import get_asset_path, condense_meaning

# 角色帧路径（透明 PNG）
SPRITE_OPEN = "pets/pet_1.png"          # 睁眼帧
SPRITE_BLINK = "pets/pet_1_blink.png"   # 闭眼（眨眼）帧

# 点击时的气泡文案（词库为空时的兜底）
BUBBLE_TEXTS = [
    "背单词啦！", "加油鸭~", "今天背了吗？", "嘿嘿，我在这儿~",
    "复习时间到！", "学累了就歇会儿~", "你认真的样子真好看~",
]


class _SpeechBubble(QWidget):
    """自绘对话气泡：柔粉色圆角矩形 + 小三角尾巴 + 淡入动画

    柔粉色系与粉色系角色协调，白色文字区、圆润可爱；
    单独顶层窗口，不参与鼠标事件。
    """

    MAX_W = 280      # 最大宽度（像素），超长自动换行
    PAD = 14         # 内边距
    TAIL = 9         # 尾巴高度
    RADIUS = 16      # 圆角半径
    FILL = "#FFF1F4"          # 气泡底色（柔粉白）
    BORDER = "#F2B8C8"        # 描边（柔粉）
    TEXT = "#5A4B4E"          # 文字（暖深灰）

    def __init__(self, parent: QWidget = None):
        super().__init__(
            parent,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            | Qt.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFont(QFont("Microsoft YaHei", 14))
        self._text = ""
        self._tail_down = True   # 尾巴朝下（气泡在宠物上方时指向宠物头部）
        # 淡入动画
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(160)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        # 飘浮动画：出现后像气球轻轻上下飘动
        self._bob_timer = QTimer(self)
        self._bob_timer.timeout.connect(self._bob_tick)
        self._bob_phase = 0.0
        self._base_y = 0
        self.hide()

    def text(self) -> str:
        """当前气泡文字（便于测试/外部读取）"""
        return self._text

    def set_content(self, text: str, tail_down: bool) -> None:
        """设置文字与尾巴方向，并据此计算窗口尺寸"""
        self._text = text
        self._tail_down = tail_down
        fm = self.fontMetrics()
        # 用最大宽度计算换行后的文本包围盒
        rect = fm.boundingRect(
            QRect(0, 0, self.MAX_W - self.PAD * 2, 10000),
            Qt.TextWordWrap, text,
        )
        w = min(self.MAX_W, rect.width() + self.PAD * 2 + 2)
        h = rect.height() + self.PAD * 2 + self.TAIL + 2
        self.setFixedSize(w, h)
        self.update()

    def fade_in(self) -> None:
        """淡入动画（每次显示前调用）"""
        self._fade.stop()
        self._fade.start()

    def float_in(self) -> None:
        """淡入同时开始轻轻上下飘动（气球效果）"""
        self._base_y = self.y()
        self._bob_phase = 0.0
        self._bob_timer.start(33)
        self.fade_in()

    def _bob_tick(self) -> None:
        """每帧更新气泡位置：正弦上下浮动（幅度 5px）"""
        self._bob_phase += 0.18
        dy = round(math.sin(self._bob_phase) * 5)
        self.move(self.x(), self._base_y + dy)

    def hideEvent(self, event) -> None:
        """隐藏时停止飘动并回到基准位置"""
        self._bob_timer.stop()
        if self._base_y:
            self.move(self.x(), self._base_y)
        super().hideEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx = w / 2.0
        body = QRectF(1, 1, w - 2, h - self.TAIL - 1)
        path = QPainterPath()
        path.addRoundedRect(body, self.RADIUS, self.RADIUS)
        # 小三角尾巴（朝下指向宠物，或朝上）
        if self._tail_down:
            tri = QPolygonF([
                QPointF(cx - 8, h - self.TAIL - 2),
                QPointF(cx + 8, h - self.TAIL - 2),
                QPointF(cx, h - 1),
            ])
        else:
            tri = QPolygonF([
                QPointF(cx - 8, self.TAIL + 2),
                QPointF(cx + 8, self.TAIL + 2),
                QPointF(cx, 1),
            ])
        path.addPolygon(tri)
        painter.setPen(QPen(QColor(self.BORDER), 1.2))
        painter.setBrush(QColor(self.FILL))
        painter.drawPath(path)
        # 文字
        text_rect = QRectF(
            self.PAD, self.PAD, w - self.PAD * 2, h - self.TAIL - self.PAD * 2,
        )
        painter.setPen(QColor(self.TEXT))
        painter.drawText(text_rect, Qt.TextWordWrap | Qt.AlignCenter, self._text)
        painter.end()


class DesktopPet(QWidget):
    """桌面小宠"""

    TICK_MS = 33             # 动画刷新间隔（毫秒）
    DISPLAY_H = 228          # 角色显示高度（像素，约面板高度的 3 倍，高分屏自动缩放）
    BOB_AMP = 5              # 上下浮动幅度（像素）
    BOB_SPEED = 0.14         # 浮动角速度
    WANDER_STEP = 1.2        # 每帧游走步长（像素）
    HOP_POWER = 40           # 点击跳跃初始高度（像素）
    BREATH_SPEED = 0.30      # 呼吸动画角速度
    BREATH_AMP = 0.035       # 呼吸缩放幅度（比例）
    MASK_ALPHA = 40          # 掩码阈值：高于该透明度的像素才可交互
    CLICK_MOVE = 5           # 超过该位移视为拖拽（否则视为点击）

    # 不同模式下围绕锚点的活动范围（左/右/上/下 扩展像素）
    DOCK_RANGE = (30, 30, 20, 70)
    FREE_RANGE = (90, 90, 40, 90)

    def __init__(self, config, panel, parent: QWidget = None):
        """初始化桌宠

        Args:
            config: ConfigManager 实例
            panel: FloatPanel 实例（驻留模式下跟随它）
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

        # 帧图
        self._open_pixmap = QPixmap(get_asset_path(SPRITE_OPEN))
        self._blink_pixmap = QPixmap(get_asset_path(SPRITE_BLINK))
        if self._blink_pixmap.isNull():
            self._blink_pixmap = self._open_pixmap  # 无眨眼帧时退化为睁眼
        self._pixmap = self._open_pixmap            # 当前显示帧
        self.setFixedSize(self.DISPLAY_H, self.DISPLAY_H)
        self._build_mask()

        # 动画 / 交互状态
        self._mode = "dock"          # dock=驻留面板 / free=自由活动
        self._t = 0                  # 时间步
        self._wander = 0.0           # 当前水平偏移
        self._target_dx = 0          # 目标水平偏移
        self._hop = 0                # 跳跃高度（逐帧衰减）
        self._breath = 0.0           # 呼吸缩放比例（-Amp ~ +Amp）
        self._base_pos = (0, 0)      # 锚点（左上角）
        self._dragging = False       # 是否正在拖拽
        self._drag_press_global = None
        self._drag_offset = None

        # 气泡（自绘：圆角 + 尾巴）
        self._bubble = _SpeechBubble()

        # 定时器
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self.TICK_MS)

        self._wander_timer = QTimer(self)
        self._wander_timer.timeout.connect(self._pick_target)
        self._wander_timer.start(random.randint(2500, 5000))

        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._do_blink)
        self._blink_timer.start(random.randint(2200, 4200))

    # ------------------------------------------------------------------ #
    # 掩码：透明区域可穿透点击
    # ------------------------------------------------------------------ #
    def _build_mask(self) -> None:
        """按当前显示帧的非透明像素生成窗口掩码

        只有角色实体能接收鼠标，透明处点击穿透到面板。
        """
        if self._pixmap.isNull():
            self.clearMask()
            return
        pm = self._pixmap.scaled(
            self.width(), self.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        img = pm.toImage()
        w, h = img.width(), img.height()
        region = QRegion()
        for y in range(h):
            x0 = -1
            for x in range(w):
                if QColor.fromRgba(img.pixel(x, y)).alpha() > self.MASK_ALPHA:
                    if x0 < 0:
                        x0 = x
                else:
                    if x0 >= 0:
                        region = region.united(QRegion(x0, y, x - x0, 1))
                        x0 = -1
            if x0 >= 0:
                region = region.united(QRegion(x0, y, w - x0, 1))
        self.setMask(region)

    # ------------------------------------------------------------------ #
    # 锚定 / 模式
    # ------------------------------------------------------------------ #
    def anchor(self) -> None:
        """跟随面板重算锚点（仅驻留模式生效；自由模式保持拖拽位置）"""
        if self._mode != "dock":
            return
        if not self._panel.isVisible():
            self.hide()
            return
        g = self._panel.geometry()
        # 驻留：站在面板正下方（水平居中、紧贴面板下缘），随面板移动/缩放
        self._base_pos = (
            g.x() + (g.width() - self.width()) // 2,
            g.y() + g.height() + 6,
        )
        self._wander = 0.0
        self._target_dx = 0
        self._apply_position(force=True)

    def dock_to_panel(self) -> None:
        """回到面板内（驻留模式）"""
        self._mode = "dock"
        self.anchor()

    def _screen(self):
        s = self.screen()
        return s if s else QApplication.primaryScreen()

    def _allowed_region(self) -> tuple:
        """当前模式下锚点周围的活动范围，并夹在屏幕可用区域内

        Returns: (left, right, top, bottom) —— 桌宠左上角允许坐标范围
        """
        ax, ay = self._base_pos
        if self._mode == "dock":
            dl, dr, dt, db = self.DOCK_RANGE
        else:
            dl, dr, dt, db = self.FREE_RANGE
        left, right = ax - dl, ax + dr
        top, bottom = ay - dt, ay + db
        scr = self._screen()
        if scr is not None:
            ag = scr.availableGeometry()
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
        self._target_dx = random.randint(left - ax, right - ax)
        self._wander_timer.start(random.randint(2500, 5000))

    # ------------------------------------------------------------------ #
    # 动画
    # ------------------------------------------------------------------ #
    def _do_blink(self) -> None:
        """切换到闭眼帧，140ms 后恢复睁眼"""
        if not self.isVisible():
            return
        self._pixmap = self._blink_pixmap
        self.update()
        QTimer.singleShot(140, self._end_blink)
        self._blink_timer.start(random.randint(2200, 4200))

    def _end_blink(self) -> None:
        """恢复睁眼帧"""
        self._pixmap = self._open_pixmap
        self.update()

    def _tick(self) -> None:
        """动画主循环：浮动 + 游走 + 呼吸 + 跳跃（无旋转，保持连贯）"""
        self._t += 1
        if not self.isVisible() or not self._panel.isVisible() or self._dragging:
            return
        # 呼吸：正弦缩放比例
        self._breath = math.sin(self._t * self.BREATH_SPEED) * self.BREATH_AMP
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
        self.update()

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

    def paintEvent(self, event) -> None:
        """绘制当前帧：脚底固定做轻微「呼吸」缩放（无旋转，避免割裂感）"""
        if self._pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        # 呼吸：身体纵向轻微收放、横向轻微反向补偿，脚底保持不动
        scale_y = 1.0 + self._breath
        scale_x = 1.0 - self._breath * 0.5
        painter.translate(w / 2.0, h)
        painter.scale(scale_x, scale_y)
        painter.translate(-w / 2.0, -h)
        painter.drawPixmap(0, 0, w, h, self._pixmap)
        painter.end()

    # ------------------------------------------------------------------ #
    # 交互：点击（跳跃+气泡）/ 拖拽（拖到哪就在哪活动）
    # ------------------------------------------------------------------ #
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_press_global = event.globalPosition().toPoint()
            self._drag_offset = self._drag_press_global - self.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and self._drag_offset is not None:
            # 跟随鼠标移动
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            scr = self._screen()
            if scr is not None:
                ag = scr.availableGeometry()
                new_pos.setX(max(ag.x(), min(ag.x() + ag.width() - self.width(), new_pos.x())))
                new_pos.setY(max(ag.y(), min(ag.y() + ag.height() - self.height(), new_pos.y())))
            self.move(new_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            moved = (event.globalPosition().toPoint() - self._drag_press_global).manhattanLength()
            if moved > self.CLICK_MOVE:
                # 拖拽落点：进入自由模式，在落点附近活动
                self._mode = "free"
                self._base_pos = (self.pos().x(), self.pos().y())
                self._wander = 0.0
                self._target_dx = 0
            else:
                # 点击：跳跃 + 冒气泡（说出当前单词词义）
                self._hop = self.HOP_POWER
                self.show_bubble()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def show_bubble(self, text: str = None) -> None:
        """在宠物头顶弹出带尾巴的气泡（1.8 秒后自动消失）

        默认显示「当前单词的词义」（如：apple：n. 苹果）；
        词库为空时显示随机鼓励语。上方放不下时放到宠物下方。
        """
        if text is None:
            row = self._panel.current_word_row()
            if row and (row.get("word") or row.get("meaning")):
                word = row.get("word") or ""
                meaning = condense_meaning(row.get("meaning") or "")
                text = "{}：{}".format(word, meaning) if meaning else word
            else:
                text = random.choice(BUBBLE_TEXTS)
        scr = self._screen()
        ag = scr.availableGeometry() if scr is not None else None
        # 先假设放在宠物上方（尾巴朝下指向头部）
        tail_down = True
        bw = self._bubble.width() or 160
        bh = self._bubble.height() or 50
        x = self.x() + (self.width() - bw) // 2
        y = self.y() - bh - 4
        if ag is not None and y < ag.y() + 4:
            # 上方放不下 → 放到宠物下方，尾巴朝上
            tail_down = False
            y = self.y() + self.height() + 4
        if ag is not None:
            x = max(ag.x() + 4, min(ag.x() + ag.width() - bw - 4, x))
        self._bubble.set_content(text, tail_down)
        # set_content 后尺寸可能变化，重新定位（保持横向居中）
        x = self.x() + (self.width() - self._bubble.width()) // 2
        if ag is not None:
            x = max(ag.x() + 4, min(ag.x() + ag.width() - self._bubble.width() - 4, x))
        if tail_down:
            y = self.y() - self._bubble.height() - 4
        else:
            y = self.y() + self.height() + 4
        self._bubble.move(x, y)
        self._bubble.show()
        self._bubble.raise_()
        self._bubble.float_in()
        QTimer.singleShot(1800, self._bubble.hide)

    def contextMenuEvent(self, event) -> None:
        """右键菜单：回到面板内 / 隐藏小宠"""
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #FFFFFF; border: 1px solid #E0E0E0; }"
            "QMenu::item { padding: 6px 22px; color: #333333; }"
            "QMenu::item:selected { background: #EAF3FC; color: #4A90E2; }"
        )
        act_back = menu.addAction("回到面板内")
        act_hide = menu.addAction("隐藏小宠")
        chosen = menu.exec(event.globalPos())
        if chosen == act_back:
            self.dock_to_panel()
        elif chosen == act_hide:
            self.hide()
            self._bubble.hide()

    def hideEvent(self, event) -> None:
        """隐藏时一并隐藏气泡"""
        self._bubble.hide()
        super().hideEvent(event)
