# -*- coding: utf-8 -*-
"""大模型 API 接入测试：LLMClient + 设置窗口 AI 区 + ArticleGenerator LLM 分支

运行：& "D:\python\python.exe" -u tests\llm_test.py
说明：所有网络请求都用假的 requests.post 拦截，绝不发真实请求。
"""
import os
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import requests
import src.llm_client as llm_mod
from src.config import ConfigManager
from src.article_generator import ArticleGenerator
from src.word_manager import WordManager
from PySide6.QtWidgets import QApplication

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


# --------------------------------------------------------------------- #
# 伪造网络层
# --------------------------------------------------------------------- #
class FakeResp:
    """伪造的 requests.Response"""

    def __init__(self, payload, http_error=None):
        self._payload = payload
        self._http_error = http_error

    def raise_for_status(self):
        if self._http_error:
            raise requests.HTTPError("{} error".format(self._http_error))
        return None

    def json(self):
        return self._payload


def install_fake_ok(content):
    """正常响应：返回给定助手文本"""
    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResp({"choices": [{"message": {"content": content}}]})
    llm_mod.requests.post = fake_post


def install_fake_raise(exc):
    """网络异常"""
    def fake_post(url, headers=None, json=None, timeout=None):
        raise exc
    llm_mod.requests.post = fake_post


def install_fake_http(status):
    """HTTP 错误（如 401 密钥错误）"""
    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResp({}, http_error=status)
    llm_mod.requests.post = fake_post


def make_cfg(**llm):
    """构造带 llm 配置的临时 ConfigManager"""
    tmp = tempfile.mkdtemp()
    cfg = ConfigManager(os.path.join(tmp, "config.json"))
    for k, v in llm.items():
        cfg.set("llm." + k, v)
    cfg.save()
    return cfg


