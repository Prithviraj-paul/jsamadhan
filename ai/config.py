"""Single configuration layer for the hybrid AI architecture.

Reads everything from environment variables (optionally via a local `.env`
file). Missing keys never crash the app — the provider is simply marked
unavailable and the orchestrator falls through to the next option.

Secrets are never printed, logged, or returned by any function here.
"""

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    # python-dotenv is optional at import time; plain env vars still work.
    pass


def _get(name, default=""):
    value = os.environ.get(name, default)
    return value.strip() if isinstance(value, str) else value


def _get_int(name, default):
    try:
        return max(1, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def _get_bool(name, default=True):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class AIConfig:
    """Resolved AI configuration (instantiate once via get_config)."""

    def __init__(self):
        self.enabled = _get_bool("AI_ENABLED", True)
        self.timeout_seconds = _get_int("AI_TIMEOUT_SECONDS", 20)
        self.max_retries = min(_get_int("AI_MAX_RETRIES", 2), 3)

        self.gemini_api_key = _get("GEMINI_API_KEY")
        self.groq_api_key = _get("GROQ_API_KEY")
        self.openrouter_api_key = _get("OPENROUTER_API_KEY")
        self.hf_token = _get("HF_TOKEN")

        self.gemini_model = _get("GEMINI_MODEL", "gemini-3.5-flash-lite")
        self.groq_text_model = _get("GROQ_TEXT_MODEL", "openai/gpt-oss-20b")
        self.groq_whisper_model = _get(
            "GROQ_WHISPER_MODEL", "whisper-large-v3-turbo"
        )
        self.openrouter_model = _get("OPENROUTER_MODEL", "openrouter/free")
        self.hf_embedding_model = _get(
            "HF_EMBEDDING_MODEL", "intfloat/multilingual-e5-small"
        )
        # Multilingual embedding fallbacks (same task family only — never a
        # generation model). Tried in order if the primary is unavailable.
        self.hf_embedding_fallbacks = (
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        )

    # -- availability (key present + globally enabled) ---------------------
    @property
    def gemini_available(self):
        return self.enabled and bool(self.gemini_api_key)

    @property
    def groq_available(self):
        return self.enabled and bool(self.groq_api_key)

    @property
    def openrouter_available(self):
        return self.enabled and bool(self.openrouter_api_key)

    @property
    def hf_available(self):
        return self.enabled and bool(self.hf_token)

    def provider_status(self):
        """Safe status snapshot (no secrets) for the admin dashboard."""
        return {
            "enabled": self.enabled,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "gemini": {
                "configured": bool(self.gemini_api_key),
                "model": self.gemini_model,
            },
            "groq": {
                "configured": bool(self.groq_api_key),
                "model": self.groq_text_model,
                "whisper_model": self.groq_whisper_model,
            },
            "openrouter": {
                "configured": bool(self.openrouter_api_key),
                "model": self.openrouter_model,
            },
            "huggingface": {
                "configured": bool(self.hf_token),
                "model": self.hf_embedding_model,
            },
        }


_CONFIG = None


def get_config():
    """Process-wide singleton (safe to call from anywhere, never raises)."""
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = AIConfig()
    return _CONFIG


def reset_config():
    """Forget the cached singleton (used by tests after changing env)."""
    global _CONFIG
    _CONFIG = None
