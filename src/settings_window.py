# -*- coding: utf-8 -*-
"""设置窗口模块 - SettingsWindow

普通模态窗口，居中显示（内容放在滚动区内，小屏幕也可完整显示）。
设置项：
- 轮播间隔：滑块 7-20 秒，实时生效
- 面板透明度：滑块 0.5-1.0，实时预览
- 面板背景：内置预设 / 选择本地图片 / 清除背景（静态图）
- 开机自启：开关按钮（写入 Windows 注册表）
- AI 生成文章：厂商预设 / 接口地址 / 模型名 / API Key / 启用开关 / 测试连接
确定保存配置并立即生效；取消恢复原值。
"""
import os

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QPushButton, QCheckBox, QFrame, QMessageBox, QWidget,
    QFileDialog, QScrollArea, QLineEdit, QComboBox,
)

from .utils import (
    set_auto_launch, get_auto_launch_enabled,
    get_backgrounds_dir, resolve_asset_rel, copy_file_to_backgrounds,
    BASE_DIR,
)


class SettingsWindow(QDialog):
    """设置窗口"""

    # 实时生效信号（滑块/背景变更时发出）
    interval_changed = Signal(int)    # 轮播间隔（秒）
    opacity_changed = Signal(float)   # 面板透明度
    background_changed = Signal(str)  # 面板背景图（相对路径，空字符串表示清除）
    house_changed = Signal(bool)      # 房子样式面板开关
    # 确定/取消信号（供主程序在取消时回滚预览效果）
    applied = Signal()
    canceled = Signal()

    COLOR_PRIMARY = "#4A90E2"
    COLOR_TEXT = "#333333"
    COLOR_GRAY = "#999999"

    # AI 厂商预设（OpenAI 兼容，切换只需改 base_url + model 两项）
    LLM_PRESETS = [
        ("自定义", "", ""),
        ("DeepSeek", "https://api.deepseek.com", "deepseek-chat"),
        ("豆包（火山方舟）",
         "https://ark.cn-beijing.volces.com/api/v3", "doubao-seed-2-1-turbo"),
        ("通义千问",
         "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-turbo"),
        ("智谱 GLM",
         "https://open.bigmodel.cn/api/paas/v4", "glm-4.7-flash"),
    ]

    def __init__(self, config, parent: QWidget = None):
        """初始化设置窗口

        Args:
            config: ConfigManager 实例
        """
        super().__init__(parent)
        self._config = config
        self._pending_bg = ""  # 当前选中的背景图（相对路径，空=默认）
        self.setWindowTitle("设置")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setFixedWidth(380)

        self._build_ui()
        self._load_values()

    # ------------------------------------------------------------------ #
    # UI 构建
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        """构建设置界面"""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # 设置项较多，全部放进滚动区，小屏幕也能完整显示
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        container = QWidget()
        layout = QVBoxLayout(container)
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

        # 3. 开关类
        self._auto_launch_check = QCheckBox("开机自启", self)
        self._auto_launch_check.setStyleSheet(
            "QCheckBox { font-size: 13px; color: #333333; }"
            "QCheckBox::indicator { width: 16px; height: 16px; }"
        )
        layout.addWidget(self._auto_launch_check)

        # 桌宠开关（Q版小人跟随面板）
        self._pet_check = QCheckBox("显示桌宠（Q版小人跟随面板）", self)
        self._pet_check.setStyleSheet(
            "QCheckBox { font-size: 13px; color: #333333; }"
            "QCheckBox::indicator { width: 16px; height: 16px; }"
        )
        layout.addWidget(self._pet_check)

        # 房子样式开关（粉色小屋面板）
        self._house_check = QCheckBox("房子样式面板（粉色小屋）", self)
        self._house_check.setStyleSheet(
            "QCheckBox { font-size: 13px; color: #333333; }"
            "QCheckBox::indicator { width: 16px; height: 16px; }"
        )
        layout.addWidget(self._house_check)

        layout.addWidget(self._divider())

        # 4. 面板背景（静态背景图）
        bg_title = QLabel("面板背景")
        bg_title.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: {};".format(self.COLOR_TEXT)
        )
        layout.addWidget(bg_title)

        # 预览区
        self._bg_preview = QLabel("未设置背景图（默认白色）")
        self._bg_preview.setFixedHeight(56)
        self._bg_preview.setAlignment(Qt.AlignCenter)
        self._bg_preview.setStyleSheet(
            "border: 1px dashed #CCCCCC; border-radius: 6px;"
            "color: #999999; font-size: 12px; background: #FFFFFF;"
        )
        layout.addWidget(self._bg_preview)

        # 内置预设（assets/backgrounds 下的图片自动扫描出来）
        presets = self._scan_presets()
        if presets:
            preset_scroll = QScrollArea(self)
            preset_scroll.setWidgetResizable(True)
            preset_scroll.setFixedHeight(58)
            preset_scroll.setFrameShape(QFrame.NoFrame)
            preset_scroll.setStyleSheet(
                "QScrollArea { background: transparent; }"
                "QScrollArea > QWidget > QWidget { background: transparent; }"
            )
            preset_host = QWidget()
            preset_row = QHBoxLayout(preset_host)
            preset_row.setContentsMargins(0, 0, 0, 0)
            preset_row.setSpacing(6)
            for p in presets:
                btn = QPushButton(preset_host)
                pm = QPixmap(p)
                if not pm.isNull():
                    thumb = pm.scaled(
                        66, 44, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                    )
                    btn.setIcon(QIcon(thumb))
                    btn.setIconSize(QSize(66, 44))
                    btn.setFixedSize(72, 50)
                    btn.setToolTip("使用：{}".format(os.path.basename(p)))
                    btn.setCursor(Qt.PointingHandCursor)
                    btn.setStyleSheet(
                        "QPushButton { border: 1px solid #DDDDDD;"
                        "  border-radius: 6px; background: #FFFFFF; }"
                        "QPushButton:hover { border-color: #4A90E2; }"
                    )
                    btn.clicked.connect(
                        lambda _, path=p: self._on_bg_selected(path)
                    )
                    preset_row.addWidget(btn)
            preset_row.addStretch(1)
            preset_scroll.setWidget(preset_host)
            layout.addWidget(preset_scroll)

        # 选择 / 清除按钮
        bg_btn_row = QHBoxLayout()
        self._bg_pick_btn = QPushButton("选择图片…", self)
        self._bg_clear_btn = QPushButton("清除背景", self)
        for btn in (self._bg_pick_btn, self._bg_clear_btn):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(self._small_btn_style())
        self._bg_pick_btn.clicked.connect(self._on_bg_pick)
        self._bg_clear_btn.clicked.connect(self._on_bg_clear)
        bg_btn_row.addWidget(self._bg_pick_btn)
        bg_btn_row.addWidget(self._bg_clear_btn)
        bg_btn_row.addStretch(1)
        layout.addLayout(bg_btn_row)

        layout.addWidget(self._divider())

        # 5. AI 生成（每日复习文章用大模型写）
        ai_title = QLabel("AI 生成文章（每日复习）")
        ai_title.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: {};".format(self.COLOR_TEXT)
        )
        layout.addWidget(ai_title)

        # 厂商预设（选中后自动填地址和模型名）
        preset_row = QHBoxLayout()
        preset_lbl = QLabel("厂商预设")
        preset_lbl.setStyleSheet("color: #666666; font-size: 12px;")
        self._llm_preset = QComboBox()
        for name, _, _ in self.LLM_PRESETS:
            self._llm_preset.addItem(name)
        self._llm_preset.setStyleSheet(
            "QComboBox { border: 1px solid #CCCCCC; border-radius: 6px;"
            "  padding: 4px 8px; background: #FFFFFF; }"
        )
        self._llm_preset.currentIndexChanged.connect(self._on_llm_preset)
        preset_row.addWidget(preset_lbl)
        preset_row.addWidget(self._llm_preset, 1)
        layout.addLayout(preset_row)

        # 接口地址
        self._llm_url = QLineEdit()
        self._llm_url.setPlaceholderText(
            "接口地址（OpenAI 兼容，如 https://api.deepseek.com）"
        )
        self._llm_url.setStyleSheet(self._line_edit_style())
        layout.addWidget(self._llm_url)

        # 模型名
        self._llm_model = QLineEdit()
        self._llm_model.setPlaceholderText("模型名（如 deepseek-chat）")
        self._llm_model.setStyleSheet(self._line_edit_style())
        layout.addWidget(self._llm_model)

        # API Key（密码显示）
        self._llm_key = QLineEdit()
        self._llm_key.setEchoMode(QLineEdit.Password)
        self._llm_key.setPlaceholderText(
            "API Key（仅保存在本地 config.json）"
        )
        self._llm_key.setStyleSheet(self._line_edit_style())
        layout.addWidget(self._llm_key)

        # 启用开关
        self._llm_check = QCheckBox(
            "启用 AI 生成（未配置或失败时自动回落本地模板）", self
        )
        self._llm_check.setStyleSheet(
            "QCheckBox { font-size: 12px; color: #333333; }"
            "QCheckBox::indicator { width: 16px; height: 16px; }"
        )
        layout.addWidget(self._llm_check)

        # 测试连接
        test_row = QHBoxLayout()
        self._llm_test_btn = QPushButton("测试连接")
        self._llm_test_btn.setCursor(Qt.PointingHandCursor)
        self._llm_test_btn.setStyleSheet(self._small_btn_style())
        self._llm_test_btn.clicked.connect(self._on_llm_test)
        self._llm_test_label = QLabel("")
        self._llm_test_label.setStyleSheet("color: #999999; font-size: 12px;")
        self._llm_test_label.setWordWrap(True)
        test_row.addWidget(self._llm_test_btn)
        test_row.addWidget(self._llm_test_label, 1)
        layout.addLayout(test_row)

        layout.addWidget(self._divider())

        # 6. 底部按钮
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
        self._house_check.toggled.connect(self.house_changed.emit)
        self._ok_btn.clicked.connect(self._on_ok)
        self._cancel_btn.clicked.connect(self._on_cancel)

        scroll.setWidget(container)
        outer.addWidget(scroll)

    @staticmethod
    def _line_edit_style() -> str:
        """输入框统一样式"""
        return (
            "QLineEdit { border: 1px solid #CCCCCC; border-radius: 6px;"
            "  padding: 6px 8px; background: #FFFFFF; color: #333333; }"
            "QLineEdit:focus { border-color: #4A90E2; }"
        )

    def _on_llm_preset(self, index: int) -> None:
        """选中厂商预设：自动填入接口地址和模型名"""
        if index <= 0:
            return
        _, url, model = self.LLM_PRESETS[index]
        if url:
            self._llm_url.setText(url)
        if model:
            self._llm_model.setText(model)

    def _on_llm_test(self) -> None:
        """测试连接：用当前输入框的值发一条极简消息"""
        self._llm_test_btn.setEnabled(False)
        self._llm_test_label.setText("正在测试...")
        self._llm_test_label.setStyleSheet("color: #999999; font-size: 12px;")
        try:
            from src.llm_client import LLMClient
            client = LLMClient(self._config)
            ok, msg = client.test_connection(
                base_url=self._llm_url.text().strip(),
                api_key=self._llm_key.text().strip(),
                model=self._llm_model.text().strip(),
            )
            self._llm_test_label.setText(msg)
            self._llm_test_label.setStyleSheet(
                "color: #3BA55D; font-size: 12px;" if ok
                else "color: #D9534F; font-size: 12px;"
            )
        except Exception as e:
            self._llm_test_label.setText("测试异常：{}".format(e))
            self._llm_test_label.setStyleSheet("color: #D9534F; font-size: 12px;")
        finally:
            self._llm_test_btn.setEnabled(True)

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

    @staticmethod
    def _small_btn_style() -> str:
        """选择图片/清除背景/测试连接等次级按钮样式"""
        return (
            "QPushButton {"
            "  background: #FFFFFF;"
            "  color: #333333;"
            "  border: 1px solid #CCCCCC;"
            "  border-radius: 6px;"
            "  padding: 5px 14px;"
            "  font-size: 12px;"
            "}"
            "QPushButton:hover { border-color: #4A90E2; color: #4A90E2; }"
            "QPushButton:pressed { background: #F5FAFF; }"
        )

    def _scan_presets(self) -> list:
        """扫描 assets/backgrounds 下的内置背景图，返回绝对路径列表"""
        result = []
        try:
            bg_dir = get_backgrounds_dir()
            for name in sorted(os.listdir(bg_dir)):
                if name.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp")):
                    result.append(os.path.join(bg_dir, name))
        except Exception:
            pass
        return result

    # ------------------------------------------------------------------ #
    # 背景图处理
    # ------------------------------------------------------------------ #
    def _to_rel(self, path: str) -> str:
        """把绝对/相对路径统一转成相对项目根的路径（用于存入配置）"""
        if not path:
            return ""
        try:
            return os.path.relpath(path, BASE_DIR)
        except Exception:
            return path

    def _on_bg_selected(self, path: str) -> None:
        """点击内置预设：预览并实时应用到面板"""
        rel = self._to_rel(path)
        self._pending_bg = rel
        self._update_preview(path)
        self.background_changed.emit(rel)

    def _on_bg_pick(self) -> None:
        """选择本地图片：复制到项目背景目录后应用"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择背景图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp);;所有文件 (*)",
        )
        if not path:
            return
        rel = copy_file_to_backgrounds(path)
        if not rel:
            QMessageBox.warning(self, "提示", "背景图保存失败，请重试")
            return
        self._pending_bg = rel
        self._update_preview(rel)
        self.background_changed.emit(rel)

    def _on_bg_clear(self) -> None:
        """清除背景：恢复默认白底"""
        self._pending_bg = ""
        self._update_preview("")
        self.background_changed.emit("")

    def _update_preview(self, path: str) -> None:
        """更新预览缩略图（path 可为相对或绝对路径）"""
        abs_path = resolve_asset_rel(path)
        if abs_path and os.path.exists(abs_path):
            pm = QPixmap(abs_path)
            if not pm.isNull():
                self._bg_preview.setText("")
                self._bg_preview.setPixmap(
                    pm.scaled(
                        330, 50, Qt.KeepAspectRatioByExpanding,
                        Qt.SmoothTransformation,
                    )
                )
                return
        self._bg_preview.setPixmap(QPixmap())
        self._bg_preview.setText("未设置背景图（默认白色）")

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
        # 桌宠开关
        self._pet_check.setChecked(bool(self._config.get("panel.pet_enabled", True)))
        # 房子样式开关
        self._house_check.setChecked(bool(self._config.get("panel.house", True)))
        # 背景图（仅填充预览，不重新发出信号；面板已在启动时加载）
        self._pending_bg = str(self._config.get("panel.background", "") or "")
        self._update_preview(self._pending_bg)
        # AI 生成设置（预设不触发填充，保留用户自定义值）
        self._llm_preset.blockSignals(True)
        self._llm_preset.setCurrentIndex(0)
        self._llm_preset.blockSignals(False)
        self._llm_check.setChecked(bool(self._config.get("llm.enabled", False)))
        self._llm_url.setText(str(self._config.get("llm.base_url", "") or ""))
        self._llm_key.setText(str(self._config.get("llm.api_key", "") or ""))
        self._llm_model.setText(str(self._config.get("llm.model", "") or ""))

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
        self._config.set("panel.background", self._pending_bg)
        self._config.set("panel.pet_enabled", self._pet_check.isChecked())
        self._config.set("panel.house", self._house_check.isChecked())
        # 保存 AI 生成设置
        self._config.set("llm.enabled", self._llm_check.isChecked())
        self._config.set("llm.base_url", self._llm_url.text().strip())
        self._config.set("llm.api_key", self._llm_key.text().strip())
        self._config.set("llm.model", self._llm_model.text().strip())
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
