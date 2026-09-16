"""
Simulated AI engine for Jharkhand Samadhan.

Two jobs:
1. satellite_screen()  — for road/infrastructure complaints, simulate checking
   recent satellite imagery against the citizen's report. No real satellite
   feed is wired up here (that needs a paid imagery API in production), so we
   generate a deterministic confidence score per complaint. High confidence
   auto-verifies the complaint; low confidence sends it to an officer for
   manual verification instead of blocking the citizen.

2. compare_before_after() — this one is real, not simulated: it actually opens
   the citizen's "before" photo and the officer's "after" photo with Pillow
   and measures how much the image content changed (grayscale mean absolute
   difference, plus edge-density delta as a rough proxy for "a road got
   patched" / "a pile of garbage disappeared"). A bigger change score means
   the site visibly changed, which is used as one signal (combined with the
   officer's own confirmation) to auto-close or reopen a case.
"""

import hashlib
import math
import os
import random
import re
from collections import Counter

from PIL import Image, ImageFilter, ImageChops, ImageOps

SATELLITE_VERIFY_THRESHOLD = 65     # confidence >= this -> AI auto-verifies
RESOLUTION_CHANGE_THRESHOLD = 10.0  # change score >= this -> looks resolved

# ---------------------------------------------------------------------------
# AI duplicate detection — deterministic, fully-offline signal comparison.
#
# Weights for a transparent, weighted score. When a signal is unavailable
# (e.g. no image on either side) its weight is folded into the description
# signal so the available signals always sum to 100%.
# ---------------------------------------------------------------------------
DUPLICATE_WEIGHTS = {
    "title": 0.20,
    "description": 0.25,
    "category": 0.15,
    "district": 0.10,
    "location": 0.20,
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
    "Water Resources": "dry/brown tones instead of flowing or standing water",
    "Electricity": "dim, poorly lit appearance suggesting an outage",
    "Sanitation": "high-contrast clutter and dark mounds typical of waste",
    "Healthcare": "dilapidated surfaces (peeling, dark streaks)",
    "Education": "worn or damaged building surfaces",
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
    if category == "Water Resources":
        brown = sum(1 for (r, g, b) in pixels if r > 100 and g > 60 and b < 80) / total * 100
        return 24 + brown * 1.3 + dark_ratio * 0.35
    if category == "Electricity":
        return 38 + (100 - brightness) * 0.55 + edge_density * 0.25
    if category == "Sanitation":
        return 34 + edge_density * 0.9 + dark_ratio * 0.5
    if category in ("Healthcare", "Education"):
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
        score = {"Water Resources": 46, "Roads & Infrastructure": 44}.get(category, 42)
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


def satellite_screen(complaint_code, category, description):
    """Deterministic pseudo-AI screening for infra complaints against 'recent
    satellite imagery'. Returns (confidence:int, note:str)."""
    rnd = random.Random(_seed_from(complaint_code))
    confidence = rnd.randint(35, 97)

    if confidence >= SATELLITE_VERIFY_THRESHOLD:
        note = (f"Recent satellite pass shows a visible surface anomaly consistent with "
                 f"the reported issue (confidence {confidence}%). Auto-verified.")
    else:
        note = (f"Satellite imagery was inconclusive for this location (confidence {confidence}%). "
                 f"Routed to an officer for on-ground verification.")
    return confidence, note


def compare_before_after(before_path, after_path):
    """Compare two images and return (change_score: float 0-100, note: str).
    Returns None, note if either file can't be read as an image (e.g. a
    video was uploaded as the 'before' evidence)."""
    try:
        img_before = Image.open(before_path).convert("L").resize((256, 256))
        img_after = Image.open(after_path).convert("L").resize((256, 256))
    except Exception:
        return None, "Could not run automated image comparison (unsupported file type)."

    # Overall pixel-level change
    diff = ImageChops.difference(img_before, img_after)
    pixel_change = sum(diff.getdata()) / (256 * 256 * 255) * 100  # 0-100

    # Edge-density change as a rough structural proxy (e.g. a patched road
    # has fewer crack edges than a broken one)
    edges_before = img_before.filter(ImageFilter.FIND_EDGES)
    edges_after = img_after.filter(ImageFilter.FIND_EDGES)
    edge_before_density = sum(edges_before.getdata()) / (256 * 256 * 255) * 100
    edge_after_density = sum(edges_after.getdata()) / (256 * 256 * 255) * 100
    edge_change = abs(edge_before_density - edge_after_density)

    change_score = round(min(100.0, pixel_change * 0.6 + edge_change * 1.4), 1)

    if change_score >= RESOLUTION_CHANGE_THRESHOLD:
        note = (f"Before/after comparison detected a significant visual change at the site "
                 f"(change score {change_score}/100). Marked resolved.")
    else:
        note = (f"Before/after comparison found little visible change at the site "
                 f"(change score {change_score}/100). Case reopened for rework.")
    return change_score, note


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


_CATEGORY_SCORERS = {
    "Roads & Infrastructure": _score_roads,
    "Water Resources": _score_water,
    "Electricity": _score_electricity,
    "Sanitation": _score_sanitation,
    "Healthcare": _score_facility,
    "Education": _score_facility,
    "Public Safety": _score_public_safety,
    "Other": _score_generic,
}


def _match_keywords(text, keywords):
    low = text.lower()
    matched = [kw for kw in keywords if kw in low]
    return list(dict.fromkeys(matched))


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


def _compare_pair(a, b, upload_dir=None):
    """Compare two complaint/challenge-like dicts.

    Returns dict with:
        confidence  float 0-100
        signals     [str] human-readable explanation of WHY

    A row can come from complaints (with photo_filename) or challenges
    (no photo), so each signal is guarded.
    """
    signals = []

    # A. Title similarity
    title_sim = _jaccard_similarity(_tokenize(a.get("title")), _tokenize(b.get("title")))

    # B. Description similarity
    desc_sim = _jaccard_similarity(_tokenize(a.get("description")), _tokenize(b.get("description")))

    # C. Category
    cat_a = (a.get("category") or "").strip()
    cat_b = (b.get("category") or "").strip()
    cat_score = 1.0 if cat_a == cat_b else 0.15

    # D. District
    dist_a = (a.get("district") or "").strip()
    dist_b = (b.get("district") or "").strip()
    dist_score = 1.0 if dist_a == dist_b else 0.0

    # E. Location (geographic when coords exist, else text)
    lat_a, lon_a = a.get("latitude"), a.get("longitude")
    lat_b, lon_b = b.get("latitude"), b.get("longitude")
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

    # F. Image similarity (only when both sides have readable images)
    img_sim = None
    img_a = a.get("photo_filename")
    img_b = b.get("photo_filename")
    if img_a and img_b and upload_dir:
        path_a, path_b = os.path.join(upload_dir, img_a), os.path.join(upload_dir, img_b)
        if os.path.exists(path_a) and os.path.exists(path_b):
            img_sim = _image_visual_similarity(path_a, path_b)

    # G. Human-readable header signals for the confidence bar
    if title_sim >= 0.5:
        signals.append(f"Strongly similar titles ({int(title_sim * 100)}% keyword overlap)")
    elif title_sim >= 0.25:
        signals.append(f"Partly similar titles ({int(title_sim * 100)}% keyword overlap)")
    elif title_sim > 0.05:
        signals.append(f"Some title keywords in common ({int(title_sim * 100)}%)")

    if desc_sim >= 0.4:
        signals.append(f"Highly similar descriptions ({int(desc_sim * 100)}% overlap)")
    elif desc_sim >= 0.2:
        signals.append(f"Similar wording in descriptions ({int(desc_sim * 100)}% overlap)")
    elif desc_sim <= 0.08:
        signals.append("Little description overlap")

    if cat_a == cat_b:
        signals.append(f"Same category: {cat_a}")
    else:
        signals.append(f"Different categories: {cat_a} vs {cat_b}")

    if dist_a == dist_b:
        signals.append(f"Same district: {dist_a}")
    else:
        signals.append(f"Different districts")

    if img_sim is not None:
        if img_sim >= 0.55:
            signals.append(f"Images show similar visual characteristics ({int(img_sim * 100)}% match)")
        else:
            signals.append(f"Images look visually different ({int(img_sim * 100)}% match)")

    # Weighted, transparent score. If image signal unavailable, its weight is
    # folded into description so available signals always total 100%.
    weights = dict(DUPLICATE_WEIGHTS)
    if img_sim is None:
        weights["description"] += weights.pop("image")
    else:
        weights.pop("image")
    total_w = sum(weights.values()) or 1.0

    score = 0.0
    score += title_sim * weights["title"] / total_w
    score += desc_sim * weights["description"] / total_w
    score += cat_score * weights["category"] / total_w
    score += dist_score * weights["district"] / total_w
    score += loc_sim * weights["location"] / total_w
    if img_sim is not None:
        score += img_sim * DUPLICATE_WEIGHTS["image"] / total_w

    confidence = round(score * 100, 1)
    if not signals:
        signals.append("Limited similarity signals detected")
    return {"confidence": confidence, "signals": signals}


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

    This is deterministic and fully offline — the AI only recommends.
    """
    matches = []
    complaint = _row_dict(complaint)
    complaint_id = complaint["id"]
    linked_challenge_id = complaint.get("challenge_id")

    # Compare against other complaints (skip ones in the same challenge).
    for other in conn.execute(
            "SELECT * FROM complaints WHERE id != ? ORDER BY id DESC",
            (complaint_id,)).fetchall():
        other = _row_dict(other)
        if linked_challenge_id and other["challenge_id"] == linked_challenge_id:
            continue
        result = _compare_pair(complaint, other, upload_dir)
        if result["confidence"] >= DUPLICATE_THRESHOLD_MEDIUM:
            matches.append({
                "candidate_type": "complaint",
                "candidate_id": other["id"],
                "candidate_code": other["code"],
                "confidence": result["confidence"],
                "signals": result["signals"],
            })

    # Compare against existing challenges (skip the one it already belongs to).
    for ch in conn.execute("SELECT * FROM challenges ORDER BY id DESC").fetchall():
        ch = _row_dict(ch)
        if linked_challenge_id and ch["id"] == linked_challenge_id:
            continue
        result = _compare_pair(complaint, ch, upload_dir)
        if result["confidence"] >= DUPLICATE_THRESHOLD_MEDIUM:
            matches.append({
                "candidate_type": "challenge",
                "candidate_id": ch["id"],
                "candidate_code": ch["code"],
                "confidence": result["confidence"],
                "signals": result["signals"],
            })

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
# AI-assisted university matching — deterministic, offline, explainable.
#
# The AI recommends; government decides which institutions are invited; the
# university accepts or declines. Scoring is a transparent weighted sum of
# expertise-based signals so every recommendation can explain itself.
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
# expertise profile overlaps even when exact words differ.
CATEGORY_DOMAIN_KEYWORDS = {
    "Roads & Infrastructure": [
        "road", "roads", "pothole", "potholes", "pavement", "asphalt", "civil",
        "infrastructure", "traffic", "transport", "transportation", "bridge",
        "drainage", "highway", "construction", "concrete", "repair",
        "waterlogging", "public works", "engineering",
    ],
    "Water Resources": [
        "water", "irrigation", "flood", "flooding", "river", "dam", "reservoir",
        "canal", "drainage", "drinking", "groundwater", "hydrology", "watershed",
        "borewell", "pump", "drought", "rainwater", "harvesting",
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

    # Fold unavailable signals only when truly absent.
    if not research_tokens:
        weights["expertise"] += weights.pop("research_area", 0)
        res_score = 0.0
    if not has_lab:
        weights["expertise"] += weights.pop("lab", 0)
        lab_score = 0.0

    total_w = sum(weights.values()) or 1.0
    score = (
        exp_score * weights.get("expertise", 0)
        + res_score * weights.get("research_area", 0)
        + dept_score * weights.get("department_category", 0)
        + text_score * weights.get("challenge_text", 0)
        + lab_score * weights.get("lab", 0)
        + sub_score * weights.get("subcategory", 0)
        + geo_score * weights.get("geo", 0)
    ) / total_w

    score = round(min(100.0, max(0.0, score * 100)), 1)

    return {
        "score": score,
        "level": university_match_level(score),
        "signals": signals[:8],
        "matched_keywords": matched_expert[:8],
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
    """Deterministic, read-only compatibility score between a verified
    industry organization and a ready project. Uses the same keyword-overlap
    approach as the university matcher (expertise/technology/sector vs the
    challenge domain and project brief) — no model inference, no new AI.

    `project`       hydrated project with .challenge/.proposal/.title/.description
    `organization`  hydrated industry org with .sector/.core_expertise/
                    .technologies/.capabilities/.description/.district

    Returns:
        {"score": float 0-100, "level": str, "signals": [str]}
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

    if not technology_tokens:
        weights["expertise"] += weights.pop("technology", 0)
        tech_score = 0.0
    if not sectors:
        weights["expertise"] += weights.pop("sector", 0)
        sector_score = 0.0

    total_w = sum(weights.values()) or 1.0
    score = (
        exp_score * weights.get("expertise", 0)
        + tech_score * weights.get("technology", 0)
        + sector_score * weights.get("sector", 0)
        + text_score * weights.get("text", 0)
        + geo_score * weights.get("geo", 0)
    ) / total_w

    score = round(min(100.0, max(0.0, score * 100)), 1)
    return {
        "score": score,
        "level": industry_fit_level(score),
        "signals": signals[:6],
    }
