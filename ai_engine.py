"""
Simulated AI engine for Jharkhand Samadhan.

Two jobs:
1. evidence_screen()  — honest automated screening for infrastructure
   complaints based on the real photo-vs-problem check. This project has
   no satellite feed; satellite_screen() remains only as a deprecated
   compatibility wrapper that routes to manual review.

2. compare_before_after() — Gemini-multimodal before/after verification
   with Pillow fallback: Gemini judges whether the reported problem
   appears improved at a plausibly matching site (structured statuses
   LIKELY_RESOLVED / PARTIALLY_RESOLVED / NOT_RESOLVED /
   INSUFFICIENT_EVIDENCE / POSSIBLE_DIFFERENT_LOCATION / AI_UNAVAILABLE).
   compare_images_local() keeps the Pillow pixel/edge metrics as a
   secondary-only signal. Pixel difference alone never marks a case
   resolved — see resolution_decision().
"""

import hashlib
import math
import logging
import os
import random
import re
from collections import Counter

from PIL import Image, ImageFilter, ImageChops, ImageOps

logger = logging.getLogger("jsamadhan.ai_engine")

SATELLITE_VERIFY_THRESHOLD = 65     # legacy constant (see satellite_screen)
# NOTE: pixel difference is never a resolution decision rule. The old
# "change score >= 10 -> Resolved" logic has been removed; see
# resolution_decision() for the Gemini-status-based workflow.

# ---------------------------------------------------------------------------
# AI duplicate detection — deterministic, fully-offline signal comparison.
#
# Weights for a transparent, weighted score. When a signal is unavailable
# (e.g. no image on either side) its weight is folded into the description
# signal so the available signals always sum to 100%.
# ---------------------------------------------------------------------------
# Hybrid duplicate weights (Phase 4): semantic similarity leads; GPS gates
# far-apart reports; image weight redistributes when unavailable.
DUPLICATE_WEIGHTS = {
    "semantic": 0.45,
    "location": 0.25,
    "category": 0.15,
    "time": 0.05,
    "image": 0.10,
}

# Confidence interpretation (both configurable in this single location).
DUPLICATE_THRESHOLD_HIGH = 80    # >= this -> Highly likely duplicate
DUPLICATE_THRESHOLD_MEDIUM = 65  # >= this -> Possible duplicate (else low)

# Location distance gates for _location_score (metres).
LOCATION_DIST_NEAR = 100
LOCATION_DIST_CLOSE = 500
LOCATION_DIST_REGION = 2000
LOCATION_DIST_FAR = 5000

_STOP_WORDS = {
    "a", "an", "after", "all", "also", "am", "and", "are", "at", "be",
    "been", "before", "being", "between", "both", "but", "can", "could",
    "did", "do", "does", "during", "each", "every", "few", "for", "from",
    "had", "has", "have", "he", "her", "here", "his", "how", "if", "in",
    "into", "is", "it", "its", "just", "may", "might", "more", "most",
    "my", "not", "now", "of", "on", "or", "our", "should", "so", "some",
    "such", "than", "that", "the", "their", "these", "they", "this",
    "through", "to", "too", "very", "was", "we", "were", "what", "when",
    "where", "which", "who", "whom", "will", "with", "would", "you",
    "your", "about", "above", "below", "between", "different", "into",
    "other", "same",
}

# Photo-vs-complaint verification (real Pillow cross-check).
VERIFY_THRESHOLD = 62                 # confidence >= this -> AI auto-verifies
MIN_DETAIL_PIXELS = 96 * 96           # warn when the photo is low-resolution
BLUR_MIN = 14.0                       # Laplacian blur floor (focus check)

_CATEGORY_HINTS = {
    "Roads & Infrastructure": "dark patchy regions and crack-like edges",
    "Roads & Public Infrastructure": "dark patchy regions and crack-like edges",
    "Water Resources": "dry/brown tones instead of flowing or standing water",
    "Water & Sanitation": "standing water, leakage, or waste-cluttered surroundings",
    "Electricity": "dim, poorly lit appearance suggesting an outage",
    "Sanitation": "high-contrast clutter and dark mounds typical of waste",
    "Healthcare": "dilapidated surfaces (peeling, dark streaks)",
    "Education": "worn or damaged building surfaces",
    "Education Infrastructure": "damaged school-building surfaces, toilets or water points",
    "Public Safety": "heavy shadows and irregular structures",
    "Other": "visible structural irregularity",
}


def _urgency_from_score(score):
    if score >= 75:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 25:
        return "normal"
    return "low"


def _category_score(image, category):
    """Score an image 0-100 for a given category using cheap Pillow stats."""
    gray = image.convert("L")
    pixels = list(image.convert("RGB").getdata())
    total = len(pixels) or 1

    brightness = sum(gray.getdata()) / (total * 255) * 100
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_density = sum(edges.getdata()) / (total * 255) * 100
    dark_ratio = sum(1 for v in gray.getdata() if v < 80) / total * 100

    if category == "Roads & Infrastructure":
        return 30 + edge_density * 1.4 + dark_ratio * 0.5
    if category == "Roads & Public Infrastructure":
        return 30 + edge_density * 1.4 + dark_ratio * 0.5
    if category == "Water Resources":
        brown = sum(1 for (r, g, b) in pixels if r > 100 and g > 60 and b < 80) / total * 100
        return 24 + brown * 1.3 + dark_ratio * 0.35
    if category == "Water & Sanitation":
        brown = sum(1 for (r, g, b) in pixels if r > 100 and g > 60 and b < 80) / total * 100
        return 24 + brown * 1.3 + dark_ratio * 0.35
    if category == "Electricity":
        return 38 + (100 - brightness) * 0.55 + edge_density * 0.25
    if category == "Sanitation":
        return 34 + edge_density * 0.9 + dark_ratio * 0.5
    if category in ("Healthcare", "Education"):
        return 35 + (100 - brightness) * 0.30 + edge_density * 0.25
    if category == "Education Infrastructure":
        return 35 + (100 - brightness) * 0.30 + edge_density * 0.25
    return 40 + edge_density * 0.5 + dark_ratio * 0.3


def analyze_severity(image_path, category):
    """Real, Pillow-based severity assessment for a complaint photo.

    Returns a dict:
        score  - int 0-100
        urgency - "critical" | "high" | "normal" | "low"
        note   - short explainer for the officer

    When no readable image is available (video evidence, or no photo at all)
    we fall back to a category-only estimate at level 'normal'/'high'.
    """
    try:
        img = Image.open(image_path).convert("RGB").resize((256, 256))
    except Exception:
        score = {"Water Resources": 46, "Water & Sanitation": 46,
                 "Roads & Infrastructure": 44,
                 "Roads & Public Infrastructure": 44}.get(category, 42)
        urgency = _urgency_from_score(score)
        return {
            "score": score,
            "urgency": urgency,
            "note": (f"AI severity estimate {score}/100 ({urgency} level) based on the "
                     f"complaint category alone — no readable photo to analyze."),
        }

    score = int(max(0, min(100, round(_category_score(img, category)))))
    urgency = _urgency_from_score(score)

    hint_text = {
        "critical": "Visible damage indicators are severe; immediate intervention recommended.",
        "high": "Notable damage indicators detected; priority action advised.",
        "normal": "Moderate concern; standard handling time applies.",
        "low": "Mild indicators; routine handling sufficient.",
    }[urgency]

    note = (f"AI severity analysis: {urgency.title()} (score {score}/100). "
            f"Detected {_CATEGORY_HINTS.get(category, 'damage indicators')}. {hint_text}")
    return {"score": score, "urgency": urgency, "note": note}


def _seed_from(text):
    h = hashlib.sha256(text.encode()).hexdigest()
    return int(h[:8], 16)


def evidence_screen(complaint_code, category, description, photo_verified=False,
                    photo_confidence=None, has_photo=False):
    """Honest automated evidence screening for infrastructure complaints.

    This project has NO satellite imagery feed and never did — no function
    here may claim otherwise. Screening is based only on the real
    Pillow photo-vs-problem check (when a photo exists) and report
    completeness. Returns (confidence:int|None, note:str, method:str).
    """
    if photo_verified:
        conf = photo_confidence if isinstance(photo_confidence, int) else 70
        return (conf,
                "AI-assisted review of submitted evidence found it consistent "
                "with the reported problem (assessment score %d/100). "
                "Awaiting officer validation." % conf,
                "pillow_photo_check")
    if has_photo:
        return (None,
                "AI-assisted review of submitted evidence could not confirm "
                "the reported problem. Routed to an officer for manual "
                "verification.",
                "pillow_photo_check")
    return (None,
            "No photo evidence was submitted with this report. Awaiting "
            "manual verification by an officer.",
            "none")


def satellite_screen(complaint_code, category, description):
    """Deprecated compatibility wrapper (pre-audit name).

    Previously returned a deterministic pseudo-random 'satellite'
    confidence — that behavior is removed because this project has no
    satellite imagery. Delegates to evidence_screen() without photo
    evidence, so old callers route to manual review instead of
    auto-verifying. Returns (confidence:int|None, note:str).
    """
    conf, note, _method = evidence_screen(
        complaint_code, category, description,
        photo_verified=False, has_photo=False)
    return conf, note


