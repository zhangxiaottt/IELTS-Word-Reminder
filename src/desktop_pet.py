# -*- coding: utf-8 -*-
"""桌面小宠模块 - DesktopPet（立体感 + 多动作版）

一只 Q 版双马尾少女（粉色系，与面板背景预设同角色）。

参考 GitHub 上主流桌宠项目（QtDesktopPet / OpenClaw / DyberPet / Haven 等）的
通用手法，在"单一透明贴图"前提下用程序化动画实现立体感与多动作：
- 状态机：idle / walk / jump / drag 四种状态自动切换
- 地面阴影：一只随跳跃高度缩小变淡的软阴影，提供强烈深度感（"立体"）
- Squash & Stretch（挤压-拉伸）：起跳前压扁、空中拉伸、落地压扁回弹
- 行走：按移动方向水平翻转朝向 + 高频小幅度颠簸，像真的在走
- 反应性视线：光标靠近时她微微朝光标方向侧身（Haven 的 reactive gaze）
- 随机 idle 变体：呼吸 + 眨眼 + 偶尔伸个懒腰
- 说话：自动定时 + 点击触发，内容是"日常话语"（按时段问好、催背单词等），
  不再是点一下报词义

交互：
- 左键拖拽 = 换位置（自由模式，在落点附近活动）；单击 = 跳跃 + 日常话语气泡
- 右键菜单：回到面板内 / 隐藏小宠
- 窗口按角色像素生成掩码：透明区域可穿透点击到下层面板
"""
import math
import random
import datetime

from PySide6.QtCore import Qt, QTimer, QRect, QRectF, QPointF, QPropertyAnimation
from PySide6.QtGui import (
    QPixmap, QPainter, QRegion, QColor, QPen, QFont,
    QPainterPath, QPolygonF, QRadialGradient, QCursor,
)
from PySide6.QtWidgets import QApplication, QWidget, QMenu

from .utils import get_asset_path

# 角色帧路径（透明 PNG）
SPRITE_OPEN = "pets/pet_1.png"          # 睁眼帧
SPRITE_BLINK = "pets/pet_1_blink.png"   # 闭眼（眨眼）帧
# 走路帧序列（同角色不同迈步姿态，已按脚底/中心/体型对齐）
SPRITE_WALK = ("pets/walk_1.png", "pets/walk_2.png", "pets/walk_3.png")

# 日常话语（按时段问好 + 催促背单词 + 可爱闲聊）
MORNING_TEXTS = [
    "早安！今天也要好好背单词呀~",
    "早上好呀，先背两个单词清醒一下？",
    "新的一天，从复习开始吧！",
]
NOON_TEXTS = [
    "午安~吃完饭记得复习一会儿~",
    "中午好，背单词时间到！",
    "午后容易困，背两个单词提提神~",
]
EVENING_TEXTS = [
    "晚上好呀，今天的单词背完了吗？",
    "夜晚最适合背单词啦，加油！",
    "睡前再温习一遍今天的词吧~",
]
NIGHT_TEXTS = [
    "夜深啦，注意休息~",
    "这么晚还在，要加油哦~",
    "熬夜伤身，早点休息呀。",
]
REMIND_TEXTS = [
    "背单词啦！", "复习时间到咯~", "要不要来一局单词测试？",
    "我在这儿陪你~", "摸鱼一分钟，背词一下午~",
    "该复习啦，快回来！", "嘿嘿，记得打卡今天的单词~",
    "休息够了吗？继续吧！",
]


def _daily_phrase() -> str:
    """按当前时段挑一句日常话语（问好或催背单词）"""
    h = datetime.datetime.now().hour
    if h < 6:
        pool = NIGHT_TEXTS
    elif h < 12:
        pool = MORNING_TEXTS
    elif h < 14:
        pool = NOON_TEXTS
    elif h < 18:
        pool = EVENING_TEXTS
    else:
        pool = NIGHT_TEXTS
    # 70% 概率说时段话语，30% 说通用催促
    if random.random() < 0.7:
        return random.choice(pool)
    return random.choice(REMIND_TEXTS)


