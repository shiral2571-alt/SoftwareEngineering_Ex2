"""LLM providers behind one interface (Strategy pattern, SRS FR-7.1–7.4, D-11).

The lecturer picks a provider and a model in Settings and pastes an API key. The key is stored on the
server only and never sent back to the browser (it is shown masked). Without a key, `OfflineClient` is
used and the AI features fall back to offline methods.
"""
import sqlite3
from abc import ABC, abstractmethod

# 2–3 well-known models per provider, cheapest/fastest first (SRS FR-7.1a, D-15).
# Model names change often: verified against the providers' docs on 2026-11-16; a custom ID is also allowed.
MODEL_CATALOG = {
    "anthropic": {"label": "Anthropic Claude", "models": [
        ("claude-haiku-5-5", "Claude Haiku 5.5 — fast, cheapest"),
        ("claude-sonnet-5-5", "Claude Sonnet 5.5 — balanced"),
        ("claude-opus-5-5", "Claude Opus 5.5 — strongest"),
    ]},
    "google": {"label": "Google Gemini", "models": [
        ("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite — fast, cheapest"),
        ("gemini-3.8-flash", "Gemini 3.8 Flash — balanced"),
        ("gemini-4-carbon", "Gemini 4 Carbon — strongest"),
    ]},
    "openai": {"label": "OpenAI", "models": [
        ("gpt-6-luna", "GPT-6 Luna — fast, cheapest"),
        ("gpt-6.1-sol", "GPT-6.1 Sol — balanced"),
        ("gpt-6-astra", "GPT-6 Astra — strongest"),
    ]},
}
MAX_TOKENS = 16000


class LLMError(RuntimeError):
    pass


class LLMClient(ABC):
    """One method the rest of the app depends on. New providers are new subclasses (Open/Closed)."""

    def __init__(self, model: str = "", api_key: str = ""):
        self.model, self.api_key = model, api_key

    @property
    def name(self) -> str:
        return f"{MODEL_CATALOG[self.provider]['label']} · {self.model}"

    provider = ""

    @abstractmethod
    def complete(self, system: str, prompt: str) -> str: ...


class ClaudeClient(LLMClient):
    provider = "anthropic"

    def complete(self, system: str, prompt: str) -> str:
        import anthropic  # imported lazily: the app runs without the package
        client = anthropic.Anthropic(api_key=self.api_key)
        kwargs = {}
        if self.model in ("claude-opus-5-5", "claude-sonnet-5-5"):
            # If a safety classifier declines, retry on another model instead of failing.
            kwargs = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        response = client.beta.messages.create(
            model=self.model, max_tokens=MAX_TOKENS, system=system,
            messages=[{"role": "user", "content": prompt}], **kwargs)
        if response.stop_reason == "refusal":
            raise LLMError("The model declined this request")
        return "".join(b.text for b in response.content if b.type == "text").strip()


class GeminiClient(LLMClient):
    provider = "google"

    def complete(self, system: str, prompt: str) -> str:
        from google import genai
        client = genai.Client(api_key=self.api_key)
        if hasattr(client, "interactions"):  # current API (Interactions)
            return client.interactions.create(model=self.model, system_instruction=system,
                                              input=prompt).output_text.strip()
        from google.genai import types  # older SDK versions
        return client.models.generate_content(
            model=self.model, contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system)).text.strip()


class OpenAIClient(LLMClient):
    provider = "openai"

    def complete(self, system: str, prompt: str) -> str:
        from openai import OpenAI
        response = OpenAI(api_key=self.api_key).responses.create(model=self.model, instructions=system, input=prompt)
        return response.output_text.strip()


class OfflineClient(LLMClient):
    """No key configured. Features detect this and use offline methods instead."""
    provider = ""

    @property
    def name(self) -> str:
        return "Offline (no API key)"

    def complete(self, system: str, prompt: str) -> str:
        raise LLMError("No AI provider is configured")


CLIENTS = {c.provider: c for c in (ClaudeClient, GeminiClient, OpenAIClient)}


class LLMSettings:
    """Provider, model and key, stored in the server's database (never in the browser)."""

    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def _get(self, key: str) -> str:
        r = self.db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return r["value"] if r else ""

    def _put(self, key: str, value: str) -> None:
        self.db.execute("INSERT INTO settings(key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    def save(self, provider: str, model: str, api_key: str | None) -> None:
        """`api_key=None` keeps the stored key (the form never receives it back, only a mask)."""
        if provider not in CLIENTS:
            raise ValueError("Unknown provider")
        if not model.strip():
            raise ValueError("Choose a model")
        if provider != self._get("provider"):
            self._put("api_key", "")  # a key belongs to one provider
        self._put("provider", provider)
        self._put("model", model.strip())
        if api_key is not None and api_key.strip():
            self._put("api_key", api_key.strip())

    def clear_key(self) -> None:
        self._put("api_key", "")

    def public_view(self) -> dict:
        """What the settings screen may show. The key itself never leaves the server."""
        key = self._get("api_key")
        return {"provider": self._get("provider") or "anthropic", "model": self._get("model"),
                "key_set": bool(key), "key_mask": f"{key[:3]}…{key[-4:]}" if len(key) > 8 else ("•••" if key else ""),
                "catalog": MODEL_CATALOG}

    def client(self) -> LLMClient:
        provider, model, key = self._get("provider"), self._get("model"), self._get("api_key")
        if provider in CLIENTS and model and key:
            return CLIENTS[provider](model, key)
        return OfflineClient()


def test_connection(client: LLMClient) -> str:
    """Tiny real request, so the lecturer knows the key and model work (FR-7.3)."""
    if isinstance(client, OfflineClient):
        raise LLMError("Add an API key first")
    return client.complete("Reply with exactly one word.", "Say OK.")
