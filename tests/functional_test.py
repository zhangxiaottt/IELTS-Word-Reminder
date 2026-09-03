# -*- coding: utf-8 -*-
"""功能测试：验证「录入 → 展示 → 轮播 → 标记 → 设置」完整链路

运行方式：
    D:\\python\\python.exe tests\\functional_test.py

使用离屏（offscreen）平台，通过 QTest 模拟键盘与按钮点击。
"""
import os
import sys
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402
from PySide6.QtCore import Qt, QCoreApplication  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

app = QApplication.instance() or QApplication([])

from src.config import ConfigManager  # noqa: E402
from src.word_manager import WordManager  # noqa: E402
from src.float_panel import FloatPanel  # noqa: E402
from src.input_widget import InputWidget  # noqa: E402
from src.settings_window import SettingsWindow  # noqa: E402
from src.word_library_window import WordLibraryWindow  # noqa: E402
from src.test_mode_window import TestModeWindow, meaning_similarity  # noqa: E402

TMP = tempfile.mkdtemp(prefix="ielts_func_")
PASS = 0
FAIL = 0


def spin_wait(ms):
    """推进事件循环 ms 毫秒（避免使用离屏平台下不稳定的 QTest.qWait）"""
    import time
    end = time.time() + ms / 1000.0
    while time.time() < end:
        QCoreApplication.processEvents()
        time.sleep(0.01)


