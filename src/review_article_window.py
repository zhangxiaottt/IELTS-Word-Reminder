# -*- coding: utf-8 -*-
"""每日复习文章窗口

独立完整页面：把最近几天学过的单词编成的英文短文集中展示。
功能：
- 当天首次打开自动生成，后续打开沿用当天已生成的文章（稳定不跳变）
- 「换一篇」用新随机种子重新生成并覆盖当天文章
- 日期导航：可回看之前每一天生成的文章，也可预览未来日期
- 文中近期单词高亮（蓝色加粗），点击可跳转
- 右侧「本篇文章用到的词」词汇表：单词 + 音标 + 释义，点击词跳回正文对应位置
- 「复制全文」一键复制纯文本到剪贴板
"""
import html
import random
import re
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QTextBrowser,
    QSplitter, QToolBar, QMessageBox,
)

from src.article_generator import ArticleGenerator

COLOR_PRIMARY = "#4A90E2"
FONT_FAMILY = "Microsoft YaHei"


class ReviewArticleWindow(QMainWindow):
    """每日复习文章窗口（普通窗口，可最大化/最小化）"""

    closed = Signal()  # 关闭信号（主程序据此释放单例引用）

    def __init__(self, word_manager, parent: QWidget = None,
                 data_file: str = None, config=None):
        super().__init__(parent)
        self._wm = word_manager
        # 可选大模型客户端：由 config 构建（OpenAI 兼容、厂商无关）。
        # 配置并启用时用 AI 写文章；未配置 / 失败时自动回落本地模板。
        llm = None
        if config is not None:
            try:
                from src.llm_client import LLMClient
                llm = LLMClient(config)
            except Exception:
                llm = None
        self._gen = ArticleGenerator(word_manager, data_file=data_file,
                                     llm_client=llm)
        self._current = None          # 当前展示的文章 dict
        self._cur_date = datetime.now().strftime("%Y-%m-%d")

        self.setWindowTitle("每日复习文章")
        self.resize(960, 660)
        self._build_ui()
        # 首次打开：自动生成今天的文章
        self._open_date(self._cur_date)

    # ------------------------------------------------------------------ #
    # UI 构建
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        """组装：工具栏（日期导航/操作） + 正文区（文章 | 词汇表）"""
        # 工具栏：日期导航与操作按钮
        toolbar = QToolBar("操作")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self._btn_prev = QPushButton("◀ 前一天")
        self._btn_prev.setCursor(Qt.PointingHandCursor)
        self._btn_prev.clicked.connect(lambda: self._navigate(-1))
        toolbar.addWidget(self._btn_prev)

        self._date_label = QLabel()
        self._date_label.setAlignment(Qt.AlignCenter)
        self._date_label.setMinimumWidth(140)
        self._date_label.setStyleSheet(
            "color:#333333;font-weight:bold;padding:4px 10px;"
        )
        toolbar.addWidget(self._date_label)

        self._btn_next = QPushButton("后一天 ▶")
        self._btn_next.setCursor(Qt.PointingHandCursor)
        self._btn_next.clicked.connect(lambda: self._navigate(1))
        toolbar.addWidget(self._btn_next)

        toolbar.addSeparator()

        self._btn_regenerate = QPushButton("换一篇")
        self._btn_regenerate.setCursor(Qt.PointingHandCursor)
        self._btn_regenerate.setToolTip("用新的随机种子重新生成今天的文章")
        self._btn_regenerate.clicked.connect(self._regenerate)
        toolbar.addWidget(self._btn_regenerate)

        self._btn_copy = QPushButton("复制全文")
        self._btn_copy.setCursor(Qt.PointingHandCursor)
        self._btn_copy.clicked.connect(self._copy_text)
        toolbar.addWidget(self._btn_copy)

        self._used_label = QLabel()
        self._used_label.setStyleSheet("color:#888888;padding:0 8px;")
        toolbar.addWidget(self._used_label)

        # 正文区：左侧文章 + 右侧词汇表（可拖动分隔）
        self._article_browser = QTextBrowser()
        self._article_browser.setOpenExternalLinks(False)
        self._article_browser.setStyleSheet(
            "QTextBrowser { background:#FFFFFF; border:1px solid #E4E7EC;"
            "border-radius:8px; padding:12px; }"
        )

        self._glossary_browser = QTextBrowser()
        self._glossary_browser.setOpenLinks(False)  # 拦截链接用于跳转
        self._glossary_browser.setStyleSheet(
            "QTextBrowser { background:#FBFBFD; border:1px solid #E4E7EC;"
            "border-radius:8px; padding:10px; }"
        )
        self._glossary_browser.anchorClicked.connect(self._on_glossary_click)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._article_browser)
        splitter.addWidget(self._glossary_browser)
        splitter.setSizes([680, 260])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        self.setCentralWidget(splitter)

        self._apply_style()

    def _apply_style(self) -> None:
        """统一扁平化按钮样式"""
        btn_css = (
            "QPushButton {{ background:#FFFFFF; color:#333333;"
            "border:1px solid #D5DAE1; border-radius:6px; padding:5px 14px; }}"
            "QPushButton:hover {{ background:#EAF3FC; color:{0};"
            "border-color:{0}; }}"
            "QPushButton:pressed {{ background:#DCEBFB; }}"
        ).format(COLOR_PRIMARY)
        for btn in (self._btn_prev, self._btn_next, self._btn_regenerate,
                    self._btn_copy):
            btn.setStyleSheet(btn_css)

    # ------------------------------------------------------------------ #
    # 数据加载与渲染
    # ------------------------------------------------------------------ #
    def _open_date(self, date_str: str) -> None:
        """加载指定日期的文章（无则自动生成并存档）"""
        art = self._gen.get_or_generate(date_str)
        self._cur_date = date_str
        self._current = art
        self._render(art)
        # 后一天不能超出今天
        self._btn_next.setEnabled(date_str < datetime.now().strftime("%Y-%m-%d"))

    def _regenerate(self) -> None:
        """换一篇：用新随机种子覆盖当天文章"""
        seed = random.randint(1, 10 ** 9)
        art = self._gen.generate(date_str=self._cur_date, seed=seed)
        self._gen.save(self._cur_date, art)
        self._current = art
        self._render(art)

    def _navigate(self, delta: int) -> None:
        """前一天 / 后一天"""
        try:
            date_str = (self._gen.date_before(self._cur_date) if delta < 0
                        else self._gen.date_after(self._cur_date))
        except Exception:
            return
        self._open_date(date_str)

    def _copy_text(self) -> None:
        """复制全文（纯文本）到剪贴板"""
        if not self._current:
            return
        text = "{} — {}\n\n{}".format(
            self._current.get("title", ""),
            self._current.get("date", ""),
            self._current.get("text", ""),
        )
        try:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(text)
        except Exception:
            pass

    def _render(self, art: dict) -> None:
        """把文章渲染到正文区与词汇表"""
        self._date_label.setText(self._cur_date)
        self._used_label.setText(
            "文中用到 {} / {} 个近期词".format(art.get("used_count", 0),
                                          art.get("target_count", 0))
        )
        self._article_browser.setHtml(self._article_html(art))
        self._glossary_browser.setHtml(self._glossary_html(art))
        # 回到文章顶部
        self._article_browser.moveCursor(QTextCursor.Start)

    # ------------------------------------------------------------------ #
    # HTML 渲染
    # ------------------------------------------------------------------ #
    def _article_html(self, art: dict) -> str:
        """正文 HTML：标题 + 段落，近期单词高亮为蓝色锚点（可跳转）"""
        title = html.escape(art.get("title", ""))
        text = html.escape(art.get("text", ""))
        words = [w.get("word", "") for w in art.get("words", [])]
        words = [w for w in words if w]
        if words:
            # 按词长降序，避免长词被短词子串误替换（如 book 命中 bookcase）
            words_sorted = sorted(words, key=len, reverse=True)
            pattern = "|".join(r"\b{}\b".format(re.escape(w)) for w in words_sorted)

            def _hl(match):
                w = match.group(0)
                return ('<a name="{}"><b style="color:{};">{}</b></a>'
                        .format(w.lower(), COLOR_PRIMARY, w))

            text = re.sub(pattern, _hl, text, flags=re.IGNORECASE)
        paragraphs = "".join("<p>{}</p>".format(p) for p in text.split("\n\n"))
        return (
            "<html><body style=\"font-family:'{font}';font-size:14px;"
            "color:#333333;line-height:1.95;\">"
            "<h2 style=\"color:{color};margin:4px 0 10px 0;\">{title}</h2>"
            "{body}"
            "</body></html>"
        ).format(font=FONT_FAMILY, color=COLOR_PRIMARY,
                 title=title, body=paragraphs)

    def _glossary_html(self, art: dict) -> str:
        """词汇表 HTML：文中用到的词（词/音标/释义），点击跳回正文"""
        head = ("<h3 style=\"color:{0};margin:4px 0 8px 0;\">"
                "本篇文章用到的词</h3>").format(COLOR_PRIMARY)
        items = []
        for w in art.get("words", []):
            word = html.escape(w.get("word", ""))
            ph = html.escape(w.get("phonetic", "") or "")
            mean = html.escape(w.get("meaning", "") or "")
            items.append(
                '<p style="margin:0 0 10px 0;"><a href="{}" '
                'style="color:{};font-weight:bold;text-decoration:none;">'
                "{}</a>".format(word.lower(), COLOR_PRIMARY, word)
                + (' <span style="color:#9AA0A6;">{}</span>'.format(ph) if ph else "")
                + "<br><span style=\"color:#555555;\">{}</span></p>".format(mean)
            )
        return (
            "<html><body style=\"font-family:'{font}';font-size:13px;"
            "color:#333333;\">{head}{items}</body></html>"
        ).format(font=FONT_FAMILY, head=head, items="".join(items))

    # ------------------------------------------------------------------ #
    # 事件
    # ------------------------------------------------------------------ #
    def _on_glossary_click(self, url) -> None:
        """点击词汇表单词：滚动正文到该词第一次出现的位置"""
        try:
            self._article_browser.scrollToAnchor(url.toString())
        except Exception:
            pass

    def closeEvent(self, event) -> None:  # noqa: N802
        """关闭时发出信号，供主程序释放单例引用"""
        try:
            self.closed.emit()
        except Exception:
            pass
        super().closeEvent(event)