def compare_images_local(before_path, after_path):
    """Secondary-only visual metrics for a before/after pair.

    Returns {pixel_change, edge_change, before_quality, after_quality,
    readable} or None when either file is not a readable image. These
    metrics describe *difference*, never resolution — a high pixel
    difference only means 'significant visual difference detected'.
    """
    try:
        with Image.open(before_path) as im:
            im.verify()
        with Image.open(after_path) as im:
            im.verify()
        img_before = Image.open(before_path).convert("L").resize((256, 256))
        img_after = Image.open(after_path).convert("L").resize((256, 256))
    except Exception:
        return None

    def quality(img):
        w, h = img.size
        if w < 96 or h < 96:
            return "very low resolution"
        data = list(img.getdata())
        mean = sum(data) / len(data)
        if mean < 25:
            return "very dark"
        if mean > 230:
            return "overexposed"
        return "usable"

    diff = ImageChops.difference(img_before, img_after)
    pixel_change = round(sum(diff.getdata()) / (256 * 256 * 255) * 100, 1)

    edges_before = img_before.filter(ImageFilter.FIND_EDGES)
    edges_after = img_after.filter(ImageFilter.FIND_EDGES)
    edge_before_density = sum(edges_before.getdata()) / (256 * 256 * 255) * 100
    edge_after_density = sum(edges_after.getdata()) / (256 * 256 * 255) * 100
    edge_change = round(abs(edge_before_density - edge_after_density), 1)

    return {
        "pixel_change": pixel_change,
        "edge_change": edge_change,
        "before_quality": quality(img_before),
        "after_quality": quality(img_after),
        "readable": True,
    }


RESOLUTION_STATUS_LABELS = {
    "LIKELY_RESOLVED": "Likely Resolved",
    "PARTIALLY_RESOLVED": "Partially Resolved",
    "NOT_RESOLVED": "Not Resolved",
    "INSUFFICIENT_EVIDENCE": "Insufficient Evidence",
    "POSSIBLE_DIFFERENT_LOCATION": "Possible Different Location",
    "AI_UNAVAILABLE": "AI Unavailable",
}

RESOLVE_THRESHOLD = 75  # LIKELY_RESOLVED + score >= this (+no review flag) -> Resolved


def compare_before_after(before_path, after_path, title="", description="",
                         category="", subcategory="", district="",
                         location_text=""):
    """Gemini-multimodal before/after verification with Pillow fallback.

    Returns a structured dict (never a bare score tuple):
        success, provider, model, resolution_status, resolution_score,
        same_scene_assessment, same_scene_score, before_issue_visible,
        after_issue_visible, evidence_relevance, summary,
        observed_changes, limitations, manual_review_required,
        local_metrics, latency_ms.

    When Gemini is unavailable the result is AI_UNAVAILABLE with local
    Pillow metrics attached as secondary information only.
    """
    local_metrics = compare_images_local(before_path, after_path)
    if local_metrics is None:
        return {
            "success": False,
            "provider": "none",
            "model": None,
            "resolution_status": "INSUFFICIENT_EVIDENCE",
            "resolution_score": 0,
            "same_scene_assessment": "possibly_same_site",
            "same_scene_score": 0,
            "before_issue_visible": False,
            "after_issue_visible": False,
            "evidence_relevance": "LOW",
            "summary": "Could not run automated image comparison (unsupported file type).",
            "observed_changes": [],
            "limitations": ["One or both files could not be read as images."],
            "manual_review_required": True,
            "local_metrics": None,
            "latency_ms": 0,
        }

    images = []
    try:
        for path in (before_path, after_path):
            with open(path, "rb") as fh:
                blob = fh.read()
            ext = (os.path.splitext(path)[1] or "").lower()
            mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg")
            images.append((blob, mime))
    except Exception:
        images = []

    result = {
        "success": False,
        "provider": "none",
        "model": None,
        "resolution_status": "AI_UNAVAILABLE",
        "resolution_score": 0,
        "same_scene_assessment": "possibly_same_site",
        "same_scene_score": 0,
        "before_issue_visible": False,
        "after_issue_visible": False,
        "evidence_relevance": "LOW",
        "summary": ("AI verification temporarily unavailable. "
                    "Resolution evidence was saved for manual review."),
        "observed_changes": [],
        "limitations": ["Automated visual assessment could not run."],
        "manual_review_required": True,
        "local_metrics": local_metrics,
        "latency_ms": 0,
    }

    if not images:
        return result

    try:
        from ai import get_config, ai_generate, redact_personal_data
        from ai.prompts import BEFORE_AFTER_SYSTEM, before_after_user

        config = get_config()
        context = {
            "title": redact_personal_data(title),
            "description": redact_personal_data(description),
            "category": category,
            "subcategory": subcategory,
            "district": district,
            "location_text": redact_personal_data(location_text),
            "pixel_change": local_metrics["pixel_change"],
            "edge_change": local_metrics["edge_change"],
            "before_quality": local_metrics["before_quality"],
            "after_quality": local_metrics["after_quality"],
            "solution": "",
        }
        meta = ai_generate(
            config, task="before_after",
            system_prompt=BEFORE_AFTER_SYSTEM,
            user_text=before_after_user(context),
            images=images,
        )
        result["latency_ms"] = meta.get("latency_ms", 0)
        if meta.get("success"):
            data = meta["data"]
            result.update({
                "success": True,
                "provider": meta.get("provider", "gemini"),
                "model": meta.get("model"),
                "resolution_status": data["resolution_status"],
                "resolution_score": data["resolution_score"],
                "same_scene_assessment": data["same_scene_assessment"],
                "same_scene_score": data["same_scene_score"],
                "before_issue_visible": data["before_issue_visible"],
                "after_issue_visible": data["after_issue_visible"],
                "evidence_relevance": data["evidence_relevance"],
                "summary": data["summary"] or result["summary"],
                "observed_changes": data["observed_changes"],
                "limitations": data["limitations"] or result["limitations"],
                "manual_review_required": data["manual_review_required"],
            })
        else:
            result["provider"] = "none"
    except Exception:
        logger.exception("Gemini before/after verification failed")
    return result


def resolution_decision(result):
    """Map a verification result to (status, resolved_bool).

    Status is one of Resolved / Reopened / Accepted by Officer (manual
    review pending). Pixel difference is never a decision rule.
    """
    status = result.get("resolution_status", "AI_UNAVAILABLE")
    score = result.get("resolution_score", 0) or 0
    manual = bool(result.get("manual_review_required", True))
    if status == "LIKELY_RESOLVED" and score >= RESOLVE_THRESHOLD and not manual:
        return "Resolved", True
    if status == "AI_UNAVAILABLE":
        return "Accepted by Officer", False
    return "Reopened", False


def resolution_note_text(result, officer_name=""):
    """Human-readable note stored in resolution_note (no provider secrets)."""
    label = RESOLUTION_STATUS_LABELS.get(
        result.get("resolution_status"), "Needs Review")
    lines = [
        "AI-assisted visual assessment: %s (score %s/100)."
        % (label, result.get("resolution_score", 0)),
    ]
    if result.get("summary"):
        lines.append(result["summary"])
    changes = result.get("observed_changes") or []
    if changes:
        lines.append("Observed: " + "; ".join(changes[:6]) + ".")
    scene = (result.get("same_scene_assessment") or "").replace("_", " ")
    if scene:
        lines.append("Site comparison: %s." % scene)
    limits = result.get("limitations") or []
    if limits:
        lines.append("Limitations: " + "; ".join(limits[:4]))
    if officer_name:
        lines.append("Submitted by %s." % officer_name)
    return " ".join(lines)[:2000]


# ---------------------------------------------------------------------------
# photo-vs-complaint verification — real Pillow cross-check (offline, no ML)
#
# This complements analyze_severity(): severity scores how BAD the problem
# looks, while verify_image_against_problem() checks whether the uploaded
# photo actually MATCHES the problem the citizen described.
# ---------------------------------------------------------------------------

