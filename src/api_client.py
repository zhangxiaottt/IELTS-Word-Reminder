# -*- coding: utf-8 -*-
"""Java 服务层 HTTP 客户端 - ApiClient

混合架构的桥接层：
- Python 界面层（Qt）通过本模块调用 Java 服务层（LocalServer，默认 127.0.0.1:21001）
- Java 服务层承载：配置管理 / 单词库 CRUD / 复习算法 / 有道词典 / 大模型 / 每日文章
- 本模块所有方法都做超时 + 异常兜底：服务不可用时返回 None/False/空列表，
  调用方（各窗口）再回退到 Python 本地实现，保证程序离线也能用。

响应约定（Java 端统一格式）：
    {"code": 0, "data": ...}   成功
    {"code": 1, "msg": "..."}  失败
"""
import json
import socket
import time

import requests

# Java 服务默认端口与探测范围（与 LocalServer.DEFAULT_PORT 保持一致）
DEFAULT_PORT = 21001
MAX_PORT_PROBE = 5
HTTP_TIMEOUT = 3.0  # 秒


class ApiClient:
    """Java 服务层客户端（单例）"""

    _instance = None

    @classmethod
    def get_instance(cls) -> "ApiClient":
        """单例：避免重复初始化端口探测"""
        if cls._instance is None:
            cls._instance = ApiClient()
        return cls._instance

    def __init__(self, host: str = "127.0.0.1", port: int = None):
        self.host = host
        self.port = port or self._probe_port(host)
        self.base_url = "http://{}:{}".format(self.host, self.port)
        # 请求会话（复用连接，加快多次调用）
        self._session = requests.Session()

    # ------------------------------------------------------------------ #
    # 端口探测与健康检查
    # ------------------------------------------------------------------ #
    @staticmethod
    def _probe_port(host: str, start: int = None) -> int:
        """探测 Java 服务实际监听的端口（顺延机制与 Java 端一致）"""
        start = start or DEFAULT_PORT
        for port in range(start, start + MAX_PORT_PROBE):
            try:
                with socket.create_connection((host, port), timeout=0.5):
                    return port
            except OSError:
                continue
        return start  # 探不到也返回默认端口，请求会快速失败走兜底

    def ping(self) -> bool:
        """健康检查：GET /api/health"""
        try:
            data = self._get("/api/health")
            return bool(data and data.get("status") == "ok")
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # HTTP 基础
    # ------------------------------------------------------------------ #
    def _request(self, method: str, path: str, params: dict = None,
                 body: dict = None) -> dict:
        """发请求并解析响应；任何异常/非预期格式都返回 None（不抛出）"""
        try:
            url = self.base_url + path
            resp = self._session.request(
                method, url, params=params, json=body, timeout=HTTP_TIMEOUT
            )
            payload = resp.json()
            if payload.get("code") != 0:
                return None
            return payload.get("data")
        except Exception:
            return None

    def _get(self, path: str, params: dict = None) -> dict:
        return self._request("GET", path, params=params)

    def _post(self, path: str, body: dict = None) -> dict:
        return self._request("POST", path, body=body)

    def _put(self, path: str, body: dict = None) -> dict:
        return self._request("PUT", path, body=body)

    def _delete(self, path: str, body: dict = None) -> dict:
        return self._request("DELETE", path, body=body)

    # ------------------------------------------------------------------ #
    # 单词库
    # ------------------------------------------------------------------ #
    def add_word(self, word: str, phonetic: str = "", meaning: str = "",
                 example: str = "") -> dict:
        """录入单词；成功返回单词行 dict，失败返回 None"""
        return self._post("/api/words", {
            "word": word, "phonetic": phonetic,
            "meaning": meaning, "example": example,
        })

    def update_word(self, word_id: int, data: dict) -> bool:
        """修改单词信息"""
        return self._put("/api/words/{}".format(word_id), data) is not None

    def delete_word(self, word_id: int) -> bool:
        """删除单个单词"""
        return self._delete("/api/words/{}".format(word_id)) is not None

    def delete_words(self, word_ids) -> bool:
        """批量删除单词"""
        return self._delete("/api/words/batch", {"ids": list(word_ids)}) is not None

    def get_words(self, keyword: str = None, date_from: str = None,
                  date_to: str = None) -> list:
        """查询单词列表（支持关键词 / 录入时间范围筛选）"""
        data = self._get("/api/words", {
            "keyword": keyword or "", "date_from": date_from or "",
            "date_to": date_to or "",
        })
        return data if isinstance(data, list) else []

    def get_review_list(self) -> list:
        """获取复习列表（昨日新词 → 近5天 → 历史随机）"""
        data = self._get("/api/review/list")
        return data if isinstance(data, list) else []

    def get_random_words(self, limit: int = 10, max_familiar: int = 100) -> list:
        """随机取词（测试模式用），可限制熟悉度上限"""
        data = self._get("/api/words/random",
                         {"limit": limit, "max_familiar": max_familiar})
        return data if isinstance(data, list) else []

    def mark_familiar(self, word_id: int, known: bool) -> bool:
        """标记认识/不认识，更新熟悉度与复习次数"""
        return self._post("/api/words/{}/familiar".format(word_id),
                          {"known": bool(known)}) is not None

    # ------------------------------------------------------------------ #
    # 词典
    # ------------------------------------------------------------------ #
    def query_dict(self, word: str) -> dict:
        """查询有道词典；失败返回 None（调用方回落本地 DictAPI）"""
        return self._get("/api/dict", {"word": word or ""})

    # ------------------------------------------------------------------ #
    # 每日文章（LLM 生成）
    # ------------------------------------------------------------------ #
    def get_article(self, date: str = None) -> dict:
        """读取某天已生成的文章；不存在返回 None"""
        return self._get("/api/article", {"date": date or ""})

    def generate_article(self, date: str = None, seed: str = None,
                         days: int = 3, limit: int = 12) -> dict:
        """生成/获取当天复习文章（Java 端优先 AI，失败回落模板）"""
        return self._post("/api/article/generate", {
            "date": date, "seed": seed, "days": days, "limit": limit,
        })

    # ------------------------------------------------------------------ #
    # 配置与大模型
    # ------------------------------------------------------------------ #
    def config_set(self, key: str, value) -> bool:
        """写配置（点号路径），Java 端保存到 config/config.json"""
        return self._post("/api/config/set", {"key": key, "value": value}) is not None

    def config_get(self) -> dict:
        """读取完整配置"""
        data = self._get("/api/config")
        return data if isinstance(data, dict) else {}

    def test_llm(self, base_url: str = None, api_key: str = None,
                 model: str = None) -> tuple:
        """测试大模型连接；返回 (是否成功, 提示文本)"""
        data = self._get("/api/llm/test", {
            "base_url": base_url or "", "api_key": api_key or "",
            "model": model or "",
        })
        if data is None:
            return False, "Java 服务不可用，无法测试连接"
        return bool(data.get("ok")), str(data.get("message", ""))


def wait_java_ready(timeout: float = 5.0) -> bool:
    """等待 Java 服务就绪（供 main.py 启动子进程后轮询）"""
    client = ApiClient.get_instance()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if client.ping():
            return True
        time.sleep(0.2)
    return False
