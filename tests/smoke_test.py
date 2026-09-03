# -*- coding: utf-8 -*-
"""冒烟测试：验证配置、数据库、词典 API、界面类均可正常工作

运行方式：
    D:\\python\\python.exe tests\\smoke_test.py

覆盖范围：
1. ConfigManager：默认配置生成、get/set/save、损坏配置自动恢复
2. WordManager：增删改查、查重、复习列表算法、熟悉度更新、损坏库重建、导入导出
3. DictAPI：真实网络查询（apple）
4. 界面类：离线模式下实例化各窗口类不抛异常
"""
import os
import shutil
import sys
import tempfile

# 将项目根目录加入模块搜索路径
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

# 使用临时目录，避免污染真实配置与数据库
TMP = tempfile.mkdtemp(prefix="ielts_test_")
os.environ["IELTS_TEST_TMP"] = TMP

PASS = 0
FAIL = 0


def report(name: str, ok: bool, detail: str = "") -> None:
    """输出单条测试结果"""
    global PASS, FAIL
    if ok:
        PASS += 1
        print("[PASS] {}".format(name))
    else:
        FAIL += 1
        print("[FAIL] {} {}".format(name, detail))


# ---------------------------------------------------------------------- #
# 1. ConfigManager
# ---------------------------------------------------------------------- #
def test_config() -> None:
    from src.config import ConfigManager

    cfg_path = os.path.join(TMP, "config.json")

    # 1.1 默认配置生成
    cfg = ConfigManager(cfg_path)
    report("Config: 默认配置生成", os.path.exists(cfg_path))
    report("Config: 默认透明度 0.85",
           abs(float(cfg.get("panel.opacity")) - 0.85) < 1e-9)
    report("Config: 默认间隔 10",
           int(cfg.get("review.interval")) == 10)

    # 1.2 get/set/save
    cfg.set("panel.opacity", 0.92)
    cfg.set("panel.x", 200)
    cfg.save()
    cfg2 = ConfigManager(cfg_path)
    report("Config: set/get/save 往返", abs(float(cfg2.get("panel.opacity")) - 0.92) < 1e-9
           and int(cfg2.get("panel.x")) == 200)

    # 1.3 点号路径缺省值
    report("Config: 缺失键返回默认", cfg.get("not.exist.key", "dft") == "dft")

    # 1.4 损坏配置自动恢复
    with open(cfg_path, "w", encoding="utf-8") as f:
        f.write("{ 这不是合法 JSON ###")
    cfg3 = ConfigManager(cfg_path)
    report("Config: 损坏配置自动恢复",
           abs(float(cfg3.get("panel.opacity")) - 0.85) < 1e-9)
    report("Config: 损坏文件已备份", os.path.exists(cfg_path + ".bak"))


# ---------------------------------------------------------------------- #
# 2. WordManager
# ---------------------------------------------------------------------- #
def test_word_manager() -> None:
    from src.word_manager import WordManager

    db_path = os.path.join(TMP, "word_lib.db")
    wm = WordManager(db_path)

    # 2.1 新增 + 查重
    ok = wm.add_word("apple", "/ˈæpl/", "n. 苹果", "I eat an apple.")
    report("Word: 新增单词", ok)
    dup = wm.add_word("apple", "", "重复", "")
    report("Word: 重复单词返回 False", dup is False)
    report("Word: 总数=1", wm.count_all() == 1)

    # 2.2 查重查询
    row = wm.get_word_by_word("apple")
    report("Word: 按单词查询", row is not None and row["meaning"] == "n. 苹果")

    # 2.3 更新
    ok = wm.update_word(row["id"], {"meaning": "n. 苹果；苹果树"})
    row2 = wm.get_word_by_id(row["id"])
    report("Word: 更新释义", ok and row2["meaning"] == "n. 苹果；苹果树")

    # 2.4 熟悉度标记
    wm.mark_familiar(row["id"], True)
    wm.mark_familiar(row["id"], True)
    row3 = wm.get_word_by_id(row["id"])
    report("Word: 认识两次熟悉度=40", row3["familiar"] == 40)
    report("Word: 复习次数=2", row3["review_count"] == 2)
    wm.mark_familiar(row["id"], False)
    row4 = wm.get_word_by_id(row["id"])
    report("Word: 不认识熟悉度-20=20", row4["familiar"] == 20)

    # 2.5 复习列表算法（昨日新词 → 近5天 → 历史随机）
    # 通过直接写库构造不同录入时间的单词
    today = "datetime('now','localtime')"
    yesterday = "datetime('now','localtime','-1 day')"
    two_days_ago = "datetime('now','localtime','-2 day')"
    ten_days_ago = "datetime('now','localtime','-10 day')"
    conn = wm._conn
    for word, cexpr in [
        ("yesterday_word", yesterday),
        ("recent_word", two_days_ago),
        ("old_word", ten_days_ago),
        ("today_word", today),
    ]:
        conn.execute(
            "INSERT INTO words (word, created_at) VALUES (?, {})".format(cexpr), (word,)
        )
    conn.commit()

    review = wm.get_review_word_list()
    words = [r["word"] for r in review]
    # 注意：apple（今天录入）也属于近5天段，因此列表会包含它
    required = ["yesterday_word", "recent_word", "old_word", "today_word"]
    report("Word: 复习列表包含全部新词",
           all(w in words for w in required), "got={}".format(words))
    report("Word: 昨日新词排最前",
           len(words) >= 1 and words[0] == "yesterday_word", "got={}".format(words))
    report("Word: 今日词在近5天段(历史之前)",
           words.index("today_word") < words.index("old_word"), "got={}".format(words))
    report("Word: 近5天在历史之前",
           words.index("recent_word") < words.index("old_word"), "got={}".format(words))

    # 2.6 删除 + 批量删除
    old_row = wm.get_word_by_word("old_word")
    wm.delete_word(old_row["id"])
    report("Word: 单个删除", wm.get_word_by_word("old_word") is None)
    ids = [wm.get_word_by_word("today_word")["id"],
           wm.get_word_by_word("recent_word")["id"]]
    wm.delete_words(ids)
    report("Word: 批量删除",
           wm.get_word_by_word("today_word") is None
           and wm.get_word_by_word("recent_word") is None)

    # 2.7 导入导出
    export_path = os.path.join(TMP, "export.json")
    ok = wm.export_to_json(export_path)
    report("Word: 导出 JSON", ok and os.path.exists(export_path))
    wm2 = WordManager(os.path.join(TMP, "word_lib2.db"))
    result = wm2.import_from_json(export_path)
    report("Word: 导入 JSON 成功", result["added"] >= 1,
           "added={}".format(result))

    # 2.8 数据库损坏自动重建
    wm3 = WordManager(db_path)  # 现有正常库
    # 人为写坏文件头
    with open(db_path, "r+b") as f:
        f.write(b"NOT A SQLITE DATABASE" * 4)
    wm4 = WordManager(db_path)
    report("Word: 损坏库自动重建",
           wm4.count_all() >= 0 and os.path.exists(db_path + ".bak"))


