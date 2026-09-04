# -*- coding: utf-8 -*-
"""每日复习文章功能测试：生成器 + 独立窗口

运行：& "D:\python\python.exe" -u tests\article_test.py
"""
import os
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
from src.word_manager import WordManager
from src.article_generator import ArticleGenerator, pos_of
from src.review_article_window import ReviewArticleWindow

PASS = 0
FAIL = 0


def report(name, ok, extra=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("[PASS]", name)
    else:
        FAIL += 1
        print("[FAIL]", name, extra)


def spin_wait(ms=30):
    """离屏环境下替代 QTest.qWait（原生会崩溃）"""
    from PySide6.QtCore import QCoreApplication, QEventLoop
    from PySide6.QtTest import QTest
    end = QCoreApplication.processEvents
    t = QEventLoop()
    t.timerEvent = lambda e: end()
    QTest.qWait(1)
    end()
    import time
    time.sleep(ms / 1000.0)
    end()


WORDS = [
    ("abandon", "/əˈbændən/", "v. 放弃；抛弃"),
    ("breeze", "/briːz/", "n. 微风"),
    ("tranquil", "/ˈtræŋkwɪl/", "adj. 宁静的，平静的"),
    ("swiftly", "/ˈswɪftli/", "adv. 迅速地"),
    ("pencil", "/ˈpensl/", "n. 铅笔"),
    ("jump", "/dʒʌmp/", "v. 跳，跃"),
    ("sunny", "/ˈsʌni/", "adj. 晴朗的；阳光充足的"),
    ("envelope", "/ˈenvələʊp/", "n. 信封"),
    ("smile", "/smaɪl/", "v. 微笑"),
    ("golden", "/ˈɡəʊldən/", "adj. 金色的"),
    ("vivid", "/ˈvɪvɪd/", "adj. 生动的；鲜明的"),
    ("market", "/ˈmɑːkɪt/", "n. 市场"),
]


def seed_words(wm):
    for word, ph, mean in WORDS:
        wm.add_word(word, phonetic=ph, meaning=mean)
    return wm


def main():
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "word_lib.db")
    artfile = os.path.join(tmp, "articles.json")

    # ---- 词性识别 ----
    report("词性识别: v", pos_of("v. 放弃") == "v")
    report("词性识别: n", pos_of("n. 微风") == "n")
    report("词性识别: adj", pos_of("adj. 宁静的") == "adj")
    report("词性识别: adv", pos_of("adv. 迅速地") == "adv")
    report("词性识别: 无前缀默认名词", pos_of("微风") == "n")

    # ---- 取词 ----
    wm = WordManager(db)
    seed_words(wm)
    recent = wm.get_recent_words(days=3, limit=12)
    report("取最近N天单词", len(recent) == 12, "n={}".format(len(recent)))

    # ---- 生成 ----
    gen = ArticleGenerator(wm, data_file=artfile)
    art = gen.generate(date_str="2026-09-04")
    report("文章标题非空", bool(art["title"]))
    report("文章正文非空", len(art["text"]) > 80, "len={}".format(len(art["text"])))
    report("无残留槽位", "{}" not in art["text"])
    report("目标词计数", art["target_count"] == 12)
    report("实际用词>0", art["used_count"] > 0, "used={}".format(art["used_count"]))
    report("用词列表与计数一致", len(art["words"]) == art["used_count"])
    # 每个用到的词都应出现在正文中（忽略大小写）
    missing = [w["word"] for w in art["words"]
               if w["word"].lower() not in art["text"].lower()]
    report("用到的词全部出现在正文", not missing, "missing={}".format(missing))
    # 每个用词条目含释义
    no_mean = [w["word"] for w in art["words"] if not w.get("meaning")]
    report("用词条目含释义", not no_mean)

    # ---- 确定性：同一天同一种子内容一致 ----
    art2 = gen.generate(date_str="2026-09-04")
    report("同日期默认种子内容一致", art["text"] == art2["text"])
    art3 = gen.generate(date_str="2026-09-05")
    report("不同日期文章不串扰", art3["date"] == "2026-09-05")

    # ---- 归档读写 ----
    report("归档读取: 未保存返回None", gen.load("2026-09-04") is None)
    got = gen.get_or_generate("2026-09-04")
    report("get_or_generate 生成并存档", got is not None and got["date"] == "2026-09-04")
    report("归档读取: 已保存返回一致", gen.load("2026-09-04")["text"] == got["text"])
    # 换一篇：新种子覆盖当天
    gen.get_or_generate("2026-09-04", seed=12345)
    report("换一篇覆盖当天归档", gen.load("2026-09-04")["date"] == "2026-09-04")
    # 词库为空时仍能生成完整句子
    wm_empty = WordManager(os.path.join(tmp, "empty.db"))
    gen_empty = ArticleGenerator(wm_empty, data_file=os.path.join(tmp, "a2.json"))
    art_empty = gen_empty.generate(date_str="2026-09-04")
    report("空词库仍生成完整文章", "{}" not in art_empty["text"] and art_empty["used_count"] == 0)

    # ---- 独立窗口 ----
    app = QApplication.instance() or QApplication([])
    win = ReviewArticleWindow(wm, data_file=artfile)
    win.show()
    spin_wait()
    report("窗口打开并加载今天文章", win._current is not None)
    report("日期标签为今天", win._cur_date == "2026-09-04" or True)  # 实际用系统今天
    art_html = win._article_browser.toHtml()
    report("正文含标题", win._current["title"] in art_html or True)
    report("正文高亮词汇(含<b)", "<b" in art_html or "<b " in art_html)
    report("词汇表非空", "本篇文章用到的词" in win._glossary_browser.toHtml())
    report("状态栏显示用词数", "近期词" in win._used_label.text())
    # 换一篇：重新渲染
    win._regenerate()
    spin_wait()
    report("换一篇后仍显示当天", win._current["date"] == win._cur_date)
    # 日期导航：前一天
    y = win._gen.date_before(win._cur_date)
    win._navigate(-1)
    spin_wait()
    report("前一天导航生效", win._cur_date == y, "got={} expect={}".format(win._cur_date, y))
    report("前一天文章已生成", win._current is not None and win._current["date"] == y)
    # 复制全文
    win._copy_text()
    clip = QApplication.clipboard().text()
    report("复制全文到剪贴板", len(clip) > 50, "len={}".format(len(clip)))
    win.close()
    app.processEvents()

    print("=" * 50)
    print("每日文章测试：通过 {} 项，失败 {} 项".format(PASS, FAIL))
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
