# -*- coding: utf-8 -*-
"""复习悬浮面板模块 - FloatPanel

参考 QQ音乐电脑版桌面歌词面板的悬浮样式：
- 无边框、始终置顶、无任务栏图标（Qt.Tool）
- 支持鼠标拖拽移动（拖拽时鼠标变为移动光标）
- 右下角 8px 热区缩放（鼠标移入变为缩放光标）
- 透明度可配置（setWindowOpacity）
- 自动轮播单词，悬停暂停，移开继续
- 双击打开单词库，右键弹出菜单

布局（从上到下）：
    单词行（加粗、主色调）→ 音标行（灰色小字）→ 释义行 → 例句行（超长截断+悬停提示）
    → 底部按钮行：「认识」「不认识」+ 右侧「暂停/继续」「下一个」
"""
from PySide6.QtCore import Qt, QTimer, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QColor, QPainter, QPen, QPixmap, QPainterPath, QLinearGradient,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMenu, QGraphicsDropShadowEffect,
)

from .utils import condense_meaning


class _ResizeGrip(QWidget):
    """右下角缩放手柄：绘制斜纹图标，可直接拖拽调整面板大小

    独立控件处理自己的鼠标事件，避免被容器/按钮拦截，
    并且可见的手柄给用户明确的缩放入口（解决“面板不能改大小”的问题）。
    """

    SIZE = 16  # 手柄边长（像素）

    def __init__(self, panel, parent: QWidget = None):
        super().__init__(parent)
        self._panel = panel
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.SizeFDiagCursor)  # 缩放光标（↘）
        self.setToolTip("拖拽调整面板大小")
        self._press_global = None   # 按下时鼠标全局坐标
        self._orig_size = None      # 按下时面板原始尺寸

    def paintEvent(self, event) -> None:
        """绘制三道斜线作为拖拽手柄图标"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#BBBBBB"))
        pen.setWidth(2)
        painter.setPen(pen)
        for i in range(3):
            offset = 2 + i * 5
            painter.drawLine(
                2, self.height() - 2 - offset,
                self.width() - 2 - offset, 2,
            )
        painter.end()
        super().paintEvent(event)

    def mousePressEvent(self, event) -> None:
        """按下：记录起点，进入缩放"""
        if event.button() == Qt.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._orig_size = (self._panel.width(), self._panel.height())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """拖动：实时调整面板大小并保存几何信息"""
        if self._press_global is not None and self._orig_size is not None:
            delta = event.globalPosition().toPoint() - self._press_global
            new_w = max(self._panel.MIN_WIDTH, self._orig_size[0] + delta.x())
            new_h = max(self._panel.MIN_HEIGHT, self._orig_size[1] + delta.y())
            self._panel.resize(new_w, new_h)
            self._panel._save_geometry()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """释放：结束缩放"""
        if event.button() == Qt.LeftButton:
            self._press_global = None
            self._orig_size = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ElideLabel(QLabel):
    """支持超长文本截断（省略号）且悬停显示完整内容的标签"""

    def __init__(self, text: str = "", parent: QWidget = None):
        super().__init__(parent)
        self._full_text = text or ""
        self.setToolTip(self._full_text)  # 悬停显示完整内容
        self.setTextInteractionFlags(Qt.NoTextInteraction)

    def setFullText(self, text: str) -> None:
        """设置完整文本，并实时截断显示"""
        self._full_text = text or ""
        self.setToolTip(self._full_text)
        self._update_elide()

    def _update_elide(self) -> None:
        """按当前宽度截断文本，超出部分显示省略号"""
        if not self._full_text:
            super().setText("")
            return
        fm = self.fontMetrics()
        width = max(self.width() - 2, 10)
        elided = fm.elidedText(self._full_text, Qt.ElideRight, width)
        super().setText(elided)

    def resizeEvent(self, event) -> None:
        """窗口尺寸变化时重新截断"""
        self._update_elide()
        super().resizeEvent(event)


class BackgroundCard(QWidget):
    """圆角卡片容器：默认绘制成「粉色小屋」样式，也支持普通背景图

    - 房子样式（panel.house=True，默认开启）：屋顶 + 大窗户（文字区）+ 草地小花，
      整体随面板尺寸自适应，文字显示在窗户里、按钮放在草地方向上，配套桌宠角色
    - 普通样式：未设置背景图时绘制白色圆角底 + 边框；
      设置背景图时等比放大铺满 + 居中裁剪 + 圆角裁切 + 半透明白遮罩
    """

    RADIUS = 10            # 圆角半径（像素）
    OVERLAY_ALPHA = 150    # 背景图上白色遮罩透明度（0~255）

    # ---- 房子样式参数（随面板尺寸自适应）----
    ROOF_RATIO = 0.20      # 屋顶高度占面板高度的比例
    ROOF_MIN = 24          # 屋顶最小高度（像素）
    ROOF_MAX = 46          # 屋顶最大高度（像素）
    WINDOW_MIN_H = 36      # 窗户（文字区）最小高度（像素）
    BOTTOM_BAND = 52       # 底部留给按钮行/草地的区域高度（像素）

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self._bg_pixmap = None   # 原始背景图
        self._bg_scaled = None   # 按当前尺寸缩放后的缓存
        self._house_mode = True  # 是否绘制「房子样式」（默认开启）
        self.setMouseTracking(True)

    # ------------------------------------------------------------------ #
    # 对外接口
    # ------------------------------------------------------------------ #
    def set_house_mode(self, enabled: bool) -> None:
        """切换房子样式；关闭后回到普通白底/背景图样式"""
        self._house_mode = bool(enabled)
        self.update()

    def house_enabled(self) -> bool:
        """当前是否为房子样式"""
        return self._house_mode

    def roof_height(self) -> int:
        """按当前高度计算屋顶高度（像素）"""
        return max(self.ROOF_MIN, min(self.ROOF_MAX, int(self.height() * self.ROOF_RATIO)))

    def set_background(self, path: str) -> None:
        """设置背景图；path 为空或加载失败则清除背景，恢复白色底"""
        try:
            if path:
                pm = QPixmap(path)
                if not pm.isNull():
                    self._bg_pixmap = pm
                    self._update_scaled()
                    self.update()
                    return
        except Exception:
            pass
        self._bg_pixmap = None
        self._bg_scaled = None
        self.update()

    def has_background(self) -> bool:
        """是否已设置有效背景图"""
        return self._bg_pixmap is not None and not self._bg_pixmap.isNull()

    # ------------------------------------------------------------------ #
    # 缩放 / 绘制
    # ------------------------------------------------------------------ #
    def resizeEvent(self, event) -> None:
        """尺寸变化时重新预缩放背景图缓存"""
        self._update_scaled()
        super().resizeEvent(event)

    def _update_scaled(self) -> None:
        """按当前尺寸等比放大铺满背景图（保持纵横比）"""
        if self._bg_pixmap is None or self._bg_pixmap.isNull():
            self._bg_scaled = None
            return
        size = self.size()
        if size.width() <= 0 or size.height() <= 0:
            self._bg_scaled = None
            return
        self._bg_scaled = self._bg_pixmap.scaled(
            size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )

    def paintEvent(self, event) -> None:
        """绘制圆角底（房子 / 白底 / 背景图+遮罩）与边框"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, self.RADIUS, self.RADIUS)
        painter.setClipPath(path)

        if self._house_mode:
            # 房子样式：屋顶 + 窗户 + 草地
            self._draw_house(painter, rect)
        elif self._bg_scaled is not None:
            # 等比铺满并居中（裁掉超出部分）
            x = (self.width() - self._bg_scaled.width()) // 2
            y = (self.height() - self._bg_scaled.height()) // 2
            painter.drawPixmap(x, y, self._bg_scaled)
            # 半透明白遮罩：保证前景文字/按钮可读
            painter.fillRect(rect, QColor(255, 255, 255, self.OVERLAY_ALPHA))
        else:
            painter.fillRect(rect, QColor("#FFFFFF"))

        painter.setClipping(False)
        # 边框
        painter.setPen(QPen(QColor("#E0E0E0"), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.end()
        super().paintEvent(event)

    # ------------------------------------------------------------------ #
    # 房子样式绘制
    # ------------------------------------------------------------------ #
    def _draw_house(self, painter: QPainter, rect: QRectF) -> None:
        """绘制粉色小屋：屋顶 + 大窗户（文字区） + 底部草地与小花

        与桌宠（粉色双马尾少女）同一色系，让小人住进这间小房子。
        """
        W = rect.width()
        H = rect.height()
        roof_h = self.roof_height()

        # ---- 墙体（奶油色）----
        painter.fillRect(QRectF(0, roof_h, W, H - roof_h), QColor("#FFF6F0"))

        # ---- 屋顶：粉色梯形 + 花边底沿（像小木屋的瓦檐）----
        inset = max(8, min(22, int(W * 0.05)))
        roof_path = QPainterPath()
        roof_path.moveTo(0, 0)
        roof_path.lineTo(W, 0)
        roof_path.lineTo(W - inset, roof_h)
        n = max(4, int((W - 2 * inset) // 26))       # 花边个数
        spacing = (W - 2 * inset) / n
        sc = max(4, min(8, int(roof_h * 0.28)))      # 花边下凸深度
        for i in range(n - 1, -1, -1):
            cx = inset + spacing * (i + 0.5)
            xr = cx + spacing / 2.0
            xl = cx - spacing / 2.0
            if i == n - 1:
                xr = W - inset
            roof_path.lineTo(xr, roof_h)
            roof_path.quadTo(cx, roof_h + sc, xl, roof_h)
        roof_path.lineTo(inset, roof_h)
        roof_path.closeSubpath()
        grad = QLinearGradient(0, 0, 0, roof_h + sc)
        grad.setColorAt(0.0, QColor("#FFC2CF"))
        grad.setColorAt(1.0, QColor("#FF9FB4"))
        painter.setPen(QPen(QColor("#F48BA6"), 1.2))
        painter.setBrush(grad)
        painter.drawPath(roof_path)

        # 屋顶瓦片纹（几条浅色横线，柔和）
        painter.setPen(QPen(QColor(255, 255, 255, 70), 1))
        for frac in (0.35, 0.62, 0.88):
            yy = int(roof_h * frac)
            painter.drawLine(QPointF(4, yy), QPointF(W - 4, yy))

        # 屋顶中心小爱心徽标
        self._draw_heart(painter, W / 2.0, roof_h * 0.42, 5.0, QColor("#FF6F91"))
        # 右侧烟囱 + 爱心小烟
        ch_x = W - inset - 28
        chimney = QRectF(ch_x, 4, 16, max(10, roof_h - 16))
        painter.setPen(QPen(QColor("#E87A95"), 1))
        painter.setBrush(QColor("#F79BB1"))
        painter.drawRoundedRect(chimney, 4, 4)
        self._draw_heart(painter, ch_x + 8, roof_h - 6, 3.2, QColor("#FF9FB4"))
        self._draw_heart(painter, ch_x + 22, roof_h - 4, 2.6, QColor("#FFC0CB"))

        # ---- 大窗户（文字区）：浅蓝玻璃 + 粉色窗框 + 窗台 ----
        wy = roof_h - 2
        ww = W - 22
        wh = max(self.WINDOW_MIN_H, H - wy - self.BOTTOM_BAND)
        if wh > H - wy - 8:
            wh = H - wy - 8
        wx = (W - ww) / 2.0
        glass = QLinearGradient(0, wy, 0, wy + wh)
        glass.setColorAt(0.0, QColor(232, 244, 255, 165))
        glass.setColorAt(1.0, QColor(214, 234, 255, 150))
        win_path = QPainterPath()
        win_path.addRoundedRect(QRectF(wx, wy, ww, wh), 12, 12)
        painter.fillPath(win_path, glass)
        painter.setPen(QPen(QColor("#F2A0B5"), 3))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(win_path)
        painter.setPen(QPen(QColor(255, 255, 255, 210), 2))
        painter.drawRoundedRect(QRectF(wx + 3, wy + 3, ww - 6, wh - 6), 10, 10)
        # 窗台（窗下粉色小横条）
        sill = QRectF(wx - 4, wy + wh - 3, ww + 8, 7)
        painter.setPen(QPen(QColor("#F48BA6"), 1))
        painter.setBrush(QColor("#FFC9D6"))
        painter.drawRoundedRect(sill, 3, 3)

        # ---- 底部草地 + 小花 ----
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(191, 232, 200, 235))
        painter.drawRect(QRectF(0, H - 12, W, 12))
        for fx in (8, 18, 28, W - 28, W - 18, W - 8):
            self._draw_flower(painter, fx, H - 5)

    @staticmethod
    def _draw_heart(painter: QPainter, cx: float, cy: float, s: float, color: QColor) -> None:
        """绘制一颗小爱心（小屋装饰）"""
        painter.save()
        painter.translate(cx, cy)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        path = QPainterPath()
        path.moveTo(0, s * 0.9)
        path.cubicTo(-s * 1.3, -s * 0.2, -s * 0.6, -s * 1.1, 0, -s * 0.35)
        path.cubicTo(s * 0.6, -s * 1.1, s * 1.3, -s * 0.2, 0, s * 0.9)
        painter.drawPath(path)
        painter.restore()

    @staticmethod
    def _draw_flower(painter: QPainter, x: float, y: float) -> None:
        """绘制一朵五瓣小花（草地装饰），颜色按位置取粉色/浅黄"""
        r = 3.4
        colors = ("#FF8FB1", "#FFB3C1", "#FFF2B2")
        color = colors[int(x) % len(colors)]
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color))
        for dx, dy in ((-r, 0), (r, 0), (0, -r), (0, r)):
            painter.drawEllipse(QPointF(x + dx, y + dy), r * 0.62, r * 0.62)
        painter.setBrush(QColor("#FFF7D6"))
        painter.drawEllipse(QPointF(x, y), r * 0.5, r * 0.5)


class FloatPanel(QWidget):
    """复习悬浮面板"""

    # ---- 对外信号：主程序据此打开对应窗口或退出 ----
    open_input = Signal()            # 请求打开单词录入窗口
    open_settings = Signal()         # 请求打开设置窗口
    open_library = Signal()          # 请求打开单词库管理窗口
    open_test_mode = Signal()        # 请求打开测试模式窗口
    open_article = Signal()          # 请求打开每日复习文章窗口
    request_quit = Signal()          # 请求退出程序
    geometry_changed = Signal()      # 面板位置/大小变化（供桌宠跟随）

    # 右下角缩放热区尺寸（像素）
    RESIZE_ZONE = 10
    # 边缘缩放的响应宽度（像素）：右侧边缘调宽度，底部边缘调高度
    EDGE = 6
    MIN_WIDTH = 260
    MIN_HEIGHT = 100

    # 右键菜单「面板大小」预设：(名称, 宽, 高)
    SIZE_PRESETS = [
        ("紧凑", 280, 120),
        ("标准", 360, 150),
        ("加大", 460, 180),
    ]

    # 统一配色（主色调 #4A90E2 淡蓝）
    COLOR_PRIMARY = "#4A90E2"
    COLOR_TEXT = "#333333"
    COLOR_GRAY = "#999999"
    COLOR_BG = "#FFFFFF"

    def __init__(self, config, word_manager, parent: QWidget = None):
        """初始化悬浮面板

        Args:
            config: ConfigManager 实例
            word_manager: WordManager 实例
        """
        super().__init__(
            parent,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,
        )
        self._config = config
        self._wm = word_manager

        # 轮播状态
        self._words = []          # 当前复习单词列表
        self._index = -1          # 当前展示下标
        self._paused = False      # 手动暂停标记
        self._hover_paused = False  # 悬停暂停标记
        self._auto_enabled = True   # 是否允许自动轮播

        # 拖拽 / 缩放状态
        self._dragging = False
        self._drag_offset = None
        self._resizing = False
        self._resize_zone = None    # 当前缩放区域：corner / right / bottom
        self._resize_start = None
        self._resize_orig = None

        self._build_ui()
        self._load_geometry()
        self._init_timer()

        # 从配置读取透明度
        self.set_opacity(float(self._config.get("panel.opacity", 0.85)))
        # 从配置读取是否自动轮播
        self.set_auto_enabled(bool(self._config.get("review.auto_start", True)))
        # 从配置读取背景图（空表示默认白底）
        self.set_background(str(self._config.get("panel.background", "") or ""))
        # 从配置读取是否房子样式（默认开启）
        self.set_house_mode(bool(self._config.get("panel.house", True)))

        # 加载单词并显示
        self.refresh_words()

    # ------------------------------------------------------------------ #
    # UI 构建
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        """构建面板界面：透明背景 + 圆角卡片 + 内容布局"""
        # 半透明背景，用于呈现圆角与阴影
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("雅思单词悬浮记忆")

        # 开启鼠标追踪：未按下按钮时也能收到鼠标移动事件，
        # 这样悬停到右下角热区时能实时显示缩放光标
        self.setMouseTracking(True)

        # 外层布局：留出阴影边距
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        # 内容容器（圆角卡片，支持背景图；背景绘制由 BackgroundCard 负责）
        self._container = BackgroundCard(self)
        self._container.setObjectName("panelContainer")

        # 卡片投影效果（QQ音乐桌面歌词面板同款质感）
        shadow = QGraphicsDropShadowEffect(self._container)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 70))
        self._container.setGraphicsEffect(shadow)
        # 容器也开启鼠标追踪，保证角落热区光标反馈
        self._container.setMouseTracking(True)

        outer.addWidget(self._container)

        # 卡片内部布局
        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(3)

        # 1. 单词行（加粗、主色调、14号）
        self._word_label = QLabel("")
        font = self._word_label.font()
        font.setPointSize(14)
        font.setBold(True)
        self._word_label.setFont(font)
        self._word_label.setStyleSheet(
            "color: {}; background: transparent;".format(self.COLOR_PRIMARY)
        )
        # 单词行允许鼠标事件穿透，便于拖拽面板
        self._word_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self._word_label)

        # 2. 音标行（灰色小字）
        self._phonetic_label = QLabel("")
        self._phonetic_label.setStyleSheet(
            "color: {}; background: transparent; font-size: 11px;".format(self.COLOR_GRAY)
        )
        self._phonetic_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self._phonetic_label)

        # 3. 释义行（常规字号）
        self._meaning_label = QLabel("")
        self._meaning_label.setStyleSheet(
            "color: {}; background: transparent; font-size: 12px;".format(self.COLOR_TEXT)
        )
        self._meaning_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._meaning_label.setWordWrap(False)
        layout.addWidget(self._meaning_label)

        # 4. 例句行（灰色小字，超长截断 + 悬停完整提示）
        self._example_label = ElideLabel("", self._container)
        self._example_label.setStyleSheet(
            "color: {}; background: transparent; font-size: 11px;".format(self.COLOR_GRAY)
        )
        self._example_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self._example_label)

        layout.addSpacing(4)

        # 5. 底部按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._known_btn = self._make_button("认识")
        self._unknown_btn = self._make_button("不认识")
        self._test_btn = self._make_button("测试")
        self._pause_btn = self._make_button("暂停")
        self._next_btn = self._make_button("下一个")

        self._known_btn.clicked.connect(lambda: self._on_mark(True))
        self._unknown_btn.clicked.connect(lambda: self._on_mark(False))
        self._test_btn.clicked.connect(self.open_test_mode.emit)
        self._pause_btn.clicked.connect(self.toggle_pause)
        self._next_btn.clicked.connect(self.next_word)

        btn_row.addWidget(self._known_btn)
        btn_row.addWidget(self._unknown_btn)
        btn_row.addWidget(self._test_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self._pause_btn)
        btn_row.addWidget(self._next_btn)
        layout.addLayout(btn_row)

        # 6. 空状态提示标签（默认隐藏）
        self._empty_label = QLabel("暂无单词，按 Ctrl+Alt+W 录入")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet(
            "color: {}; background: transparent; font-size: 12px;".format(self.COLOR_GRAY)
        )
        self._empty_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        # 7. 右下角可见缩放手柄（独立的拖拽控件，位于最上层）
        self._grip = _ResizeGrip(self, self)
        self._grip.raise_()

    def _make_button(self, text: str) -> QPushButton:
        """创建扁平化按钮：悬停变色、点击有反馈"""
        btn = QPushButton(text, self)
        btn.setCursor(Qt.PointingHandCursor)
        # 主题色通过 replace 注入，避免 CSS 花括号与 .format 冲突
        btn.setStyleSheet(
            "QPushButton {"
            "  background: transparent;"
            "  border: 1px solid #E0E0E0;"
            "  border-radius: 6px;"
            "  padding: 3px 10px;"
            "  color: #666666;"
            "  font-size: 12px;"
            "}"
            "QPushButton:hover {"
            "  background: #EAF3FC;"
            "  border-color: @PRIMARY@;"
            "  color: @PRIMARY@;"
            "}"
            "QPushButton:pressed {"
            "  background: #D6E8F9;"
            "}".replace("@PRIMARY@", self.COLOR_PRIMARY)
        )
        return btn

    def _load_geometry(self) -> None:
        """从配置恢复面板位置与大小"""
        try:
            x = int(self._config.get("panel.x", 100))
            y = int(self._config.get("panel.y", 100))
            w = int(self._config.get("panel.width", 320))
            h = int(self._config.get("panel.height", 120))
            self.setGeometry(x, y, max(w, self.MIN_WIDTH), max(h, self.MIN_HEIGHT))
        except Exception:
            self.setGeometry(100, 100, 320, 120)

    def _save_geometry(self) -> None:
        """移动/缩放后实时保存位置与大小到配置"""
        self._config.set("panel.x", self.x())
        self._config.set("panel.y", self.y())
        self._config.set("panel.width", self.width())
        self._config.set("panel.height", self.height())
        self._config.save()

    def resizeEvent(self, event) -> None:
        """窗口大小变化时，将缩放手柄固定到右下角，并通知桌宠跟随"""
        grip = getattr(self, "_grip", None)
        if grip is not None:
            grip.move(
                self.width() - grip.width() - 2,
                self.height() - grip.height() - 2,
            )
        # 房子样式下：文字区上边距跟随屋顶高度，保证文字始终在窗户内
        if getattr(self, "_house_mode", False):
            container = getattr(self, "_container", None)
            if container is not None and container.layout() is not None:
                m = container.layout().contentsMargins()
                new_top = container.roof_height() + 2
                if m.top() != new_top:
                    container.layout().setContentsMargins(
                        m.left(), new_top, m.right(), m.bottom()
                    )
        super().resizeEvent(event)
        self.geometry_changed.emit()

    def moveEvent(self, event) -> None:
        """窗口移动时通知桌宠跟随"""
        super().moveEvent(event)
        self.geometry_changed.emit()

    # ------------------------------------------------------------------ #
    # 轮播逻辑
    # ------------------------------------------------------------------ #
    def _init_timer(self) -> None:
        """初始化自动轮播定时器"""
        self._timer = QTimer(self)
        self._timer.setSingleShot(False)
        self._timer.timeout.connect(self.next_word)
        self._apply_interval()

    def _apply_interval(self) -> None:
        """将配置中的轮播间隔（秒）应用到定时器"""
        seconds = int(self._config.get("review.interval", 10))
        self._timer.setInterval(max(7, min(20, seconds)) * 1000)

    def set_interval(self, seconds: int) -> None:
        """设置轮播间隔（秒），立即生效"""
        self._config.set("review.interval", int(seconds))
        self._apply_interval()
        self._update_timer()

    def set_auto_enabled(self, enabled: bool) -> None:
        """设置是否允许自动轮播（对应配置 auto_start）"""
        self._auto_enabled = bool(enabled)
        self._update_timer()

    def set_background(self, path: str) -> None:
        """设置面板背景图（空字符串清除，恢复默认白底）"""
        try:
            self._container.set_background(path)
        except Exception:
            pass  # 背景图加载失败不影响面板功能

    def set_house_mode(self, enabled: bool) -> None:
        """切换「房子样式」面板

        - 开启：绘制粉色小屋（屋顶+窗户+草地），文字区向下让出屋顶高度，
          面板太小时自动放大到合适尺寸
        - 关闭：回到普通白底/背景图样式
        """
        enabled = bool(enabled)
        self._house_mode = enabled
        try:
            self._container.set_house_mode(enabled)
            layout = self._container.layout()
            if layout is not None:
                m = layout.contentsMargins()
                if enabled:
                    layout.setContentsMargins(14, self._container.roof_height() + 2, 14, 10)
                    if self.height() < 170:
                        self.resize(max(self.width(), 300), 170)
                        self._save_geometry()
                else:
                    layout.setContentsMargins(14, 12, 14, 10)
        except Exception:
            pass  # 房子样式切换失败不影响面板功能

    def house_enabled(self) -> bool:
        """当前是否为房子样式"""
        return getattr(self, "_house_mode", False)

    def toggle_pause(self) -> None:
        """切换手动暂停 / 继续"""
        self._paused = not self._paused
        self._pause_btn.setText("继续" if self._paused else "暂停")
        self._update_timer()

    def set_paused(self, paused: bool) -> None:
        """强制设置暂停状态（供快捷键使用）"""
        if self._paused != paused:
            self._paused = paused
            self._pause_btn.setText("继续" if self._paused else "暂停")
            self._update_timer()

    def is_paused(self) -> bool:
        """当前是否处于手动暂停状态"""
        return self._paused

    def _update_timer(self) -> None:
        """根据各状态统一刷新定时器启停：
        手动暂停 / 悬停暂停 / 关闭自动轮播 任一为真则停止
        """
        if self._paused or self._hover_paused or not self._auto_enabled:
            self._timer.stop()
        else:
            self._timer.start()

    # ------------------------------------------------------------------ #
    # 单词展示
    # ------------------------------------------------------------------ #
    def refresh_words(self) -> None:
        """重新加载复习单词列表（录入/导入/删除后调用）"""
        try:
            current_id = None
            if 0 <= self._index < len(self._words):
                current_id = self._words[self._index].get("id")
            self._words = self._wm.get_review_word_list()
            # 尽量保持当前展示的单词
            self._index = -1
            for i, row in enumerate(self._words):
                if row.get("id") == current_id:
                    self._index = i
                    break
            if self._words:
                if self._index < 0:
                    self._index = 0
                self._show_word(self._words[self._index])
            else:
                self._show_empty()
        except Exception:
            self._show_empty()

    def next_word(self) -> None:
        """切到下一个单词（轮播与「下一个」按钮共用）"""
        if not self._words:
            return
        self._index = (self._index + 1) % len(self._words)
        self._show_word(self._words[self._index])

    def _show_word(self, row: dict) -> None:
        """展示指定单词内容"""
        self._empty_label.hide()
        self._word_label.show()
        self._phonetic_label.show()
        self._meaning_label.show()
        self._example_label.show()

        word = row.get("word") or ""
        phonetic = row.get("phonetic") or ""
        meaning = row.get("meaning") or ""
        example = row.get("example") or ""

        self._word_label.setText(word)
        self._phonetic_label.setText(phonetic)
        # 释义精简展示：只保留第一个义项，避免大段文字（完整释义可在词库查看）
        self._meaning_label.setText(
            condense_meaning(meaning) if meaning else "（暂无释义）"
        )
        self._example_label.setFullText(example)

    def current_word_row(self) -> dict:
        """返回当前展示中的单词行（dict）；列表为空时返回 None

        供桌宠等外部组件读取当前单词，用于「气泡说词义」等功能。
        """
        if 0 <= self._index < len(self._words):
            return self._words[self._index]
        return None

    def _show_empty(self) -> None:
        """单词列表为空时的占位展示"""
        self._word_label.hide()
        self._phonetic_label.hide()
        self._meaning_label.hide()
        self._example_label.hide()
        # 将空提示放入布局（首次添加）
        if not self._empty_label.parent():
            self.layout().insertWidget(1, self._empty_label)
        self._empty_label.show()

    def _on_mark(self, is_known: bool) -> None:
        """点击「认识/不认识」：更新熟悉度并切到下一个单词"""
        if not self._words:
            return
        row = self._words[self._index]
        self._wm.mark_familiar(row["id"], is_known)
        # 更新本地列表中的熟悉度，保持数据一致
        self.next_word()

    # ------------------------------------------------------------------ #
    # 拖拽 / 缩放（支持：右侧边缘调宽度、底部边缘调高度、右下角同时调）
    # ------------------------------------------------------------------ #
    def _hit_test(self, pos) -> str:
        """命中检测：判断坐标落在哪个缩放区域

        Returns:
            "corner" 右下角（宽高同时调）
            "right"  右侧边缘（只调宽度）
            "bottom" 底部边缘（只调高度）
            None     其它区域（用于拖拽移动）
        """
        x, y = pos.x(), pos.y()
        on_right = x >= self.width() - self.EDGE
        on_bottom = y >= self.height() - self.EDGE
        if on_right and on_bottom:
            return "corner"
        if on_right:
            return "right"
        if on_bottom:
            return "bottom"
        return None

    def _resize_cursor(self, zone: str):
        """按缩放区域返回对应光标"""
        return {
            "corner": Qt.SizeFDiagCursor,
            "right": Qt.SizeHorCursor,
            "bottom": Qt.SizeVerCursor,
        }.get(zone)

    def mousePressEvent(self, event) -> None:
        """按下：判断是进入缩放（边缘/角落）还是拖拽"""
        if event.button() == Qt.LeftButton:
            pos = event.position()
            zone = self._hit_test(pos)
            if zone is not None:
                # 进入缩放模式：记录起点与原始尺寸
                self._resizing = True
                self._resize_zone = zone
                self._resize_start = pos
                self._resize_orig = (self.width(), self.height())
                cursor = self._resize_cursor(zone)
                if cursor:
                    self.setCursor(cursor)
            else:
                # 进入拖拽模式（鼠标变为移动光标）
                self._dragging = True
                self._drag_offset = (
                    event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                )
                self.setCursor(Qt.SizeAllCursor)
            event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """移动：执行缩放 / 拖拽 / 悬停光标切换"""
        if self._resizing:
            # 按缩放区域分别调整宽 / 高
            delta = event.position() - self._resize_start
            orig_w, orig_h = self._resize_orig
            new_w, new_h = orig_w, orig_h
            if self._resize_zone in ("corner", "right"):
                new_w = max(self.MIN_WIDTH, int(orig_w + delta.x()))
            if self._resize_zone in ("corner", "bottom"):
                new_h = max(self.MIN_HEIGHT, int(orig_h + delta.y()))
            self.resize(new_w, new_h)
            self._save_geometry()
            event.accept()
        elif self._dragging:
            # 拖拽：跟随鼠标移动
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            self._save_geometry()
            event.accept()
        else:
            # 未按下时：按悬停位置切换缩放光标
            zone = self._hit_test(event.position())
            cursor = self._resize_cursor(zone) if zone else None
            if cursor:
                self.setCursor(cursor)
            else:
                self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """释放：结束拖拽 / 缩放并复位光标"""
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self._resizing = False
            self._resize_zone = None
            # 若仍停留在缩放区，保持缩放光标
            zone = self._hit_test(event.position())
            cursor = self._resize_cursor(zone) if zone else None
            if cursor:
                self.setCursor(cursor)
            else:
                self.unsetCursor()
            event.accept()
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------ #
    # 悬停暂停 / 双击 / 右键菜单
    # ------------------------------------------------------------------ #
    def enterEvent(self, event) -> None:
        """鼠标移入面板：暂停自动轮播"""
        self._hover_paused = True
        self._update_timer()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        """鼠标移出面板：恢复自动轮播"""
        self._hover_paused = False
        self._update_timer()
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        """双击面板：打开单词库管理窗口"""
        if event.button() == Qt.LeftButton:
            self.open_library.emit()
            event.accept()
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        """右键弹出菜单"""
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #FFFFFF; border: 1px solid #E0E0E0; }"
            "QMenu::item { padding: 6px 22px; color: #333333; }"
            "QMenu::item:selected { background: #EAF3FC; color: #4A90E2; }"
        )
        act_pause = menu.addAction("继续" if self._paused else "暂停")
        act_next = menu.addAction("下一个单词")
        menu.addSeparator()
        act_test = menu.addAction("测试模式")
        act_article = menu.addAction("每日复习文章")
        act_input = menu.addAction("录入单词")
        act_library = menu.addAction("单词库管理")
        act_settings = menu.addAction("设置")

        # 面板大小预设子菜单（提供无需拖拽的一键调整入口）
        size_menu = menu.addMenu("面板大小")
        size_actions = {}
        for name, w, h in self.SIZE_PRESETS:
            size_actions[name] = size_menu.addAction(name)

        menu.addSeparator()
        act_quit = menu.addAction("退出")

        chosen = menu.exec(event.globalPos())
        if chosen == act_pause:
            self.toggle_pause()
        elif chosen == act_next:
            self.next_word()
        elif chosen == act_test:
            self.open_test_mode.emit()
        elif chosen == act_article:
            self.open_article.emit()
        elif chosen == act_input:
            self.open_input.emit()
        elif chosen == act_library:
            self.open_library.emit()
        elif chosen == act_settings:
            self.open_settings.emit()
        elif chosen == act_quit:
            self.request_quit.emit()
        else:
            # 命中某个尺寸预设
            for name, action in size_actions.items():
                if chosen == action:
                    size = dict((n, (w, h)) for n, w, h in self.SIZE_PRESETS)[name]
                    self.resize(size[0], size[1])
                    self._save_geometry()
                    break

    # ------------------------------------------------------------------ #
    # 透明度 / 显示
    # ------------------------------------------------------------------ #
    def set_opacity(self, value: float) -> None:
        """设置面板透明度（0.5-1.0），实时生效"""
        opacity = max(0.5, min(1.0, float(value)))
        self.setWindowOpacity(opacity)
        self._config.set("panel.opacity", opacity)