# ---------------------------------------------------------------------- #
# 3. DictAPI（真实网络）
# ---------------------------------------------------------------------- #
def test_dict_api() -> None:
    from src.dict_api import DictAPI

    api = DictAPI()
    result = api.query("apple")
    report("Dict: 查询 apple 成功", bool(result), "result={}".format(result))
    if result:
        report("Dict: 含音标", bool(result.get("phonetic")), str(result))
        report("Dict: 含释义", bool(result.get("meaning")), str(result))
    # 查询不存在/异常单词不抛异常
    empty = api.query("zzzznotaword12345")
    report("Dict: 不存在单词返回空（不抛异常）", isinstance(empty, dict))
    # 空输入
    report("Dict: 空输入返回空", api.query("   ") == {})


# ---------------------------------------------------------------------- #
# 4. 界面类（离屏模式实例化）
# ---------------------------------------------------------------------- #
def test_gui_classes() -> None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    from src.config import ConfigManager
    from src.word_manager import WordManager
    from src.float_panel import FloatPanel
    from src.input_widget import InputWidget
    from src.settings_window import SettingsWindow
    from src.word_library_window import WordLibraryWindow

    cfg = ConfigManager(os.path.join(TMP, "config.json"))
    wm = WordManager(os.path.join(TMP, "word_lib.db"))

    # 离屏平台下 windowOpacity / 系统托盘不支持，仅验证实例化不抛异常
    panel = FloatPanel(cfg, wm)
    report("GUI: FloatPanel 实例化", isinstance(panel, FloatPanel))
    panel.set_interval(12)
    panel.set_opacity(0.8)
    panel.toggle_pause()
    panel.set_paused(False)
    panel.refresh_words()
    report("GUI: FloatPanel 基础操作", True)

    win = InputWidget(cfg, wm, None)
    report("GUI: InputWidget 实例化", isinstance(win, InputWidget))

    sw = SettingsWindow(cfg)
    report("GUI: SettingsWindow 实例化", isinstance(sw, SettingsWindow))

    lib = WordLibraryWindow(wm)
    lib.reload_data()
    report("GUI: WordLibraryWindow 实例化", isinstance(lib, WordLibraryWindow))
    # 分页逻辑
    lib._sort_col = 0
    lib._sort_asc = True
    lib._sort_rows()
    lib._next_page()
    lib._prev_page()
    report("GUI: 分页/排序基础逻辑", True)


# ---------------------------------------------------------------------- #
if __name__ == "__main__":
    print("=" * 60)
    print("雅思单词悬浮记忆工具 - 冒烟测试")
    print("=" * 60)
    try:
        test_config()
    except Exception as e:
        report("Config 测试异常", False, repr(e))
    try:
        test_word_manager()
    except Exception as e:
        report("WordManager 测试异常", False, repr(e))
    try:
        test_dict_api()
    except Exception as e:
        report("DictAPI 测试异常", False, repr(e))
    try:
        test_gui_classes()
    except Exception as e:
        report("GUI 测试异常", False, repr(e))

    print("=" * 60)
    print("结果：通过 {} 项，失败 {} 项".format(PASS, FAIL))
    # 清理临时目录
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if FAIL else 0)
