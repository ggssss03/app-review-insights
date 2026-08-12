"""LLM 适配器：OpenAI 兼容 Chat Completions（DeepSeek/OpenAI/Qwen/Ollama 通用）。

- 用标准库 urllib 实现，避免 M2 阶段额外依赖；
- 强制 JSON 输出 + 重试 + 超时；
- MockLLM 用于离线测试，生产可换成任意 OpenAI 兼容服务。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Optional


class LLMError(Exception):
    """模型调用失败（网络/鉴权/解析等）。"""


def parse_json_content(content: str) -> dict:
    """解析模型返回的 JSON，容忍 markdown 代码围栏与前后噪声。"""
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise LLMError(f"模型输出不是合法 JSON：{content[:200]!r}")


class LLMClient:
    def __init__(
        self,
        *,
        provider: str = "deepseek",
        base_url: str = "https://api.deepseek.com",
        api_key: str = "",
        model: str = "deepseek-chat",
        temperature: float = 0.3,
        timeout: int = 60,
        max_retries: int = 2,
    ):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.max_retries = max_retries

    def chat_json(self, messages: list[dict], *, max_tokens: int = 2000) -> dict:
        url = self.base_url if self.base_url.endswith("/chat/completions") else f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                return parse_json_content(content)
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):
                    raise LLMError(f"LLM 鉴权失败（HTTP {exc.code}），请检查 LLM_API_KEY") from exc
                last_error = exc
                if exc.code == 429 or exc.code >= 500:
                    time.sleep(2**attempt)
                    continue
                raise LLMError(f"LLM HTTP {exc.code}：{exc.reason}") from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
                last_error = exc
                time.sleep(2**attempt)
        raise LLMError(f"LLM 调用失败（已重试 {self.max_retries} 次）：{last_error}")


class MockLLM:
    """离线测试用：responder 接收 messages，返回 dict 或抛出异常。"""

    def __init__(self, responder: Callable[[list[dict]], dict]):
        self.responder = responder

    def chat_json(self, messages: list[dict], *, max_tokens: int = 2000) -> dict:
        return self.responder(messages)