CATEGORY_KEYWORDS = {
    "Roads & Infrastructure": [
        "road", "pothole", "crack", "break", "broken", "damage", "damaged",
        "pavement", "asphalt", "tar", "bridge", "footpath", "sidewalk",
        "trench", "dig", "digging", "barricade", "concrete", "highway",
        "lane", "speed breaker", "speedbreaker", "diversion", "surface",
        "repair", "filler", "manhole",
    ],
    "Water Resources": [
        "water", "leak", "leaking", "pipe", "flood", "flooded", "logging",
        "overflow", "overflowing", "drain", "sump", "tank", "supply", "bore",
        "well", "stagnant", "puddle", "pipeburst", "burst", "wet", "mud",
        "mosquito", "seepage", "pressure",
    ],
    "Electricity": [
        "electric", "electricity", "power", "light", "lighting", "streetlight",
        "street light", "fuse", "wire", "wires", "transformer", "pole",
        "voltage", "shock", "dark", "blackout", "cut", "inverter", "grid",
        "cable", "spark", "sparking", "burn", "burnt", "meter", "high tension",
    ],
    "Sanitation": [
        "garbage", "waste", "trash", "rubbish", "litter", "dump", "dumping",
        "dumped", "dirt", "sewage", "smell", "smelly", "open drain", "canal",
        "clean", "hygienic", "stale", "manure", "dung", "clutter", "debris",
        "odour", "rotten", "stagnant", "bins", "filth",
    ],
    "Healthcare": [
        "hospital", "clinic", "doctor", "medicine", "medical", "ambulance",
        "nurse", "pharmacy", "health", "first aid", "emergency", "bed", "ward",
        "dispensary", "injured", "patient", "vaccin", "anaemi", "ill", "sick",
    ],
    "Education": [
        "school", "college", "teacher", "classroom", "student", "blackboard",
        "library", "computer lab", "uniform", "mid-day", "toilet", "playground",
        "fence", "fencing", "building", "roof", "class", "admission", "books",
    ],
    "Public Safety": [
        "dark", "darkness", "crime", "violent", "violence", "threat", "harass",
        "stalk", "thief", "theft", "burglary", "unsafe", "safety", "patrol",
        "lighting", "streetlight", "street light", "footpath", "parapet",
        "fallen", "tree", "hang", "hanging", "sagging", "wire", "uncovered",
        "open manhole", "accident", "hit", "pothole", "slippery",
    ],
    # Phase-1 pilot focus areas (superset keywords so renamed categories keep
    # the same verification behaviour as their legacy equivalents).
    "Roads & Public Infrastructure": [
        "road", "pothole", "crack", "break", "broken", "damage", "damaged",
        "pavement", "asphalt", "tar", "bridge", "culvert", "footpath",
        "sidewalk", "streetlight", "street light", "drainage", "drain",
        "public asset", "access road", "lane", "highway", "manhole",
        "surface", "repair", "unsafe infrastructure",
    ],
    "Water & Sanitation": [
        "water", "handpump", "hand pump", "leak", "leaking", "pipeline",
        "pipe", "drinking water", "supply", "waterlogging", "logging",
        "flood", "overflow", "drain", "blocked drain", "sanitation",
        "toilet", "community toilet", "waste", "garbage", "accumulation",
        "bore", "well", "tank", "stagnant", "seepage",
    ],
    "Education Infrastructure": [
        "school", "classroom", "building", "roof", "wall", "toilet",
        "drinking water", "electricity", "classroom infrastructure",
        "accessibility", "ramp", "premises", "repair", "damaged",
        "unsafe classroom", "school premises",
    ],
}

OTHER_KEYWORDS = ["problem", "issue", "broken", "damaged", "repair", "broken",
                  "not working", "bad", "poor", "unusable", "blocked",
                  "collapsed", "dilapidated", "critical", "urgent"]


def _extract_features(image_path):
    """Open the photo and pull out hand-crafted visual features.

    Returns (features: dict, warnings: list) or (None, [error]) if the file
    is not a readable image. Warnings hold quality caveats (blur, darkness...).
    """
    try:
        img = Image.open(image_path)
        img = ImageOps.exif_transpose(img)  # respect camera rotation tag
        img.load()
    except Exception:
        return None, ["Could not read the uploaded file as an image."]

    width, height = img.size
    small = img.resize((96, 96)).convert("RGB")
    gray = small.convert("L")
    px = list(small.getdata())
    n = len(px)

    # average brightness (0-100) and exposure buckets
    lum = [int(0.299 * r + 0.587 * g + 0.114 * b) for r, g, b in px]
    brightness = sum(lum) / n / 255.0 * 100
    dark_ratio = sum(1 for v in lum if v < 55) / n
    bright_ratio = sum(1 for v in lum if v > 205) / n

    # sharpness: variance of a 3x3 Laplacian over the downsized image
    lap = gray.filter(ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0],
                                         scale=1))
    flat = list(lap.getdata())
    mean = sum(flat) / len(flat)
    blur = round(sum((v - mean) ** 2 for v in flat) / len(flat), 1)

    # edge density on 1-100 scale
    edges = sum(list(gray.filter(ImageFilter.FIND_EDGES).getdata())) / n / 255 * 100

    # colour composition buckets
    buckets = Counter()
    for r, g, b in px:
        mx, mn = max(r, g, b), min(r, g, b)
        sat = (mx - mn) / 255.0
        lum_v = (0.299 * r + 0.587 * g + 0.114 * b)
        if lum_v < 55:
            buckets["dark"] += 1
        elif mx - mn < 26 and lum_v > 200:
            buckets["white"] += 1
        elif mx - mn < 26:
            buckets["gray"] += 1
        elif b > r and b > g and (b - r) >= 18 and b >= 100 and lum_v < 175:
            buckets["water"] += 1
        elif g >= r + 10 and g >= b + 10 and lum_v > 40:
            buckets["green"] += 1
        elif r >= 90 and r > b + 20 and g >= b + 10:
            buckets["brown"] += 1
        elif r > g + 28 and r > b + 28 and lum_v > 55:
            buckets["bright_color"] += 1
        else:
            buckets["other"] += 1

    for key in ("dark", "white", "gray", "water", "green", "brown",
                "bright_color", "other"):
        buckets.setdefault(key, 0)

    colorfulness = round(
        sum((max(r, g, b) - min(r, g, b)) / 255.0 for r, g, b in px) / n * 100, 1)

    regions = {k: round(v / n, 3) for k, v in buckets.items()}

    features = {
        "width": width, "height": height,
        "pixels": width * height,
        "blur": blur,
        "brightness": round(brightness, 1),
        "dark_ratio": round(dark_ratio, 3),
        "bright_ratio": round(bright_ratio, 3),
        "edge_density": round(edges, 1),
        "colorfulness": colorfulness,
        "regions": regions,
    }

    warnings = []
    if blur < BLUR_MIN:
        warnings.append("Image looks blurry/out of focus — fine details may be hard to judge.")
    if dark_ratio > 0.60:
        warnings.append("Image is very dark — most of the scene is obscured.")
    if bright_ratio > 0.80:
        warnings.append("Image is overexposed/very bright — little can be confirmed from it.")
    if features["pixels"] < MIN_DETAIL_PIXELS:
        warnings.append("Image resolution is low — small details may be lost.")
    features["blank"] = features["edge_density"] < 6 and colorfulness < 7
    if features["blank"]:
        warnings.append("Image appears blank or near-uniform — it may not show a problem at all.")

    return features, warnings


def clamp(value, low=5, high=95):
    return round(max(low, min(high, value)))


def _score_roads(f):
    s, sigs = 30.0, []
    if f["edge_density"] > 45:
        s += 32; sigs.append("High edge density — consistent with cracking or a damaged surface.")
    elif f["edge_density"] > 30:
        s += 18; sigs.append("Moderate edge density — surface texture is visible.")
    if f["regions"]["gray"] > 0.32:
        s += 15; sigs.append("Large grey region — appears to be a paved/asphalt surface.")
    if 20 <= f["brightness"] <= 80:
        s += 10; sigs.append("Outdoor daylight capture with details visible.")
    return s, sigs


def _score_water(f):
    s, sigs = 30.0, []
    wr = f["regions"]["water"]
    if wr > 0.20:
        s += 45; sigs.append(f"~{int(wr * 100)}% of the frame is blue/water-toned — consistent with water logging, flooding or leakage.")
    elif wr > 0.08:
        s += 25; sigs.append("A water-toned region is visible in the frame.")
    if f["dark_ratio"] > 0.45:
        s += 10; sigs.append("Shadowed/wet ground detected — plausible for standing water.")
    return s, sigs


def _score_electricity(f):
    s, sigs = 30.0, []
    if f["dark_ratio"] > 0.50:
        s += 40; sigs.append("Image captured in darkness — consistent with a street-light/power failure.")
    if f["edge_density"] > 35:
        s += 15; sigs.append("Visible structures against the dark — masts/poles/wiring plausible.")
    return s, sigs


def _score_sanitation(f):
    s, sigs = 30.0, []
    if f["colorfulness"] > 24:
        s += 25; sigs.append("High colour variance — scattered clutter/debris is plausible.")
    if f["regions"]["brown"] > 0.22:
        s += 22; sigs.append("Large earthy/brown area — consistent with garbage or dirt piles.")
    if f["regions"]["green"] > 0.15 and f["regions"]["brown"] > 0.10:
        s += 10; sigs.append("Mixed organic tones — foliage mixed with waste is common at dumping sites.")
    if f["regions"]["white"] > 0.18:
        s += 8; sigs.append("Bright/white specks — plastic wraps or paper litter are common.")
    return s, sigs