def report(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("[PASS]", name)
    else:
        FAIL += 1
        print("[FAIL]", name, detail)


def main():
    cfg = ConfigManager(os.path.join(TMP, "config.json"))
    wm = WordManager(os.path.join(TMP, "word_lib.db"))

    # ---- 1. 录入窗口：手动输入释义（无网络）路径 ----
    win = InputWidget(cfg, wm, None)  # API 传 None -> 走手动输入分支
    win.show()
    win._input.setText("hello")
    # 手动输入自己的释义
    win._meaning_edit.setText("int. 你好，喂")
    QTest.keyClick(win._input, Qt.Key_Return)
    # 保存后 1 秒自动关闭（用离屏事件循环推进）
    spin_wait(1200)
    row = wm.get_word_by_word("hello")
    report("录入: 回车保存单词", row is not None)
    report("录入: 手动释义已保存", row is not None and row["meaning"] == "int. 你好，喂",
           "meaning={}".format(row["meaning"] if row else None))
    report("录入: 保存后自动关闭", not win.isVisible())

    # ---- 2. 已存在单词：确认覆盖路径（替换 QMessageBox 弹窗） ----
    win2 = InputWidget(cfg, wm, None)
    win2.show()
    # 先注入「是」返回值，再触发回车（避免真实确认框阻塞）
    orig_question = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    win2._input.setText("hello")
    QTest.keyClick(win2._input, Qt.Key_Return)
    spin_wait(300)
    QMessageBox.question = orig_question
    row2 = wm.get_word_by_word("hello")
    report("录入: 已存在确认更新", row2 is not None)
    win2.close()

    # ---- 3. 悬浮面板：展示 / 轮播 / 标记 ----
    panel = FloatPanel(cfg, wm)
    panel.refresh_words()
    report("面板: 加载到单词", len(panel._words) == 1,
           "words={}".format([w["word"] for w in panel._words]))
    panel._show_word(panel._words[0])
    report("面板: 单词展示", "hello" in panel._word_label.text())
    report("面板: 释义展示", bool(panel._meaning_label.text()))

    # 认识标记 -> 熟悉度 +20
    before = wm.get_word_by_word("hello")["familiar"]
    panel._on_mark(True)
    after = wm.get_word_by_word("hello")["familiar"]
    report("面板: 认识标记 +20", after == before + 20,
           "{}->{}".format(before, after))

    # 暂停/继续 + 下一个
    panel.toggle_pause()
    report("面板: 暂停生效", panel.is_paused() and not panel._timer.isActive())
    panel.set_paused(False)
    report("面板: 继续生效", not panel.is_paused() and panel._timer.isActive())

    # 轮播间隔实时调整
    panel.set_interval(15)
    report("面板: 间隔生效", panel._timer.interval() == 15000)
    # 透明度（离屏平台无法回读窗口透明度，验证配置已写入）
    panel.set_opacity(0.9)
    report("面板: 透明度生效", abs(float(cfg.get("panel.opacity")) - 0.9) < 1e-6)

    # 空词库提示
    panel.show()
    wm.delete_word(wm.get_word_by_word("hello")["id"])
    panel.refresh_words()
    report("面板: 空词库提示",
           "暂无单词" in panel._empty_label.text() and not panel._empty_label.isHidden())
    # 恢复数据供后续使用
    wm.add_word("hello", "/həˈloʊ/", "int. 你好", "Hello, world!")

    # ---- 4. 设置窗口：滑块 + 确定保存 ----
    sw = SettingsWindow(cfg)
    sw._interval_slider.setValue(18)
    sw._opacity_slider.setValue(70)
    sw._on_ok()
    report("设置: 间隔已保存", int(cfg.get("review.interval")) == 18)
    report("设置: 透明度已保存", abs(float(cfg.get("panel.opacity")) - 0.70) < 1e-6)

    # ---- 5. 单词库窗口：搜索 / 分页 / 排序 / 删除 ----
    for w in ("banana", "cherry", "apple"):
        wm.add_word(w)
    lib = WordLibraryWindow(wm)
    lib.reload_data()
    report("词库: 数据加载", lib._table.rowCount() >= 1)
    report("词库: 总数=4", len(lib._all_rows) == 4,
           "n={}".format(len(lib._all_rows)))
    # 搜索
    lib._search_edit.setText("ba")
    lib.reload_data()
    report("词库: 搜索过滤", len(lib._all_rows) == 1,
           "rows={}".format([r["word"] for r in lib._all_rows]))
    lib._search_edit.clear()
    lib.reload_data()
    # 分页（PAGE_SIZE=50，4 条只有一页）
    report("词库: 单页分页", lib._total_pages() == 1)
    # 排序
    lib._sort_col = 0
    lib._sort_asc = True
    lib._sort_rows()
    sorted_words = [r["word"] for r in lib._all_rows]
    report("词库: 排序", sorted_words == sorted(sorted_words),
           "got={}".format(sorted_words))

    # ---- 6. 测试模式：相似度计算 / 选项生成 / 答题判分 ----
    # 补充带释义的词（用于生成相近干扰项）
    for w, ph, m, e in (
        ("abandon", "/\u0259\u02c8b\u00e6nd\u0259n/", "v. 抛弃；放弃", "They abandoned the plan."),
        ("desert", "/d\u026a\u02c8z\u025c\u02d0t/", "v. 抛弃；n. 沙漠", "Don't desert me!"),
        ("quit", "/kw\u026at/", "v. 离开；放弃", "He quit the job."),
    ):
        wm.add_word(w, ph, m, e)

    # 相似度：近义词应明显高于无关词
    sim_syn = meaning_similarity("v. 抛弃", "v. 放弃")
    sim_unrelated = meaning_similarity("v. 抛弃", "n. 苹果")
    report("测试: 近义词相似度更高",
           sim_syn > sim_unrelated,
           "syn={:.2f} unr={:.2f}".format(sim_syn, sim_unrelated))

    tm = TestModeWindow(wm)
    # 选项生成：正确项唯一、干扰项互异、3~4 选项、相似干扰项被选中
    target = {"id": 999, "word": "abandon", "meaning": "v. 抛弃"}
    candidates = [
        {"id": 1, "word": "desert", "meaning": "v. 抛弃；沙漠"},
        {"id": 2, "word": "quit", "meaning": "v. 离开；放弃"},
        {"id": 3, "word": "apple", "meaning": "n. 苹果"},
        {"id": 4, "word": "banana", "meaning": "n. 香蕉"},
    ]
    options = tm._make_options(target, candidates)
    corrects = [t for t, c in options if c]
    report("测试: 选项含唯一正确答案",
           len(corrects) == 1 and corrects[0] == "v. 抛弃")
    report("测试: 选项数量为3或4", len(options) in (3, 4), "n={}".format(len(options)))
    texts = [t for t, _ in options]
    report("测试: 选项互不重复", len(set(texts)) == len(texts))
    report("测试: 相似干扰项被选中",
           any("抛弃；沙漠" in t for t, _ in options))

    # 整轮答题：随机抽题、判分、自动下一题
    tm.start_round(question_count=6)
    report("测试: 随机抽题生成", 1 <= len(tm._questions) <= 6,
           "n={}".format(len(tm._questions)))
    # 答对第一题：得分 +1 并自动进入下一题
    tm._show_question()
    correct_idx = next(i for i, (t, c) in enumerate(tm._current_options) if c)
    tm._on_option_clicked(correct_idx)
    report("测试: 答对得分+1", tm._score == 1, "score={}".format(tm._score))
    spin_wait(1100)  # 等待自动跳转
    report("测试: 答对自动下一题", tm._q_index == 1,
           "idx={}".format(tm._q_index))
    # 答错第二题：不加分，且正确答案高亮为绿色
    wrong_idx = next(i for i, (t, c) in enumerate(tm._current_options) if not c)
    tm._on_option_clicked(wrong_idx)
    report("测试: 答错不加分", tm._score == 1, "score={}".format(tm._score))
    correct_style = next(
        btn.styleSheet()
        for i, btn in enumerate(tm._option_buttons)
        if i < len(tm._current_options) and tm._current_options[i][1]
    )
    report("测试: 答错高亮正确答案", "#43A047" in correct_style)

    print("=" * 50)
    print("功能测试：通过 {} 项，失败 {} 项".format(PASS, FAIL))
    import shutil
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
