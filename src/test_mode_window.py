# -*- coding: utf-8 -*-
"""测试模式窗口模块 - TestModeWindow

与「复习悬浮面板」相互独立的测试系统功能：
- 从词库随机抽取单词，自动生成选择题（4 个或 3 个选项）
- 展示英文单词 + 音标，选项为其中文释义，用于检测是否真正认识该单词
- 干扰项自动挑选与目标释义「意思相近、不易辨别」的其它单词释义
- 答题后即时判分、高亮正确答案、统计正确率，支持再来一轮

算法说明（meaning_similarity）：
    基于中文释义的汉字重叠率（字符集合 Jaccard）+ 相同词性加成，
    对词库中其它单词的释义排序，取最相似的作为干扰项。
"""
import random
import re

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGraphicsDropShadowEffect, QMessageBox,
)

# 每轮默认题数
DEFAULT_QUESTION_COUNT = 10
# 最多干扰项数量（4 选项 = 正确 + 3 干扰）
MAX_DISTRACTORS = 3
# 选项字母前缀
OPTION_LETTERS = ["A", "B", "C", "D"]

# 配色
COLOR_PRIMARY = "#4A90E2"
COLOR_TEXT = "#333333"
COLOR_GRAY = "#999999"
COLOR_GREEN = "#43A047"
COLOR_GREEN_BG = "#E8F5E9"
COLOR_RED = "#E53935"
COLOR_RED_BG = "#FFEBEE"


def meaning_similarity(a: str, b: str) -> float:
    """计算两段中文释义的相似度（0~1），用于挑选「不易辨别」的干扰项

    策略：
    1. 提取释义中的汉字集合，计算字符重叠率（Jaccard 相似度）
       ——「抛弃」vs「放弃」这类近义词共享汉字，相似度明显更高
    2. 若词性前缀（n. / v. / adj. 等）相同则加分
       —— 同词性的词更容易混淆

    Args:
        a: 第一段释义
        b: 第二段释义
    Returns:
        float: 0~1 的相似度
    """
    def pos_tag(text: str) -> str:
        """提取词性前缀，如 n. / v. / adj. / abbr. 等"""
        m = re.match(r"([a-z]+)", text or "")
        return m.group(1).lower() if m else ""

    def han_chars(text: str) -> str:
        """去掉词性前缀与标点，只保留汉字"""
        t = re.sub(r"^[a-z]+\.?\s*", "", (text or "").lower())
        return re.sub(r"[^\u4e00-\u9fff]+", "", t)

    ca, cb = han_chars(a), han_chars(b)
    if not ca or not cb:
        return 0.0
    sa, sb = set(ca), set(cb)
    inter = len(sa & sb)
    union = len(sa | sb)
    jaccard = inter / union if union else 0.0
    # 词性相同加分（优先级低，仅作为辅助）
    bonus = 0.1 if pos_tag(a) == pos_tag(b) and pos_tag(a) else 0.0
    return min(1.0, jaccard + bonus)


