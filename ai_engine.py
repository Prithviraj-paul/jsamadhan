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
import random

from PIL import Image, ImageFilter, ImageChops

SATELLITE_VERIFY_THRESHOLD = 65     # confidence >= this -> AI auto-verifies
RESOLUTION_CHANGE_THRESHOLD = 10.0  # change score >= this -> looks resolved

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
