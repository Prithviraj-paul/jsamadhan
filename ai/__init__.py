"""Hybrid AI layer for Jharkhand Samadhan (server-side only).

Public interface used by the rest of the application:

    from ai import get_config, ai_generate, embed_texts, transcribe_audio

`ai_engine.py` keeps working exactly as before — nothing here changes any
route until later integration parts explicitly opt in.
"""

from .config import get_config, reset_config  # noqa: F401
from .embeddings import embed_texts, semantic_similarity  # noqa: F401
from .orchestrator import ai_generate, transcribe_audio  # noqa: F401
from .providers import check_connectivity  # noqa: F401
from .schemas import MULTIMODAL_TASKS, validate  # noqa: F401
from .utils import redact_personal_data  # noqa: F401

__all__ = [
    "get_config",
    "reset_config",
    "ai_generate",
    "transcribe_audio",
    "embed_texts",
    "semantic_similarity",
    "check_connectivity",
    "validate",
    "MULTIMODAL_TASKS",
    "redact_personal_data",
]