class _GroundShadow(QWidget):
    """地面软阴影：随跳跃高度缩小变淡，制造深度感

    独立透明窗口，置于宠物脚下地面，不参与鼠标事件。
    """

    def __init__(self, parent: QWidget = None):
        super().__init__(
            parent,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            | Qt.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(120, 22)
        self._scale = 1.0
        self._alpha = 150
        self.hide()

    def set_state(self, scale: float, alpha: int) -> None:
        """更新阴影缩放与不透明度"""
        self._scale = max(0.3, min(1.0, scale))
        self._alpha = max(30, min(200, alpha))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width() * self._scale
        h = 13 * self._scale
        x = (self.width() - w) / 2.0
        y = self.height() - h
        rect = QRectF(x, y, w, h)
        grad = QRadialGradient(x + w / 2.0, y + h / 2.0, max(w, h) / 2.0)
        grad.setColorAt(0.0, QColor(0, 0, 0, self._alpha))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(grad)
        painter.drawEllipse(rect)
        painter.end()


class _SpeechBubble(QWidget):
    """自绘对话气泡：柔粉色圆角矩形 + 小三角尾巴 + 淡入 + 飘浮

    柔粉色系与角色协调，圆润可爱；单独顶层窗口，不参与鼠标事件。
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
        self._tail_down = True
        # 淡入动画
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(160)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        # 飘浮动效：像气球轻轻上下飘动
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
        """淡入 + 开始轻轻上下飘动（气球效果）"""
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
        text_rect = QRectF(
            self.PAD, self.PAD, w - self.PAD * 2, h - self.TAIL - self.PAD * 2,
        )
        painter.setPen(QColor(self.TEXT))
        painter.drawText(text_rect, Qt.TextWordWrap | Qt.AlignCenter, self._text)
        painter.end()


class DesktopPet(QWidget):
    """桌面小宠（状态机 + 程序化多动作）"""

    TICK_MS = 33             # 动画刷新间隔（毫秒）
    DISPLAY_H = 228          # 角色显示高度（像素，高分屏自适应）
    # 待机：呼吸/浮动
    BOB_AMP = 5
    BOB_SPEED = 0.14
    BREATH_SPEED = 0.30
    BREATH_AMP = 0.035
    # 行走：方向翻转 + 高频颠簸
    WALK_FRAME_MS = 150      # 每帧间隔（毫秒）
    WALK_CYCLE = (0, 1, 2, 1)  # 4 拍循环：右步→换步→左步→换步
    WALK_BOB_AMP = 2
    WALK_BOB_SPEED = 0.42
    WANDER_STEP = 1.2
    # 跳跃：抛物线 + 挤压/拉伸
    JUMP_H = 72
    JUMP_TICKS = 44
    LAND_SQUASH = 0.12       # 落地挤压幅度（比例）
    # 反应性视线（光标靠近时侧身）
    GAZE_RADIUS = 240        # 光标在此半径内才反应（像素）
    GAZE_AMP = 8             # 最大侧身偏移（像素）
    MASK_ALPHA = 40
    CLICK_MOVE = 5           # 超过该位移视为拖拽（否则视为点击）

    # 不同模式下围绕锚点的活动范围（左/右/上/下 扩展像素）
    DOCK_RANGE = (30, 30, 20, 70)
    FREE_RANGE = (90, 90, 40, 90)

    def __init__(self, config, panel, parent: QWidget = None):
        super().__init__(
            parent,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,
        )
        self._config = config
        self._panel = panel

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle("雅思小宠")

        # 帧图
        self._open_pixmap = QPixmap(get_asset_path(SPRITE_OPEN))
        self._blink_pixmap = QPixmap(get_asset_path(SPRITE_BLINK))
        if self._blink_pixmap.isNull():
            self._blink_pixmap = self._open_pixmap
        self._walk_pixmaps = []
        for _p in SPRITE_WALK:
            _pm = QPixmap(get_asset_path(_p))
            if not _pm.isNull():
                self._walk_pixmaps.append(_pm)
        if not self._walk_pixmaps:
            self._walk_pixmaps = [self._open_pixmap]
        self._walk_idx = 0
        self._pixmap = self._open_pixmap
        self.setFixedSize(self.DISPLAY_H, self.DISPLAY_H)
        self._build_mask()

        # 状态机与动画状态
        self._mode = "dock"          # dock=驻留面板 / free=自由活动
        self._state = "idle"         # idle / walk / jump / drag
        self._face = 1               # 朝向：1=右 / -1=左
        self._t = 0
        self._wander = 0.0
        self._target_dx = 0
        self._jump_phase = 0.0
        self._land_squash = 0.0      # 落地挤压衰减（0..1）
        self._stretch = 0.0          # 伸懒腰幅度（0..1）
        self._breath = 0.0
        self._base_pos = (0, 0)
        self._dragging = False
        self._drag_press_global = None
        self._drag_offset = None

        # 地面阴影（立体感）
        self._shadow = _GroundShadow()
        self._shadow.move(-1000, -1000)

        # 气泡（日常话语）
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

        # 走路帧循环定时器（走路时切换迈步帧）
        self._walk_timer = QTimer(self)
        self._walk_timer.timeout.connect(self._advance_walk)
        self._walk_timer.setInterval(self.WALK_FRAME_MS)

        self._stretch_timer = QTimer(self)
        self._stretch_timer.timeout.connect(self._start_stretch)
        self._stretch_timer.start(random.randint(9000, 15000))

        # 自动说话（日常话语）
        self._talk_timer = QTimer(self)
        self._talk_timer.timeout.connect(self._auto_talk)
        self._talk_timer.start(random.randint(22000, 38000))

    # ------------------------------------------------------------------ #
    # 掩码
    # ------------------------------------------------------------------ #
    def _build_mask(self) -> None:
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
        if self._mode != "dock":
            return
        if not self._panel.isVisible():
            self.hide()
            return
        g = self._panel.geometry()
        self._base_pos = (
            g.x() + (g.width() - self.width()) // 2,
            g.y() + g.height() + 6,
        )
        self._wander = 0.0
        self._target_dx = 0
        self._apply_position(force=True)
        self._update_shadow()

    def dock_to_panel(self) -> None:
        self._mode = "dock"
        self.anchor()

    def _screen(self):
        s = self.screen()
        return s if s else QApplication.primaryScreen()

    def _allowed_region(self) -> tuple:
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
        ax, _ = self._base_pos
        left, right, _, _ = self._allowed_region()
        self._target_dx = random.randint(left - ax, right - ax)
        self._wander_timer.start(random.randint(2500, 5000))

    # ------------------------------------------------------------------ #
    # 动画：状态机
    # ------------------------------------------------------------------ #
    def _do_blink(self) -> None:
        if not self.isVisible() or self._state == "walk":
            return
        self._pixmap = self._blink_pixmap
        self.update()
        QTimer.singleShot(140, self._end_blink)
        self._blink_timer.start(random.randint(2200, 4200))

    def _end_blink(self) -> None:
        self._pixmap = self._open_pixmap
        self.update()

    def _advance_walk(self) -> None:
        """走路帧循环：按 4 拍切换迈步帧；离开走路状态则停止"""
        if self._state != "walk":
            self._walk_timer.stop()
            return
        self._walk_idx = (self._walk_idx + 1) % len(self.WALK_CYCLE)
        frame = self._walk_pixmaps[
            self.WALK_CYCLE[self._walk_idx] % len(self._walk_pixmaps)
        ]
        if frame is not self._pixmap:
            # 不同迈步姿态帧底形不同，重建掩码避免被剪辑
            self._pixmap = frame
            self._build_mask()
            self.update()

    def _reset_to_base_frame(self) -> None:
        """离开走路状态时切回睁眼基准帧（同时恢复掩码）"""
        if (self._pixmap is not self._open_pixmap
                and self._pixmap is not self._blink_pixmap):
            self._pixmap = self._open_pixmap
            self._build_mask()
            self.update()

    def _start_stretch(self) -> None:
        """偶尔伸个懒腰（小幅纵向拉长，随即恢复）"""
        if self.isVisible() and self._state == "idle":
            self._stretch = 0.05
        self._stretch_timer.start(random.randint(9000, 15000))

    def _start_jump(self) -> None:
        """点击触发跳跃"""
        self._walk_timer.stop()
        self._reset_to_base_frame()
        self._state = "jump"
        self._jump_phase = 0.0

    def _auto_talk(self) -> None:
        """自动说一句日常话语"""
        if self.isVisible() and self._panel.isVisible() and not self._dragging:
            self.show_bubble()
        self._talk_timer.start(random.randint(22000, 38000))

    def _tick(self) -> None:
        """主循环：状态机 + 位置 + 阴影"""
        self._t += 1
        if not self.isVisible() or not self._panel.isVisible() or self._dragging:
            return

        # 呼吸 / 伸懒腰衰减
        self._breath = math.sin(self._t * self.BREATH_SPEED) * self.BREATH_AMP
        if self._stretch > 0:
            self._stretch -= 0.004
            if self._stretch < 0:
                self._stretch = 0

        # 跳跃进度
        if self._state == "jump":
            self._jump_phase += 1.0 / self.JUMP_TICKS
            if self._jump_phase >= 1.0:
                self._jump_phase = 1.0
                self._state = "idle"
                self._land_squash = 1.0  # 落地挤压开始

        # 落地挤压衰减
        if self._land_squash > 0:
            self._land_squash -= 0.08
            if self._land_squash < 0:
                self._land_squash = 0

        # 游走（跳跃时保持水平位移，不更新状态）
        if self._state != "jump":
            dx = self._wander
            if abs(self._target_dx - dx) <= self.WANDER_STEP:
                self._wander = float(self._target_dx)
                self._state = "idle"
            else:
                self._wander += self.WANDER_STEP if self._target_dx > dx else -self.WANDER_STEP
                self._state = "walk"
                # 朝向：按移动方向翻转
                self._face = 1 if self._target_dx >= self._wander else -1

        # 走路帧管理：走路时启动迈步循环，否则恢复睁眼帧
        if self._state == "walk":
            if not self._walk_timer.isActive():
                self._walk_timer.start()
                # 进入走路立即切到第一帧迈步（不等定时器首次触发，反应更快）
                self._walk_idx = 0
                self._pixmap = self._walk_pixmaps[
                    self.WALK_CYCLE[0] % len(self._walk_pixmaps)
                ]
                self._build_mask()
                self.update()
        else:
            if self._walk_timer.isActive():
                self._walk_timer.stop()
            self._reset_to_base_frame()

        self._apply_position()
        self._update_shadow()
        self.update()

    def _apply_position(self, force: bool = False) -> None:
        """根据锚点 + 状态计算位置（跳跃时抬升、夹在活动范围内）"""
        x = self._base_pos[0] + int(round(self._wander))
        # 待机浮动 / 行走颠簸 / 跳跃高度
        if self._state == "jump":
            y = self._base_pos[1] - int(round(
                math.sin(math.pi * self._jump_phase) * self.JUMP_H
            ))
        elif self._state == "walk":
            y = self._base_pos[1] + int(round(
                math.sin(self._t * self.WALK_BOB_SPEED) * self.WALK_BOB_AMP
            ))
        else:
            y = self._base_pos[1] + int(round(
                math.sin(self._t * self.BOB_SPEED) * self.BOB_AMP
            ))
        left, right, top, bottom = self._allowed_region()
        x = max(left, min(right, x))
        if self._state == "jump":
            # 跳跃允许越过活动区上界，仅受屏幕顶部限制
            scr = self._screen()
            top_lim = scr.availableGeometry().y() if scr is not None else -99999
            y = max(top_lim, y)
        else:
            y = max(top, min(bottom, y))
        if force or self.pos().x() != x or self.pos().y() != y:
            self.move(x, y)

    def _update_shadow(self) -> None:
        """地面阴影跟随宠物水平位置，跳跃时缩小变淡"""
        ground_y = self._base_pos[1] + self.height() - 2
        sx = self.x() + self.width() / 2.0 - self._shadow.width() / 2.0
        sy = ground_y - self._shadow.height() + 3
        self._shadow.move(round(sx), round(sy))
        if self._state == "jump":
            h = math.sin(math.pi * self._jump_phase)  # 0..1
            self._shadow.set_state(1.0 - 0.45 * h, 150 - int(100 * h))
        else:
            self._shadow.set_state(1.0, 150)
        self._shadow.show()

    def paintEvent(self, event) -> None:
        """绘制当前帧：朝向翻转 + 挤压拉伸 + 反应性视线（无旋转）"""
        if self._pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()

        # 反应性视线：光标靠近时微微侧身（水平平移，不出掩码范围）
        gaze = 0.0
        cur = QCursor.pos()
        center_x = self.x() + w / 2.0
        rel = cur.x() - center_x
        if abs(rel) < self.GAZE_RADIUS:
            gaze = (rel / self.GAZE_RADIUS) * self.GAZE_AMP

        # 纵向挤压/拉伸（脚底固定）
        if self._state == "jump":
            p = self._jump_phase
            if p < 0.12:      # 起跳挤压 → 回弹
                t = p / 0.12
                sy = 0.85 + 0.15 * t
                sx = 1.12 - 0.12 * t
            elif p < 0.88:    # 空中拉伸
                t = (p - 0.12) / 0.76
                st = math.sin(math.pi * t) * 0.08
                sy = 1.0 + st
                sx = 1.0 - st * 0.8
            else:             # 落地挤压
                t = (p - 0.88) / 0.12
                sy = 1.0 - 0.10 * t
                sx = 1.0 + 0.12 * t
        elif self._land_squash > 0:   # 落地余震
            sy = 1.0 - self.LAND_SQUASH * self._land_squash
            sx = 1.0 + self.LAND_SQUASH * 1.3 * self._land_squash
        else:                 # 呼吸 + 伸懒腰
            sy = 1.0 + self._breath + self._stretch
            sx = 1.0 - self._breath * 0.5 - self._stretch * 0.6

        painter.translate(w / 2.0, h)
        painter.scale(sx, sy)
        if self._face < 0:
            painter.scale(-1.0, 1.0)   # 朝左：水平翻转
        painter.translate(-w / 2.0 + gaze * self._face, -h)
        painter.drawPixmap(0, 0, w, h, self._pixmap)
        painter.end()

    # ------------------------------------------------------------------ #
    # 交互
    # ------------------------------------------------------------------ #
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._walk_timer.stop()
            self._reset_to_base_frame()
            self._dragging = True
            self._state = "drag"
            self._drag_press_global = event.globalPosition().toPoint()
            self._drag_offset = self._drag_press_global - self.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and self._drag_offset is not None:
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
                self._state = "idle"
            else:
                # 单击：跳跃 + 说一句日常话语
                self._start_jump()
                self.show_bubble()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------ #
    # 说话（日常话语）
    # ------------------------------------------------------------------ #
    def show_bubble(self, text: str = None) -> None:
        """在宠物头顶弹出带尾巴的气泡（1.8 秒后自动消失）

        默认说一句「日常话语」：按时段问好 / 催促背单词 / 可爱闲聊。
        """
        if text is None:
            text = _daily_phrase()
        scr = self._screen()
        ag = scr.availableGeometry() if scr is not None else None
        tail_down = True
        bw = self._bubble.width() or 160
        bh = self._bubble.height() or 50
        x = self.x() + (self.width() - bw) // 2
        y = self.y() - bh - 4
        if ag is not None and y < ag.y() + 4:
            tail_down = False
            y = self.y() + self.height() + 4
        if ag is not None:
            x = max(ag.x() + 4, min(ag.x() + ag.width() - bw - 4, x))
        self._bubble.set_content(text, tail_down)
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
            self._shadow.hide()

    def hideEvent(self, event) -> None:
        self._bubble.hide()
        self._shadow.hide()
        super().hideEvent(event)
