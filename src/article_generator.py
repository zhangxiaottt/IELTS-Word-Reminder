# -*- coding: utf-8 -*-
"""每日复习文章生成模块

把最近几天学过的单词编进一篇连贯的英文短文：
1. 从词库取最近 N 天录入的单词（默认 3 天，最多 12 个）
2. 按词性（名词/动词/形容词/副词）匹配到「故事模板」的槽位，
   槽位周围的句子保证任意该词性的词都能语法正确填入
3. 每天的文章按日期归档到 data/articles.json，可换一篇、可回看历史

文章结构（dict）：
    {
        "date": "2026-09-04",      # 文章归属日期
        "title": "The Morning Market",
        "text": "段落1\n\n段落2...",  # 纯文本全文
        "words": [{"word","phonetic","meaning"}, ...],  # 文中实际用到的词
        "target_count": 12,        # 目标词总数
        "used_count": 5            # 文中用到的目标词数
    }
"""
import json
import os
import random
import re
from datetime import datetime, timedelta

from src.utils import get_data_dir

# 占位词：某词性没有可用目标词时用于补位，保证句子完整通顺
_FILLER = {
    "n": "book",
    "v": "look",
    "adj": "quiet",
    "adv": "slowly",
    "any": "thing",
}

# 词性识别：有道中文释义一般带 "n. / v. / adj." 等前缀
_POS_RE = re.compile(r"^\s*(n|v|vt|vi|adj|adv|prep|conj|pron|num|art|int)\.?\s*", re.I)
# 归一到三类核心词性（未识别默认名词）
_POS_MAP = {
    "n": "n", "v": "v", "vt": "v", "vi": "v",
    "adj": "adj", "adv": "adv",
}


def pos_of(meaning: str) -> str:
    """从中文释义提取词性（n/v/adj/adv/any），失败默认名词"""
    if not meaning:
        return "n"
    m = _POS_RE.match(meaning.strip())
    if m:
        return _POS_MAP.get(m.group(1).lower(), "n")
    return "n"