class TestModeWindow(QWidget):
    """测试模式窗口（无边框、置顶、无任务栏图标）"""

    closed = Signal()  # 窗口关闭信号（供主程序恢复悬浮面板轮播）

    def __init__(self, word_manager, parent: QWidget = None):
        """初始化测试模式窗口

        Args:
            word_manager: WordManager 实例
        """
        super().__init__(
            parent,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,
        )
        self._wm = word_manager

        # 测试状态
        self._questions = []       # 当前一轮的题目列表
        self._q_index = 0          # 当前题号
        self._score = 0            # 答对题数
        self._locked = False       # 答题反馈期间锁定点击
        self._current_options = []  # 当前题选项 [(text, is_correct)]

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("测试模式")
        self.setFixedSize(420, 380)
        self._build_ui()
        self._center_on_screen()

    # ------------------------------------------------------------------ #
    # UI 构建
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        """构建界面：圆角卡片 + 标题栏 + 题目区 + 选项区 + 状态栏"""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        card = QWidget(self)
        card.setObjectName("testCard")
        card.setStyleSheet(
            "#testCard {"
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
        layout.setContentsMargins(20, 14, 20, 16)
        layout.setSpacing(10)

        # ---- 标题栏：标题 + 进度/得分 + 关闭 ----
        header = QHBoxLayout()
        title = QLabel("测试模式")
        title.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: {};".format(COLOR_PRIMARY)
        )
        self._progress_label = QLabel("第 0 / 0 题")
        self._progress_label.setStyleSheet(
            "font-size: 12px; color: {};".format(COLOR_GRAY)
        )
        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #999999;"
            "  border: none; font-size: 16px; }"
            "QPushButton:hover { color: #E53935; }"
        )
        close_btn.clicked.connect(self.close)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self._progress_label)
        header.addSpacing(8)
        header.addWidget(close_btn)
        layout.addLayout(header)

        # ---- 单词展示区 ----
        self._word_label = QLabel("")
        word_font = QFont()
        word_font.setPointSize(20)
        word_font.setBold(True)
        self._word_label.setFont(word_font)
        self._word_label.setAlignment(Qt.AlignCenter)
        self._word_label.setStyleSheet("color: {};".format(COLOR_PRIMARY))
        layout.addWidget(self._word_label)

        self._phonetic_label = QLabel("")
        self._phonetic_label.setAlignment(Qt.AlignCenter)
        self._phonetic_label.setStyleSheet(
            "font-size: 12px; color: {};".format(COLOR_GRAY)
        )
        layout.addWidget(self._phonetic_label)

        # ---- 选项区（最多 4 个按钮） ----
        self._option_buttons = []
        for i in range(4):
            btn = QPushButton("", self)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(self._option_style())
            btn.clicked.connect(lambda _, idx=i: self._on_option_clicked(idx))
            btn.hide()
            layout.addWidget(btn)
            self._option_buttons.append(btn)

        # ---- 状态栏（反馈提示 + 得分） ----
        self._feedback_label = QLabel("")
        self._feedback_label.setAlignment(Qt.AlignCenter)
        self._feedback_label.setStyleSheet(
            "font-size: 13px; color: {};".format(COLOR_TEXT)
        )
        layout.addWidget(self._feedback_label)

        # ---- 底部按钮（开始时显示，答题过程中隐藏） ----
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._start_btn = QPushButton("开始测试")
        self._again_btn = QPushButton("再来一轮")
        for btn in (self._start_btn, self._again_btn):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(self._action_style())
            btn.hide()
        self._start_btn.clicked.connect(self.start_round)
        self._again_btn.clicked.connect(self.start_round)
        btn_row.addWidget(self._again_btn)
        btn_row.addWidget(self._start_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # 初始提示
        self._word_label.setText("点击「开始测试」")
        self._start_btn.show()

    @staticmethod
    def _option_style() -> str:
        """选项按钮默认样式"""
        return (
            "QPushButton {"
            "  text-align: left;"
            "  padding: 10px 14px;"
            "  border: 1px solid #DDDDDD;"
            "  border-radius: 8px;"
            "  background: #FFFFFF;"
            "  color: #333333;"
            "  font-size: 13px;"
            "}"
            "QPushButton:hover { border-color: #4A90E2; background: #F5FAFF; }"
            "QPushButton:pressed { background: #EAF3FC; }"
        )

    @staticmethod
    def _action_style() -> str:
        """开始/再来一轮按钮样式"""
        return (
            "QPushButton {"
            "  background: #4A90E2;"
            "  color: #FFFFFF;"
            "  border: none;"
            "  border-radius: 6px;"
            "  padding: 6px 20px;"
            "  font-size: 13px;"
            "}"
            "QPushButton:hover { background: #3D82D1; }"
            "QPushButton:pressed { background: #3473BC; }"
        )

    def _center_on_screen(self) -> None:
        """居中显示在当前屏幕中央"""
        screen = self.screen()
        geo = screen.availableGeometry() if screen else self.windowHandle().screen().availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + (geo.height() - self.height()) // 2
        self.move(x, y)

    # ------------------------------------------------------------------ #
    # 题目生成
    # ------------------------------------------------------------------ #
    def start_round(self, question_count: int = DEFAULT_QUESTION_COUNT) -> None:
        """开始一轮测试：从词库随机抽词生成题目

        Args:
            question_count: 本轮题数（默认 10 题）
        """
        pool = self._build_pool()
        if len(pool) < 3:
            QMessageBox.information(
                self, "提示",
                "词库中带释义的单词不足 3 个，无法生成选项。\n"
                "请先录入单词（Ctrl+Alt+W），或为已有单词补充释义。",
            )
            return

        random.shuffle(pool)
        targets = pool[:question_count]
        self._questions = []
        for target in targets:
            candidates = [r for r in pool if r["id"] != target["id"]]
            options = self._make_options(target, candidates)
            if len(options) >= 3:  # 至少 3 个选项
                self._questions.append({
                    "target": target,
                    "options": options,
                })

        if not self._questions:
            QMessageBox.information(self, "提示", "暂时无法生成题目，请检查词库。")
            return

        # 复位状态
        self._q_index = 0
        self._score = 0
        self._start_btn.hide()
        self._again_btn.hide()
        self._show_question()

    def _build_pool(self) -> list:
        """构建可出题词池：有释义且释义唯一（避免选项重复）"""
        seen_meaning = {}
        pool = []
        for row in self._wm.get_all_words():
            meaning = (row.get("meaning") or "").strip()
            if not meaning:
                continue
            if meaning in seen_meaning:
                continue  # 释义重复的跳过，保证选项互不相同
            seen_meaning[meaning] = row
            pool.append(row)
        return pool

    def _make_options(self, target: dict, candidates: list) -> list:
        """为目标词生成选项（含正确项 + 相似干扰项），返回打乱后的 [(文本, 是否正确), ...]

        Args:
            target: 目标词数据
            candidates: 候选干扰词列表
        Returns:
            list[tuple[str, bool]]: 打乱后的选项
        """
        correct = (target.get("meaning") or "").strip()

        # 干扰项按与目标释义的相似度降序排列，取最相似的（不易辨别）
        scored = sorted(
            candidates,
            key=lambda r: meaning_similarity(correct, r.get("meaning") or ""),
            reverse=True,
        )
        # 去重：保证干扰项释义互不相同、且不等于正确项
        seen = {correct}
        distractors = []
        for row in scored:
            m = (row.get("meaning") or "").strip()
            if m in seen:
                continue
            seen.add(m)
            distractors.append(m)
            if len(distractors) >= MAX_DISTRACTORS:
                break

        # 确定选项数量：优先 4 个，不足则 3 个
        if len(distractors) >= 3:
            distractors = distractors[:3]   # 4 选项
        elif len(distractors) >= 2:
            distractors = distractors[:2]   # 3 选项
        else:
            distractors = distractors       # 2 选项（极端情况）

        options = [(correct, True)] + [(m, False) for m in distractors]
        random.shuffle(options)
        return options

    # ------------------------------------------------------------------ #
    # 答题流程
    # ------------------------------------------------------------------ #
    def _show_question(self) -> None:
        """展示当前题目"""
        if self._q_index >= len(self._questions):
            self._show_result()
            return

        q = self._questions[self._q_index]
        target = q["target"]
        options = q["options"]
        self._current_options = options
        self._locked = False

        self._word_label.setText(target.get("word") or "")
        phonetic = target.get("phonetic") or ""
        self._phonetic_label.setText("[{}]".format(phonetic) if phonetic else "")
        self._feedback_label.setText("")

        for i, btn in enumerate(self._option_buttons):
            if i < len(options):
                text, _ = options[i]
                btn.setText("{}、{}".format(OPTION_LETTERS[i], text))
                btn.setStyleSheet(self._option_style())
                btn.show()
            else:
                btn.hide()
        self._update_progress()

    def _update_progress(self) -> None:
        """更新进度与得分显示"""
        self._progress_label.setText(
            "第 {} / {} 题 · 答对 {}".format(
                min(self._q_index + 1, len(self._questions)),
                len(self._questions),
                self._score,
            )
        )

    def _on_option_clicked(self, index: int) -> None:
        """点击选项：判分 → 高亮反馈 → 自动进入下一题"""
        if self._locked or index >= len(self._current_options):
            return
        self._locked = True

        text, is_correct = self._current_options[index]
        btn = self._option_buttons[index]

        if is_correct:
            # 答对：绿色高亮
            self._score += 1
            btn.setStyleSheet(self._feedback_style(True))
            self._feedback_label.setText("✓ 答对了！")
            self._feedback_label.setStyleSheet(
                "font-size: 13px; color: {};".format(COLOR_GREEN)
            )
            QTimer.singleShot(900, self._next_question)
        else:
            # 答错：选中项红色，正确项绿色
            btn.setStyleSheet(self._feedback_style(False))
            for i, (t, c) in enumerate(self._current_options):
                if c:
                    self._option_buttons[i].setStyleSheet(self._feedback_style(True))
            correct_text = [t for t, c in self._current_options if c][0]
            self._feedback_label.setText("✗ 正确答案：{}".format(correct_text))
            self._feedback_label.setStyleSheet(
                "font-size: 13px; color: {};".format(COLOR_RED)
            )
            QTimer.singleShot(1600, self._next_question)

    @staticmethod
    def _feedback_style(correct: bool) -> str:
        """答题反馈后的按钮样式（对/错高亮）

        注意：QSS 含 CSS 花括号，不能用 .format()，这里用 replace() 注入颜色。
        """
        color = COLOR_GREEN if correct else COLOR_RED
        bg = COLOR_GREEN_BG if correct else COLOR_RED_BG
        return (
            "QPushButton {"
            "  text-align: left;"
            "  padding: 10px 14px;"
            "  border: 2px solid __COLOR__;"
            "  border-radius: 8px;"
            "  background: __BG__;"
            "  color: #333333;"
            "  font-size: 13px;"
            "}".replace("__COLOR__", color).replace("__BG__", bg)
        )

    def _next_question(self) -> None:
        """进入下一题或展示结果"""
        self._q_index += 1
        if self._q_index >= len(self._questions):
            self._show_result()
        else:
            self._show_question()

    def _show_result(self) -> None:
        """一轮结束：展示成绩汇总"""
        total = len(self._questions)
        percent = int(round(self._score * 100.0 / total)) if total else 0
        self._word_label.setText("测试完成！")
        self._phonetic_label.setText("")
        self._feedback_label.setText(
            "答对 {} / {} 题，正确率 {}%".format(self._score, total, percent)
        )
        self._feedback_label.setStyleSheet(
            "font-size: 15px; color: {};".format(COLOR_PRIMARY)
        )
        for btn in self._option_buttons:
            btn.hide()
        self._start_btn.setText("再来一轮")
        self._start_btn.show()
        self._again_btn.show()
        self._progress_label.setText("共 {} 题".format(total))

    # ------------------------------------------------------------------ #
    # 窗口行为
    # ------------------------------------------------------------------ #
    def keyPressEvent(self, event) -> None:
        """Esc 关闭窗口"""
        if event.key() == Qt.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        """关闭时停止待执行的跳转定时器并发出 closed 信号"""
        QTimer.singleShot(0, lambda: None)  # 触发事件循环继续
        for btn in self._option_buttons:
            btn.hide()
        self.closed.emit()
        super().closeEvent(event)
