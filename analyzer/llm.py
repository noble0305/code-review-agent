"""LLM abstraction layer — supports multiple providers."""
import os
import json
import logging
from typing import Optional, Generator

logger = logging.getLogger(__name__)


class LLMConfig:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "openai")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.base_url = os.getenv("LLM_BASE_URL", "")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", "2048"))
        self.timeout = int(os.getenv("LLM_TIMEOUT", "60"))


class LLMClient:
    """Unified LLM client with provider abstraction."""

    def __init__(self, config: LLMConfig = None):
        self.config = config or LLMConfig()
        self._client = None

    @property
    def available(self) -> bool:
        """Check if LLM is configured and available."""
        if self.config.provider == "ollama":
            return True
        return bool(self.config.api_key)

    @property
    def provider(self) -> str:
        return self.config.provider

    @property
    def model(self) -> str:
        return self.config.model

    def _get_client(self):
        """Lazy init provider client."""
        if self._client is not None:
            return self._client

        provider = self.config.provider

        if provider == "openai":
            from openai import OpenAI
            kwargs = {"api_key": self.config.api_key}
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client = OpenAI(**kwargs)

        elif provider == "anthropic":
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.config.api_key)

        elif provider == "ollama":
            from openai import OpenAI
            self._client = OpenAI(
                api_key="ollama",
                base_url=self.config.base_url or "http://localhost:11434/v1"
            )

        elif provider == "zhipu":
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self.config.api_key,
                base_url="https://open.bigmodel.cn/api/paas/v4"
            )

        else:
            # fallback: treat as openai-compatible
            from openai import OpenAI
            kwargs = {"api_key": self.config.api_key}
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client = OpenAI(**kwargs)

        return self._client

    def chat(self, system: str, user: str) -> str:
        """Single-turn chat, return full text."""
        if not self.available:
            return ""
        try:
            client = self._get_client()

            if self.config.provider == "anthropic":
                resp = client.messages.create(
                    model=self.config.model,
                    max_tokens=self.config.max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}]
                )
                return resp.content[0].text

            resp = client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ],
                max_tokens=self.config.max_tokens,
                stream=False,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            logger.error("LLM chat error: %s", e)
            return ""

    def chat_stream(self, system: str, user: str) -> Generator[str, None, None]:
        """Streaming chat, yield text chunks."""
        if not self.available:
            return
        try:
            client = self._get_client()

            if self.config.provider == "anthropic":
                import anthropic
                with client.messages.stream(
                    model=self.config.model,
                    max_tokens=self.config.max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}]
                ) as stream:
                    for text in stream.text_stream:
                        yield text
                return

            resp = client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ],
                max_tokens=self.config.max_tokens,
                stream=True,
            )
            for chunk in resp:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
        except Exception as e:
            logger.error("LLM stream error: %s", e)
            yield f"\n\n⚠️ LLM 调用出错: {e}"


# Singleton
_default_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
