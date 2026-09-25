"""Low-level provider clients (server-side only).

One function per capability; each returns a uniform triple:

    (ok: bool, payload: dict, error: dict|None)

`error` is one of: auth, rate_limited, timeout, bad_request,
not_found, server, network, invalid_response, unsupported_model,
unavailable, transcribe_failed, embed_failed. Only transient errors
(rate_limited, timeout, server, network) are retried — never 401/403.

No API key is ever logged, printed, or included in any error message.
"""

import base64
import io
import os
import time

try:
    import requests
except Exception:  # pragma: no cover — guarded at call time
    requests = None

TRANSIENT_ERRORS = frozenset({"rate_limited", "timeout", "server", "network"})


def _need_requests():
    if requests is None:
        return False, {"type": "unavailable", "message": "HTTP client not installed"}
    return True, None


def _classify(status_code):
    if status_code == 400:
        return "bad_request"
    if status_code in (401, 403):
        return "auth"
    if status_code == 404:
        return "not_found"
    if status_code == 408:
        return "timeout"
    if status_code == 429:
        return "rate_limited"
    if status_code and 500 <= status_code < 600:
        return "server"
    return "server"


def _safe_message(data, default):
    """Extract a short, key-free error message from a provider body."""
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])[:300]
        if isinstance(err, str) and err:
            return err[:300]
        if isinstance(data.get("message"), str):
            return data["message"][:300]
    return default


# --------------------------------------------------------------------------
# Google Gemini (REST generateContent — text and multimodal)
# --------------------------------------------------------------------------

def gemini_generate(config, system_prompt, user_text, images=None,
                    temperature=0.2):
    """Call Gemini. `images` is a list of (bytes, mime_type) or None.

    Images are only ever sent to Gemini multimodal — never to text models.
    """
    ok, err = _need_requests()
    if not ok:
        return False, {}, err
    if not config.gemini_available:
        return False, {}, {"type": "unavailable", "message": "Gemini not configured"}
    if images and not isinstance(images, list):
        return False, {}, {"type": "bad_request", "message": "bad image payload"}

    parts = []
    if user_text:
        parts.append({"text": user_text[:12000]})
    for blob, mime in images or []:
        if not blob or len(blob) > 8 * 1024 * 1024:
            continue
        parts.append({"inline_data": {
            "mime_type": mime or "image/jpeg",
            "data": base64.b64encode(blob).decode("ascii"),
        }})
    body = {
        "system_instruction": {"parts": [{"text": system_prompt[:4000]}]},
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": temperature,
                             "response_mime_type": "application/json"},
    }
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           "%s:generateContent" % config.gemini_model)
    timeout = config.timeout_seconds
    last_error = {"type": "network", "message": "request failed"}
    for attempt in range(1 + config.max_retries):
        try:
            resp = requests.post(
                url, params={"key": config.gemini_api_key}, json=body,
                timeout=timeout)
        except requests.Timeout:
            last_error = {"type": "timeout",
                          "message": "Gemini timed out after %ss" % timeout}
            continue
        except requests.RequestException as exc:
            last_error = {"type": "network",
                          "message": "Gemini network error: %s" % type(exc).__name__}
            continue
        if resp.status_code == 200:
            try:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
            except (ValueError, KeyError, IndexError, TypeError):
                return False, {}, {"type": "invalid_response",
                                    "message": "Gemini returned no text"}
            if not (text or "").strip():
                return False, {}, {"type": "invalid_response",
                                    "message": "Gemini returned an empty response"}
            return True, {"text": text}, None
        err_type = _classify(resp.status_code)
        try:
            msg = _safe_message(resp.json(), "Gemini HTTP %s" % resp.status_code)
        except ValueError:
            msg = "Gemini HTTP %s" % resp.status_code
        if err_type == "not_found":
            msg = "Gemini model '%s' unavailable: %s" % (config.gemini_model, msg)
            return False, {}, {"type": "unsupported_model", "message": msg}
        last_error = {"type": err_type, "message": msg}
        if err_type not in TRANSIENT_ERRORS:
            break
        time.sleep(min(2 ** attempt, 4))
    return False, {}, last_error


# --------------------------------------------------------------------------
# OpenAI-compatible chat completions (Groq + OpenRouter share this path)
# --------------------------------------------------------------------------

