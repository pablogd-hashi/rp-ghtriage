"""How we talk to a model. One method, three implementations.

The narrow interface is the point: the reasoning loop should not know or care
whether it is talking to a 3B model on this laptop or a hosted one. That is also
what makes the tests possible. FakeLLM implements the same one method.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

import requests


class LLMError(Exception):
    """The model could not be reached, or refused. Distinct from a ParseError:
    this means we got no answer at all, not a bad one."""


class LLMClient(ABC):
    """One method. Text in, text out. No streaming, no tools, no chat history."""

    name: str = "unknown"

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int = 700) -> str:
        ...


class FakeLLM(LLMClient):
    """Returns scripted replies, in order, and remembers what it was asked.

    Used by the tests to drive every branch of the reasoning loop deterministically:
    a malformed reply, a low-confidence reply, a good reply. The call log is how a
    test asserts "the second call did / did not happen".

    NOT used for demos, seeded demo rows come from a real earlier run, so nothing
    on screen is ever invented by this class.
    """

    name = "fake"

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, str]] = []

    def complete(self, system: str, user: str, max_tokens: int = 700) -> str:
        self.calls.append({"system": system, "user": user})
        if not self.replies:
            raise LLMError("FakeLLM ran out of scripted replies")
        return self.replies.pop(0)


class OllamaLLM(LLMClient):
    """Local model. Free, no account, works with no network."""

    def __init__(self, host: str, model: str, timeout: int = 120) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.name = f"ollama/{model}"
        self.timeout = timeout

    def complete(self, system: str, user: str, max_tokens: int = 700) -> str:
        try:
            response = requests.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    # temperature 0: we want the same answer for the same PR. This
                    # is a classifier, not a writing assistant.
                    "options": {"temperature": 0, "num_predict": max_tokens},
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()["message"]["content"]
        except (requests.RequestException, KeyError, ValueError) as exc:
            raise LLMError(f"ollama call failed: {exc}") from exc


class AnthropicLLM(LLMClient):
    """Hosted. Better answers, needs a key. Same interface, so the loop is unchanged."""

    def __init__(self, api_key: str, model: str, timeout: int = 60) -> None:
        self.api_key = api_key
        self.model = model
        self.name = f"anthropic/{model}"
        self.timeout = timeout

    def complete(self, system: str, user: str, max_tokens: int = 700) -> str:
        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "temperature": 0,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()["content"][0]["text"]
        except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"anthropic call failed: {exc}") from exc


def get_client() -> LLMClient:
    """Pick the backend from the environment. Deliberately an if/elif, a registry
    would be less code to read and more code to explain."""
    provider = os.environ.get("LLM_PROVIDER", "ollama").strip().lower()

    if provider == "ollama":
        return OllamaLLM(
            host=os.environ.get("OLLAMA_HOST", "http://ollama:11434"),
            model=os.environ.get("OLLAMA_MODEL", "qwen2.5:3b"),
        )
    if provider == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise LLMError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is empty")
        return AnthropicLLM(
            api_key=key,
            model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5"),
        )
    if provider == "fake":
        raise LLMError("LLM_PROVIDER=fake is for tests only; construct FakeLLM directly")

    raise LLMError(f"unknown LLM_PROVIDER: {provider!r}")
