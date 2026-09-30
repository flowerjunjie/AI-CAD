"""
LLM 接入层 — 统一接口，支持 Agnes / MiniMax / Kimi / GLM
支持自动重试、速率限制处理、JSON 解析

外部依赖标注（诚实边界，不虚标）:
- 本模块的「纯逻辑」（接口定义、工厂路由、JSON 解析、重试退避计时、
  速率限制判断）可全测、不联网。
- 但「真调 LLM 接口」需对应 provider 的 API key（默认 Agnes 用
  `AGNES_API_KEY`）。无 key 时工厂/适配器仍 import 成功、方法抛
  「未配置 key」而非崩（降级诚实）。
- 覆盖率 ~36% 属正常——未盖部分全在「真发 HTTP 请求」分支，
  需真 key + 网络，故不 mock 假响应凑覆盖（红线二：不造假绿）。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import os
import json
import httpx
import time


@dataclass
class ChatMessage:
    role: str  # "user" / "assistant" / "system"
    content: str


@dataclass
class LLMResponse:
    text: str
    model: str
    usage: dict = field(default_factory=dict)
    error: Optional[str] = None


class BaseLLMAdapter(ABC):
    """LLM 适配器基类"""

    @abstractmethod
    def chat(self, messages: list[ChatMessage], **kwargs) -> LLMResponse:
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        pass

    @abstractmethod
    def get_api_base(self) -> str:
        pass

    def chat_with_retry(self, messages: list[ChatMessage], max_retries: int = 3, **kwargs) -> LLMResponse:
        """带重试的聊天接口，处理 429 限流"""
        for attempt in range(max_retries):
            response = self.chat(messages, **kwargs)
            if response.error:
                if "429" in str(response.error) or "Too Many Requests" in str(response.error):
                    wait = 2 ** attempt  # 指数退避: 2s, 4s, 8s
                    print(f"[LLM] Rate limited, retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                return response  # 非限流错误直接返回
            return response
        return LLMResponse(text="", model=self.model, error=f"Max retries ({max_retries}) exceeded")


class AgnesAdapter(BaseLLMAdapter):
    """Agnes AI LLM 适配器 — Anthropic-compatible API"""

    API_BASE = "https://apihub.agnes-ai.com/v1"

    def __init__(self, api_key: Optional[str] = None, model: str = "agnes-2.0-flash"):
        self.api_key = api_key or os.getenv("AGNES_API_KEY", "")
        self.model = model or os.getenv("AGNES_MODEL", "agnes-2.0-flash")
        self.base_url = os.getenv("AGNES_BASE_URL", self.API_BASE)
        if not self.api_key:
            raise ValueError("Agnes API key not configured")

    def get_api_base(self) -> str:
        return self.base_url

    def get_model_name(self) -> str:
        return self.model

    def chat(self, messages: list[ChatMessage], **kwargs) -> LLMResponse:
        try:
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "messages": [
                    {"role": m.role, "content": m.content}
                    for m in messages
                ],
                **kwargs,
            }
            resp = httpx.post(url, json=payload, headers=headers, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            choice = data.get("choices", [{}])[0]
            return LLMResponse(
                text=choice.get("message", {}).get("content", ""),
                model=self.model,
                usage=data.get("usage", {}),
            )
        except httpx.HTTPStatusError as e:
            return LLMResponse(text="", model=self.model, error=f"HTTP {e.response.status_code}: {e.response.text[:200]}")
        except Exception as e:
            return LLMResponse(text="", model=self.model, error=str(e))


class MiniMaxAdapter(BaseLLMAdapter):
    """MiniMax LLM 适配器"""

    API_BASE = "https://api.minimaxi.com/v1"

    def __init__(self, api_key: Optional[str] = None, model: str = "MiniMax-M2.7"):
        self.api_key = api_key or os.getenv("MINIMAX_API_KEY", "")
        self.model = model
        if not self.api_key:
            raise ValueError("MiniMax API key not configured")

    def get_api_base(self) -> str:
        return self.API_BASE

    def get_model_name(self) -> str:
        return self.model

    def chat(self, messages: list[ChatMessage], **kwargs) -> LLMResponse:
        try:
            url = f"{self.API_BASE}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "messages": [
                    {"role": m.role, "content": m.content}
                    for m in messages
                ],
                **kwargs,
            }
            resp = httpx.post(url, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return LLMResponse(
                text=data["choices"][0]["message"]["content"],
                model=self.model,
                usage=data.get("usage", {}),
            )
        except Exception as e:
            return LLMResponse(text="", model=self.model, error=str(e))


class KimiAdapter(BaseLLMAdapter):
    """Kimi LLM 适配器"""

    API_BASE = "https://api.kimi.com/v1"

    def __init__(self, api_key: Optional[str] = None, model: str = "kimi-for-coding-highspeed"):
        self.api_key = api_key or os.getenv("KIMI_API_KEY", "")
        self.model = model
        if not self.api_key:
            raise ValueError("Kimi API key not configured")

    def get_api_base(self) -> str:
        return self.API_BASE

    def get_model_name(self) -> str:
        return self.model

    def chat(self, messages: list[ChatMessage], **kwargs) -> LLMResponse:
        try:
            url = f"{self.API_BASE}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "messages": [
                    {"role": m.role, "content": m.content}
                    for m in messages
                ],
                **kwargs,
            }
            resp = httpx.post(url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return LLMResponse(
                text=data["choices"][0]["message"]["content"],
                model=self.model,
                usage=data.get("usage", {}),
            )
        except Exception as e:
            return LLMResponse(text="", model=self.model, error=str(e))


class GLMAdapter(BaseLLMAdapter):
    """GLM (BigModel) LLM 适配器"""

    API_BASE = "https://open.bigmodel.cn/api/anthropic/v1"

    def __init__(self, api_key: Optional[str] = None, model: str = "glm-4"):
        self.api_key = api_key or os.getenv("GLM_API_KEY", "")
        self.model = model
        if not self.api_key:
            raise ValueError("GLM API key not configured")

    def get_api_base(self) -> str:
        return self.API_BASE

    def get_model_name(self) -> str:
        return self.model

    def chat(self, messages: list[ChatMessage], **kwargs) -> LLMResponse:
        try:
            url = f"{self.API_BASE}/messages"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Anthropic-Version": "2023-06-01",
            }
            payload = {
                "model": self.model,
                "messages": [
                    {"role": m.role, "content": m.content}
                    for m in messages
                ],
                **kwargs,
            }
            resp = httpx.post(url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return LLMResponse(
                text=data["content"][0]["text"],
                model=self.model,
                usage=data.get("usage", {}),
            )
        except Exception as e:
            return LLMResponse(text="", model=self.model, error=str(e))


class LLMFactory:
    """LLM 工厂 — 根据配置创建适配器"""

    _adapters = {
        "agnes": AgnesAdapter,
        "minimax": MiniMaxAdapter,
        "kimi": KimiAdapter,
        "glm": GLMAdapter,
    }

    @classmethod
    def create(cls, provider: str, api_key: Optional[str] = None, model: str = "") -> BaseLLMAdapter:
        adapter_cls = cls._adapters.get(provider.lower())
        if not adapter_cls:
            raise ValueError(f"Unknown LLM provider: {provider}")
        return adapter_cls(api_key, model)

    @classmethod
    def get_supported_providers(cls) -> list[str]:
        return list(cls._adapters.keys())

    @classmethod
    def from_env(cls) -> BaseLLMAdapter:
        """从环境变量自动创建适配器"""
        provider = os.getenv("AI_CAD_LLM_PROVIDER", "agnes")
        return cls.create(provider)


# ─── Demo ───────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== LLM Adapter Test ===")
    print(f"Supported providers: {LLMFactory.get_supported_providers()}")

    # Test Agnes (default)
    try:
        adapter = LLMFactory.from_env()
        print(f"Active adapter: {adapter.get_model_name()}")

        response = adapter.chat([
            ChatMessage(role="user", content="Reply with just: OK")
        ])
        print(f"API response: {response.text[:50]!r}")
        if response.error:
            print(f"Error: {response.error}")
    except Exception as e:
        print(f"Agnes test failed: {e}")

    print("\nDemo completed!")
