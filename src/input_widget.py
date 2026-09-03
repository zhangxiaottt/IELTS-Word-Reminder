# -*- coding: utf-8 -*-
"""单词录入窗口模块 - InputWidget

无边框、始终置顶、居中弹出、输入框自动聚焦。
- 输入单词后自动调用词典 API 实时显示结果（带防抖与后台线程）
- 「中文释义」输入框始终可见、可编辑：自动查到的释义可直接修改，
  也可以完全手动输入自己的释义（网络异常时同样可以手动填）
- 回车保存，成功后提示「已保存」，1 秒后自动关闭
- Esc 直接关闭
- 单词已存在时提示「该单词已收录，是否更新释义？」，确认则覆盖
"""
from PySide6.QtCore import Qt, QTimer, Signal, QThread
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QLabel,
    QMessageBox, QGraphicsDropShadowEffect, QApplication,
)


class _QueryWorker(QThread):
    """后台词典查询线程：避免网络请求阻塞界面"""

    result_ready = Signal(str, dict)  # (查询单词, 结果字典)

    def __init__(self, api, word: str, parent=None):
        super().__init__(parent)
        self._api = api
        self._word = word

    def run(self) -> None:
        """在线程中执行查询并发出结果信号"""
        result = self._api.query(self._word) if self._api else {}
        self.result_ready.emit(self._word, result)