# --------------------------------------------------------------------------- #
# 故事模板池
# 每个主题 = 标题 + 若干片段；片段有两种：
#   ("……{}……", "词性")  带一个 {} 槽位，用该词性的目标词填入
#   ("……", None)         固定叙述文字（衔接剧情，让文章连贯）
# 槽位句子的写法保证：任意该词性的词都能语法自然填入。
# --------------------------------------------------------------------------- #
THEMES = [
    {
        "title": "The Morning Market",
        "parts": [
            ("Early on Saturday, Anna went to the morning market. ", None),
            ("The crowd made the old street feel alive; she noticed every {} around her.", "n"),
            ("She walked slowly and looked at everything with fresh eyes. ", None),
            ("The whole morning felt bright and {}.", "adj"),
            ("A young man sold fruit in a cheerful voice. ", None),
            ("Anna stopped to {} for a while before moving on.", "v"),
            ("When the sun rose higher, she picked a small gift. ", None),
            ("She chose a little {} and paid for it with a smile.", "n"),
            ("Walking home, she felt light and happy. ", None),
            ("It had been a truly {} morning.", "adj"),
        ],
    },
    {
        "title": "A Rainy Day",
        "parts": [
            ("The rain began at noon. ", None),
            ("Drops of water covered every {} on the street.", "n"),
            ("Mike stayed inside with a cup of hot tea. ", None),
            ("The room felt quiet and {}.", "adj"),
            ("He watched the window for a long time. ", None),
            ("Soon he decided to {} his homework.", "v"),
            ("Outside, the street was empty and grey. ", None),
            ("It was a {} afternoon.", "adj"),
            ("When evening came, the rain finally stopped. ", None),
            ("He put his {} on the table and smiled.", "n"),
        ],
    },
    {
        "title": "The Library Afternoon",
        "parts": [
            ("Lily spent her afternoon in the school library. ", None),
            ("She took out a {} from her bag and began to read.", "n"),
            ("The pages turned slowly in the quiet room. ", None),
            ("Everything felt {} and calm.", "adj"),
            ("Sometimes she stopped reading for a moment. ", None),
            ("She liked to {} before turning the page.", "v"),
            ("After an hour, she carried her books home. ", None),
            ("A small {} was under her arm.", "n"),
            ("Lily smiled as she walked. ", None),
            ("It was exactly the {} ending she needed.", "adj"),
        ],
    },
    {
        "title": "The Trip to the City",
        "parts": [
            ("Tom took the early bus to the city. ", None),
            ("The street was full of noise and {}.", "n"),
            ("He had a map in one hand and a ticket in the other. ", None),
            ("The tall buildings looked {}.", "adj"),
            ("For lunch he found a small restaurant. ", None),
            ("He ordered a bowl of noodles and began to {}.", "v"),
            ("In the afternoon, he walked along the river. ", None),
            ("He bought a {} from a small shop by the water.", "n"),
            ("On the way home, Tom thought about the day. ", None),
            ("It had been simple but {}.", "adj"),
        ],
    },
    {
        "title": "Cooking Dinner",
        "parts": [
            ("Mia decided to cook dinner for her family. ", None),
            ("She opened the fridge and took out a {}.", "n"),
            ("The kitchen smelled warm and sweet. ", None),
            ("Cooking always made her feel {}.", "adj"),
            ("She followed the recipe step by step. ", None),
            ("Carefully, she began to {} in the quiet kitchen.", "v"),
            ("Soon the whole house was full of a good smell. ", None),
            ("She put the {} on the table with pride.", "n"),
            ("At dinner, everyone smiled. ", None),
            ("Her parents said the meal was {}.", "adj"),
        ],
    },
    {
        "title": "The Evening Walk",
        "parts": [
            ("After dinner, Dad and I went for a walk. ", None),
            ("I picked up a tiny {} from the path and put it in my pocket.", "n"),
            ("The air was cool and fresh. ", None),
            ("The evening sky looked {}.", "adj"),
            ("We talked about small things and laughed. ", None),
            ("Sometimes we stopped to {} together.", "v"),
            ("On the way back, the moon came out. ", None),
            ("Dad found a {} and showed it to me.", "n"),
            ("I smiled all the way home. ", None),
            ("It was a simple, {} evening.", "adj"),
        ],
    },
    {
        "title": "The School Trip",
        "parts": [
            ("The whole class went on a school trip. ", None),
            ("Everyone carried a {} in their bag.", "n"),
            ("The bus left early in the morning. ", None),
            ("The weather was warm and {}.", "adj"),
            ("At the museum, the guide spoke clearly. ", None),
            ("The students listened and began to {}.", "v"),
            ("At lunch, they sat together under a tree. ", None),
            ("Someone shared a {} with the group.", "n"),
            ("By the end of the day, everyone was tired but happy. ", None),
            ("It was a {} day they would remember.", "adj"),
        ],
    },
    {
        "title": "The Busy Weekend",
        "parts": [
            ("This weekend was busier than usual. ", None),
            ("On Saturday morning, Tom found a {} in the drawer.", "n"),
            ("He worked until noon without stopping. ", None),
            ("The room finally looked {}.", "adj"),
            ("In the afternoon, his friend called. ", None),
            ("They decided to {} together in the park.", "v"),
            ("They talked and laughed for hours. ", None),
            ("Later, they bought a {} from a street stand.", "n"),
            ("By night, Tom felt tired but pleased. ", None),
            ("It had been a long, {} day.", "adj"),
        ],
    },
]


