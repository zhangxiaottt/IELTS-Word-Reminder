# -*- coding: utf-8 -*-
"""设置窗口模块 - SettingsWindow

普通模态窗口，居中显示。
设置项：
- 轮播间隔：滑块 7-20 秒，实时生效
- 面板透明度：滑块 0.5-1.0，实时预览
- 开机自启：开关按钮（写入 Windows 注册表）
确定保存配置并立即生效；取消恢复原值。
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QPushButton, QCheckBox, QFrame, QMessageBox, QWidget,
)

from .utils import set_auto_launch, get_auto_launch_enabled


class SettingsWindow(QDialog):
    """设置窗口"""

    # 实时生效信号（滑块拖动时发出）
    interval_changed = Signal(int)    # 轮播间隔（秒）
    opacity_changed = Signal(float)   # 面板透明度
    # 确定/取消信号（供主程序在取消时回滚预览效果）
    applied = Signal()
    canceled = Signal()

    COLOR_PRIMARY = "#4A90E2"
    COLOR_TEXT = "#333333"
    COLOR_GRAY = "#999999"

    def __init__(self, config, parent: QWidget = None):
        """初始化设置窗口

        Args:
            config: ConfigManager 实例
        """
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("设置")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setFixedWidth(360)

        self._build_ui()
        self._load_values()

    # ------------------------------------------------------------------ #
    # UI 构建
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        """构建设置界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(14)

        # 1. 轮播间隔
        interval_title = QLabel("轮播间隔")
        interval_title.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: {};".format(self.COLOR_TEXT)
        )
        layout.addWidget(interval_title)

        interval_row = QHBoxLayout()
        self._interval_slider = QSlider(Qt.Horizontal, self)
        self._interval_slider.setRange(7, 20)
        self._interval_slider.setTickPosition(QSlider.TicksBelow)
        self._interval_slider.setTickInterval(1)
        self._interval_value = QLabel("10 秒")
        self._interval_value.setFixedWidth(52)
        self._interval_value.setStyleSheet("color: {};".format(self.COLOR_PRIMARY))
        interval_row.addWidget(self._interval_slider, 1)
        interval_row.addWidget(self._interval_value)
        layout.addLayout(interval_row)

        layout.addWidget(self._divider())

        # 2. 面板透明度
        opacity_title = QLabel("面板透明度")
        opacity_title.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: {};".format(self.COLOR_TEXT)
        )
        layout.addWidget(opacity_title)

        opacity_row = QHBoxLayout()
        self._opacity_slider = QSlider(Qt.Horizontal, self)
        self._opacity_slider.setRange(50, 100)  # 0.50 ~ 1.00
        self._opacity_value = QLabel("85%")
        self._opacity_value.setFixedWidth(52)
        self._opacity_value.setStyleSheet("color: {};".format(self.COLOR_PRIMARY))
        opacity_row.addWidget(self._opacity_slider, 1)
        opacity_row.addWidget(self._opacity_value)
        layout.addLayout(opacity_row)

        layout.addWidget(self._divider())

        # 3. 开机自启（开关按钮）
        self._auto_launch_check = QCheckBox("开机自启", self)
        self._auto_launch_check.setStyleSheet(
            "QCheckBox { font-size: 13px; color: #333333; }"
            "QCheckBox::indicator { width: 16px; height: 16px; }"
        )
        layout.addWidget(self._auto_launch_check)

        # 4. 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._ok_btn = QPushButton("确定", self)
        self._cancel_btn = QPushButton("取消", self)
        self._ok_btn.setStyleSheet(self._btn_style())
        self._cancel_btn.setStyleSheet(self._btn_style())
        self._ok_btn.setDefault(True)
        btn_row.addWidget(self._ok_btn)
        btn_row.addWidget(self._cancel_btn)
        layout.addLayout(btn_row)

        # 事件绑定
        self._interval_slider.valueChanged.connect(self._on_interval_changed)
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self._ok_btn.clicked.connect(self._on_ok)
        self._cancel_btn.clicked.connect(self._on_cancel)

    def _divider(self) -> QFrame:
        """返回一条浅色分隔线"""
        line = QFrame(self)
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #EEEEEE;")
        return line

    @staticmethod
    def _btn_style() -> str:
        """确定/取消按钮样式"""
        return (
            "QPushButton {"
            "  background: #4A90E2;"
            "  color: white;"
            "  border: none;"
            "  border-radius: 6px;"
            "  padding: 6px 22px;"
            "  font-size: 13px;"
            "}"
            "QPushButton:hover { background: #3D82D1; }"
            "QPushButton:pressed { background: #3473BC; }"
            "QPushButton:disabled { background: #B9D4F2; }"
        )

    # ------------------------------------------------------------------ #
    # 数据加载 / 保存
    # ------------------------------------------------------------------ #
    def _load_values(self) -> None:
        """从配置读取当前值填充控件"""
        interval = int(self._config.get("review.interval", 10))
        opacity = float(self._config.get("panel.opacity", 0.85))
        self._interval_slider.setValue(max(7, min(20, interval)))
        self._opacity_slider.setValue(int(round(max(0.5, min(1.0, opacity)) * 100)))
        # 开机自启状态与注册表对齐
        self._auto_launch_check.setChecked(get_auto_launch_enabled())

    def _on_interval_changed(self, value: int) -> None:
        """轮播间隔滑块：更新数值标签并实时生效"""
        self._interval_value.setText("{} 秒".format(value))
        self.interval_changed.emit(value)

    def _on_opacity_changed(self, value: int) -> None:
        """透明度滑块：更新百分比标签并实时预览"""
        opacity = value / 100.0
        self._opacity_value.setText("{}%".format(value))
        self.opacity_changed.emit(opacity)

    def _on_ok(self) -> None:
        """确定：保存配置、设置开机自启、发出 applied 信号"""
        # 写入配置
        self._config.set("review.interval", self._interval_slider.value())
        self._config.set(
            "panel.opacity", self._opacity_slider.value() / 100.0
        )
        # 开机自启写入注册表
        enabled = self._auto_launch_check.isChecked()
        self._config.set("auto_launch", enabled)
        if not set_auto_launch(enabled):
            QMessageBox.warning(self, "提示", "开机自启设置失败，请检查系统权限")
        self._config.save()
        self.applied.emit()
        self.accept()

    def _on_cancel(self) -> None:
        """取消：发出 canceled 信号（主程序据此回滚实时预览）"""
        self.canceled.emit()
        self.reject()
