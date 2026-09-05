# -*- coding: utf-8 -*-
"""雅思单词悬浮记忆工具 - 程序入口 main.py

职责：
- 初始化配置、数据库、词典 API
- 注册全局快捷键（Ctrl+Alt+W 唤起录入 / Ctrl+Alt+S 暂停/继续轮播）
- 创建系统托盘（左键切换悬浮面板显隐；右键菜单：录入/单词库/设置/退出）
- 启动复习悬浮面板
- 退出时自动保存面板位置、大小、当前配置

使用方式：
    python main.py

测试钩子（不影响正常使用）：
    python main.py --auto-quit 8    # 启动 8 秒后自动退出并保存，便于自动化冒烟测试
"""
import os
import sys

# ---- 高 DPI 自适应：必须在创建 QApplication 之前设置，避免高分屏模糊 ----
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

from PySide6.QtCore import Qt, QObject, Signal, QTimer  # noqa: E402
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QSystemTrayIcon, QMenu, QMessageBox,
)

# 将项目根目录加入模块搜索路径（保证打包后相对路径导入正常）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.utils import (  # noqa: E402
    ensure_dirs, get_asset_path, set_auto_launch, get_auto_launch_enabled,
)
from src.config import ConfigManager  # noqa: E402
from src.dict_api import DictAPI  # noqa: E402
from src.word_manager import WordManager  # noqa: E402
from src.float_panel import FloatPanel  # noqa: E402
from src.input_widget import InputWidget  # noqa: E402
from src.settings_window import SettingsWindow  # noqa: E402
from src.word_library_window import WordLibraryWindow  # noqa: E402
from src.test_mode_window import TestModeWindow  # noqa: E402
from src.review_article_window import ReviewArticleWindow  # noqa: E402
from src.desktop_pet import DesktopPet  # noqa: E402

# 统一主题色
COLOR_PRIMARY = "#4A90E2"


class HotkeyBridge(QObject):
    """全局快捷键回调桥接

    keyboard 库的回调运行在独立线程，不能直接操作 Qt 界面。
    通过该对象的信号把快捷键名称投递回 Qt 主线程处理。
    """

    triggered = Signal(str)  # 参数：快捷键标识（"input" / "toggle"）


def make_app_icon() -> QIcon:
    """程序化生成应用图标（蓝底白色「雅」字），避免依赖二进制资源文件"""
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    # 圆角蓝色底
    painter.setBrush(QColor(COLOR_PRIMARY))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(3, 3, 58, 58, 14, 14)
    # 白色文字
    font = QFont("Microsoft YaHei", 24)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#FFFFFF"))
    painter.drawText(pm.rect(), Qt.AlignCenter, "雅")
    painter.end()
    return QIcon(pm)