def _score_facility(f):
    # Healthcare / Education — the photo should be a usable, well-lit shot of a site
    s, sigs = 50.0, []
    if f["blur"] >= BLUR_MIN:
        s += 15; sigs.append("Photo is sharp — structure/building details are readable.")
    if 15 <= f["brightness"] <= 85:
        s += 15; sigs.append("Well-exposed capture of the site.")
    if f["regions"]["green"] > 0.2:
        s += 8; sigs.append("Vegetation around the site is visible for context.")
    return s, sigs


def _score_public_safety(f):
    s, sigs = 30.0, []
    if f["dark_ratio"] > 0.50:
        s += 35; sigs.append("Image captured in darkness — poor/absent lighting visible.")
    if f["edge_density"] > 30:
        s += 20; sigs.append("Object edges visible — wires, sagging structures or obstacles plausible.")
    if f["bright_ratio"] > 0.7:
        s -= 15
    return s, sigs


def _score_generic(f):
    s, sigs = 42.0, []
    if f["blur"] >= BLUR_MIN:
        s += 15; sigs.append("Photo is sharp enough to inspect.")
    if 15 <= f["brightness"] <= 85:
        s += 13; sigs.append("Correctly exposed capture.")
    return s, sigs


def _score_water_sanitation(f):
    """Pilot Water & Sanitation scorer: best of the water and sanitation
    visual checks (leakage/standing water vs waste accumulation)."""
    ws, w_sigs = _score_water(f)
    ss, s_sigs = _score_sanitation(f)
    if ws >= ss:
        return ws, w_sigs
    return ss, s_sigs


_CATEGORY_SCORERS = {
    "Roads & Infrastructure": _score_roads,
    "Roads & Public Infrastructure": _score_roads,
    "Water Resources": _score_water,
    "Water & Sanitation": _score_water_sanitation,
    "Electricity": _score_electricity,
    "Sanitation": _score_sanitation,
    "Healthcare": _score_facility,
    "Education": _score_facility,
    "Education Infrastructure": _score_facility,
    "Public Safety": _score_public_safety,
    "Other": _score_generic,
}


def _match_keywords(text, keywords):
    low = text.lower()
    matched = [kw for kw in keywords if kw in low]
    return list(dict.fromkeys(matched))


# Keywords used only for the free-text category screen. Sweep words (problem,
# broken, repair...) never score — they appear in every card and would bias
# the match toward nothing in particular.
_CATEGORY_SWEEP_WORDS = {
    "problem", "issue", "broken", "damaged", "repair", "work", "need",
    "needed", "not working", "bad", "poor", "unusable", "blocked",
    "collapsed", "dilapidated", "critical", "urgent", "please", "fix",
}


def screen_category_match(title, description, selected_category):
    """Deterministic, keyless screen: does the free text belong to the card
    the citizen selected?

    Scores title+description against each active category's domain
    vocabulary (CATEGORY_DOMAIN_KEYWORDS). Generic sweep words are ignored.
    Returns:

    {
        "match": bool,          # True when text best fits the selected card
        "suggested": str,       # best-fitting active category
        "score": int,           # 0-100 confidence in the suggestion
        "selected": str,
        "note": str,            # short explanation for the citizen/officer
    }

    Weak or ambiguous text never blocks: when no card gains a clear lead the
    screen passes by default (AI sorts, humans decide; the citizen's chosen
    card is never silently rewritten).
    """
    import db as _db

    def _normalise(s):
        low = (s or "").lower()
        for token in sorted(_STOP_WORDS, key=len, reverse=True):
            low = low.replace(" " + token + " ", " ")
        return low.strip()

    text = _normalise((title or "") + " " + (description or "")).strip()
    if len(text) < 10:
        return {
            "match": True, "suggested": selected_category,
            "score": 0, "selected": selected_category,
            "note": "Description too short for reliable category screening.",
        }

    scores = {}
    for cat in _db.PILOT_CATEGORIES:
        kws = [k for k in CATEGORY_DOMAIN_KEYWORDS.get(cat, [])]
        hits = _match_keywords(text, kws)
        scores[cat] = len(hits)

    if not any(scores.values()):
        return {
            "match": True, "suggested": selected_category,
            "score": 0, "selected": selected_category,
            "note": "No category vocabulary detected; the citizen's card stands.",
        }

    top = max(scores, key=lambda c: scores[c])
    selected_score = scores.get(selected_category, 0)
    top_score = scores[top]
    # A clear lead requires >= 2 keyword hits and better than the selected
    # card by a margin, so short/ambiguous text passes.
    lead = top_score >= 2 and top_score >= selected_score + 1
    match = (not lead) or (top == selected_category)
    if match:
        return {
            "match": True, "suggested": top, "score": top_score,
            "selected": selected_category,
            "note": "Free text is consistent with the selected card.",
        }
    return {
        "match": False, "suggested": top, "score": top_score,
        "selected": selected_category,
        "note": (f"The description fits '{top}' better than '{selected_category}' — "
                "the citizen should switch cards or an officer reviews it."),
    }


def verify_image_against_problem(image_path, title, description, category):
    """Cross-check an uploaded photo against the citizen's stated problem.

    Opens the image, extracts visual features, scores how well the picture
    matches the reported category/description, and returns a verdict dict:

    {
        "ok": bool,                # False if the file isn't a readable image
        "confidence": int,         # 0-100
        "verified": bool,          # True when confidence >= VERIFY_THRESHOLD
        "note": str,               # one-line summary for the timeline
        "signals": [str],          # evidence the AI actually looked for
        "warnings": [str],         # quality caveats
        "category": str,
        "threshold": int,
    }
    """
    category = category if category in _CATEGORY_SCORERS else "Other"

    features, warnings = _extract_features(image_path)
    if features is None:
        return {
            "ok": False, "confidence": 0, "verified": False,
            "note": (warnings[0] if warnings else "Could not analyse the uploaded file.")
                    + " Routed for officer verification.",
            "signals": [], "warnings": warnings, "category": category,
            "threshold": VERIFY_THRESHOLD,
        }

    text = f"{title} {description} {category}"

    # --- textual cross-check ---------------------------------------------
    kw_list = CATEGORY_KEYWORDS.get(category, OTHER_KEYWORDS)
    matched = _match_keywords(text, kw_list)
    text_score = 15.0
    text_signals = []
    if matched:
        text_score = min(100.0, 30.0 * len(matched))
        clipped = matched[:6]
        text_signals.append(
            "Description keywords consistent with the category: " + ", ".join(clipped) + ".")

    # --- visual cross-check ----------------------------------------------
    scorer = _CATEGORY_SCORERS[category]
    visual_score, visual_signals = scorer(features)

    confidence = clamp(0.35 * text_score + 0.65 * visual_score)

    # quality gates — poor evidence caps confidence (never fully blocks)
    if features["blur"] < BLUR_MIN:
        confidence = min(confidence, 70)
    if features["dark_ratio"] > 0.60 and category not in ("Electricity", "Public Safety"):
        confidence = min(confidence, 65)
    if features["bright_ratio"] > 0.80:
        confidence = min(confidence, 60)
    if features["pixels"] < MIN_DETAIL_PIXELS:
        confidence = min(confidence, 70)
    if features["blank"]:
        if category in ("Electricity", "Public Safety") and features["dark_ratio"] > 0.5:
            warnings = [w for w in warnings
                        if w != "Image appears blank or near-uniform — it may not show a problem at all."]
        else:
            confidence = min(confidence, 25)

    verified = confidence >= VERIFY_THRESHOLD

    if verified:
        note = (f"AI cross-checked your photo against the reported problem "
                f"({category}) and found consistent visual and textual evidence "
                f"(confidence {confidence}%). Auto-verified.")
    else:
        note = (f"AI cross-check of the photo could not fully confirm the "
                f"reported problem ({category}) (confidence {confidence}%). "
                f"Routed to an officer for manual verification.")

    signals = (text_signals + visual_signals)[:7]

    return {
        "ok": True,
        "confidence": int(confidence),
        "verified": verified,
        "note": note,
        "signals": signals,
        "warnings": warnings,
        "category": category,
        "threshold": VERIFY_THRESHOLD,
    }


# ---------------------------------------------------------------------------
# AI duplicate detection — find reports that are likely about the same
# real-world problem. Deterministic and fully offline. The AI RECOMMENDS; a
# government officer always makes the final call.
# ---------------------------------------------------------------------------

def _tokenize(text):
    """Normalise text to lowercase word tokens, dropping stop words."""
    if not text:
        return []
    tokens = re.findall(r"[a-z\u0900-\u097f]+", text.lower())
    return [t for t in tokens if len(t) > 2 and t not in _STOP_WORDS]


