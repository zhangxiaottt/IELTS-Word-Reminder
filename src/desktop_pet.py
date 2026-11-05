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
    QPixmap, QPainter, QRegion, QColor, QPen, QFont, QImage,
    QPainterPath, QPolygonF, QRadialGradient, QLinearGradient, QCursor,
)
from PySide6.QtWidgets import QApplication, QWidget, QMenu

from .utils import get_asset_path

# 角色帧路径（透明 PNG）
SPRITE_OPEN = "pets/pet_1.png"          # 睁眼帧
SPRITE_BLINK = "pets/pet_1_blink.png"   # 闭眼（眨眼）帧
# 走路迈步帧（左右腿交替前迈，已按脚底/中心/体型对齐）
# 站姿用 walk_base，与迈步帧拼成 4 拍循环：左迈 → 经过 → 右迈 → 经过
# 原先的 walk_1（跨步过大）/ walk_2（双腿交叉）已弃用，不再引用
SPRITE_WALK = ("pets/walk_left.png", "pets/walk_right.png")
# 待机小动作为从精灵表切分出来的 4 个 pose：挥手 / 叉腰 / 捧脸 / 闭眼放松
SPRITE_IDLE_POSES = (
    "pets/idle_wave.png",
    "pets/idle_hips.png",
    "pets/idle_giggle.png",
    "pets/idle_relax.png",
)

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
        """双层地面投影：外层柔和扩散影 + 内层接触硬影

        单层椭圆像"贴纸浮在桌面"，加了紧贴脚底的接触影才有真正踩地的重量感。
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width() * self._scale
        h = 13 * self._scale
        x = (self.width() - w) / 2.0
        y = self.height() - h
        painter.setPen(Qt.NoPen)

        # 外层：大范围柔和扩散影
        grad = QRadialGradient(x + w / 2.0, y + h / 2.0, max(w, h) / 2.0)
        grad.setColorAt(0.0, QColor(0, 0, 0, int(self._alpha * 0.55)))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(grad)
        painter.drawEllipse(QRectF(x, y, w, h))

        # 内层：紧贴脚底的接触硬影，锚定"踩在地上"
        contact = QRectF(x + w * 0.22, y + h * 0.44, w * 0.56, h * 0.44)
        grad2 = QRadialGradient(
            contact.center(), max(contact.width(), contact.height()) / 2.0
        )
        grad2.setColorAt(0.0, QColor(35, 20, 30, min(210, self._alpha)))
        grad2.setColorAt(1.0, QColor(35, 20, 30, 0))
        painter.setBrush(grad2)
        painter.drawEllipse(contact)
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

    TICK_MS = 16             # 动画刷新间隔（毫秒，60fps）
    DISPLAY_H = 228          # 角色显示高度（像素，高分屏自适应）
    # 待机：呼吸/浮动（速度按 tick 换算，已随 60fps 重新标定）
    BOB_AMP = 4
    BOB_SPEED = 0.068        # rad/tick ≈ 4.2 rad/s
    BREATH_SPEED = 0.146
    BREATH_AMP = 0.024
    # 行走：4 拍循环（触地 → 经过 → 触地 → 经过）
    # 不用帧间交叉淡化：两张不同腿位半透明叠加会短暂出现"四条腿/交叉腿"，
    # 这正是旧版被嫌"摆腿奇怪"的观感来源；改为每拍落地压缩一下代替。
    # 索引含义与 _walk_frames 对应：0=站姿(经过帧) 1=左腿前迈 2=右腿前迈
    WALK_ORDER = (1, 0, 2, 0)
    # 每拍的额外纵向压缩：触地拍承重下沉，经过拍回弹
    WALK_SQUASH = (0.018, 0.0, 0.018, 0.0)
    FRAME_STEP_PX = 8.0      # 一拍对应的地面位移，用于把换帧节奏和移动速度锁死（防滑步）
    WALK_BOB_AMP = 3         # 每拍起伏幅度（像素）
    WALK_LEAN_AMP = 2.5      # 重心左右摆动幅度（像素）
    SWAY_MAX = 5.0           # 头发/裙摆的滞后摆动最大偏移（像素）
    MASK_PAD = 10            # 窗口掩码向外膨胀（像素），避免重心偏差/阴影被裁切
    MASK_VPAD = 10           # 掩码纵向膨胀：氛围光晕在头顶/脚下发光，不膨胀会被硬裁掉
    SPRITE_FIT = 0.95        # 角色在窗口内缩到 95%：给跳跃/伸懒腰留出头顶余量，避免被窗口上边裁切
    SHADOW_DX = 2            # 角色自阴影右下偏移
    SHADOW_DY = 3
    SHADOW_ALPHA = 0.12      # 自阴影不透明度（过重会把角色压成灰边）
    WANDER_STEP = 0.85       # 像素/tick（约 53 px/s）
    # 巡逻模式：沿屏幕底部自己来回走，用侧身帧
    PATROL_SPEED = 1.0       # 像素/tick（约 63 px/s）
    PATROL_FRAME_STEP_PX = 9.0   # 侧身一拍的位移，同样用于锁节奏
    # 跳跃：抛物线 + 挤压/拉伸
    JUMP_H = 72
    JUMP_TICKS = 44          # 44 tick × 16ms ≈ 0.7s
    LAND_SQUASH = 0.12       # 落地挤压幅度（比例）
    # 反应性视线（光标靠近时侧身）
    GAZE_RADIUS = 240        # 光标在此半径内才反应（像素）
    GAZE_AMP = 8             # 最大侧身偏移（像素）
    GAZE_EASE = 0.18         # 视线缓动系数（越小越柔和）
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
        # 待机小 pose（挥手/叉腰/捧脸/闭眼），随机出现几秒
        self._idle_pixmaps = []
        for _p in SPRITE_IDLE_POSES:
            _pm = QPixmap(get_asset_path(_p))
            if not _pm.isNull():
                self._idle_pixmaps.append(_pm)
        # 侧身帧（巡逻模式用）：只载朝右版，朝左由 paintEvent 按 _face 水平翻转
        self._side_frames = {
            "stand": QPixmap(get_asset_path("pets/side_stand_r.png")),
            "walk":  QPixmap(get_asset_path("pets/side_walk_r.png")),
        }
        # 站姿（经过帧）：优先用专门的 walk_base，缺失时退回睁眼帧
        _wbase = QPixmap(get_asset_path("pets/walk_base.png"))
        if _wbase.isNull():
            _wbase = self._open_pixmap
        if len(self._walk_pixmaps) < 2:
            self._walk_pixmaps = [self._open_pixmap, self._open_pixmap]
        # 行走帧池（含经过帧）：0=经过 1=左迈 2=右迈
        self._walk_pixmaps = list(self._walk_pixmaps[:2]) + [_wbase]
        self._walk_frames = [_wbase, self._walk_pixmaps[0], self._walk_pixmaps[1]]
        self._walk_idx = 0
        self._pixmap = self._open_pixmap
        # 待机基准帧（可能是某个小 pose，眨眼/恢复都回到它）
        self._idle_frame = self._open_pixmap
        # 换帧只替换贴图，不叠加半透明混合（避免双腿重影）
        self._frame_elapsed = 0.0
        self._walk_interval = 150.0
        # 预缩放缓存：1024 原图 → 屏幕逻辑尺寸(+DPR)，每帧不再重复缩放
        self._dpr = QApplication.primaryScreen().devicePixelRatio() if \
            QApplication.primaryScreen() is not None else 1.0
        self._scale_cache = {}
        # 剪影缓存（角色自阴影用）：cacheKey -> QPixmap
        self._sil_cache = {}
        self.setFixedSize(self.DISPLAY_H, self.DISPLAY_H)
        self._build_mask()

        # 状态机与动画状态
        self._mode = "dock"          # dock=驻留面板 / free=落点附近 / patrol=沿屏幕底部来回走
        self._patrol_dir = 1          # 巡逻方向：1=向右 / -1=向左
        self._state = "idle"         # idle / walk / jump / drag
        self._face = 1               # 朝向：1=右 / -1=左
        self._t = 0
        self._wander = 0.0
        self._target_dx = 0
        self._jump_phase = 0.0
        self._land_squash = 0.0      # 落地挤压衰减（0..1）
        self._stretch = 0.0          # 伸懒腰幅度（0..1）
        self._breath = 0.0
        self._gaze = 0.0             # 视线偏移（缓动后）
        self._pose_pop = 0.0         # 换姿势/停步时的弹性挤压（0..1）
        self._turn = 0.0             # 转身挤压（0..1）：横向压扁再回弹，模拟绕竖轴转身
        self._last_face = 1
        self._sway = 0.0             # 头发/裙摆滞后偏移（2.5D 形变用）
        self._look_target = 0.0       # 自主视线目标（-1..1，光标不在附近时用）
        self._look_bias = 0.0         # 缓动后的自主视线
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

        # 自主视线：光标不在附近时，隔几秒自己换个方向看看
        self._look_timer = QTimer(self)
        self._look_timer.timeout.connect(self._pick_look)
        self._look_timer.start(random.randint(3500, 6000))

        # 走路帧循环定时器（走路时切换迈步帧）
        self._walk_timer = QTimer(self)
        self._walk_timer.timeout.connect(self._advance_walk)
        self._walk_timer.setInterval(self._beat_interval())

        self._stretch_timer = QTimer(self)
        self._stretch_timer.timeout.connect(self._start_stretch)
        self._stretch_timer.start(random.randint(9000, 15000))

        # 待机时随机摆一个 pose（挥手/叉腰/捧脸/闭眼），几秒后回到站姿
        self._pose_timer = QTimer(self)
        self._pose_timer.timeout.connect(self._maybe_switch_pose)
        self._pose_timer.start(random.randint(14000, 24000))

        # 自动说话（日常话语）
        self._talk_timer = QTimer(self)
        self._talk_timer.timeout.connect(self._auto_talk)
        self._talk_timer.start(random.randint(22000, 38000))

    # ------------------------------------------------------------------ #
    # 掩码
    # ------------------------------------------------------------------ #
    def _all_frames(self) -> list:
        """所有会用到的动作帧（用于生成统一的窗口掩码）"""
        frames = []
        for pm in (self._open_pixmap, self._blink_pixmap):
            if pm is not None and not pm.isNull():
                frames.append(pm)
        for pm in self._walk_pixmaps:
            if pm is not None and not pm.isNull():
                frames.append(pm)
        for pm in self._idle_pixmaps:
            if pm is not None and not pm.isNull():
                frames.append(pm)
        for pm in self._side_frames.values():
            if pm is not None and not pm.isNull():
                frames.append(pm)
        return frames or [self._pixmap]

    def _row_region(self, x0: int, x1: int, y: int, w: int) -> QRegion:
        """单行不透明区间 + 左右膨胀（膨胀量不超过窗口边界）"""
        left = max(0, x0 - self.MASK_PAD)
        right = min(w - 1, x1 + self.MASK_PAD)
        return QRegion(left, y, right - left + 1, 1)

    def _build_mask(self) -> None:
        """按所有动作帧的透明轮廓并集生成窗口掩码，并向外膨胀 MASK_PAD

        用并集而不是逐帧重建：换帧不再重算掩码（省开销、轮廓不抖），
        膨胀后重心摆动 / 视线偏移 / 自阴影都不会被窗口裁切。
        """
        if self._pixmap.isNull():
            self.clearMask()
            return
        w, h = self.width(), self.height()
        region = QRegion()
        for pm in self._all_frames():
            img = pm.scaled(
                w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ).toImage()
            iw, ih = img.width(), img.height()
            for y in range(ih):
                x0 = -1
                for x in range(iw):
                    if QColor.fromRgba(img.pixel(x, y)).alpha() > self.MASK_ALPHA:
                        if x0 < 0:
                            x0 = x
                    else:
                        if x0 >= 0:
                            region = region.united(self._row_region(x0, x - 1, y, w))
                            x0 = -1
                if x0 >= 0:
                    region = region.united(self._row_region(x0, iw - 1, y, w))
        # 纵向膨胀：轮廓只占角色所在的行，氛围光晕与高光会向上/向下溢出，
        # 不把掩码上下各撑开一段，光晕就会被切成一条生硬的直边。
        if self.MASK_VPAD > 0:
            grown = QRegion()
            for dy in range(-self.MASK_VPAD, self.MASK_VPAD + 1):
                grown = grown.united(region.translated(0, dy))
            region = grown
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

    def start_patrol(self) -> None:
        """进入巡逻模式：脱离面板，沿屏幕底部自己来回走"""
        scr = self._screen()
        ag = scr.availableGeometry() if scr is not None else None
        self._wander_timer.stop()
        self._mode = "patrol"
        self._patrol_dir = 1
        self._face = 1
        self._wander = 0.0
        self._target_dx = 0
        if ag is not None:
            self._base_pos = (
                self.x(),
                ag.y() + ag.height() - self.height() - 4,
            )
        self._state = "idle"
        self._apply_position(force=True)
        self._update_shadow()

    def _screen(self):
        s = self.screen()
        return s if s else QApplication.primaryScreen()

    def _allowed_region(self) -> tuple:
        ax, ay = self._base_pos
        scr = self._screen()
        if self._mode == "patrol":
            # 巡逻：y 固定贴屏幕底部，x 在全屏幕范围内
            ag = scr.availableGeometry() if scr is not None else None
            if ag is not None:
                left = ag.x()
                right = ag.x() + ag.width() - self.width()
                bottom = ag.y() + ag.height() - self.height() - 4
                top = bottom - 16   # 允许走路起伏不超过 16px
            else:
                left, right, top, bottom = ax - 500, ax + 500, ay - 10, ay + 10
            return left, right, top, bottom
        if self._mode == "dock":
            dl, dr, dt, db = self.DOCK_RANGE
        else:
            dl, dr, dt, db = self.FREE_RANGE
        left, right = ax - dl, ax + dr
        top, bottom = ay - dt, ay + db
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

    def _pick_look(self) -> None:
        """随机决定下一次自主视线方向：多数时间看正前方，偶尔左右瞥一眼"""
        self._look_target = random.choice(
            (0.0, 0.0, 0.0, -0.7, 0.7, -1.0, 1.0)
        )
        self._look_timer.start(random.randint(3200, 6500))

    # ------------------------------------------------------------------ #
    # 动画：状态机
    # ------------------------------------------------------------------ #
    def _do_blink(self) -> None:
        """眨眼：随机闭合时长 + 25% 连眨两下，且不打断当前待机 pose"""
        if not self.isVisible() or self._state != "idle" or self._dragging:
            self._blink_timer.start(random.randint(2200, 4200))
            return
        self._pixmap = self._blink_pixmap
        self.update()
        close_ms = random.randint(80, 130)
        QTimer.singleShot(close_ms, self._end_blink)
        if random.random() < 0.25:
            QTimer.singleShot(close_ms + random.randint(60, 110), self._second_blink)
        self._blink_timer.start(random.randint(2200, 4200))

    def _second_blink(self) -> None:
        """连眨的第二下（只在仍待机时生效）"""
        if self.isVisible() and self._state == "idle":
            self._pixmap = self._blink_pixmap
            self.update()
            QTimer.singleShot(random.randint(70, 110), self._end_blink)

    def _end_blink(self) -> None:
        # 回到「当前待机基准帧」而不是固定的睁眼帧，避免把 pose 吃掉
        self._pixmap = self._idle_frame
        self.update()

    def _advance_walk(self) -> None:
        """走路帧循环

        - dock/free 模式：正面 4 拍（左迈 → 经过 → 右迈 → 经过）
        - patrol 模式：侧身 2 拍（stand → walk 交替），根据朝向翻转
        """
        if self._state != "walk":
            self._walk_timer.stop()
            return
        if self._mode == "patrol":
            self._walk_idx = (self._walk_idx + 1) % 2
            frame = "walk" if self._walk_idx == 1 else "stand"
            self._pixmap = self._side_frames[frame]
        else:
            self._walk_idx = (self._walk_idx + 1) % len(self.WALK_ORDER)
            self._pixmap = self._walk_frames[self.WALK_ORDER[self._walk_idx]]
        self._frame_elapsed = 0.0
        self.update()

    def _beat_interval(self) -> int:
        """按「一拍位移 ÷ 移动速度」算出换帧间隔，让脚步和地面位移严格同步（防滑步）"""
        if self._mode == "patrol":
            speed, step = self.PATROL_SPEED, self.PATROL_FRAME_STEP_PX
        else:
            speed, step = self.WANDER_STEP, self.FRAME_STEP_PX
        px_per_ms = max(0.001, speed / float(self.TICK_MS))
        return int(max(90, min(300, step / px_per_ms)))

    def _reset_to_base_frame(self) -> None:
        """离开走路状态时切回基准帧（patrol 模式用侧身站姿，其余回当前待机帧）"""
        if self._mode == "patrol":
            target = self._side_frames["stand"]
        else:
            target = self._idle_frame
        if self._pixmap is not target:
            self._pixmap = target
            self._pose_pop = max(self._pose_pop, 0.55)   # 停步时轻微回弹，避免硬切
            self.update()

    def _start_stretch(self) -> None:
        """偶尔伸个懒腰（小幅纵向拉长，随即恢复）"""
        if self.isVisible() and self._state == "idle":
            self._stretch = 0.05
        self._stretch_timer.start(random.randint(9000, 15000))

    def _maybe_switch_pose(self) -> None:
        """待机时随机摆一个小 pose（挥手/叉腰/捧脸/闭眼），几秒后回站姿"""
        if self.isVisible() and self._state == "idle" and self._idle_pixmaps and self._mode != "patrol":
            self._idle_frame = random.choice(self._idle_pixmaps)
            self._pixmap = self._idle_frame
            self._pose_pop = 1.0     # 换姿势时弹一下，掩盖帧之间的硬切
            self.update()
            # 4-6 秒后自动回到默认站姿（由 singleShot 触发）
            QTimer.singleShot(random.randint(4000, 6000), self._reset_idle_pose)
        self._pose_timer.start(random.randint(14000, 24000))

    def _reset_idle_pose(self) -> None:
        """从随机 pose 回到默认站姿（仅当仍处于 idle 时）"""
        if self._state == "idle":
            self._idle_frame = self._open_pixmap
            self._pixmap = self._open_pixmap
            self._pose_pop = 0.8
            self.update()

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

        # 呼吸 / 伸懒腰衰减（呼吸速度做极慢的微调，避免机械的等周期起伏）
        breath_speed = self.BREATH_SPEED * (
            1.0 + 0.10 * math.sin(self._t * 0.0035)
        )
        self._breath = math.sin(self._t * breath_speed) * self.BREATH_AMP
        if self._stretch > 0:
            self._stretch -= 0.008
            if self._stretch < 0:
                self._stretch = 0
        # 换姿势 / 停步的弹性挤压衰减
        if self._pose_pop > 0:
            self._pose_pop = max(0.0, self._pose_pop - 0.09)
        # 转身挤压衰减（约 160ms 内横向压扁再回弹）
        if self._turn > 0:
            self._turn = max(0.0, self._turn - 0.09)
        # 头发/裙摆惯性：向移动的反方向滞后摆动（越靠上越明显，脚底不动）
        sway_target = self._gaze * 0.5
        if self._state == "walk":
            sway_target += 2.2 * self._face
        elif self._state == "idle":
            # 待机时靠呼吸带动上半身极慢地晃，避免站着像一张静止贴纸；
            # 再叠一层几秒周期的左右重心转移，人才会"自己站着"而不是定住
            sway_target += math.sin(self._t * self.BOB_SPEED * 0.8) * 1.3
            sway_target += math.sin(self._t * 0.021) * 1.5
        sway_target = max(-self.SWAY_MAX, min(self.SWAY_MAX, sway_target))
        self._sway += (sway_target - self._sway) * 0.14

        # 反应性视线：朝光标侧身，做缓动避免"瞬移"式跳变
        rel = QCursor.pos().x() - (self.x() + self.width() / 2.0)
        target_gaze = 0.0
        if abs(rel) < self.GAZE_RADIUS:
            target_gaze = (rel / float(self.GAZE_RADIUS)) * self.GAZE_AMP
        elif self._state == "idle":
            # 光标不在附近：自己偶尔左右看看，让待机不再是一张固定的脸
            target_gaze = self._look_bias * self.GAZE_AMP * 0.8
        self._gaze += (target_gaze - self._gaze) * self.GAZE_EASE
        self._look_bias += (self._look_target - self._look_bias) * 0.06

        # 当前拍内进度（驱动上下起伏与重心摆动）
        if self._state == "walk":
            self._frame_elapsed += self.TICK_MS

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
        if self._mode == "patrol" and self._state != "jump":
            # 巡逻模式：持续水平移动，到屏幕边缘转向并短暂停顿
            self._wander += self.PATROL_SPEED * self._patrol_dir
            left, right, _, _ = self._allowed_region()
            ax = self._base_pos[0]
            if self._wander <= left - ax:
                self._wander = float(left - ax)
                self._patrol_dir = 1
                self._face = 1
                self._state = "idle"
            elif self._wander >= right - ax:
                self._wander = float(right - ax)
                self._patrol_dir = -1
                self._face = -1
                self._state = "idle"
            else:
                self._state = "walk"
                self._face = self._patrol_dir
        elif self._state != "jump":
            dx = self._wander
            if abs(self._target_dx - dx) <= self.WANDER_STEP:
                self._wander = float(self._target_dx)
                self._state = "idle"
            else:
                self._wander += self.WANDER_STEP if self._target_dx > dx else -self.WANDER_STEP
                self._state = "walk"
                # 朝向：按移动方向翻转
                self._face = 1 if self._target_dx >= self._wander else -1

        # 朝向改变 → 触发一次转身挤压（视觉上像绕竖轴转过来，而不是瞬间镜像）
        if self._face != self._last_face:
            self._last_face = self._face
            if self._state != "jump":
                self._turn = 1.0

        # 走路帧管理：走路时启动迈步循环，否则恢复睁眼帧
        if self._state == "walk":
            if not self._walk_timer.isActive():
                interval = self._beat_interval()
                self._walk_interval = float(interval)
                self._walk_timer.setInterval(interval)
                self._walk_timer.start()
                # 进入走路立即切到迈步帧（不等定时器首次触发，反应更快）
                self._walk_idx = 0
                self._frame_elapsed = 0.0
                if self._mode == "patrol":
                    self._pixmap = self._side_frames["stand"]
                else:
                    self._pixmap = self._walk_frames[self.WALK_ORDER[0]]
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
            # 每拍独立起伏：脚步落地时最低、抬腿到中段最高，与换帧严格同步
            p = min(1.0, self._frame_elapsed / max(1.0, self._walk_interval))
            amp = self.WALK_BOB_AMP
            y = self._base_pos[1] + int(round(-abs(math.sin(math.pi * p)) * amp))
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
        # 阴影随光源反向偏移：身体左倾时影子略偏右，贴合方向光
        sx = (self.x() + self.width() / 2.0 - self._shadow.width() / 2.0
              - self._gaze * 0.6)
        sy = ground_y - self._shadow.height() + 3
        self._shadow.move(round(sx), round(sy))
        if self._state == "jump":
            h = math.sin(math.pi * self._jump_phase)  # 0..1
            self._shadow.set_state(1.0 - 0.45 * h, 150 - int(100 * h))
        elif self._state == "walk":
            # 与步频同步：抬腿腾空瞬间影子收窄变淡，触地拍最宽最深
            p = min(1.0, self._frame_elapsed / max(1.0, self._walk_interval))
            air = abs(math.sin(math.pi * p))
            self._shadow.set_state(1.0 - 0.10 * air, 150 - int(22 * air))
        else:
            self._shadow.set_state(1.0, 150)
        self._shadow.show()

    def _scaled(self, pm: QPixmap) -> QPixmap:
        """取屏幕尺寸的预缩放帧（按 DPR 生成一次，之后每帧直接复用）

        原实现每帧把 1024 原图缩放一次，60fps 下非常吃 CPU；
        这里在首次使用时缩放到显示尺寸并缓存，绘制时零缩放开销。
        """
        if pm is None or pm.isNull():
            return pm
        dpr = self._dpr
        size = int(round(self.DISPLAY_H * dpr))
        key = (pm.cacheKey(), size)
        hit = self._scale_cache.get(key)
        if hit is not None:
            return hit
        sp = pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        sp.setDevicePixelRatio(dpr)
        if len(self._scale_cache) > 64:
            self._scale_cache.clear()
        self._scale_cache[key] = sp
        return sp

    def _draw_warped(self, painter, pm: QPixmap, w: float, h: float) -> None:
        """2.5D 形变：以脚底为锚点的整体横向剪切

        这里用仿射剪切（shear）替代"切条逐条错位"：数学效果等价 ——
        越靠上横向偏移越大、脚底固定不动，但整张图只画一次，
        不会在条带边界因为取整/高 DPI 抗锯齿漏出横向缝隙（那条缝
        叠在透明窗口上就是一条条小黑线）。
        """
        sway = self._sway
        if abs(sway) < 0.35:
            painter.drawPixmap(0, 0, pm)
            return
        # x' = x + (sway/h)*y - sway：y=0（头顶）偏移 -sway，y=h（脚底）偏移 0
        painter.translate(-sway, 0)
        painter.shear(sway / float(h), 0)
        painter.drawPixmap(0, 0, pm)

    def _silhouette(self, pm: QPixmap) -> QPixmap:
        """生成角色剪影（保留原 alpha、填充深色），用于角色自阴影

        基于已缩放到显示尺寸的帧生成，避免每帧染一遍 1024 原图；
        结果按 pixmap 缓存。
        """
        key = (pm.cacheKey(), pm.width())
        hit = self._sil_cache.get(key)
        if hit is not None:
            return hit
        img = pm.toImage().convertToFormat(QImage.Format_ARGB32)
        p = QPainter(img)
        # SourceIn：把不透明像素整体染成深色，保留原轮廓与抗锯齿边
        p.setCompositionMode(QPainter.CompositionMode_SourceIn)
        p.fillRect(img.rect(), QColor(46, 26, 40))
        p.end()
        sil = QPixmap.fromImage(img)
        sil.setDevicePixelRatio(pm.devicePixelRatio())
        if len(self._sil_cache) > 64:
            self._sil_cache.clear()
        self._sil_cache[key] = sil
        return sil

    def paintEvent(self, event) -> None:
        """绘制角色：动态光源 + 边缘浮雕 + 方向性环境光 + 高光

        「立体」不靠贴图，而靠逐帧光影：
        1) 投影（随光源方向偏移）  2) 亮边浮雕（迎光面高光描边）
        3) 本体                    4) 方向性环境光（迎光面亮、背光面暗）
        5) 面部/肩部高光（随光标位置移动）
        光源方向由光标位置驱动，转动视角时明暗随动，才有真正的体积感。
        """
        if self._pixmap.isNull():
            return

        # 跨屏拖动导致 DPR 变化时，重建预缩放与剪影缓存
        dpr = self.devicePixelRatioF() or 1.0
        if abs(dpr - self._dpr) > 0.01:
            self._dpr = dpr
            self._scale_cache.clear()
            self._sil_cache.clear()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        frame = self._scaled(self._pixmap)

        # ---- 光源方向（-1..1）：光标在左则光从左来，投影向右 ----
        cur = QCursor.pos()
        lx = max(-1.0, min(1.0, (cur.x() - (self.x() + w / 2.0)) / 420.0))
        ly = max(-1.0, min(1.0, (cur.y() - (self.y() + h / 2.0)) / 420.0))

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
            # 呼吸只保留很轻的整体纵向缩放：幅度大了会变成"橡皮人"，
            # 立绘没有骨骼，靠光影和剪切来体现体积更稳
            sy = 1.0 + self._breath * 0.45 + self._stretch
            sx = 1.0 - self._breath * 0.3 - self._stretch * 0.6

        # 换姿势/停步的弹性挤压（掩盖硬切）
        if self._pose_pop > 0:
            sy *= 1.0 - 0.05 * self._pose_pop
            sx *= 1.0 + 0.06 * self._pose_pop
        # 转身：横向压扁再回弹（绕竖轴旋转的透视错觉），压扁时略拉高
        if self._turn > 0:
            sx *= 1.0 - 0.45 * self._turn
            sy *= 1.0 + 0.04 * self._turn

        # 行走：每拍落地压缩（承重下沉）+ 重心摆动 + 轻微侧倾
        lean = 0.0
        rot = self._breath * 6.0      # 待机时随呼吸极轻微摆动（不到 1 度）
        if self._state == "walk":
            p = min(1.0, self._frame_elapsed / max(1.0, self._walk_interval))
            step = self.WALK_ORDER[self._walk_idx]
            direction = -1.0 if step == 1 else (1.0 if step == 2 else 0.0)
            lean = math.sin(math.pi * p) * self.WALK_LEAN_AMP * direction
            rot = math.sin(math.pi * p) * 1.8 * direction   # 绕脚底侧倾 → 重心感
            squash = self.WALK_SQUASH[self._walk_idx]
            if squash:
                sy *= 1.0 - squash
                sx *= 1.0 + squash * 1.4
            if self._mode == "patrol":
                lean = 2.0      # 侧身走持续前压

        def draw_one(target, opacity: float, dx: float = 0.0, dy: float = 0.0) -> None:
            """按当前变换绘制一帧（target 为已预缩放的贴图或剪影）"""
            if target is None or target.isNull() or opacity <= 0.01:
                return
            painter.save()
            painter.setOpacity(opacity)
            painter.translate(w / 2.0 + dx, h + dy)
            painter.rotate(rot)
            # 整体收缩 SPRITE_FIT：拉伸/跳跃时头顶还有余量，不会被窗口上沿切平
            painter.scale(sx * self.SPRITE_FIT, sy * self.SPRITE_FIT)
            if self._face < 0:
                painter.scale(-1.0, 1.0)   # 朝左：水平翻转
            painter.translate(-w / 2.0 + (self._gaze + lean) * self._face, -h)
            self._draw_warped(painter, target, w, h)
            painter.restore()

        # 0) 背光氛围：角色后方一层暖色柔光，把它从桌面背景里"托"起来
        glow = QRadialGradient(w * 0.5, h * 0.45, w * 0.62)
        glow.setColorAt(0.0, QColor(255, 246, 238, 34))
        glow.setColorAt(0.55, QColor(255, 238, 228, 14))
        glow.setColorAt(1.0, QColor(255, 238, 228, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawRect(0, 0, w, h)

        sil = self._silhouette(frame)

        # 1) 投影：与光源反向偏移，光源在左时影子落向右下
        draw_one(sil, self.SHADOW_ALPHA,
                 self.SHADOW_DX - lx * 3.0, self.SHADOW_DY - ly * 2.0)

        # 2) 亮边浮雕：两层剪影错位叠加 —— 外层宽而淡、内层窄而亮，
        #    迎光面形成由柔到硬的体积高光边（单层会像"贴纸描边"）
        draw_one(sil, 0.07, -2.4 - lx * 3.2, -2.4 - ly * 3.2)
        draw_one(sil, 0.12, -1.0 - lx * 1.6, -1.0 - ly * 1.6)

        # 3) 本体
        draw_one(frame, 1.0)

        # 3.5) 跳跃运动残影：按竖直速度调制（起跳/下落最快、顶点几乎无残影），
        #      避免在最高点拖出一条压到窗口底边的重影
        if self._state == "jump" and 0.12 < self._jump_phase < 0.92:
            speed = abs(math.cos(math.pi * self._jump_phase))
            draw_one(frame, 0.18 * speed, 0.0, 12.0 * speed)
            draw_one(frame, 0.10 * speed, 0.0, 24.0 * speed)

        # 4) 方向性环境光：迎光面亮、背光面偏冷紫暗部（只在角色像素内部着色）
        painter.setCompositionMode(QPainter.CompositionMode_SourceAtop)
        gx, gy = w * 0.5, h * 0.5
        r = max(w, h) * 0.75
        grad = QLinearGradient(gx - lx * r, gy - ly * r, gx + lx * r, gy + ly * r)
        grad.setColorAt(0.0, QColor(255, 255, 255, 30))
        grad.setColorAt(0.45, QColor(255, 255, 255, 0))
        grad.setColorAt(1.0, QColor(104, 68, 96, 44))
        painter.setPen(Qt.NoPen)
        painter.setBrush(grad)
        painter.drawRect(0, 0, w, h)

        # 5) 高光：迎光面偏上的柔和光斑（脸部/发丝提亮，塑料/丝绸质感）
        spec = QRadialGradient(
            gx - lx * w * 0.20, h * 0.24 - ly * h * 0.10, w * 0.36
        )
        spec.setColorAt(0.0, QColor(255, 255, 255, 34))
        spec.setColorAt(0.55, QColor(255, 255, 255, 10))
        spec.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(spec)
        painter.drawRect(0, 0, w, h)

        # 6) 底部接触暗部：脚踝/裙摆附近压一层极淡的暗色，脚尖更"踩得住"
        ao = QLinearGradient(0, h * 0.78, 0, h)
        ao.setColorAt(0.0, QColor(40, 22, 34, 0))
        ao.setColorAt(1.0, QColor(40, 22, 34, 20))
        painter.setBrush(ao)
        painter.drawRect(0, 0, w, h)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
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
        act_patrol = menu.addAction("沿屏幕底部走动")
        act_back = menu.addAction("回到面板内")
        act_hide = menu.addAction("隐藏小宠")
        chosen = menu.exec(event.globalPos())
        if chosen == act_patrol:
            self.start_patrol()
        elif chosen == act_back:
            self.dock_to_panel()
        elif chosen == act_hide:
            self.hide()
            self._bubble.hide()
            self._shadow.hide()

    def hideEvent(self, event) -> None:
        self._bubble.hide()
        self._shadow.hide()
        super().hideEvent(event)
