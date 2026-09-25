"""Validated schemas for every AI task.

Each entry describes the expected JSON shape; `validate(task, data)`
returns (ok, cleaned_dict, errors). Cleaning clamps numbers, restricts
enums to the Phase-1 pilot vocabulary and caps string lengths so a
misbehaving model can never corrupt application state.
"""

from .utils import (
    clean_bool,
    clean_enum,
    clamp_int as clean_int,
    clean_list_of_str,
    clean_text,
)

PILOT_CATEGORIES = (
    "Roads & Infrastructure",
    "Water Resources",
    "Electricity",
    "Sanitation",
    "Healthcare",
    "Education",
)

SEVERITIES = ("low", "normal", "high", "critical")
DESCRIPTION_QUALITY = ("insufficient", "sufficient", "detailed")
DUPLICATE_CLASSES = ("HIGH", "MEDIUM", "LOW")
READINESS_RECOMMENDATIONS = (
    "CONTINUE_MONITORING",
    "REVIEW_FOR_CHALLENGE",
    "HIGH_PRIORITY_REVIEW",
)
PROBLEM_ALIGNMENT = ("low", "medium", "high")


def _validate_complaint(d):
    return {
        "summary": clean_text(d.get("summary"), 500),
        "recommended_category": clean_enum(
            d.get("recommended_category"), PILOT_CATEGORIES, PILOT_CATEGORIES[0]
        ),
        "recommended_subcategory": clean_text(
            d.get("recommended_subcategory"), 80, default="Other"
        ),
        "severity_score": clean_int(d.get("severity_score"), 0, 100, 42),
        "severity": clean_enum(d.get("severity"), SEVERITIES, "normal"),
        "urgency": clean_enum(d.get("urgency"), SEVERITIES, "normal"),
        "evidence_relevant": clean_bool(d.get("evidence_relevant"), False),
        "evidence_confidence": round(
            max(0.0, min(1.0, float(d.get("evidence_confidence", 0.0) or 0.0))), 2
        ),
        "description_quality": clean_enum(
            d.get("description_quality"), DESCRIPTION_QUALITY, "sufficient"
        ),
        "possible_safety_risk": clean_bool(d.get("possible_safety_risk"), False),
        "reasoning_summary": clean_list_of_str(d.get("reasoning_summary")),
        "missing_information": clean_list_of_str(d.get("missing_information")),
        "limitations": clean_list_of_str(d.get("limitations")),
    }


RESOLUTION_STATUSES = (
    "LIKELY_RESOLVED",
    "PARTIALLY_RESOLVED",
    "NOT_RESOLVED",
    "INSUFFICIENT_EVIDENCE",
    "POSSIBLE_DIFFERENT_LOCATION",
    "AI_UNAVAILABLE",
)
SAME_SCENE = ("likely_same_site", "possibly_same_site", "likely_different_site")
EVIDENCE_RELEVANCE = ("HIGH", "MEDIUM", "LOW")


def _validate_before_after(d):
    return {
        "same_scene_assessment": clean_enum(
            d.get("same_scene_assessment"), SAME_SCENE, "possibly_same_site"
        ),
        "same_scene_score": clean_int(d.get("same_scene_score"), 0, 100, 50),
        "before_issue_visible": clean_bool(d.get("before_issue_visible"), False),
        "after_issue_visible": clean_bool(d.get("after_issue_visible"), False),
        "resolution_status": clean_enum(
            d.get("resolution_status"), RESOLUTION_STATUSES, "INSUFFICIENT_EVIDENCE"
        ),
        "resolution_score": clean_int(d.get("resolution_score"), 0, 100, 0),
        "evidence_relevance": clean_enum(
            d.get("evidence_relevance"), EVIDENCE_RELEVANCE, "LOW"
        ),
        "summary": clean_text(d.get("summary"), 800),
        "observed_changes": clean_list_of_str(d.get("observed_changes")),
        "limitations": clean_list_of_str(d.get("limitations")),
        "manual_review_required": clean_bool(d.get("manual_review_required"), True),
        # Backwards-compatible aliases kept for older callers/templates.
        "visible_change": clean_bool(d.get("visible_change"), False),
        "change_type": clean_text(d.get("change_type"), 200),
        "confidence": round(
            max(0.0, min(1.0, float(d.get("confidence", 0.0) or 0.0))), 2
        ),
        "evidence_supports_improvement": clean_bool(
            d.get("evidence_supports_improvement"), False
        ),
    }


def _validate_duplicate(d):
    return {
        "duplicate_probability": round(
            max(0.0, min(1.0, float(d.get("duplicate_probability", 0.0) or 0.0))), 3
        ),
        "semantic_similarity": round(
            max(0.0, min(1.0, float(d.get("semantic_similarity", 0.0) or 0.0))), 3
        ),
        "classification": clean_enum(
            d.get("classification"), DUPLICATE_CLASSES, "LOW"
        ),
        "reason": clean_text(d.get("reason"), 400),
    }


def _validate_readiness(d):
    return {
        "summary": clean_text(d.get("summary"), 600),
        "recommendation": clean_enum(
            d.get("recommendation"),
            READINESS_RECOMMENDATIONS,
            "CONTINUE_MONITORING",
        ),
        "key_signals": clean_list_of_str(d.get("key_signals"), max_items=10),
        "missing_evidence": clean_list_of_str(d.get("missing_evidence"), max_items=10),
    }


