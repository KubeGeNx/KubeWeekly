from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger(__name__)

# DeepSeek's API is OpenAI-compatible (chat completions), so it's reached via
# the `openai` SDK pointed at DeepSeek's base_url rather than the Anthropic
# SDK. This module is the seam between the two: every pipeline stage talks to
# LLMClient.complete(), never to a provider SDK directly.

# Model defaults per provider live in kubeweekly.config.PROVIDER_DEFAULTS,
# not here - this module only knows how to reach each provider's API.
DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class LLMClient(Protocol):
    def complete(self, system: str, user_content: str, max_tokens: int, model: str) -> str: ...


class ClaudeClient:
    def __init__(self, api_key: str):
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, system: str, user_content: str, max_tokens: int, model: str) -> str:
        response = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        return "".join(block.text for block in response.content if block.type == "text").strip()


class DeepSeekClient:
    def __init__(self, api_key: str):
        import openai

        self._client = openai.OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)

    def complete(self, system: str, user_content: str, max_tokens: int, model: str) -> str:
        response = self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
        )
        return (response.choices[0].message.content or "").strip()


def build_llm_client(provider: str, api_key: str) -> LLMClient:
    if provider == "deepseek":
        return DeepSeekClient(api_key=api_key)
    if provider == "claude":
        return ClaudeClient(api_key=api_key)
    raise ValueError(f"Unknown LLM_PROVIDER {provider!r}, expected 'claude' or 'deepseek'")
