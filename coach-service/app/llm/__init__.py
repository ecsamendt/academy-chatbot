"""All AI-provider calls go through this package, so the provider can be swapped."""

from app.llm.base import Classification, DraftAnswer, LLMProvider, Usage
from app.llm.openai_provider import OpenAIProvider

_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = OpenAIProvider()
    return _provider


__all__ = ["Classification", "DraftAnswer", "LLMProvider", "Usage", "get_provider"]
