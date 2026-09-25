"""Single text/multimodal orchestration layer.

Application code calls `ai_generate(...)` and never learns which provider
answered. Fallback order for text: Gemini → Groq → OpenRouter →
caller-supplied deterministic fallback. For images: Gemini multimodal →
caller-supplied Pillow fallback. Images are never sent to text-only models.

Every result carries metadata: success, provider, model, task,
fallback_used, latency_ms, data. Raw provider internals stay server-side.
"""

import logging
import time

from .providers import gemini_generate, groq_chat, openrouter_chat
from .schemas import MULTIMODAL_TASKS, validate
from .utils import extract_json

logger = logging.getLogger("jsamadhan.ai")


def _metadata(success, provider, model, task, fallback_used, latency_ms,
              data=None, error=None):
    meta = {
        "success": success,
        "provider": provider,
        "model": model,
        "task": task,
        "fallback_used": fallback_used,
        "latency_ms": latency_ms,
    }
    if data is not None:
        meta["data"] = data
    if error is not None:
        meta["error"] = error
    return meta


def ai_generate(config, task, system_prompt, user_text, images=None,
                local_fallback=None):
    """Run one AI task through the fallback chain.

    `local_fallback` is an optional zero-arg callable returning a plain
    dict matching the task schema (the deterministic Pillow/rules path).
    """
    start = time.time()
    multimodal = bool(images) or task in MULTIMODAL_TASKS and images

    def elapsed():
        return int((time.time() - start) * 1000)

    # --- multimodal path: Gemini only, then local fallback ----------------
    if images:
        ok, payload, err = gemini_generate(
            config, system_prompt, user_text, images=images)
        if ok:
            parsed, data = extract_json(payload["text"])
            if parsed:
                valid, cleaned, _ = validate(task, data)
                if valid:
                    return _metadata(True, "gemini", config.gemini_model,
                                     task, False, elapsed(), cleaned)
                logger.warning("AI multimodal output failed schema validation (task=%s)", task)
            else:
                logger.warning("AI multimodal output was not valid JSON (task=%s): %s",
                               task, data)
        elif err:
            logger.warning("AI multimodal provider failed (task=%s): %s",
                           task, err.get("type"))
        if local_fallback is not None:
            try:
                data = local_fallback()
                valid, cleaned, _ = validate(task, data)
                if valid:
                    cleaned["_fallback_method"] = "local_image_heuristics"
                    return _metadata(True, "local", "local_image_heuristics",
                                     task, True, elapsed(), cleaned)
            except Exception:
                logger.exception("AI local image fallback failed (task=%s)", task)
        return _metadata(False, "none", None, task, True, elapsed(),
                         error="multimodal analysis unavailable")

    # --- text path: Gemini → Groq → OpenRouter → local fallback ------------
    chain = [
        ("gemini", config.gemini_model if config.gemini_available else None,
         lambda: gemini_generate(config, system_prompt, user_text)),
        ("groq", config.groq_text_model if config.groq_available else None,
         lambda: groq_chat(config, system_prompt, user_text)),
        ("openrouter", config.openrouter_model if config.openrouter_available else None,
         lambda: openrouter_chat(config, system_prompt, user_text)),
    ]
    last_error = "all text providers unavailable"
    for provider, model, call in chain:
        if model is None:
            continue
        ok, payload, err = call()
        if not ok:
            last_error = (err or {}).get("type", "error")
            logger.warning("AI text provider %s failed (task=%s): %s",
                           provider, task, last_error)
            continue
        parsed, data = extract_json(payload["text"])
        if not parsed:
            last_error = "invalid_response: %s" % data
            logger.warning("AI text provider %s returned invalid JSON (task=%s)",
                           provider, task)
            continue
        valid, cleaned, _ = validate(task, data)
        if not valid:
            last_error = "schema_validation_failed"
            logger.warning("AI text provider %s failed schema validation (task=%s)",
                           provider, task)
            continue
        return _metadata(True, provider, model, task,
                         provider != "gemini", elapsed(), cleaned)

    if local_fallback is not None:
        try:
            data = local_fallback()
            valid, cleaned, _ = validate(task, data)
            if valid:
                return _metadata(True, "local", "deterministic_rules",
                                 task, True, elapsed(), cleaned)
        except Exception:
            logger.exception("AI local text fallback failed (task=%s)", task)
    return _metadata(False, "none", None, task, True, elapsed(),
                     error=last_error)


def transcribe_audio(config, audio_bytes, filename="recording.webm",
                     mime_type="audio/webm"):
    """Server-side transcription via Groq Whisper (browser speech recognition
    remains the primary in-form path). Returns {success, text, language}."""
    from .providers import groq_transcribe

    start = time.time()
    ok, payload, err = groq_transcribe(config, audio_bytes, filename,
                                       mime_type)
    meta = {"success": ok,
            "latency_ms": int((time.time() - start) * 1000),
            "provider": "groq" if ok else "none"}
    if ok:
        meta.update({"text": payload["text"], "language": payload["language"]})
    else:
        meta["error"] = (err or {}).get("message", "transcription failed")
        meta["error_type"] = (err or {}).get("type", "error")
    return meta