def _validate_match_explain(d):
    return {
        "explanation": clean_text(d.get("explanation"), 600),
        "key_signals": clean_list_of_str(d.get("key_signals"), max_items=8),
    }


def _validate_proposal(d):
    return {
        "executive_summary": clean_text(d.get("executive_summary"), 800),
        "problem_alignment": clean_enum(
            d.get("problem_alignment"), PROBLEM_ALIGNMENT, "medium"
        ),
        "strengths": clean_list_of_str(d.get("strengths"), max_items=8),
        "risks": clean_list_of_str(d.get("risks"), max_items=8),
        "missing_information": clean_list_of_str(
            d.get("missing_information"), max_items=8
        ),
        "pilot_considerations": clean_list_of_str(
            d.get("pilot_considerations"), max_items=8
        ),
        "measurable_metrics_found": clean_list_of_str(
            d.get("measurable_metrics_found"), max_items=8
        ),
        "clarification_questions": clean_list_of_str(
            d.get("clarification_questions"), max_items=8
        ),
    }


def _validate_pilot_impact(d):
    return {
        "summary": clean_text(d.get("summary"), 800),
        "goals_met": clean_list_of_str(d.get("goals_met"), max_items=8),
        "goals_partially_met": clean_list_of_str(
            d.get("goals_partially_met"), max_items=8
        ),
        "missing_evidence": clean_list_of_str(d.get("missing_evidence"), max_items=8),
        "risks_to_scaling": clean_list_of_str(d.get("risks_to_scaling"), max_items=8),
    }


def _validate_challenge_draft(d):
    return {
        "title": clean_text(d.get("title"), 200),
        "problem_statement": clean_text(d.get("problem_statement"), 1500),
        "evidence_summary": clean_text(d.get("evidence_summary"), 1000),
        "affected_area": clean_text(d.get("affected_area"), 300),
        "recurring_pattern": clean_text(d.get("recurring_pattern"), 500),
        "desired_outcomes": clean_text(d.get("desired_outcomes"), 800),
        "success_indicators": clean_list_of_str(
            d.get("success_indicators"), max_items=8
        ),
    }


def _validate_report_parse(d):
    cat = clean_enum(d.get("category"), PILOT_CATEGORIES, "")
    sub = clean_text(d.get("subcategory"), 80)
    try:
        import db as _db

        allowed = _db.PILOT_SUBCATEGORIES.get(cat, []) if cat else []
        if sub not in allowed:
            sub = ""
    except Exception:
        if not cat:
            sub = ""
    districts = ()
    try:
        import db as _db2

        districts = tuple(_db2.DISTRICTS)
    except Exception:
        districts = ()
    dist = clean_text(d.get("district"), 60)
    if dist:
        match = next((x for x in districts if x.lower() == dist.lower()), "")
        dist = match
    aff = d.get("people_affected")
    try:
        aff = int(aff) if aff not in (None, "") else None
    except (TypeError, ValueError):
        aff = None
    if aff is not None and not (0 <= aff <= 1000000):
        aff = None
    return {
        "title": clean_text(d.get("title"), 150),
        "description": clean_text(d.get("description"), 3000),
        "category": cat,
        "subcategory": sub,
        "district": dist,
        "landmark": clean_text(d.get("landmark"), 200),
        "location": clean_text(d.get("location"), 300),
        "duration": clean_enum(
            d.get("duration"),
            ("just_started", "days", "weeks", "months", "long"), ""),
        "people_affected": aff,
        "frequency": clean_enum(
            d.get("frequency"), ("one_time", "recurring"), ""),
    }


_VALIDATORS = {
    "complaint_analysis": _validate_complaint,
    "before_after": _validate_before_after,
    "duplicate_pair": _validate_duplicate,
    "challenge_readiness": _validate_readiness,
    "match_explain": _validate_match_explain,
    "proposal_review": _validate_proposal,
    "pilot_summary": _validate_pilot_impact,
    "impact_summary": _validate_pilot_impact,
    "challenge_draft": _validate_challenge_draft,
    "report_parse": _validate_report_parse,
}

# Tasks allowed to carry images (multimodal). Anything else must be
# text-only — images are never sent to text-only models.
MULTIMODAL_TASKS = frozenset({"complaint_analysis", "before_after"})


def validate(task, data):
    """Validate + clean model output. Returns (ok, cleaned, errors).

    `ok` is False when required content is missing (empty summary etc.);
    out-of-range values are clamped, not rejected.
    """
    validator = _VALIDATORS.get(task)
    if validator is None:
        return False, {}, ["unknown task: %s" % task]
    if not isinstance(data, dict):
        return False, {}, ["model output is not an object"]
    cleaned = validator(data)
    errors = []
    if task == "complaint_analysis" and not cleaned["summary"]:
        errors.append("missing summary")
    if task == "before_after" and not cleaned["summary"]:
        errors.append("missing change assessment")
    if task == "challenge_draft" and not cleaned["title"]:
        errors.append("missing draft title")
    return (len(errors) == 0), cleaned, errors