def _openai_chat(base_url, api_key, model, system_prompt, user_text,
                 timeout, max_retries, provider_name):
    ok, err = _need_requests()
    if not ok:
        return False, {}, err
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt[:4000]},
            {"role": "user", "content": (user_text or "")[:12000]},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    last_error = {"type": "network", "message": "request failed"}
    for attempt in range(1 + max_retries):
        try:
            resp = requests.post(
                base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer %s" % api_key},
                json=body, timeout=timeout)
        except requests.Timeout:
            last_error = {"type": "timeout", "message": "%s timed out after %ss"
                          % (provider_name, timeout)}
            continue
        except requests.RequestException as exc:
            last_error = {"type": "network", "message": "%s network error: %s"
                          % (provider_name, type(exc).__name__)}
            continue
        if resp.status_code == 200:
            try:
                text = resp.json()["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError):
                return False, {}, {"type": "invalid_response",
                                    "message": "%s returned no text" % provider_name}
            if not (text or "").strip():
                return False, {}, {"type": "invalid_response",
                                    "message": "%s returned an empty response"
                                    % provider_name}
            return True, {"text": text}, None
        err_type = _classify(resp.status_code)
        try:
            msg = _safe_message(resp.json(),
                                "%s HTTP %s" % (provider_name, resp.status_code))
        except ValueError:
            msg = "%s HTTP %s" % (provider_name, resp.status_code)
        if err_type == "not_found":
            return False, {}, {"type": "unsupported_model",
                                "message": "%s model '%s' unavailable"
                                % (provider_name, model)}
        last_error = {"type": err_type, "message": msg}
        if err_type not in TRANSIENT_ERRORS:
            break
        time.sleep(min(2 ** attempt, 4))
    return False, {}, last_error


def groq_chat(config, system_prompt, user_text):
    if not config.groq_available:
        return False, {}, {"type": "unavailable", "message": "Groq not configured"}
    return _openai_chat("https://api.groq.com/openai/v1", config.groq_api_key,
                        config.groq_text_model, system_prompt, user_text,
                        config.timeout_seconds, config.max_retries, "Groq")


def openrouter_chat(config, system_prompt, user_text):
    if not config.openrouter_available:
        return False, {}, {"type": "unavailable",
                            "message": "OpenRouter not configured"}
    ok, payload, err = _openai_chat(
        "https://openrouter.ai/api/v1", config.openrouter_api_key,
        config.openrouter_model, system_prompt, user_text,
        config.timeout_seconds, config.max_retries, "OpenRouter")
    return ok, payload, err


# --------------------------------------------------------------------------
# Groq Whisper speech-to-text
# --------------------------------------------------------------------------

ALLOWED_AUDIO = {
    "audio/webm": "webm",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "m4a",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
}

MAX_AUDIO_BYTES = 8 * 1024 * 1024


def groq_transcribe(config, audio_bytes, filename="recording.webm",
                    mime_type="audio/webm"):
    ok, err = _need_requests()
    if not ok:
        return False, {}, err
    if not config.groq_available:
        return False, {}, {"type": "unavailable", "message": "Groq not configured"}
    if not audio_bytes or len(audio_bytes) > MAX_AUDIO_BYTES:
        return False, {}, {"type": "bad_request",
                            "message": "audio missing or larger than 8 MB"}
    ext = ALLOWED_AUDIO.get((mime_type or "").split(";")[0].strip().lower())
    if ext is None:
        return False, {}, {"type": "bad_request",
                            "message": "unsupported audio format"}
    safe_name = "audio.%s" % ext
    last_error = {"type": "network", "message": "request failed"}
    for attempt in range(1 + config.max_retries):
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": "Bearer %s" % config.groq_api_key},
                files={"file": (safe_name, io.BytesIO(audio_bytes), mime_type)},
                data={"model": config.groq_whisper_model,
                      "response_format": "verbose_json"},
                timeout=max(config.timeout_seconds, 45),
            )
        except requests.Timeout:
            last_error = {"type": "timeout", "message": "transcription timed out"}
            continue
        except requests.RequestException as exc:
            last_error = {"type": "network",
                          "message": "transcription network error: %s"
                          % type(exc).__name__}
            continue
        if resp.status_code == 200:
            try:
                data = resp.json()
                text = (data.get("text") or "").strip()
            except ValueError:
                return False, {}, {"type": "invalid_response",
                                    "message": "transcription unreadable"}
            if not text:
                return False, {}, {"type": "transcribe_failed",
                                    "message": "no speech detected"}
            return True, {"text": text[:2000],
                          "language": (data.get("language") or "")[:16]}, None
        err_type = _classify(resp.status_code)
        try:
            msg = _safe_message(resp.json(), "transcription HTTP %s" % resp.status_code)
        except ValueError:
            msg = "transcription HTTP %s" % resp.status_code
        last_error = {"type": err_type, "message": msg}
        if err_type not in TRANSIENT_ERRORS:
            break
        time.sleep(min(2 ** attempt, 4))
    return False, {}, last_error