class InputWidget(QWidget):
    """单词录入窗口"""

    saved = Signal(dict)  # 单词保存成功信号（供主程序刷新悬浮面板）

    # 配色
    COLOR_PRIMARY = "#4A90E2"
    COLOR_TEXT = "#333333"
    COLOR_GRAY = "#999999"

    def __init__(self, config, word_manager, dict_api, parent: QWidget = None):
        """初始化录入窗口

        Args:
            config: ConfigManager 实例
            word_manager: WordManager 实例
            dict_api: DictAPI 实例
        """
        super().__init__(
            parent,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,
        )
        self._config = config
        self._wm = word_manager
        self._api = dict_api

        # 查询状态
        self._query_timer = QTimer(self)   # 输入防抖定时器
        self._query_timer.setSingleShot(True)
        self._query_timer.setInterval(600)
        self._query_timer.timeout.connect(self._start_query)
        self._worker = None                # 当前查询线程
        self._last_query_word = ""         # 最近一次查询的单词

        # 查询结果缓存（保存时回读，避免二次网络请求）
        self._cached_result = {}

        self._build_ui()
        self._center_on_screen()

    # ------------------------------------------------------------------ #
    # UI 构建
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        """构建界面：半透明背景 + 圆角卡片 + 输入区 + 可编辑释义区"""
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("录入单词")
        self.setFixedSize(380, 252)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        card = QWidget(self)
        card.setObjectName("inputCard")
        card.setStyleSheet(
            "#inputCard {"
            "  background: #FFFFFF;"
            "  border: 1px solid #E0E0E0;"
            "  border-radius: 10px;"
            "}"
        )
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 70))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(8)

        # 标题
        title = QLabel("录入新单词")
        title.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: {};".format(self.COLOR_PRIMARY)
        )
        layout.addWidget(title)

        # 单词输入框：无边框、底部主色下划线
        self._input = QLineEdit(card)
        self._input.setPlaceholderText("输入英文单词，回车保存")
        self._input.setStyleSheet(
            "QLineEdit {"
            "  border: none;"
            "  border-bottom: 2px solid #4A90E2;"
            "  font-size: 16px;"
            "  color: #333333;"
            "  padding: 4px 2px;"
            "  background: transparent;"
            "}"
            "QLineEdit:focus { border-bottom-color: #2F7BD1; }"
        )
        layout.addWidget(self._input)

        # 音标 / 状态行（显示音标，或「正在查询...」「网络异常...」）
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(
            "font-size: 12px; color: {}; background: transparent;".format(self.COLOR_GRAY)
        )
        layout.addWidget(self._status_label)

        # 中文释义输入框（始终可见、可编辑 —— 支持自己输入/修改释义）
        self._meaning_edit = QLineEdit(card)
        self._meaning_edit.setPlaceholderText("中文释义（可手动修改）")
        self._meaning_edit.setStyleSheet(
            "QLineEdit {"
            "  border: 1px solid #E0E0E0;"
            "  border-radius: 6px;"
            "  padding: 5px 8px;"
            "  font-size: 12px;"
            "  color: #333333;"
            "}"
            "QLineEdit:focus { border-color: #4A90E2; }"
        )
        layout.addWidget(self._meaning_edit)

        # 例句行（灰色小字，超长省略）
        self._example_label = QLabel("")
        self._example_label.setStyleSheet(
            "font-size: 11px; color: {}; background: transparent;".format(self.COLOR_GRAY)
        )
        layout.addWidget(self._example_label)

        # 底部提示行
        hint = QLabel("回车保存 · Esc 关闭")
        hint.setStyleSheet(
            "font-size: 11px; color: {}; background: transparent;".format(self.COLOR_GRAY)
        )
        layout.addWidget(hint)

        # 事件绑定
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self._on_save)
        self._meaning_edit.returnPressed.connect(self._on_save)

    def _center_on_screen(self) -> None:
        """居中显示在当前屏幕中央"""
        screen = self.screen() or QApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + (geo.height() - self.height()) // 2
        self.move(x, y)

    # ------------------------------------------------------------------ #
    # 实时查询（防抖 + 后台线程）
    # ------------------------------------------------------------------ #
    def _on_text_changed(self, text: str) -> None:
        """输入变化：防抖后触发查询；空输入时清空界面"""
        text = text.strip()
        if not text:
            self._query_timer.stop()
            self._last_query_word = ""
            self._cached_result = {}
            self._status_label.setText("")
            self._meaning_edit.clear()
            self._example_label.setText("")
            return
        self._query_timer.start()

    def _start_query(self) -> None:
        """防抖到期：启动后台查询线程"""
        word = self._input.text().strip()
        if not word:
            return
        self._last_query_word = word
        self._status_label.setText("正在查询...")
        # 查询期间清空旧释义，避免误存旧数据
        self._cached_result = {}
        self._meaning_edit.clear()
        self._example_label.setText("")
        # 丢弃旧查询线程（不强制终止，用单词比对过滤过期结果）
        self._worker = _QueryWorker(self._api, word)
        self._worker.result_ready.connect(self._on_query_done)
        self._worker.start()

    def _on_query_done(self, word: str, result: dict) -> None:
        """查询线程返回：仅当仍是当前输入单词时才展示结果"""
        if word != self._input.text().strip():
            return  # 过期结果，忽略
        if not result:
            # 查询失败 / 单词不存在：允许手动输入释义
            self._cached_result = {}
            self._status_label.setText("网络异常，可手动输入释义")
            self._meaning_edit.setPlaceholderText("请输入中文释义")
            self._meaning_edit.setFocus()
            return
        self._cached_result = result
        phonetic = result.get("phonetic") or ""
        meaning = result.get("meaning") or ""
        example = result.get("example") or ""
        # 状态行显示音标
        self._status_label.setText("[{}]".format(phonetic) if phonetic else "（未查到音标）")
        # 释义自动填入，用户可自由修改
        self._meaning_edit.setText(meaning)
        self._meaning_edit.setPlaceholderText("中文释义（可手动修改）")
        # 例句行显示
        self._example_label.setText(example)

    # ------------------------------------------------------------------ #
    # 保存逻辑
    # ------------------------------------------------------------------ #
    def _on_save(self) -> None:
        """回车保存单词：查重 → 覆盖确认 → 写入 → 提示后自动关闭"""
        word = self._input.text().strip()
        if not word:
            return

        # 组装本次要保存的数据
        phonetic = ""
        example = ""
        cached = getattr(self, "_cached_result", {})
        if word == self._last_query_word and cached:
            phonetic = cached.get("phonetic") or ""
            example = cached.get("example") or ""
        # 释义以用户编辑框内容为准（自动查到的也在框里，可自由修改）
        meaning = self._meaning_edit.text().strip()

        # 查重：单词已存在 → 确认是否更新释义
        existing = self._wm.get_word_by_word(word)
        if existing:
            answer = QMessageBox.question(
                self,
                "单词已收录",
                "该单词已收录，是否更新释义？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer == QMessageBox.Yes:
                self._wm.update_word(
                    existing["id"],
                    {"phonetic": phonetic, "meaning": meaning, "example": example},
                )
                self._show_saved()
                self.saved.emit({"word": word, "id": existing["id"]})
            return

        # 新增单词
        ok = self._wm.add_word(word, phonetic, meaning, example)
        if not ok:
            QMessageBox.warning(self, "提示", "单词保存失败，请重试")
            return
        self._show_saved()
        self.saved.emit({"word": word})

    def _show_saved(self) -> None:
        """显示「已保存」提示，1 秒后自动关闭"""
        self._status_label.setText("已保存 ✓")
        QTimer.singleShot(1000, self.close)

    # ------------------------------------------------------------------ #
    # 快捷键 / 焦点
    # ------------------------------------------------------------------ #
    def keyPressEvent(self, event) -> None:
        """Esc 直接关闭窗口"""
        if event.key() == Qt.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def showEvent(self, event) -> None:
        """显示时清空输入并自动聚焦"""
        super().showEvent(event)
        self._input.clear()
        self._status_label.setText("")
        self._meaning_edit.clear()
        self._meaning_edit.setPlaceholderText("中文释义（可手动修改）")
        self._example_label.setText("")
        self._last_query_word = ""
        self._cached_result = {}
        self._input.setFocus()

    def closeEvent(self, event) -> None:
        """关闭时停止查询防抖定时器并回收线程引用"""
        self._query_timer.stop()
        if self._worker is not None:
            self._worker.result_ready.disconnect()
            self._worker = None
        super().closeEvent(event)
