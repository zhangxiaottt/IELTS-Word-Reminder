# -*- coding: utf-8 -*-
"""单词库管理窗口模块 - WordLibraryWindow

普通窗口（可最大化 / 最小化）。
- 表格展示所有单词：单词、音标、释义、录入时间、熟悉度、复习次数
- 支持按单词搜索、按录入时间范围筛选
- 支持单个删除、批量删除
- 支持导出单词库为 JSON 文件、导入 JSON 单词库
- 表格支持排序、分页显示（每页 50 条）
"""
from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QDateEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QFileDialog, QMessageBox, QCheckBox,
)


class WordLibraryWindow(QMainWindow):
    """单词库管理窗口"""

    data_changed = Signal()  # 数据发生增删（供主程序刷新悬浮面板）

    PAGE_SIZE = 50  # 每页条数

    COLOR_PRIMARY = "#4A90E2"
    COLOR_TEXT = "#333333"
    COLOR_GRAY = "#999999"

    # 表头定义：(字段, 列名, 宽度, 是否可排序)
    COLUMNS = [
        ("word", "单词", 140, True),
        ("phonetic", "音标", 130, True),
        ("meaning", "释义", 260, True),
        ("created_at", "录入时间", 150, True),
        ("familiar", "熟悉度", 80, True),
        ("review_count", "复习次数", 80, True),
    ]

    def __init__(self, word_manager, parent: QWidget = None):
        """初始化单词库窗口

        Args:
            word_manager: WordManager 实例
        """
        super().__init__(parent)
        self._wm = word_manager

        # 数据状态
        self._all_rows = []          # 当前筛选后的全部记录
        self._page = 0               # 当前页码（从 0 开始）
        self._sort_col = 0           # 当前排序列索引
        self._sort_asc = False       # 是否升序

        self.setWindowTitle("单词库管理")
        self.resize(900, 560)
        self._build_ui()
        self.reload_data()

    # ------------------------------------------------------------------ #
    # UI 构建
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        """构建主界面"""
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ---- 顶部：搜索 / 筛选 / 操作按钮 ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        # 单词搜索
        self._search_edit = QLineEdit(central)
        self._search_edit.setPlaceholderText("搜索单词...")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setFixedWidth(180)
        self._search_edit.setStyleSheet(self._input_style())

        # 时间范围筛选
        self._date_from = QDateEdit(central)
        self._date_to = QDateEdit(central)
        for d in (self._date_from, self._date_to):
            d.setCalendarPopup(True)
            d.setDisplayFormat("yyyy-MM-dd")
            d.setStyleSheet(self._input_style())
        self._date_from.setDate(QDate.currentDate().addYears(-1))
        self._date_to.setDate(QDate.currentDate())
        # 默认关闭时间筛选（勾选后才生效）
        self._date_enabled = QCheckBox("按时间筛选", central)
        self._date_enabled.setStyleSheet("font-size: 12px; color: #333333;")
        self._date_enabled.toggled.connect(self._on_date_enabled)

        # 按钮
        btn_search = self._make_tool_button("查询")
        btn_reset = self._make_tool_button("重置")
        btn_edit = self._make_tool_button("编辑")
        btn_export = self._make_tool_button("导出 JSON")
        btn_import = self._make_tool_button("导入 JSON")
        btn_delete = self._make_tool_button("删除选中")
        btn_delete.setStyleSheet(self._danger_btn_style())

        toolbar.addWidget(QLabel("单词:"))
        toolbar.addWidget(self._search_edit)
        toolbar.addWidget(btn_search)
        toolbar.addSpacing(8)
        toolbar.addWidget(self._date_enabled)
        toolbar.addWidget(self._date_from)
        toolbar.addWidget(QLabel("至"))
        toolbar.addWidget(self._date_to)
        toolbar.addStretch(1)
        toolbar.addWidget(btn_edit)
        toolbar.addWidget(btn_import)
        toolbar.addWidget(btn_export)
        toolbar.addWidget(btn_delete)
        toolbar.addWidget(btn_reset)
        layout.addLayout(toolbar)

        # ---- 表格 ----
        self._table = QTableWidget(central)
        self._table.setColumnCount(len(self.COLUMNS))
        self._table.setHorizontalHeaderLabels([c[1] for c in self.COLUMNS])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)  # 整行选择
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)  # 多选
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setStyleSheet(
            "QTableWidget {"
            "  background: #FFFFFF;"
            "  border: 1px solid #E0E0E0;"
            "  border-radius: 6px;"
            "  gridline-color: #F0F0F0;"
            "}"
            "QHeaderView::section {"
            "  background: #F7F9FC;"
            "  color: #333333;"
            "  border: none;"
            "  border-bottom: 1px solid #E0E0E0;"
            "  padding: 6px;"
            "  font-weight: bold;"
            "}"
            "QTableWidget::item { padding: 4px; }"
            "QTableWidget::item:selected { background: #EAF3FC; color: #333333; }"
        )
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        for i, col in enumerate(self.COLUMNS):
            self._table.setColumnWidth(i, col[2])
        # 释义列自适应拉伸
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        # 点击表头排序
        header.sectionClicked.connect(self._on_header_clicked)
        layout.addWidget(self._table, 1)

        # ---- 底部：分页 ----
        page_row = QHBoxLayout()
        self._page_info = QLabel("第 1 / 1 页，共 0 条", central)
        self._page_info.setStyleSheet("color: #666666; font-size: 12px;")
        btn_prev = self._make_tool_button("上一页")
        btn_next = self._make_tool_button("下一页")
        btn_prev.clicked.connect(self._prev_page)
        btn_next.clicked.connect(self._next_page)
        page_row.addWidget(self._page_info)
        page_row.addStretch(1)
        page_row.addWidget(btn_prev)
        page_row.addWidget(btn_next)
        layout.addLayout(page_row)

        # 事件绑定
        btn_search.clicked.connect(self.reload_data)
        btn_reset.clicked.connect(self._on_reset)
        btn_export.clicked.connect(self._on_export)
        btn_import.clicked.connect(self._on_import)
        btn_delete.clicked.connect(self._on_delete_selected)
        btn_edit.clicked.connect(self._on_edit)
        self._search_edit.returnPressed.connect(self.reload_data)

    # ------------------------------------------------------------------ #
    # 样式辅助
    # ------------------------------------------------------------------ #
    @staticmethod
    def _input_style() -> str:
        return (
            "QLineEdit, QDateEdit {"
            "  border: 1px solid #E0E0E0;"
            "  border-radius: 6px;"
            "  padding: 4px 8px;"
            "  font-size: 12px;"
            "  color: #333333;"
            "  background: #FFFFFF;"
            "}"
            "QLineEdit:focus, QDateEdit:focus { border-color: #4A90E2; }"
        )

    @staticmethod
    def _make_tool_button(text: str) -> QPushButton:
        """普通工具按钮样式"""
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton {"
            "  background: #FFFFFF;"
            "  border: 1px solid #CCCCCC;"
            "  border-radius: 6px;"
            "  padding: 4px 12px;"
            "  font-size: 12px;"
            "  color: #333333;"
            "}"
            "QPushButton:hover { border-color: #4A90E2; color: #4A90E2; }"
            "QPushButton:pressed { background: #F0F6FD; }"
        )
        return btn

    @staticmethod
    def _danger_btn_style() -> str:
        """删除按钮样式（红色系）"""
        return (
            "QPushButton {"
            "  background: #FFFFFF;"
            "  border: 1px solid #E57373;"
            "  border-radius: 6px;"
            "  padding: 4px 12px;"
            "  font-size: 12px;"
            "  color: #D32F2F;"
            "}"
            "QPushButton:hover { background: #FDECEA; }"
        )

    # ------------------------------------------------------------------ #
    # 数据加载 / 排序 / 分页
    # ------------------------------------------------------------------ #
    def reload_data(self) -> None:
        """按当前筛选条件重新加载数据并刷新表格"""
        keyword = self._search_edit.text().strip()
        date_from = None
        date_to = None
        if self._date_enabled.isChecked():
            date_from = self._date_from.date().toString("yyyy-MM-dd")
            date_to = self._date_to.date().toString("yyyy-MM-dd")
        self._all_rows = self._wm.get_all_words(
            keyword=keyword, date_from=date_from, date_to=date_to
        )
        self._page = 0
        self._sort_rows()
        self._render_page()

    def _on_reset(self) -> None:
        """重置筛选条件"""
        self._search_edit.clear()
        self._date_enabled.setChecked(False)
        self._date_from.setDate(QDate.currentDate().addYears(-1))
        self._date_to.setDate(QDate.currentDate())
        self.reload_data()

    def _on_date_enabled(self, checked: bool) -> None:
        """时间筛选开关：开启时立即生效"""
        if checked:
            self.reload_data()

    def _sort_rows(self) -> None:
        """按当前排序列排序（就地排序）"""
        col_key = self.COLUMNS[self._sort_col][0]

        def sort_key(row):
            val = row.get(col_key, "")
            if col_key == "familiar":
                return int(val or 0)
            if col_key == "review_count":
                return int(val or 0)
            if col_key == "created_at":
                return str(val or "")
            return str(val or "").lower()

        self._all_rows.sort(key=sort_key, reverse=not self._sort_asc)

    def _on_header_clicked(self, col_index: int) -> None:
        """点击表头：切换排序列与升降序"""
        if not self.COLUMNS[col_index][3]:  # 该列不可排序
            return
        if self._sort_col == col_index:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col_index
            self._sort_asc = True
        self._sort_rows()
        self._render_page()

    def _total_pages(self) -> int:
        """总页数（至少 1 页）"""
        return max(1, (len(self._all_rows) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)

    def _render_page(self) -> None:
        """渲染当前页数据到表格"""
        total = len(self._all_rows)
        total_pages = self._total_pages()
        self._page = max(0, min(self._page, total_pages - 1))

        start = self._page * self.PAGE_SIZE
        page_rows = self._all_rows[start:start + self.PAGE_SIZE]

        self._table.setRowCount(len(page_rows))
        for r, row in enumerate(page_rows):
            values = [row.get(c[0], "") for c in self.COLUMNS]
            # 熟悉度显示为百分比
            for c, col in enumerate(self.COLUMNS):
                text = str(values[c] or "")
                if col[0] == "familiar" and row.get("familiar") is not None:
                    text = "{}%".format(int(row["familiar"]))
                item = QTableWidgetItem(text)
                # 存储单词 id 便于删除定位
                item.setData(Qt.UserRole, row.get("id"))
                item.setTextAlignment(
                    Qt.AlignCenter if col[0] in ("familiar", "review_count")
                    else Qt.AlignLeft | Qt.AlignVCenter
                )
                self._table.setItem(r, c, item)

        # 更新分页信息
        self._page_info.setText(
            "第 {} / {} 页，共 {} 条".format(self._page + 1, total_pages, total)
        )

    def _prev_page(self) -> None:
        """上一页"""
        if self._page > 0:
            self._page -= 1
            self._render_page()

    def _next_page(self) -> None:
        """下一页"""
        if self._page < self._total_pages() - 1:
            self._page += 1
            self._render_page()

    # ------------------------------------------------------------------ #
    # 删除
    # ------------------------------------------------------------------ #
    def _get_selected_ids(self) -> list:
        """收集选中行的单词 id（去重）"""
        ids = set()
        for item in self._table.selectedItems():
            wid = item.data(Qt.UserRole)
            if wid:
                ids.add(int(wid))
        return list(ids)

    def _on_delete_selected(self) -> None:
        """删除选中单词（支持多选）"""
        ids = self._get_selected_ids()
        if not ids:
            QMessageBox.information(self, "提示", "请先选择要删除的单词")
            return
        answer = QMessageBox.question(
            self,
            "确认删除",
            "确定删除选中的 {} 个单词吗？此操作不可恢复。".format(len(ids)),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        if self._wm.delete_words(ids):
            self.reload_data()
            self.data_changed.emit()
            QMessageBox.information(self, "提示", "删除成功")
        else:
            QMessageBox.warning(self, "提示", "删除失败，请重试")

    # ------------------------------------------------------------------ #
    # 编辑（自己修改/精简释义等字段）
    # ------------------------------------------------------------------ #
    def _on_edit(self) -> None:
        """编辑选中单词：弹出表单，可修改音标 / 释义 / 例句"""
        ids = self._get_selected_ids()
        if not ids:
            QMessageBox.information(self, "提示", "请先选择要编辑的单词")
            return
        if len(ids) > 1:
            QMessageBox.information(self, "提示", "一次只能编辑一个单词，请单选后重试")
            return
        row = self._wm.get_word_by_id(ids[0])
        if not row:
            QMessageBox.warning(self, "提示", "单词不存在，可能已被删除")
            self.reload_data()
            return

        if self._edit_dialog(row):
            # 编辑成功：刷新表格并通知面板更新
            self.reload_data()
            self.data_changed.emit()

    def _edit_dialog(self, row: dict) -> bool:
        """弹出编辑表单对话框，返回是否保存成功

        Args:
            row: 单词数据字典
        Returns:
            bool: True 表示已保存修改
        """
        from PySide6.QtWidgets import (
            QDialog, QFormLayout, QDialogButtonBox,
        )

        dialog = QDialog(self)
        dialog.setWindowTitle("编辑单词")
        dialog.setModal(True)
        dialog.setMinimumWidth(380)

        form = QFormLayout(dialog)
        form.setContentsMargins(20, 18, 20, 14)
        form.setSpacing(10)

        word_edit = QLineEdit(row.get("word") or "")
        word_edit.setReadOnly(True)  # 单词本身不可改（唯一键）
        phonetic_edit = QLineEdit(row.get("phonetic") or "")
        meaning_edit = QLineEdit(row.get("meaning") or "")
        meaning_edit.setPlaceholderText("中文释义（可修改）")
        example_edit = QLineEdit(row.get("example") or "")

        for field, widget in (
            ("单词", word_edit),
            ("音标", phonetic_edit),
            ("释义", meaning_edit),
            ("例句", example_edit),
        ):
            widget.setStyleSheet(self._input_style())
            form.addRow(field, widget)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        form.addRow(buttons)

        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec() != QDialog.Accepted:
            return False

        # 保存修改（允许清空释义/例句）
        ok = self._wm.update_word(
            row["id"],
            {
                "phonetic": phonetic_edit.text().strip(),
                "meaning": meaning_edit.text().strip(),
                "example": example_edit.text().strip(),
            },
        )
        if not ok:
            QMessageBox.warning(self, "提示", "保存失败，请重试")
            return False
        QMessageBox.information(self, "提示", "已保存")
        return True

    # ------------------------------------------------------------------ #
    # 导入 / 导出
    # ------------------------------------------------------------------ #
    def _on_export(self) -> None:
        """导出单词库为 JSON 文件"""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出单词库", "word_lib_export.json", "JSON 文件 (*.json)"
        )
        if not path:
            return
        if self._wm.export_to_json(path):
            QMessageBox.information(self, "提示", "导出成功：\n" + path)
        else:
            QMessageBox.warning(self, "提示", "导出失败，请检查文件权限")

    def _on_import(self) -> None:
        """从 JSON 文件导入单词库"""
        path, _ = QFileDialog.getOpenFileName(
            self, "导入单词库", "", "JSON 文件 (*.json)"
        )
        if not path:
            return
        result = self._wm.import_from_json(path)
        if result.get("added", 0) == 0 and result.get("skipped", 0) == 0:
            QMessageBox.warning(self, "提示", "未导入任何单词，请检查文件格式")
            return
        self.reload_data()
        self.data_changed.emit()
        QMessageBox.information(
            self,
            "导入完成",
            "新增 {} 个单词，跳过已存在 {} 个。".format(
                result.get("added", 0), result.get("skipped", 0)
            ),
        )