def _jaccard_similarity(tokens_a, tokens_b):
    """Jaccard similarity 0-1 between two token lists."""
    set_a, set_b = set(tokens_a), set(tokens_b)
    if not set_a or not set_b:
        return 0.0
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def _haversine_metres(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points in metres."""
    r = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2)
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _location_score(lat1, lon1, lat2, lon2):
    """Geographic location similarity 0-1. None coords -> neutral 0.5."""
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return 0.5
    dist = _haversine_metres(lat1, lon1, lat2, lon2)
    if dist < LOCATION_DIST_NEAR:
        return 1.0
    if dist < LOCATION_DIST_CLOSE:
        return 0.8
    if dist < LOCATION_DIST_REGION:
        return 0.4
    if dist < LOCATION_DIST_FAR:
        return 0.1
    return 0.0


def _text_location_score(text_a, text_b):
    """Textual location similarity 0-1 when coordinates are unavailable."""
    ta, tb = _tokenize(text_a), _tokenize(text_b)
    if not ta or not tb:
        return 0.5
    return _jaccard_similarity(ta, tb)


def _image_visual_similarity(path_a, path_b):
    """Compare two images with cheap Pillow features. Returns 0-1 or None if
    either file cannot be read as an image.
    Signals considered: brightness, edge density, grayscale histogram."""
    try:
        img_a = Image.open(path_a).convert("L").resize((64, 64))
        img_b = Image.open(path_b).convert("L").resize((64, 64))
    except Exception:
        return None

    data_a = list(img_a.getdata())
    data_b = list(img_b.getdata())
    n = len(data_a)
    if n == 0:
        return None

    mean_a = sum(data_a) / n
    mean_b = sum(data_b) / n
    brightness_sim = 1.0 - abs(mean_a - mean_b) / 255.0

    edges_a = list(img_a.filter(ImageFilter.FIND_EDGES).getdata())
    edges_b = list(img_b.filter(ImageFilter.FIND_EDGES).getdata())
    ed_a = sum(edges_a) / n / 255.0
    ed_b = sum(edges_b) / n / 255.0
    edge_sim = 1.0 - abs(ed_a - ed_b)

    hist_a = [0] * 16
    hist_b = [0] * 16
    for v in data_a:
        hist_a[min(v * 16 // 256, 15)] += 1
    for v in data_b:
        hist_b[min(v * 16 // 256, 15)] += 1
    total_a = sum(hist_a) or 1
    total_b = sum(hist_b) or 1
    hist_diff = sum(abs(hist_a[i] / total_a - hist_b[i] / total_b)
                    for i in range(16))
    hist_sim = 1.0 - hist_diff / 2.0

    sim = round(brightness_sim * 0.3 + edge_sim * 0.3 + hist_sim * 0.4, 3)
    return sim


def _semantic_text(row):
    """Anonymized text for embeddings: category, subcategory, title,
    description, district, landmark/location only. Never name, phone,
    email, passwords or session identifiers."""
    get = row.get if isinstance(row, dict) else lambda k, d=None: getattr(row, k, d)
    parts = [
        "Focus Area: %s" % (get("category") or ""),
        "Subcategory: %s" % (get("subcategory") or ""),
        "Title: %s" % (get("title") or ""),
        "Description: %s" % (get("description") or ""),
        "District: %s" % (get("district") or ""),
        "Landmark: %s" % (get("landmark") or get("location_text") or ""),
    ]
    return "\n".join(parts)[:2000]


def _semantic_similarity(query_text, passage_text, query_vec=None):
    """Single-pair similarity (kept for match/university paths).

    `query_vec` is an optional precomputed (vector, method, model) triple.
    Returns (score 0-1, method "hf"|"gemini"|"local"). Never raises.
    """
    try:
        from ai import get_config
        from ai.embeddings import embed_texts
        from ai.utils import cosine_similarity as _cos

        if query_vec is None:
            query = embed_texts(get_config(), [query_text], kind="query")
            if query.get("ok"):
                query_vec = (query["vectors"][0], query.get("method", "hf"),
                             query.get("model"))
            else:
                query_vec = (None, "local", None)
        qvec, qmethod, qmodel = query_vec
        passage = embed_texts(get_config(), [passage_text], kind="passage",
                              model=qmodel)
        if qvec is not None and passage.get("ok"):
            return (max(0.0, min(1.0, float(_cos(qvec, passage["vectors"][0])))),
                    passage.get("method", qmethod))
        if qvec is not None:
            return 0.0, qmethod
    except Exception:
        logger.exception("Semantic similarity failed; using local fallback")
    a = _tokenize(query_text)
    return _jaccard_similarity(a, _tokenize(passage_text)), "local"


def _batch_semantic(query_text, passage_texts):
    """One query embedding + ONE batched passage call for a whole scan.

    Returns (similarities [...], method). Falls back to local Jaccard per
    pair when embeddings are unavailable. Never raises.
    """
    try:
        from ai import get_config
        from ai.embeddings import embed_texts
        from ai.utils import cosine_similarity as _cos

        cfg = get_config()
        query = embed_texts(cfg, [query_text], kind="query")
        if query.get("ok"):
            passages = embed_texts(cfg, passage_texts, kind="passage",
                                    model=query.get("model"))
            if passages.get("ok"):
                qvec = query["vectors"][0]
                sims = [max(0.0, min(1.0, float(_cos(qvec, v))))
                        for v in passages["vectors"]]
                return sims, query.get("method", "hf")
    except Exception:
        logger.exception("Batched semantic similarity failed")
    qt = _tokenize(query_text)
    return [_jaccard_similarity(qt, _tokenize(p)) for p in passage_texts], "local"


def _parse_created(value):
    try:
        from datetime import datetime

        if not value or not isinstance(value, str):
            return None
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _time_score(created_a, created_b):
    """1.0 within 7 days, decaying linearly to 0 at 90 days."""
    da, db_ = _parse_created(created_a), _parse_created(created_b)
    if da is None or db_ is None:
        return 0.5
    days = abs((da - db_).total_seconds()) / 86400.0
    if days <= 7:
        return 1.0
    if days >= 90:
        return 0.0
    return round(1.0 - (days - 7) / 83.0, 3)


def _prefilter_pair(a, b):
    """Cheap prefilter before embeddings: skip obvious non-matches so we
    never compare everything against everything. Conservative — keeps any
    pair sharing district, category, or minimal text overlap."""
    if (a.get("district") or "") == (b.get("district") or ""):
        return True
    if (a.get("category") or "") == (b.get("category") or ""):
        return True
    ta = set(_tokenize(a.get("title"))) | set(_tokenize(a.get("description")))
    tb = set(_tokenize(b.get("title"))) | set(_tokenize(b.get("description")))
    return _jaccard_similarity(ta, tb) >= 0.05


def _compare_pair(a, b, upload_dir=None, sem=None):
    """Hybrid duplicate comparison.

    Returns dict with confidence (0-100), classification (HIGH/MEDIUM/LOW),
    semantic_similarity, distance_metres (or None), duplicate_score (0-1),
    method ("hf"|"local"), reason, signals. Never auto-merges — callers
    persist PENDING matches for government review only.
    """
    signals = []

    # A. Semantic similarity (HF embeddings, local Jaccard fallback).
    # Bulk scans pass a precomputed (score, method) via sem.
    if sem is None:
        sem_sim, method = _semantic_similarity(_semantic_text(a), _semantic_text(b))
    else:
        sem_sim, method = sem
    if method in ("hf", "gemini"):
        signals.append(f"Semantically similar reports ({int(sem_sim * 100)}% embedding match)")
    elif sem_sim >= 0.4:
        signals.append(f"Highly similar descriptions ({int(sem_sim * 100)}% overlap)")
    elif sem_sim >= 0.2:
        signals.append(f"Similar wording in descriptions ({int(sem_sim * 100)}% overlap)")
    elif sem_sim <= 0.08:
        signals.append("Little description overlap")

    # B. Category + subcategory (15%)
    cat_a = (a.get("category") or "").strip()
    cat_b = (b.get("category") or "").strip()
    sub_a = (a.get("subcategory") or "").strip()
    sub_b = (b.get("subcategory") or "").strip()
    if cat_a == cat_b and sub_a and sub_a == sub_b:
        cat_score = 1.0
        signals.append(f"Same category and subcategory: {cat_a} / {sub_a}")
    elif cat_a == cat_b:
        cat_score = 0.8
        signals.append(f"Same category: {cat_a}")
    else:
        cat_score = 0.15
        signals.append(f"Different categories: {cat_a} vs {cat_b}")

    # C. District context
    dist_a = (a.get("district") or "").strip()
    dist_b = (b.get("district") or "").strip()
    if dist_a == dist_b:
        signals.append(f"Same district: {dist_a}")
    else:
        signals.append("Different districts")

    # D. Location (geographic when coords exist, else text)
    lat_a, lon_a = a.get("latitude"), a.get("longitude")
    lat_b, lon_b = b.get("latitude"), b.get("longitude")
    dist_m = None
    if lat_a is not None and lon_a is not None and lat_b is not None and lon_b is not None:
        loc_sim = _location_score(lat_a, lon_a, lat_b, lon_b)
        dist_m = _haversine_metres(lat_a, lon_a, lat_b, lon_b)
        if dist_m < 1000:
            signals.append(f"Reports are approximately {int(dist_m)}m apart")
        else:
            signals.append(f"Reports are approximately {dist_m / 1000:.1f}km apart")
    else:
        loc_tokens_a = _tokenize(a.get("location_text"))
        loc_tokens_b = _tokenize(b.get("location_text"))
        loc_sim = _text_location_score(
            a.get("location_text"), b.get("location_text"))
        if loc_tokens_a and loc_tokens_b and loc_sim >= 0.35:
            signals.append(
                f"Similar location descriptions ({int(loc_sim * 100)}% text match)")

    # E. Time proximity (5%)
    time_sim = _time_score(a.get("created_at"), b.get("created_at"))

    # F. Image similarity (only when both sides have readable images)
    img_sim = None
    img_a = a.get("photo_filename")
    img_b = b.get("photo_filename")
    if img_a and img_b and upload_dir:
        path_a, path_b = os.path.join(upload_dir, img_a), os.path.join(upload_dir, img_b)
        if os.path.exists(path_a) and os.path.exists(path_b):
            img_sim = _image_visual_similarity(path_a, path_b)
    if img_sim is not None:
        if img_sim >= 0.55:
            signals.append(f"Images show similar visual characteristics ({int(img_sim * 100)}% match)")
        else:
            signals.append(f"Images look visually different ({int(img_sim * 100)}% match)")

    # Weighted hybrid score; image weight redistributes when unavailable.
    weights = dict(DUPLICATE_WEIGHTS)
    if img_sim is None:
        img_w = weights.pop("image")
        rest = sum(weights.values()) or 1.0
        for key in weights:
            weights[key] += img_w * weights[key] / rest
    total_w = sum(weights.values()) or 1.0

    score = 0.0
    score += sem_sim * weights["semantic"] / total_w
    score += loc_sim * weights["location"] / total_w
    score += cat_score * weights["category"] / total_w
    score += time_sim * weights["time"] / total_w
    if img_sim is not None:
        score += img_sim * weights["image"] / total_w

    confidence = round(score * 100, 1)
    level = duplicate_level(confidence)
    classification = {"high": "HIGH", "medium": "MEDIUM"}.get(level, "LOW")
    reason_bits = [s for s in signals[:2]]
    if dist_m is not None:
        reason_bits.append("about %s apart" % (
            "%dm" % int(dist_m) if dist_m < 1000 else "%.1fkm" % (dist_m / 1000)))
    reason = ("Descriptions are semantically similar; " if sem_sim >= 0.4 else "") \
        + "; ".join(reason_bits)
    if not signals:
        signals.append("Limited similarity signals detected")
    return {"confidence": confidence, "signals": signals,
            "classification": classification,
            "semantic_similarity": round(sem_sim, 3),
            "distance_metres": int(dist_m) if dist_m is not None else None,
            "duplicate_score": round(score, 3),
            "method": method,
            "reason": reason[:400]}


def _row_dict(row):
    """Normalise sqlite3.Row / dict / SimpleNamespace into a plain dict."""
    if isinstance(row, dict):
        return row
    if hasattr(row, "keys"):
        return dict(row)
    return {k: getattr(row, k) for k in dir(row)}


def detect_duplicates(complaint, conn, upload_dir=None):
    """Compare a complaint against every other complaint and every existing
    Official Challenge, returning possible duplicate matches above the
    configurable medium threshold (DUPLICATE_THRESHOLD_MEDIUM).

    `complaint` must be a dict-like row (complaint + challenge_id).
    Returns a list sorted by confidence (highest first):
        {"candidate_type": "complaint"|"challenge",
         "candidate_id": int, "candidate_code": str,
         "confidence": float, "signals": [str]}

    This is deterministic-first with HF semantic embeddings when
    configured (see _semantic_similarity) — the AI only recommends.
    """
    matches = []
    complaint = _row_dict(complaint)
    complaint_id = complaint["id"]
    linked_challenge_id = complaint.get("challenge_id")

    # Phase 1: prefilter (cheap, local) so embeddings only run on plausible
    # candidates; cap the set so scans stay fast as the database grows.
    def _record(candidate_type, other, result):
        matches.append({
            "candidate_type": candidate_type,
            "candidate_id": other["id"],
            "candidate_code": other["code"],
            "confidence": result["confidence"],
            "signals": result["signals"],
            "classification": result["classification"],
            "semantic_similarity": result["semantic_similarity"],
            "distance_metres": result["distance_metres"],
            "duplicate_score": result["duplicate_score"],
            "method": result["method"],
            "reason": result["reason"],
        })
    cands, chals = [], []
    _seen = 0
    for other in conn.execute(
            "SELECT * FROM complaints WHERE id != ? ORDER BY id DESC",
            (complaint_id,)).fetchall():
        other = _row_dict(other)
        if linked_challenge_id and other["challenge_id"] == linked_challenge_id:
            continue
        if not _prefilter_pair(complaint, other):
            continue
        if _seen >= 150:
            break
        _seen += 1
        cands.append(other)
    for ch in conn.execute("SELECT * FROM challenges ORDER BY id DESC").fetchall():
        ch = _row_dict(ch)
        if linked_challenge_id and ch["id"] == linked_challenge_id:
            continue
        if not _prefilter_pair(complaint, ch):
            continue
        chals.append(ch)

    # Phase 2: ONE batched semantic call for the whole scan.
    query_text = _semantic_text(complaint)
    sems, _method = _batch_semantic(
        query_text, [_semantic_text(o) for o in cands + chals])

    # Phase 3: score pairs with precomputed semantics.
    for other, sem_sim in zip(cands, sems[:len(cands)]):
        result = _compare_pair(complaint, other, upload_dir,
                               sem=(sem_sim, _method))
        if result["confidence"] >= DUPLICATE_THRESHOLD_MEDIUM:
            # Location gate: far-apart reports (>50 km) are never the same
            # local problem, no matter how similar the wording.
            if (result["distance_metres"] or 0) > 50000:
                continue
            _record("complaint", other, result)
    for ch, sem_sim in zip(chals, sems[len(cands):]):
        result = _compare_pair(complaint, ch, upload_dir,
                               sem=(sem_sim, _method))
        if result["confidence"] >= DUPLICATE_THRESHOLD_MEDIUM:
            _record("challenge", ch, result)

    matches.sort(key=lambda m: m["confidence"], reverse=True)
    return matches


def duplicate_level(confidence):
    """Confidence level label for UI emphasis."""
    if confidence >= DUPLICATE_THRESHOLD_HIGH:
        return "high"
    if confidence >= DUPLICATE_THRESHOLD_MEDIUM:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# AI-assisted university matching — hybrid semantic + explicit signals.
#
# The AI recommends; government decides which institutions are invited; the
# university accepts or declines. Score = 65% semantic similarity (HF
# embeddings with local fallback) + 20% explicit expertise + 10% lab +
# 5% district. Every recommendation explains itself via signals.
# ---------------------------------------------------------------------------

UNIVERSITY_MATCH_WEIGHTS = {
    "expertise": 0.30,        # expertise keywords vs challenge domain
    "research_area": 0.20,    # research areas vs challenge topic
    "department_category": 0.15,  # department vs challenge category/subcategory
    "challenge_text": 0.15,   # Jaccard word overlap (challenge vs expertise)
    "lab": 0.10,              # lab capabilities relevant to the challenge
    "subcategory": 0.05,      # matches the challenge subcategory
    "geo": 0.05,              # same/nearby district (deliberately modest)
}

# Level thresholds (configurable in this single location).
UNIVERSITY_MATCH_THRESHOLDS = {
    "strong": 80,
    "good": 65,
    "possible": 50,
    "low": 0,
}
UNIVERSITY_MATCH_LEVELS = (
    ("strong", 80), ("good", 65), ("possible", 50), ("low", 0),
)

# Domain vocabulary per challenge category. Broad enough that a well-written
# expertise profile overlaps even when exact words differ. Pilot Phase-1
# names map to the same vocabularies as their legacy equivalents.
CATEGORY_DOMAIN_KEYWORDS = {
    "Roads & Infrastructure": [
        "road", "roads", "pothole", "potholes", "pavement", "asphalt", "civil",
        "infrastructure", "traffic", "transport", "transportation", "bridge",
        "drainage", "highway", "construction", "concrete", "repair",
        "waterlogging", "public works", "engineering",
    ],
    "Roads & Public Infrastructure": [
        "road", "roads", "pothole", "potholes", "pavement", "asphalt", "civil",
        "infrastructure", "traffic", "transport", "transportation", "bridge",
        "culvert", "streetlight", "drainage", "highway", "construction",
        "concrete", "repair", "waterlogging", "public works", "engineering",
        "footpath", "asset",
    ],
    "Water Resources": [
        "water", "irrigation", "flood", "flooding", "river", "dam", "reservoir",
        "canal", "drainage", "drinking", "groundwater", "hydrology", "watershed",
        "borewell", "pump", "drought", "rainwater", "harvesting",
    ],
    "Water & Sanitation": [
        "water", "handpump", "drinking", "pipeline", "leakage", "supply",
        "waterlogging", "drainage", "drain", "sanitation", "toilet",
        "irrigation", "flood", "groundwater", "hydrology", "pump",
        "waste", "hygiene", "conservation",
    ],
    "Electricity": [
        "electricity", "power", "grid", "energy", "electrical", "solar",
        "transmission", "distribution", "lighting", "streetlight", "renewable",
        "voltage", "substation", "smart grid", "load",
    ],
    "Sanitation": [
        "sanitation", "waste", "garbage", "sewage", "solid waste", "recycling",
        "hygiene", "drain", "landfill", "composting", "toilet", "swachh",
        "cleanliness", "wastewater",
    ],
    "Healthcare": [
        "healthcare", "hospital", "medicine", "public health", "maternal",
        "rural health", "vaccination", "telemedicine", "primary care",
        "nutrition", "epidemiology", "ambulance", "health",
    ],
    "Education": [
        "education", "school", "learning", "digital education", "literacy",
        "curriculum", "vocational", "teacher", "edtech", "classroom",
        "skill", "pedagogy",
    ],
    "Education Infrastructure": [
        "education", "school", "classroom", "building", "toilet",
        "drinking water", "electricity", "accessibility", "repair",
        "construction", "civil", "premises", "learning", "facility",
    ],
    "Public Safety": [
        "cybercrime", "cybersecurity", "security", "digital", "crime", "safety",
        "surveillance", "police", "intelligence", "network", "forensics",
        "disaster", "emergency", "fraud", "privacy",
    ],
    "Other": [
        "design", "technology", "innovation", "research", "development",
        "sustainability", "community", "governance",
    ],
}


def university_match_level(score):
    """Match level label for a 0-100 score (see UNIVERSITY_MATCH_LEVELS)."""
    for level, threshold in UNIVERSITY_MATCH_LEVELS:
        if score >= threshold:
            return level
    return "low"


def match_challenge_to_university(challenge, university, expertise_rows):
    """Score one verified university against one Official Challenge.

    `challenge`   dict/row with category, subcategory, title, description, district.
    `university`  dict/row with name, short_name, district.
    `expertise_rows` iterable of expertise profiles (department, expertise,
                    research_area, keywords, lab_capabilities, description).

    Returns:
        {
          "score": float 0-100,
          "level": "strong" | "good" | "possible" | "low",
          "signals": [str] human-readable reasons,
          "matched_keywords": [str],
        }
    """
    challenge = _row_dict(challenge)
    university = _row_dict(university)
    expertise_rows = [_row_dict(e) for e in expertise_rows]

    title_desc_tokens = set(_tokenize(challenge.get("title"))) | \
        set(_tokenize(challenge.get("description")))
    subcat_tokens = set(_tokenize(challenge.get("subcategory")))
    domain_tokens = set(CATEGORY_DOMAIN_KEYWORDS.get(
        challenge.get("category") or "Other", []))
    domain_tokens |= {t.lower() for t in subcat_tokens}
    all_challenge_tokens = title_desc_tokens | domain_tokens

    dept_tokens = set()
    research_tokens = set()
    knowledge_tokens = set()
    lab_tokens = set()
    has_lab = False

    for e in expertise_rows:
        dept_tokens |= set(_tokenize(e.get("department")))
        research_tokens |= set(_tokenize(e.get("research_area")))
        knowledge_tokens |= (
            set(_tokenize(e.get("expertise")))
            | set(_tokenize(e.get("keywords")))
            | set(_tokenize(e.get("description")))
        )
        lab = e.get("lab_capabilities") or ""
        if lab.strip():
            has_lab = True
            lab_tokens |= set(_tokenize(lab))

    signals = []
    weights = dict(UNIVERSITY_MATCH_WEIGHTS)

    # 1. Expertise keyword overlap with the challenge domain ---------------
    matched_expert = sorted(all_challenge_tokens & knowledge_tokens)
    if matched_expert:
        exp_score = 0.3 + 0.7 * min(1.0, len(matched_expert) / max(
            1, min(4, len(all_challenge_tokens))))
        kw_preview = ", ".join(matched_expert[:5])
        signals.append(f"{len(matched_expert)} matching expertise keyword(s): {kw_preview}")
    else:
        exp_score = 0.0
        signals.append("No expertise keywords overlap the challenge topic")

    # 2. Research area overlap ----------------------------------------------
    matched_res = sorted(all_challenge_tokens & research_tokens)
    if matched_res:
        res_score = 0.3 + 0.7 * min(1.0, len(matched_res) / 3.0)
        signals.append(
            f"Research area matches the challenge "
            f"({', '.join(matched_res[:3])})")
    else:
        res_score = 0.0
        signals.append("No research area overlaps the challenge topic")

    # 3. Department / category alignment -------------------------------------
    matched_dept = sorted((dept_tokens | knowledge_tokens)
                          & (domain_tokens | title_desc_tokens))
    if matched_dept:
        dept_score = 0.4 + 0.6 * min(1.0, len(matched_dept) / 3.0)
        signals.append(
            f"Department expertise aligns with the challenge "
            f"({', '.join(matched_dept[:3])})")
    else:
        dept_score = 0.0
        signals.append("Departments do not align with the challenge category")

    # 4. Challenge text similarity (Jaccard) -------------------------------
    text_score = _jaccard_similarity(
        sorted(title_desc_tokens), sorted(knowledge_tokens | research_tokens))
    if text_score >= 0.20:
        signals.append(
            f"Strong textual overlap with the challenge "
            f"({int(text_score * 100)}% word overlap)")
    elif text_score >= 0.08:
        signals.append(
            f"Some textual overlap with the challenge "
            f"({int(text_score * 100)}% word overlap)")

    # 5. Lab capabilities ----------------------------------------------------
    matched_lab = sorted(lab_tokens & (domain_tokens | title_desc_tokens))
    if matched_lab:
        lab_score = 1.0
        signals.append(f"Lab capabilities relevant: {', '.join(matched_lab[:3])}")
    else:
        lab_score = 0.15
        if has_lab:
            signals.append("Lab capabilities do not directly match this challenge")
        else:
            signals.append("No lab capabilities listed")

    # 6. Subcategory ----------------------------------------------------------
    if subcat_tokens:
        matched_sub = sorted(subcat_tokens & (knowledge_tokens | research_tokens | dept_tokens))
        if matched_sub:
            sub_score = 1.0
            signals.append(
                f"Matches the challenge subcategory: {challenge.get('subcategory')}")
        else:
            sub_score = 0.25
            signals.append(
                f"Does not overlap the subcategory ('{challenge.get('subcategory')}')")
    else:
        # No subcategory defined — fold its weight into challenge_text so the
        # available signals still sum to 100%.
        sub_score = 0.0
        weights["challenge_text"] += weights.pop("subcategory")

    # 7. Geographic relevance (deliberately a minor factor) ------------------
    univ_district = (university.get("district") or "").strip()
    ch_district = (challenge.get("district") or "").strip()
    if univ_district and univ_district == ch_district:
        geo_score = 1.0
        signals.append(f"Located in {univ_district} — same district as the challenge")
    else:
        geo_score = 0.2
        signals.append(
            f"Located in {univ_district or 'an unknown district'} — "
            "outside the challenge district")

    # 8. Semantic expertise match (HF embeddings, local fallback) ------------
    # Suggested: semantic 60 + prior-work 5 (no prior-work data is stored,
    # so those 5 points redistribute to semantic) + explicit expertise 20
    # + lab 10 + district 5. Government still invites manually.
    challenge_text = " ".join([
        str(challenge.get("title") or ""),
        str(challenge.get("description") or ""),
        str(challenge.get("category") or ""),
        str(challenge.get("subcategory") or ""),
        str(challenge.get("district") or ""),
    ])
    uni_bits = [str(university.get("name") or ""),
                str(university.get("short_name") or ""),
                str(university.get("district") or ""),
                str(university.get("description") or "")]
    for e in expertise_rows:
        uni_bits.extend([str(e.get("department") or ""),
                         str(e.get("expertise") or ""),
                         str(e.get("research_area") or ""),
                         str(e.get("keywords") or ""),
                         str(e.get("lab_capabilities") or ""),
                         str(e.get("description") or "")])
    sem_sim, sem_method = _semantic_similarity(
        challenge_text, "\n".join(b for b in uni_bits if b.strip()))
    if sem_method in ("hf", "gemini"):
        signals.append(f"{int(sem_sim * 100)}% semantic similarity to the challenge ({'HF' if sem_method == 'hf' else 'Gemini'} embeddings)")
    else:
        signals.append(f"{int(sem_sim * 100)}% semantic similarity to the challenge (keyword overlap)")
    if not expertise_rows:
        signals.append("Insufficient profile data for reliable AI matching — "
                       "score is indicative only")

    # Fold unavailable signals only when truly absent.
    if not research_tokens:
        weights["expertise"] += weights.pop("research_area", 0)
        res_score = 0.0
    if not has_lab:
        weights["expertise"] += weights.pop("lab", 0)
        lab_score = 0.0

    total_w = sum(weights.values()) or 1.0
    legacy = (
        exp_score * weights.get("expertise", 0)
        + res_score * weights.get("research_area", 0)
        + dept_score * weights.get("department_category", 0)
        + text_score * weights.get("challenge_text", 0)
        + lab_score * weights.get("lab", 0)
        + sub_score * weights.get("subcategory", 0)
        + geo_score * weights.get("geo", 0)
    ) / total_w

    hybrid = (sem_sim * 0.65 + exp_score * 0.20
              + lab_score * 0.10 + geo_score * 0.05)
    legacy_final = round(min(100.0, max(0.0, legacy * 100)), 1)
    if sem_method == "hf":
        score = round(min(100.0, max(0.0, hybrid * 100)), 1)
    else:
        # Offline fallback: blend with the transparent keyword score so
        # local-only matching still ranks sensibly (method is disclosed).
        score = round(min(100.0, max(0.0, (0.5 * hybrid + 0.5 * legacy) * 100)), 1)

    return {
        "score": score,
        "level": university_match_level(score),
        "signals": (["Why this institution?"] + signals)[:10],
        "matched_keywords": matched_expert[:8],
        "semantic_similarity": round(sem_sim, 3),
        "semantic_method": sem_method,
        "legacy_score": legacy_final,
    }


# ---------------------------------------------------------------------------
# Phase 5 — industry / startup / MSME fit for project discovery
# ---------------------------------------------------------------------------

INDUSTRY_FIT_WEIGHTS = {
    "expertise": 0.40,       # core_expertise keywords vs project domain
    "technology": 0.25,      # technologies vs project requirements
    "sector": 0.15,          # sector name vs challenge category
    "text": 0.15,            # Jaccard word overlap with the project brief
    "geo": 0.05,             # same district (deliberately modest)
}

INDUSTRY_FIT_LEVELS = (
    ("strong", 70), ("good", 50), ("possible", 30), ("low", 0),
)


def industry_fit_level(score):
    for level, threshold in INDUSTRY_FIT_LEVELS:
        if score >= threshold:
            return level
    return "low"


def industry_project_fit(project, organization):
    """Hybrid semantic compatibility score between a verified industry
    organization and a ready project: 60% semantic profile similarity (HF
    embeddings, local fallback) + 20% expertise + 10% technology + 5%
    sector + 5% district. Read-only; government decides collaborations.

    `project`       hydrated project with .challenge/.proposal/.title/.description
    `organization`  hydrated industry org with .sector/.core_expertise/
                    .technologies/.capabilities/.description/.district

    Returns:
        {"score": float 0-100, "level": str, "signals": [str],
         "semantic_similarity": float, "semantic_method": str, "legacy_score": float}
    """
    challenge = _row_dict(getattr(project, "challenge", None) or {})
    proposal = _row_dict(getattr(project, "proposal", None) or {})
    organization = _row_dict(organization or {})

    domain_tokens = set(CATEGORY_DOMAIN_KEYWORDS.get(
        challenge.get("category") or "Other", []))
    domain_tokens |= set(_tokenize(challenge.get("subcategory")))

    project_preview = " ".join([
        str(project.title or ""), str(project.description or ""),
        str(challenge.get("title") or ""), str(challenge.get("description") or ""),
        str(proposal.get("problem_statement") or ""),
        str(proposal.get("proposed_solution") or ""),
        str(proposal.get("expected_outcome") or ""),
    ])
    project_tokens = set(_tokenize(project_preview)) | domain_tokens

    sectors = set(_tokenize(organization.get("sector")))
    expertise = " ".join([
        str(organization.get("core_expertise") or ""),
        str(organization.get("capabilities") or ""),
        str(organization.get("description") or ""),
    ])
    expertise_tokens = set(_tokenize(expertise))
    technology_tokens = set(_tokenize(organization.get("technologies")))

    all_org_tokens = expertise_tokens | technology_tokens | sectors
    signals = []
    weights = dict(INDUSTRY_FIT_WEIGHTS)

    # 1. Expertise / capability overlap with the project brief -------------
    matched_exp = sorted(project_tokens & expertise_tokens)
    if matched_exp:
        exp_score = 0.3 + 0.7 * min(1.0, len(matched_exp) / 4.0)
        signals.append(f"{len(matched_exp)} matching expertise keyword(s): "
                       f"{', '.join(matched_exp[:5])}")
    else:
        exp_score = 0.0
        signals.append("No expertise keywords overlap the project brief")

    # 2. Technology fit ------------------------------------------------------
    matched_tech = sorted(project_tokens & technology_tokens)
    if technology_tokens:
        if matched_tech:
            tech_score = 0.4 + 0.6 * min(1.0, len(matched_tech) / 2.0)
            signals.append(f"Technologies relevant to the project: "
                           f"{', '.join(matched_tech[:4])}")
        else:
            tech_score = 0.15
            signals.append("Technologies listed do not overlap the project brief")
    else:
        tech_score = 0.0
        signals.append("No technologies listed in the profile")

    # 3. Sector vs challenge category ----------------------------------------
    matched_sector = sorted(domain_tokens & sectors)
    if sectors:
        if matched_sector:
            sector_score = 0.6 + 0.4 * min(1.0, len(matched_sector) / 1.0)
            signals.append(f"Sector matches the challenge category "
                           f"({', '.join(matched_sector[:3])})")
        else:
            sector_score = 0.2
            signals.append("Sector does not directly match the challenge category")
    else:
        sector_score = 0.0
        signals.append("No sector described")

    # 4. Textual overlap ------------------------------------------------------
    text_score = _jaccard_similarity(
        sorted(project_tokens), sorted(all_org_tokens))
    if text_score >= 0.15:
        signals.append(f"Strong textual overlap with the project "
                        f"({int(text_score * 100)}% word overlap)")
    elif text_score >= 0.06:
        signals.append(f"Some textual overlap with the project "
                        f"({int(text_score * 100)}% word overlap)")

    # 5. Geographic relevance -------------------------------------------------
    org_district = (organization.get("district") or "").strip()
    proj_district = (challenge.get("district") or "").strip()
    if org_district and proj_district and org_district == proj_district:
        geo_score = 1.0
        signals.append(f"Located in {org_district} — same district as the project")
    else:
        geo_score = 0.2
        signals.append(
            f"Located in {org_district or 'an unknown district'} — outside "
            "the project district")

    # 6. Semantic profile match (HF embeddings, local fallback) --------------
    org_profile = "\n".join([
        str(organization.get("name") or ""),
        str(organization.get("org_type") or ""),
        str(organization.get("sector") or ""),
        str(organization.get("core_expertise") or ""),
        str(organization.get("technologies") or ""),
        str(organization.get("capabilities") or ""),
        str(organization.get("description") or ""),
    ])
    project_brief = " ".join([
        str(project.title or "") if hasattr(project, "title") else "",
        str(challenge.get("title") or ""), str(challenge.get("description") or ""),
        str(challenge.get("category") or ""), str(challenge.get("subcategory") or ""),
        str(proposal.get("proposed_solution") or ""),
        str(proposal.get("expected_outcome") or ""),
    ])
    sem_sim, sem_method = _semantic_similarity(project_brief, org_profile)
    if sem_method == "hf":
        signals.append(f"{int(sem_sim * 100)}% semantic similarity to project needs (HF embeddings)")
    else:
        signals.append(f"{int(sem_sim * 100)}% semantic similarity to project needs (keyword overlap)")

    profile_bits = [organization.get("core_expertise"), organization.get("technologies"),
                    organization.get("capabilities"), organization.get("description")]
    if not any((b or "").strip() for b in profile_bits):
        signals.append("Insufficient profile data for reliable AI matching — "
                       "score is indicative only")

    if not technology_tokens:
        weights["expertise"] += weights.pop("technology", 0)
        tech_score = 0.0
    if not sectors:
        weights["expertise"] += weights.pop("sector", 0)
        sector_score = 0.0

    total_w = sum(weights.values()) or 1.0
    legacy = (
        exp_score * weights.get("expertise", 0)
        + tech_score * weights.get("technology", 0)
        + sector_score * weights.get("sector", 0)
        + text_score * weights.get("text", 0)
        + geo_score * weights.get("geo", 0)
    ) / total_w

    # Semantic-led hybrid: semantic 60 + expertise 20 + technology 10 +
    # sector 5 + district 5. Offline: blend with the keyword score.
    hybrid = (sem_sim * 0.60 + exp_score * 0.20 + tech_score * 0.10
              + sector_score * 0.05 + geo_score * 0.05)
    legacy_final = round(min(100.0, max(0.0, legacy * 100)), 1)
    if sem_method == "hf":
        score = round(min(100.0, max(0.0, hybrid * 100)), 1)
    else:
        score = round(min(100.0, max(0.0, (0.5 * hybrid + 0.5 * legacy) * 100)), 1)

    score = round(min(100.0, max(0.0, score)), 1)
    return {
        "score": score,
        "level": industry_fit_level(score),
        "signals": (["Why this partner?"] + signals)[:10],
        "semantic_similarity": round(sem_sim, 3),
        "semantic_method": sem_method,
        "legacy_score": legacy_final,
    }