def main():
    # ---- LLMClient 基本行为 ----
    cfg_off = make_cfg(enabled=False, base_url="", api_key="", model="")
    client = llm_mod.LLMClient(cfg_off)
    report("未启用时 enabled=False", not client.enabled())

    cfg_on = make_cfg(
        enabled=True, base_url="https://api.deepseek.com",
        api_key="sk-test", model="deepseek-chat",
    )
    client = llm_mod.LLMClient(cfg_on)
    report("参数齐全时 enabled=True", client.enabled())

    # 缺 key 不算启用
    cfg_nokey = make_cfg(enabled=True, base_url="https://x", api_key="", model="m")
    report("缺 key 不算启用", not llm_mod.LLMClient(cfg_nokey).enabled())

    # 请求成功：返回助手文本
    install_fake_ok("Hello from model")
    report("complete 成功返回文本",
           client.complete([{"role": "user", "content": "hi"}]) == "Hello from model")

    # 网络异常：返回 None，不崩溃
    install_fake_raise(requests.ConnectionError("boom"))
    report("网络异常返回 None", client.complete([]) is None)

    # HTTP 错误（如 401）：返回 None
    install_fake_http(401)
    report("HTTP 401 返回 None", client.complete([]) is None)

    # 参数缺失时直接 None
    report("未配置时 complete 返回 None", llm_mod.LLMClient(cfg_off).complete([]) is None)

    # test_connection 成功/失败
    install_fake_ok("正常")
    ok, msg = client.test_connection(
        base_url="https://api.deepseek.com", api_key="sk", model="deepseek-chat")
    report("测试连接成功", ok and "连接成功" in msg, msg)
    install_fake_raise(requests.ConnectionError("net"))
    ok, msg = client.test_connection(
        base_url="https://api.deepseek.com", api_key="sk", model="deepseek-chat")
    report("测试连接失败不崩溃", (not ok) and "连接失败" in msg, msg)
    ok, msg = client.test_connection(base_url="", api_key="", model="")
    report("测试连接缺参数提示", (not ok) and "填写" in msg, msg)

    # ---- ArticleGenerator 的 AI 分支 ----
    # 造词库
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "w.db")
    wm = WordManager(db)
    for word, ph, mean in [
        ("abandon", "/x/", "v. 放弃"),
        ("breeze", "/x/", "n. 微风"),
        ("tranquil", "/x/", "adj. 宁静的"),
        ("swiftly", "/x/", "adv. 迅速地"),
        ("sunny", "/x/", "adj. 晴朗的"),
        ("golden", "/x/", "adj. 金色的"),
        ("envelope", "/x/", "n. 信封"),
        ("market", "/x/", "n. 市场"),
    ]:
        wm.add_word(word, phonetic=ph, meaning=mean)

    class FakeLLM:
        """模拟 LLMClient：可返回固定文章或垃圾"""

        def __init__(self, payload):
            self._payload = payload
            self.calls = 0

        def enabled(self):
            return True

        def complete(self, messages):
            self.calls += 1
            return self._payload

    story = json.dumps({
        "title": "A Day in the Park",
        "text": "The breeze was tranquil this morning. She abandoned her old "
                "plan and walked swiftly to the market. The golden sunlight "
                "made everything sunny.\n\nShe mailed a letter in an envelope.",
        "used_words": ["breeze", "tranquil", "abandoned", "swiftly"],
    }, ensure_ascii=False)

    fake = FakeLLM(story)
    gen = ArticleGenerator(wm, data_file=os.path.join(tmp, "a.json"),
                           llm_client=fake)
    art = gen.generate(date_str="2026-09-04")
    report("启用AI时调用LLM", fake.calls == 1)
    report("AI文章标题生效", art["title"] == "A Day in the Park")
    report("AI正文生效", "breeze was tranquil" in art["text"])
    report("AI用词计数>0", art["used_count"] > 0, "used={}".format(art["used_count"]))
    # 用词以正文实际出现为准（abandoned 匹配 abandon，支持词形变化）
    wl = [w["word"] for w in art["words"]]
    report("用词包含 abandon(匹配词形变化)", "abandon" in wl, str(wl))
    report("AI用词条目含释义", all(w.get("meaning") for w in art["words"]))
    # 词表自洽：用生成器自身的匹配逻辑回测，每个用词都应能再次命中
    re_matched = gen._match_words_in_text(art["text"], art["words"])
    report("AI用词全部出现在正文", len(re_matched) == len(art["words"]),
           "matched={} used={}".format(len(re_matched), len(art["words"])))

    # LLM 返回垃圾/空 → 自动回落模板
    fake_bad = FakeLLM("not json at all")
    gen_bad = ArticleGenerator(wm, data_file=os.path.join(tmp, "a2.json"),
                               llm_client=fake_bad)
    art_bad = gen_bad.generate(date_str="2026-09-04")
    report("LLM返回垃圾回落模板", art_bad is not None and "{}" not in art_bad["text"])
    report("回落模板仍为完整文章", len(art_bad["text"]) > 50, "len={}".format(len(art_bad["text"])))

    fake_empty = FakeLLM("")
    gen_empty = ArticleGenerator(wm, data_file=os.path.join(tmp, "a3.json"),
                                 llm_client=fake_empty)
    report("LLM返回空回落模板", gen_empty.generate(date_str="2026-09-04") is not None)

    # LLM 返回 JSON 但缺 title/text → 回落
    fake_no = FakeLLM(json.dumps({"foo": 1}))
    gen_no = ArticleGenerator(wm, data_file=os.path.join(tmp, "a4.json"),
                              llm_client=fake_no)
    report("LLM缺字段回落模板", gen_no.generate(date_str="2026-09-04") is not None)

    # 未启用 LLM → 直接用模板（不调用 complete）
    fake_disabled = FakeLLM(story)
    fake_disabled.enabled = lambda: False
    gen_off = ArticleGenerator(wm, data_file=os.path.join(tmp, "a5.json"),
                               llm_client=fake_disabled)
    art_off = gen_off.generate(date_str="2026-09-04")
    report("未启用LLM走模板", fake_disabled.calls == 0 and art_off is not None)

    # ---- 设置窗口 AI 区 ----
    app = QApplication.instance() or QApplication([])
    from src.settings_window import SettingsWindow
    cfg_win = make_cfg(enabled=True, base_url="https://api.deepseek.com",
                       api_key="sk-abc", model="deepseek-chat")
    win = SettingsWindow(cfg_win)
    report("设置窗口有AI厂商预设", hasattr(win, "_llm_preset"))
    report("设置窗口加载地址", win._llm_url.text() == "https://api.deepseek.com")
    report("设置窗口加载模型", win._llm_model.text() == "deepseek-chat")
    report("设置窗口加载key", win._llm_key.text() == "sk-abc")
    report("设置窗口加载启用开关", win._llm_check.isChecked() is True)
    # 预设选择自动填地址/模型
    win._llm_preset.setCurrentIndex(2)  # 豆包
    report("预设选中填地址", "volces.com" in win._llm_url.text(), win._llm_url.text())
    report("预设选中填模型", bool(win._llm_model.text()))
    win.close()

    # ---- 主窗口接线（ReviewArticleWindow 带 config 时不崩） ----
    from src.review_article_window import ReviewArticleWindow
    cfg_llm = make_cfg(enabled=True, base_url="https://api.deepseek.com",
                       api_key="sk-abc", model="deepseek-chat")
    wwin = ReviewArticleWindow(wm, data_file=os.path.join(tmp, "win.json"),
                               config=cfg_llm)
    report("文章窗口带config构建成功", wwin._gen is not None)
    # 未配置 key 时窗口也能打开并走模板
    wwin2 = ReviewArticleWindow(wm, data_file=os.path.join(tmp, "win2.json"),
                                config=cfg_off)
    wwin2.show()
    wwin2._regenerate()
    report("无key时文章窗口走模板不崩", wwin2._current is not None)
    wwin2.close()
    app.processEvents()

    print("=" * 50)
    print("LLM 接入测试：通过 {} 项，失败 {} 项".format(PASS, FAIL))
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
