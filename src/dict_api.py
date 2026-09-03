# -*- coding: utf-8 -*-
"""词典 API 模块 - DictAPI

封装有道免费词典接口，输入英文单词返回音标、中文释义、英文例句。
返回格式统一为：{"phonetic": "", "meaning": "", "example": ""}
规则：
- 网络请求超时 3 秒
- 查询失败、单词不存在均返回空字典，绝不抛出异常
- 单例模式，避免重复初始化与重复创建会话
"""
import re

import requests


class DictAPI:
    """有道词典 API 封装（单例）

    查询策略：
    1. 优先调用有道 jsonapi 接口（含音标、释义、双语例句，信息最全）
    2. 失败时回退到 suggest 联想接口（含音标、释义）
    3. 仍失败则返回空字典
    """

    _instance = None  # 单例实例

    # 有道词典免费接口地址
    _JSONAPI_URL = "https://dict.youdao.com/jsonapi"
    _SUGGEST_URL = "https://dict.youdao.com/suggest"

    _TIMEOUT = 3  # 网络超时时间（秒）

    def __new__(cls):
        """单例：整个程序只创建一个实例，复用 requests.Session"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # 初始化一次会话，统一请求头，减少握手开销
            cls._instance._session = requests.Session()
            cls._instance._session.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.youdao.com/",
            })
        return cls._instance

    # ------------------------------------------------------------------ #
    # 对外查询入口
    # ------------------------------------------------------------------ #
    def query(self, word: str) -> dict:
        """查询英文单词，返回 {"phonetic", "meaning", "example"}

        Args:
            word: 待查询的英文单词
        Returns:
            dict: 查询成功返回解析结果；失败或不存在返回空字典
        """
        word = (word or "").strip().lower()
        if not word:
            return {}

        # 1. 优先 jsonapi（信息最全）
        result = self._query_jsonapi(word)
        if result:
            return result

        # 2. 回退 suggest 联想接口
        result = self._query_suggest(word)
        if result:
            return result

        # 3. 全部失败，返回空字典
        return {}

    # ------------------------------------------------------------------ #
    # 内部实现：jsonapi 接口（含例句）
    # ------------------------------------------------------------------ #
    def _query_jsonapi(self, word: str) -> dict:
        """调用 jsonapi 接口，解析音标/释义/双语例句"""
        try:
            resp = self._session.get(
                self._JSONAPI_URL, params={"q": word}, timeout=self._TIMEOUT
            )
            if resp.status_code != 200:
                return {}
            data = resp.json()

            phonetic = self._extract_phonetic(data)
            meaning = self._extract_meaning(data)
            example = self._extract_example(data)

            if not meaning and not phonetic and not example:
                return {}
            return {"phonetic": phonetic, "meaning": meaning, "example": example}
        except Exception:
            # 网络异常 / 解析失败均不抛出
            return {}

    @staticmethod
    def _extract_phonetic(data: dict) -> str:
        """从 jsonapi 响应中提取音标（优先英式，其次美式）"""
        try:
            word_arr = data.get("ec", {}).get("word") or []
            if word_arr:
                w = word_arr[0]
                uk = (w.get("ukphone") or "").strip()
                us = (w.get("usphone") or "").strip()
                return uk or us
        except Exception:
            pass
        # 回退：短语区音标
        try:
            phrs = data.get("phrs", {}).get("phrs") or []
            if phrs:
                return (phrs[0].get("p") or "").strip()
        except Exception:
            pass
        return ""

    @staticmethod
    def _extract_meaning(data: dict) -> str:
        """从 jsonapi 响应中提取中文释义（拼接多个词性释义）

        有道返回结构：ec.word[].trs[].tr[].l.i 为「字符串列表」，
        部分接口可能返回「字典列表」，两种都兼容处理。
        """
        try:
            trs = data.get("ec", {}).get("word", [{}])[0].get("trs") or []
            parts = []
            for tr in trs:
                items = tr.get("tr", [{}])[0].get("l", {}).get("i", [])
                if not items:
                    continue
                item = items[0]
                if isinstance(item, dict):
                    text = item.get("t") or ""
                else:
                    text = str(item)
                # 提取「词性. 释义」部分（去掉序号/括号干扰）
                text = re.sub(r"^\d+\.\s*", "", text.strip())
                if text:
                    parts.append(text)
            return "；".join(parts) if parts else ""
        except Exception:
            return ""

    @staticmethod
    def _extract_example(data: dict) -> str:
        """从 jsonapi 响应中提取首条双语例句（英文 + 中文）"""
        try:
            pairs = data.get("blng_sents_part", {}).get("sentence-pair") or []
            if not pairs:
                return ""
            first = pairs[0]
            en = (first.get("sentence") or "").strip()
            zh = (first.get("sentence-translation") or "").strip()
            if not en:
                return ""
            if zh:
                return "{}  {}".format(en, zh)
            return en
        except Exception:
            return ""

    # ------------------------------------------------------------------ #
    # 内部实现：suggest 联想接口（音标 + 释义）
    # ------------------------------------------------------------------ #
    def _query_suggest(self, word: str) -> dict:
        """调用 suggest 联想接口，解析音标与释义"""
        try:
            resp = self._session.get(
                self._SUGGEST_URL,
                params={
                    "num": 5,
                    "ver": "3.0",
                    "doctype": "json",
                    "cache": "false",
                    "le": "en",
                    "q": word,
                },
                timeout=self._TIMEOUT,
            )
            if resp.status_code != 200:
                return {}
            data = resp.json()
            entries = (data.get("data") or {}).get("entries") or []
            if not entries:
                return {}
            entry = entries[0]
            # 音标：优先英式
            pronounce = entry.get("pronounce") or {}
            phonetic = (pronounce.get("uk") or pronounce.get("ame") or "").strip()
            # 释义：explain 字段优先
            meaning = (entry.get("explain") or "").strip()
            if not meaning:
                trans = entry.get("translation") or []
                meaning = (trans[0] if trans else "").strip()
            if not meaning and not phonetic:
                return {}
            return {"phonetic": phonetic, "meaning": meaning, "example": ""}
        except Exception:
            return {}