class MainApp:
    """程序主控：组装配置、数据库、托盘、快捷键与各窗口"""

    def __init__(self, app: QApplication):
        self.app = app
        self.app.setWindowIcon(make_app_icon())

        # 统一默认字体（微软雅黑）
        font = QFont("Microsoft YaHei", 9)
        self.app.setFont(font)

        # ---- 初始化基础模块 ----
        ensure_dirs()
        self.config = ConfigManager()
        self.wm = WordManager()
        self.api = DictAPI()

        # ---- 核心：复习悬浮面板 ----
        self.panel = FloatPanel(self.config, self.wm)

        # ---- 桌面小宠：跟随悬浮面板（Q版少女） ----
        self.pet = DesktopPet(self.config, self.panel)
        self.panel.geometry_changed.connect(self.pet.anchor)

        # ---- 懒加载窗口 ----
        self._input_widget = None
        self._settings_window = None
        self._library_window = None
        self._test_window = None
        self._article_window = None

        # ---- 组装 ----
        self._build_tray()
        self._connect_signals()
        self._setup_hotkeys()
        self._save_icon_to_assets()

        # 启动时显示悬浮面板（程序本体常驻托盘）
        self.panel.show()
        # 桌宠默认随面板显示（由配置控制开关）
        self._update_pet_visibility()

    def _update_pet_visibility(self) -> None:
        """根据配置与面板显隐状态决定桌宠是否显示"""
        try:
            show = bool(self.config.get("panel.pet_enabled", True)) and self.panel.isVisible()
            if show:
                self.pet.anchor()
                self.pet.show()
            else:
                self.pet.hide()
        except Exception:
            pass  # 桌宠异常不影响程序

    # ------------------------------------------------------------------ #
    # 系统托盘
    # ------------------------------------------------------------------ #
    def _build_tray(self) -> None:
        """创建系统托盘：左键显隐面板，右键弹出功能菜单"""
        self.tray = QSystemTrayIcon(make_app_icon(), self.app)
        self.tray.setToolTip("雅思单词悬浮记忆")

        menu = QMenu()
        menu.setStyleSheet(
            "QMenu { background: #FFFFFF; border: 1px solid #E0E0E0; }"
            "QMenu::item { padding: 6px 24px; color: #333333; }"
            "QMenu::item:selected { background: #EAF3FC; color: #4A90E2; }"
        )
        act_input = menu.addAction("录入单词")
        act_library = menu.addAction("单词库管理")
        act_test = menu.addAction("测试模式")
        act_article = menu.addAction("每日复习文章")
        act_settings = menu.addAction("设置")
        menu.addSeparator()
        act_quit = menu.addAction("退出程序")

        act_input.triggered.connect(self.open_input_widget)
        act_library.triggered.connect(self.open_library_window)
        act_test.triggered.connect(self.open_test_mode)
        act_article.triggered.connect(self.open_review_article)
        act_settings.triggered.connect(self.open_settings_window)
        act_quit.triggered.connect(self.quit_app)

        self.tray.setContextMenu(menu)
        # 左键单击：显示/隐藏悬浮面板
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        """托盘图标激活：左键单击切换面板显隐（桌宠随动）"""
        if reason == QSystemTrayIcon.Trigger:
            if self.panel.isVisible():
                self.panel.hide()
            else:
                self.panel.show()
            self._update_pet_visibility()

    # ------------------------------------------------------------------ #
    # 信号连接
    # ------------------------------------------------------------------ #
    def _connect_signals(self) -> None:
        """连接悬浮面板与各窗口之间的信号"""
        self.panel.open_input.connect(self.open_input_widget)
        self.panel.open_settings.connect(self.open_settings_window)
        self.panel.open_library.connect(self.open_library_window)
        self.panel.open_test_mode.connect(self.open_test_mode)
        self.panel.open_article.connect(self.open_review_article)
        self.panel.request_quit.connect(self.quit_app)

    # ------------------------------------------------------------------ #
    # 全局快捷键
    # ------------------------------------------------------------------ #
    def _setup_hotkeys(self) -> None:
        """注册全局快捷键（Ctrl+Alt+W 录入 / Ctrl+Alt+S 暂停继续）"""
        self._bridge = HotkeyBridge()
        self._bridge.triggered.connect(self._on_hotkey)
        try:
            import keyboard
        except Exception:
            return  # 快捷键库不可用时程序照常运行

        def register(shortcut: str, name: str) -> None:
            """注册单个快捷键，失败静默忽略"""
            try:
                key = shortcut.lower().replace("+", "+")
                keyboard.add_hotkey(key, lambda n=name: self._bridge.triggered.emit(n))
            except Exception:
                pass

        register(self.config.get("shortcut.input", "Ctrl+Alt+W"), "input")
        register(self.config.get("shortcut.toggle", "Ctrl+Alt+S"), "toggle")

    def _on_hotkey(self, name: str) -> None:
        """处理快捷键回调（Qt 主线程）"""
        if name == "input":
            self.open_input_widget()
        elif name == "toggle":
            self.panel.toggle_pause()

    # ------------------------------------------------------------------ #
    # 各窗口打开逻辑（懒加载 + 单实例复用）
    # ------------------------------------------------------------------ #
    def open_input_widget(self) -> None:
        """打开单词录入窗口（单实例）"""
        if self._input_widget is None:
            self._input_widget = InputWidget(self.config, self.wm, self.api)
            self._input_widget.saved.connect(self.panel.refresh_words)
            self._input_widget.destroyed.connect(
                lambda: setattr(self, "_input_widget", None)
            )
        self._input_widget.show()
        self._input_widget.raise_()
        self._input_widget.activateWindow()

    def open_settings_window(self) -> None:
        """打开设置窗口（单实例，实时生效信号接到面板）"""
        if self._settings_window is None:
            self._settings_window = SettingsWindow(self.config)
            self._settings_window.interval_changed.connect(self.panel.set_interval)
            self._settings_window.opacity_changed.connect(self.panel.set_opacity)
            self._settings_window.background_changed.connect(self.panel.set_background)
            self._settings_window.house_changed.connect(self.panel.set_house_mode)
            self._settings_window.applied.connect(self._on_settings_applied)
            # 取消时回滚实时预览到已保存配置
            self._settings_window.canceled.connect(self._rollback_settings)
            self._settings_window.destroyed.connect(
                lambda: setattr(self, "_settings_window", None)
            )
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def _rollback_settings(self) -> None:
        """取消设置时，将面板恢复为已保存的配置值"""
        self.panel.set_interval(int(self.config.get("review.interval", 10)))
        self.panel.set_opacity(float(self.config.get("panel.opacity", 0.85)))
        self.panel.set_background(str(self.config.get("panel.background", "") or ""))
        self.panel.set_house_mode(bool(self.config.get("panel.house", True)))
        self._update_pet_visibility()

    def _on_settings_applied(self) -> None:
        """设置确定后：按新配置更新桌宠显隐"""
        self._update_pet_visibility()

    def open_library_window(self) -> None:
        """打开单词库管理窗口（单实例，数据变化刷新面板）"""
        if self._library_window is None:
            self._library_window = WordLibraryWindow(self.wm)
            self._library_window.data_changed.connect(self.panel.refresh_words)
            self._library_window.destroyed.connect(
                lambda: setattr(self, "_library_window", None)
            )
        self._library_window.show()
        self._library_window.raise_()
        self._library_window.activateWindow()

    def open_test_mode(self) -> None:
        """打开测试模式窗口（单实例，独立于复习悬浮面板）

        测试期间自动暂停复习轮播，关闭后恢复。
        """
        if self._test_window is None:
            self._test_window = TestModeWindow(self.wm)
            # 关闭时恢复面板轮播（若测试前处于播放状态）
            self._test_window.closed.connect(self._on_test_closed)
            self._test_window.destroyed.connect(
                lambda: setattr(self, "_test_window", None)
            )
            self._test_paused_before = self.panel.is_paused()
            # 测试专注：暂停悬浮面板轮播
            self.panel.set_paused(True)
        self._test_window.show()
        self._test_window.raise_()
        self._test_window.activateWindow()
        # 若测试窗口首次打开就自动开始一轮
        if self._test_window._q_index == 0 and not self._test_window._questions:
            self._test_window.start_round()

    def _on_test_closed(self) -> None:
        """测试窗口关闭后：恢复悬浮面板轮播状态"""
        try:
            if not getattr(self, "_test_paused_before", False):
                self.panel.set_paused(False)
        except Exception:
            pass  # 恢复失败不影响程序

    def open_review_article(self) -> None:
        """打开每日复习文章窗口（单实例，普通独立页面）"""
        try:
            if self._article_window is None:
                self._article_window = ReviewArticleWindow(self.wm,
                                                           config=self.config)
                self._article_window.closed.connect(
                    lambda: setattr(self, "_article_window", None)
                )
                self._article_window.destroyed.connect(
                    lambda: setattr(self, "_article_window", None)
                )
            self._article_window.show()
            self._article_window.raise_()
            self._article_window.activateWindow()
        except Exception:
            pass  # 文章窗口打开失败不影响程序

    # ------------------------------------------------------------------ #
    # 资源 / 退出
    # ------------------------------------------------------------------ #
    def _save_icon_to_assets(self) -> None:
        """把生成的图标保存到 assets/icon.png，便于用户后续替换"""
        try:
            icon_pixmap = make_app_icon().pixmap(64, 64)
            icon_pixmap.save(get_asset_path("icon.png"))
        except Exception:
            pass  # 保存失败不影响运行

    def quit_app(self) -> None:
        """退出程序：保存面板位置、大小与配置"""
        try:
            # 保存悬浮面板几何信息
            self.panel._save_geometry()
            self.panel.set_opacity(float(self.config.get("panel.opacity", 0.85)))
            self.config.save()
            self.tray.hide()
            self.app.quit()
        except Exception:
            self.app.quit()


def main() -> None:
    """程序入口"""
    # 高 DPI 缩放策略（高分屏不模糊）
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)

    # 解析测试钩子参数：--auto-quit N 表示启动 N 秒后自动退出
    auto_quit = 0
    args = sys.argv[1:]
    if "--auto-quit" in args:
        try:
            idx = args.index("--auto-quit")
            auto_quit = int(args[idx + 1])
        except Exception:
            auto_quit = 0

    main_app = MainApp(app)

    if auto_quit > 0:
        # 自动化冒烟测试：到时自动退出并保存配置
        QTimer.singleShot(auto_quit * 1000, main_app.quit_app)

    # 顶层异常兜底：任何未捕获异常都以对话框提示，不让程序无声崩溃
    sys.excepthook = lambda *exc: QMessageBox.critical(
        None, "程序异常",
        "发生未预期的错误：\n{}".format(exc[1] if exc[1] else exc[0]),
    )

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