# --------------------------------------------------------------------------
# Hugging Face embeddings (feature extraction; embedding models only)
# --------------------------------------------------------------------------

def hf_embed(config, texts, model=None):
    """Embed a list of texts. Returns (ok, {"vectors": [...]}, error).

    Tries the configured model, then multilingual fallbacks. Never a
    generation model — embedding endpoints only.
    """
    ok, err = _need_requests()
    if not ok:
        return False, {}, err
    if not config.hf_available:
        return False, {}, {"type": "unavailable",
                            "message": "Hugging Face not configured"}
    models = [model or config.hf_embedding_model] + list(
        config.hf_embedding_fallbacks)
    tried = []
    for name in dict.fromkeys(models):
        url = "https://router.huggingface.co/hf-inference/models/%s" % name
        try:
            resp = requests.post(
                url,
                headers={"Authorization": "Bearer %s" % config.hf_token},
                json={"inputs": texts, "options": {"wait_for_model": True}},
                timeout=config.timeout_seconds,
            )
        except requests.Timeout:
            tried.append((name, "timeout"))
            continue
        except requests.RequestException:
            tried.append((name, "network"))
            continue
        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                return False, {}, {"type": "invalid_response",
                                    "message": "embedding unreadable"}
            # feature-extraction returns [vectors] or a single vector
            vectors = data[0] if (isinstance(data, list) and data
                                  and isinstance(data[0], list)
                                  and data[0]
                                  and isinstance(data[0][0], list)) else data
            if (isinstance(vectors, list) and len(vectors) == len(texts)
                    and all(isinstance(v, list) and v for v in vectors)):
                dims = {len(v) for v in vectors}
                if len(dims) == 1:
                    return True, {"vectors": vectors, "model": name,
                                  "dimensions": dims.pop()}, None
            return False, {}, {"type": "invalid_response",
                                "message": "embedding shape mismatch"}
        err_type = _classify(resp.status_code)
        tried.append((name, err_type))
        if err_type in ("auth",):
            return False, {}, {"type": "auth",
                                "message": "Hugging Face authentication failed"}
        # otherwise try the next fallback model
    return False, {}, {"type": "embed_failed",
                        "message": "embeddings unavailable (tried %d model(s))"
                        % len(tried)}


# --------------------------------------------------------------------------
# Google Gemini embeddings (second tier for semantic matching)
# --------------------------------------------------------------------------

GEMINI_EMBEDDING_MODELS = ("gemini-embedding-001", "text-embedding-004")