class ArticleGenerator:
    """每日复习文章生成器

    职责：
    - 取词：从词库取最近 N 天录入的单词
    - 生成：随机选一个故事模板，把单词按词性填入槽位
    - 归档：按日期读写 data/articles.json，支持换一篇与回看历史
    """

    def __init__(self, word_manager, data_file: str = None,
                 llm_client=None):
        self._wm = word_manager
        # 默认写到 data/articles.json；测试可传入临时文件避免污染真实数据
        self._file = data_file or os.path.join(get_data_dir(), "articles.json")
        self._store = self._load_store()
        # 可选：大模型客户端（OpenAI 兼容）。配置并启用时用 AI 写文章，
        # 未配置 / 调用失败时自动回落本地模板，保证始终能出文章。
        self._llm = llm_client

    # ------------------------------------------------------------------ #
    # 归档（data/articles.json，按日期索引）
    # ------------------------------------------------------------------ #
    def _load_store(self) -> dict:
        """读取本地文章归档；损坏/缺失返回空字典"""
        try:
            with open(self._file, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_store(self) -> None:
        """写回本地归档（失败仅跳过，不影响主流程）"""
        try:
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(self._store, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def save(self, date_str: str, article: dict) -> None:
        """保存某一天的文章到归档"""
        try:
            self._store[str(date_str)] = article
            self._save_store()
        except Exception:
            pass

    def load(self, date_str: str):
        """读取某一天的文章，不存在返回 None"""
        return self._store.get(str(date_str))

    # ------------------------------------------------------------------ #
    # 取词
    # ------------------------------------------------------------------ #
    def get_target_words(self, days: int = 3, limit: int = 12) -> list:
        """最近 N 天录入的单词（用于编入文章）"""
        try:
            return self._wm.get_recent_words(days=days, limit=limit)
        except Exception:
            return []

    # ------------------------------------------------------------------ #
    # 生成
    # ------------------------------------------------------------------ #
    def generate(self, date_str: str = None, seed=None,
                 days: int = 3, limit: int = 12) -> dict:
        """为指定日期生成一篇复习文章

        Args:
            date_str: 文章归属日期 "YYYY-MM-DD"（默认今天）
            seed: 随机种子（固定种子可复现；默认以日期为种子保证当天稳定）
            days: 取最近 N 天的词
            limit: 最多取多少个目标词
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
        # 先取词（AI 与模板两条路都要用）
        words = self.get_target_words(days=days, limit=limit)

        # AI 路径：配置了 LLM 且调用成功则用 AI 写文章；失败自动回落模板
        if self._llm is not None and self._llm.enabled():
            art = self._generate_with_llm(date_str, words)
            if art is not None:
                return art

        # 模板兜底路径（离线 / 未配置 key / AI 失败时使用）
        # 以日期为默认种子：同一天多次打开内容一致；传 seed 则换一篇
        rng = random.Random(seed if seed is not None else date_str)
        theme = rng.choice(THEMES)

        # 按词性分组并打乱，保证每次选的词更随机
        buckets = {"n": [], "v": [], "adj": [], "adv": [], "any": []}
        for row in words:
            buckets[pos_of(row.get("meaning", ""))].append(row)
        for key in buckets:
            rng.shuffle(buckets[key])

        used_ids, used, text = set(), [], []
        for part, pos in theme["parts"]:
            if not part:
                continue
            if "{}" not in part:
                text.append(part)
                continue
            token, row = self._pick_word(pos, buckets, used_ids)
            if row is not None:
                used_ids.add(row["id"])
                used.append(row)
            text.append(part.format(token))

        paragraphs = self._to_paragraphs(text, rng)
        return {
            "date": date_str,
            "title": theme["title"],
            "text": "\n\n".join(paragraphs),
            "words": [
                {"word": w["word"], "phonetic": w.get("phonetic", ""),
                 "meaning": w.get("meaning", "")}
                for w in used
            ],
            "target_count": len(words),
            "used_count": len(used),
            # 来源标记：模板生成。配了 AI 后旧模板文章会被升级成 AI 版
            "source": "template",
        }

    @staticmethod
    def _pick_word(pos: str, buckets: dict, used_ids: set):
        """从对应词性桶取一个未用过的目标词；该词性不足则退回「any」桶

        返回 (填入词, 单词行)；都无可用词时返回 (占位词, None)，保证句子完整。
        """
        order = ("any",) if pos == "any" else (pos, "any")
        for key in order:
            bucket = buckets.get(key, [])
            for i, row in enumerate(bucket):
                if row["id"] not in used_ids:
                    return row["word"], bucket.pop(i)
        return _FILLER.get(pos, _FILLER["any"]), None

    @staticmethod
    def _to_paragraphs(parts: list, rng: random.Random) -> list:
        """把句子片段按 2~3 句一段打包成自然段落"""
        paras, cur = [], []
        for i, seg in enumerate(parts):
            cur.append(seg)
            size = rng.randint(2, 3)
            if len(cur) >= size or i == len(parts) - 1:
                paras.append("".join(cur).strip())
                cur = []
        return paras

    # ------------------------------------------------------------------ #
    # AI 生成路径
    # ------------------------------------------------------------------ #
    @staticmethod
    def _llm_messages(words: list) -> list:
        """构造让大模型写复习文章的对话消息"""
        word_list = "\n".join(
            "- {w}  [{p}]  {m}".format(
                w=w.get("word", ""), p=w.get("phonetic", "") or "",
                m=w.get("meaning", "") or "")
            for w in words
        )
        system = (
            "You are an English writing assistant for an IELTS vocabulary "
            "review app. Write ONE short, coherent, natural English story "
            "(150-220 words, 2-4 short paragraphs) that uses as many of the "
            "given words as possible, each in a grammatically correct way. "
            "Keep the language simple and clear for an intermediate learner. "
            "Respond ONLY with JSON (no markdown fences), with exactly three "
            'keys: "title" (a short title), "text" (the story, paragraphs '
            'separated by a blank line), "used_words" (array of the exact '
            "given words you used, in order of first appearance)."
        )
        user = (
            "Here are the words to use (word | phonetic | meaning):\n"
            + word_list + "\n\nNow write the story."
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def _generate_with_llm(self, date_str: str, words: list):
        """用大模型生成文章；成功返回文章 dict，失败返回 None（走模板兜底）"""
        try:
            content = self._llm.complete(self._llm_messages(words))
        except Exception:
            content = None
        if not content:
            return None
        parsed = self._parse_llm_article(content)
        if not parsed:
            return None
        # 用到的词以“正文中出现”为准（即便模型漏了 used_words 也能补齐词表）
        used = self._match_words_in_text(parsed["text"], words)
        return {
            "date": date_str,
            "title": parsed["title"],
            "text": parsed["text"],
            "words": [
                {"word": w["word"], "phonetic": w.get("phonetic", ""),
                 "meaning": w.get("meaning", "")}
                for w in used
            ],
            "target_count": len(words),
            "used_count": len(used),
            # 来源标记：AI 生成（与模板区分，用于缓存刷新判断）
            "source": "llm",
        }

    @staticmethod
    def _parse_llm_article(content: str):
        """宽松解析模型返回的 JSON（容忍 markdown 围栏 / 多余文字）"""
        try:
            data = json.loads(content)
        except Exception:
            m = re.search(r"\{[\s\S]*\}", content)
            if not m:
                return None
            try:
                data = json.loads(m.group(0))
            except Exception:
                return None
        if not isinstance(data, dict):
            return None
        title = str(data.get("title", "")).strip()
        text = str(data.get("text", "")).strip()
        if not title or not text:
            return None
        return {"title": title, "text": text}

    @staticmethod
    def _match_words_in_text(text: str, words: list) -> list:
        """找出正文中实际出现的目标词（支持常见词形变化）

        策略：把正文按单词切分成 token（小写），一个词命中当且仅当
        - token 与词完全相等，或
        - token 以词开头且剩余部分是常见词缀（ed/ing/s/ly/er/est 等）
        这样模型写成 abandoned / swiftly / buses 时，词表仍能挂回库里的原词。
        """
        tokens = re.findall(r"[a-z]+", text.lower())
        # 常见英文词形变化后缀（用于判断 token 是否为原词的变形）
        inflections = {
            "s", "es", "ed", "d", "ing", "ies", "ly", "er", "est", "ied",
            "en", "erly",
        }
        used = []
        for w in words:
            word = str(w.get("word", "")).strip()
            wl = word.lower()
            if not wl:
                continue
            if wl in tokens:
                used.append(w)
            elif len(wl) >= 3 and any(
                t.startswith(wl) and t[len(wl):] in inflections
                for t in tokens
            ):
                used.append(w)
        return used

    # ------------------------------------------------------------------ #
    # 对外便捷接口
    # ------------------------------------------------------------------ #
    def get_or_generate(self, date_str: str = None, seed=None,
                        days: int = 3, limit: int = 12) -> dict:
        """读取某天文章；没有则生成并存档（换一篇时传新 seed 覆盖）

        缓存刷新规则：若当天存档是「模板版」，而现在已启用 AI，
        则自动用 AI 重生成并覆盖（让配了 AI 后文章立即升级成 AI 版）；
        已是 AI 版或未启用 AI 时直接返回存档，保证同一天内容稳定。
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
        art = self.load(date_str)
        if art is None:
            art = self.generate(date_str=date_str, seed=seed, days=days, limit=limit)
            self.save(date_str, art)
            return art
        # 已有存档且之前是模板版、现在启用了 AI -> 用 AI 重生成升级
        llm_on = self._llm is not None and self._llm.enabled()
        if llm_on and art.get("source") != "llm":
            fresh = self.generate(date_str=date_str, seed=seed, days=days, limit=limit)
            # 只有真的生成了 AI 版才覆盖存档（AI 失败回落模板时不覆盖，保留原档）
            if fresh.get("source") == "llm":
                self.save(date_str, fresh)
                return fresh
        return art

    @staticmethod
    def date_before(date_str: str) -> str:
        """返回某天的前一天（"YYYY-MM-DD"）"""
        d = datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)
        return d.strftime("%Y-%m-%d")

    @staticmethod
    def date_after(date_str: str) -> str:
        """返回某天的后一天（"YYYY-MM-DD"）"""
        d = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)
        return d.strftime("%Y-%m-%d")
