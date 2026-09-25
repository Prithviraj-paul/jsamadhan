"""Semantic embeddings with graceful degradation.

Order: Hugging Face (E5 query/passage prefixes) → Gemini embeddings →
local token-overlap fallback. Results record which method produced them
so the application can display and audit the provenance.
"""

from .providers import gemini_embed, hf_embed
from .utils import cosine_similarity, jaccard_similarity, tokenize


def _e5_format(texts, kind):
    prefix = "query: " if kind == "query" else "passage: "
    return ["%s%s" % (prefix, (t or "")[:2000]) for t in texts]


def embed_texts(config, texts, kind="passage", model=None):
    """Embed texts. Returns dict: {ok, vectors|None, model, method, dims}.

    `method` is "hf" or "local". Never raises; never exposes secrets.
    """
    clean = [(t or "")[:2000] for t in texts]
    if not clean:
        return {"ok": False, "vectors": None, "model": None,
                "method": "none", "dims": 0,
                "error": "no texts to embed"}
    ok, payload, _err = hf_embed(config, _e5_format(clean, kind), model=model)
    if ok:
        return {"ok": True, "vectors": payload["vectors"],
                "model": payload.get("model"), "method": "hf",
                "dims": payload.get("dimensions", 0)}
    ok, payload, _err = gemini_embed(config, clean)
    if ok:
        return {"ok": True, "vectors": payload["vectors"],
                "model": payload.get("model"), "method": "gemini",
                "dims": payload.get("dimensions", 0)}
    return {"ok": False, "vectors": None, "model": None, "method": "local",
            "dims": 0, "error": "embeddings unavailable — local fallback"}


def semantic_similarity(config, query_text, passage_texts, model=None):
    """Cosine similarity of one query against passages via HF, or token
    overlap when embeddings are unavailable. Returns
    {similarities: [...], method, model}. Never raises."""
    result = embed_texts(config, [query_text], kind="query", model=model)
    if result["ok"]:
        passages = embed_texts(config, passage_texts, kind="passage",
                               model=result["model"])
        if passages["ok"]:
            sims = [cosine_similarity(result["vectors"][0], vec)
                    for vec in passages["vectors"]]
            return {"similarities": sims, "method": "hf",
                    "model": result["model"]}
    query_tokens = tokenize(query_text)
    sims = [jaccard_similarity(query_tokens, tokenize(p)) for p in passage_texts]
    return {"similarities": sims, "method": "local", "model": None}