def gemini_embed(config, texts):
    """Embed texts with Gemini (embedding models only). Returns
    (ok, {"vectors": [...], "model": name, "dimensions": n}, error)."""
    ok, err = _need_requests()
    if not ok:
        return False, {}, err
    if not config.gemini_available:
        return False, {}, {"type": "unavailable",
                            "message": "Gemini not configured"}
    clean = [(t or "")[:2000] for t in texts]
    for name in GEMINI_EMBEDDING_MODELS:
        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               "%s:batchEmbedContents" % name)
        try:
            resp = requests.post(
                url, params={"key": config.gemini_api_key},
                json={"requests": [{"model": "models/%s" % name,
                                     "content": {"parts": [{"text": t}]}} for t in clean]},
                timeout=config.timeout_seconds)
        except requests.Timeout:
            return False, {}, {"type": "timeout",
                                "message": "Gemini embedding timed out"}
        except requests.RequestException as exc:
            return False, {}, {"type": "network",
                                "message": "Gemini embedding network error: %s"
                                % type(exc).__name__}
        if resp.status_code == 200:
            try:
                data = resp.json()
                vectors = [e["values"] for e in data["embeddings"]]
            except (ValueError, KeyError, IndexError, TypeError):
                return False, {}, {"type": "invalid_response",
                                    "message": "embedding unreadable"}
            if (isinstance(vectors, list) and len(vectors) == len(clean)
                    and all(isinstance(v, list) and v for v in vectors)):
                dims = {len(v) for v in vectors}
                if len(dims) == 1:
                    return True, {"vectors": vectors, "model": name,
                                  "dimensions": dims.pop()}, None
            return False, {}, {"type": "invalid_response",
                                "message": "embedding shape mismatch"}
        err_type = _classify(resp.status_code)
        if err_type == "auth":
            return False, {}, {"type": "auth",
                                "message": "Gemini authentication failed"}
        if err_type not in ("not_found",) and err_type not in TRANSIENT_ERRORS:
            try:
                msg = _safe_message(resp.json(), "Gemini embedding HTTP %s" % resp.status_code)
            except ValueError:
                msg = "Gemini embedding HTTP %s" % resp.status_code
            return False, {}, {"type": err_type, "message": msg}
        # not_found (retired model) or transient: try next model / fail out
        if err_type == "not_found":
            continue
        try:
            msg = _safe_message(resp.json(), "Gemini embedding HTTP %s" % resp.status_code)
        except ValueError:
            msg = "Gemini embedding HTTP %s" % resp.status_code
        return False, {}, {"type": err_type, "message": msg}
    return False, {}, {"type": "unsupported_model",
                        "message": "no Gemini embedding model available"}


def check_connectivity(config):
    """Cheap per-provider probes for the admin status page (no secrets out)."""
    import time as _time

    results = {}
    if config.gemini_available:
        start = _time.time()
        ok, _, err = gemini_generate(
            config, "Reply with {}.", '{"ping": true}')
        results["gemini"] = {"ok": ok, "model": config.gemini_model,
                             "latency_ms": int((_time.time() - start) * 1000),
                             "error": (err or {}).get("type") if not ok else None,
                             "message": (err or {}).get("message") if not ok else "Connected"}
    else:
        results["gemini"] = {"ok": False, "model": config.gemini_model,
                             "latency_ms": None, "error": "unavailable",
                             "message": "Not configured"}
    if config.groq_available:
        start = _time.time()
        ok, _, err = groq_chat(config, "Reply with {}.", '{"ping": true}')
        results["groq"] = {"ok": ok, "model": config.groq_text_model,
                           "latency_ms": int((_time.time() - start) * 1000),
                           "error": (err or {}).get("type") if not ok else None,
                           "message": (err or {}).get("message") if not ok else "Connected"}
    else:
        results["groq"] = {"ok": False, "model": config.groq_text_model,
                           "latency_ms": None, "error": "unavailable",
                           "message": "Not configured"}
    if config.openrouter_available:
        start = _time.time()
        ok, _, err = openrouter_chat(config, "Reply with {}.", '{"ping": true}')
        results["openrouter"] = {"ok": ok, "model": config.openrouter_model,
                                 "latency_ms": int((_time.time() - start) * 1000),
                                 "error": (err or {}).get("type") if not ok else None,
                                 "message": (err or {}).get("message") if not ok else "Connected"}
    else:
        results["openrouter"] = {"ok": False, "model": config.openrouter_model,
                                 "latency_ms": None, "error": "unavailable",
                                 "message": "Not configured"}
    if config.hf_available:
        start = _time.time()
        ok, payload, err = hf_embed(config, ["connectivity probe"])
        results["huggingface"] = {
            "ok": ok, "model": (payload or {}).get("model", config.hf_embedding_model),
            "latency_ms": int((_time.time() - start) * 1000),
            "error": (err or {}).get("type") if not ok else None,
            "message": (err or {}).get("message") if not ok else "Connected"}
    else:
        results["huggingface"] = {"ok": False, "model": config.hf_embedding_model,
                                  "latency_ms": None, "error": "unavailable",
                                  "message": "Not configured"}
    return results
