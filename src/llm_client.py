# -*- coding: utf-8 -*-
"""大模型 API 客户端（LLMClient）—— OpenAI 兼容、厂商无关

候选厂商（DeepSeek / 豆包·火山方舟 / 通义千问 / 智谱 GLM 等）都提供
OpenAI 兼容的 POST {base_url}/chat/completions 接口，因此换厂商只需改
base_url / api_key / model 三项，代码零改动。

设计原则：
- 只依赖 requests（项目已内置），不引入额外依赖
- 任何网络/解析异常都被捕获，对外返回 None 或 (False, 信息)，绝不让程序崩溃
- 配置实时从 ConfigManager 读取，设置窗口改动即时生效（无需重启）
"""
import requests

DEFAULT_TIMEOUT = 15  # 生成一篇短文要给足时间；网络失败等 15 秒即返回


class LLMClient:
    """OpenAI 兼容大模型客户端"""

    def __init__(self, config=None):
        """Args:
            config: ConfigManager 实例；为 None 时始终视为未启用
        """
        self._config = config

    # ------------------------------------------------------------------ #
    # 配置读取
    # ------------------------------------------------------------------ #
    def _g(self, key: str, default):
        """安全读取配置（config 为 None 或读取异常时返回默认值）"""
        if self._config is None:
            return default
        try:
            return self._config.get(key, default)
        except Exception:
            return default

    def settings(self) -> dict:
        """返回当前生效的连接参数"""
        return {
            "enabled": bool(self._g("llm.enabled", False)),
            "base_url": str(self._g("llm.base_url", "") or "").strip(),
            "api_key": str(self._g("llm.api_key", "") or "").strip(),
            "model": str(self._g("llm.model", "") or "").strip(),
        }

    def enabled(self) -> bool:
        """是否启用且参数齐全（启用 + 地址 + 密钥 + 模型名都非空）"""
        s = self.settings()
        return bool(s["enabled"] and s["base_url"] and s["api_key"] and s["model"])

    # ------------------------------------------------------------------ #
    # 请求
    # ------------------------------------------------------------------ #
    def _request(self, messages: list, temperature: float = 0.7,
                 max_tokens: int = 800) -> str:
        """执行一次 chat/completions 请求，返回助手文本；异常向上抛给调用方"""
        s = self.settings()
        if not (s["base_url"] and s["api_key"] and s["model"]):
            raise ValueError("请先填写接口地址 / API Key / 模型名")
        url = s["base_url"].rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": "Bearer " + s["api_key"],
            "Content-Type": "application/json",
        }
        payload = {
            "model": s["model"],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        resp = requests.post(url, headers=headers, json=payload,
                             timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()  # 非 2xx 会抛 HTTPError
        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except Exception:
            raise ValueError("模型响应格式异常")
        if not isinstance(content, str):
            raise ValueError("模型返回内容不是文本")
        return content

    def complete(self, messages: list, temperature: float = 0.7,
                 max_tokens: int = 800):
        """对外主入口：成功返回助手文本，失败返回 None（不抛异常）"""
        try:
            return self._request(messages, temperature, max_tokens)
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # 连接测试（供设置窗口「测试连接」按钮使用）
    # ------------------------------------------------------------------ #
    def test_connection(self, base_url: str = None, api_key: str = None,
                        model: str = None):
        """用给定参数（或当前配置）发一条极简消息，返回 (成功?, 提示文本)

        Args:
            base_url / api_key / model: 设置窗口测试时传入输入框当前值，
                未保存也可直接测；为 None 时使用配置里的值。
        """
        cfg = self.settings()
        base_url = (base_url if base_url is not None else cfg["base_url"]).strip()
        api_key = (api_key if api_key is not None else cfg["api_key"]).strip()
        model = (model if model is not None else cfg["model"]).strip()
        if not (base_url and api_key and model):
            return False, "请先填写接口地址 / API Key / 模型名"
        url = base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "只回复两个字：正常"}],
            "temperature": 0,
            "max_tokens": 10,
        }
        try:
            resp = requests.post(url, headers=headers, json=payload,
                                 timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            return True, "连接成功，模型回复：" + (str(text)[:20])
        except Exception as e:
            return False, "连接失败：" + str(e)

