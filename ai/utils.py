"""Shared helpers: PII redaction, JSON extraction, validation, similarity.

No function here touches the network or any secret.
"""

import json
import math
import re

_PHONE_RE = re.compile(r"(?:\+?91[\s\-]?)?[6-9]\d{4}[\s\-]?\d{5}")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_AADHAAR_RE = re.compile(r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b")

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def redact_personal_data(text):
    """Remove phone numbers, emails and Aadhaar-like sequences from text
    before it is sent to an external AI API. Returns "" for bad input."""
    if not text or not isinstance(text, str):
        return ""
    redacted = _PHONE_RE.sub("[phone-redacted]", text)
    redacted = _EMAIL_RE.sub("[email-redacted]", redacted)
    redacted = _AADHAAR_RE.sub("[id-redacted]", redacted)
    return redacted


def extract_json(raw):
    """Pull a JSON object out of model output (strips ```json fences).

    Returns (ok, data_or_error_string). Never raises, never executes code.
    """
    if raw is None:
        return False, "empty response"
    text = raw if isinstance(raw, str) else str(raw)
    text = text.strip()
    if not text:
        return False, "empty response"
    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    # tolerate leading/trailing prose: find the outer braces
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return False, "no JSON object found"
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        return False, "invalid JSON: %s" % exc
    if not isinstance(data, dict):
        return False, "JSON is not an object"
    return True, data


def clamp_number(value, low, high, default):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return max(low, min(high, number))


def clamp_int(value, low, high, default):
    return int(round(clamp_number(value, low, high, default)))


def clean_text(value, max_len, default=""):
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    return text[:max_len]


def clean_enum(value, allowed, default):
    if isinstance(value, str) and value.strip() in allowed:
        return value.strip()
    if isinstance(value, str) and value.strip().lower() in allowed:
        return value.strip().lower()
    return default


def clean_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "yes", "1"):
            return True
        if low in ("false", "no", "0"):
            return False
    return default


def clean_list_of_str(value, max_items=12, max_len=280):
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip()[:max_len])
        if len(out) >= max_items:
            break
    return out


def tokenize(text):
    """Tiny local tokenizer for the deterministic similarity fallback."""
    if not text or not isinstance(text, str):
        return set()
    return set(_TOKEN_RE.findall(text.lower()))


def jaccard_similarity(a_tokens, b_tokens):
    if not a_tokens or not b_tokens:
        return 0.0
    inter = len(a_tokens & b_tokens)
    union = len(a_tokens | b_tokens)
    return inter / union if union else 0.0


def cosine_similarity(vec_a, vec_b):
    """Cosine similarity for embedding vectors (pure Python)."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))
