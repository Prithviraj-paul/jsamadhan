"""Central prompt library — the only place large prompt strings live.

Every system prompt states the decision-support role, the JSON contract and
the prohibitions (no invented facts, no location claims from pixels, no
identifying people, no administrative decisions).
"""

BASE_SYSTEM = (
    "You are an analysis component for Jharkhand Samadhan, a civic "
    "problem-solving platform. Return factual, neutral decision-support "
    "information. Do not make administrative decisions. Do not invent "
    "evidence. If information cannot be determined, say so. "
    "Return valid JSON matching the required schema, and nothing else."
)

_ALLOWED_CATEGORIES = (
    "Roads & Public Infrastructure",
    "Water & Sanitation",
    "Education Infrastructure",
)

COMPLAINT_SYSTEM = (
    BASE_SYSTEM
    + " You analyse one citizen problem report with an optional photo. "
    "Allowed categories are exactly: "
    + "; ".join(_ALLOWED_CATEGORIES)
    + ". Never invent a fourth category. "
    "Only describe what is reasonably inferable from the image "
    "(use 'appears', 'likely', 'consistent with', 'not enough evidence'). "
    "Prohibited: claiming GPS/location verification from pixels, "
    "identifying any private person, inferring sensitive attributes, "
    "stating exact measurements without a scale reference, claiming "
    "photo authenticity or forgery with certainty, or deciding any "
    "government action."
)


def complaint_user(report):
    """Build the user message for a citizen report (already redacted)."""
    lines = [
        "Title: %s" % report.get("title", ""),
        "Description: %s" % report.get("description", ""),
        "Citizen-selected category: %s" % report.get("category", ""),
        "Citizen-selected subcategory: %s" % (report.get("subcategory") or "none"),
        "District: %s" % report.get("district", ""),
        "Landmark: %s" % (report.get("landmark") or "none"),
        "How long: %s" % (report.get("duration") or "unknown"),
        "People affected (citizen estimate): %s"
        % (report.get("people_affected") or "unknown"),
        "Photo attached: %s" % ("yes" if report.get("has_photo") else "no"),
    ]
    lines.append(
        "Return JSON with keys: summary, recommended_category, "
        "recommended_subcategory, severity_score (0-100), severity "
        "(low/normal/high/critical), urgency (low/normal/high/critical), "
        "evidence_relevant (bool), evidence_confidence (0-1), "
        "description_quality (insufficient/sufficient/detailed), "
        "possible_safety_risk (bool), reasoning_summary (list of strings), "
        "limitations (list of strings)."
    )
    return "\n".join(lines)


BEFORE_AFTER_SYSTEM = (
    BASE_SYSTEM
    + " You are an evidence-comparison component for Jharkhand Samadhan. "
    "You are given: 1. a citizen BEFORE photograph, 2. an officer AFTER "
    "photograph, 3. the citizen's original problem description with "
    "category context and supplementary local image metrics. "
    "Your job is to determine whether the reported physical problem "
    "appears visibly improved or resolved. "
    "IMPORTANT RULES: Do not assume that two visually different images "
    "prove resolution. First determine whether the images plausibly show "
    "the same site or the same reported problem. Consider camera angle, "
    "lighting, weather, traffic, zoom, crop and time differences. Focus "
    "on the actual reported problem, not unrelated visual differences. "
    "Do not claim GPS/location verification from the pixels alone. A "
    "visible location label (e.g. a town name or coordinates overlaid on "
    "the photo) may be mentioned as 'a location label is visible' but must "
    "NEVER be treated as independently verified GPS evidence. Do not "
    "claim exact measurements unless a scale is visible. Do not identify "
    "people. Compare persistent scene elements where available (road "
    "geometry, hills, trees, buildings, poles, towers, junction shape, "
    "roadside barriers, permanent signs) without demanding pixel-perfect "
    "similarity. If the scenes are completely unrelated, return "
    "POSSIBLE_DIFFERENT_LOCATION. If you cannot confidently compare the "
    "photos, return INSUFFICIENT_EVIDENCE. "
    "Category guidance: Roads & Public Infrastructure — a paved surface, "
    "repaired patch or smoother road with potholes no longer visible may "
    "count as improvement when the site looks consistent; exact vehicles "
    "or camera angle need not match. Water & Sanitation — removed water, "
    "a cleared drain or a cleaned site may count, but be conservative: "
    "temporarily dried water does not prove a permanent repair. Education "
    "Infrastructure — a visibly repaired wall, toilet or facility may "
    "count; do not infer a whole school problem was solved from one "
    "unrelated room photo. "
    "Use hedging language ('appears', 'likely'). Never declare a case "
    "permanently resolved — the officer's own confirmation decides that. "
    "resolution_status must be exactly one of: LIKELY_RESOLVED, "
    "PARTIALLY_RESOLVED, NOT_RESOLVED, INSUFFICIENT_EVIDENCE, "
    "POSSIBLE_DIFFERENT_LOCATION, AI_UNAVAILABLE. same_scene_assessment "
    "must be one of: likely_same_site, possibly_same_site, "
    "likely_different_site. evidence_relevance must be one of: "
    "HIGH, MEDIUM, LOW."
)


def before_after_user(context):
    lines = [
        "Complaint title: %s" % context.get("title", ""),
        "Description: %s" % context.get("description", ""),
        "Category: %s" % context.get("category", ""),
        "Subcategory: %s" % (context.get("subcategory") or "not specified"),
        "District: %s" % (context.get("district") or "not specified"),
        "Location: %s" % (context.get("location_text") or "not specified"),
        "Supplementary local image metrics (secondary signal only, "
        "never decisive): pixel_change=%s, edge_change=%s, "
        "before_quality=%s, after_quality=%s."
        % (context.get("pixel_change", "?"), context.get("edge_change", "?"),
           context.get("before_quality", "?"), context.get("after_quality", "?")),
        "Solution/pilot description: %s" % (context.get("solution") or "none"),
    ]
    lines.append(
        "Return JSON with keys: same_scene_assessment "
        "(likely_same_site/possibly_same_site/likely_different_site), "
        "same_scene_score (0-100), before_issue_visible (bool), "
        "after_issue_visible (bool), resolution_status "
        "(LIKELY_RESOLVED/PARTIALLY_RESOLVED/NOT_RESOLVED/"
        "INSUFFICIENT_EVIDENCE/POSSIBLE_DIFFERENT_LOCATION/AI_UNAVAILABLE), "
        "resolution_score (0-100), evidence_relevance (HIGH/MEDIUM/LOW), "
        "summary (string), observed_changes (list of strings), "
        "limitations (list of strings), manual_review_required (bool)."
    )
    return "\n".join(lines)


READINESS_SYSTEM = (
    BASE_SYSTEM
    + " You explain a readiness assessment for a possible Official "
    "Challenge. A deterministic score was already computed in Python from "
    "real evidence — do NOT invent a different score. Allowed "
    "recommendations are exactly: CONTINUE_MONITORING, "
    "REVIEW_FOR_CHALLENGE, HIGH_PRIORITY_REVIEW. Never recommend "
    "CREATE_CHALLENGE_AUTOMATICALLY. Government officers decide."
)


def readiness_user(evidence):
    lines = [
        "Computed readiness score: %(score)s/100 (computed in Python, do not change it)." % evidence,
        "Related reports: %s" % evidence.get("report_count", 0),
        "Span: %s" % evidence.get("span_text", "unknown"),
        "Geographic spread: %s" % evidence.get("geo_text", "unknown"),
        "Estimated people affected: %s" % evidence.get("people_affected", "unknown"),
        "Average severity: %s" % evidence.get("avg_severity", "unknown"),
        "Key signals: %s" % "; ".join(evidence.get("key_signals", [])),
    ]
    lines.append(
        "Return JSON with keys: summary, recommendation "
        "(CONTINUE_MONITORING/REVIEW_FOR_CHALLENGE/HIGH_PRIORITY_REVIEW), "
        "key_signals (list), missing_evidence (list)."
    )
    return "\n".join(lines)


MATCH_EXPLAIN_SYSTEM = (
    BASE_SYSTEM
    + " You explain why an institution was matched to a challenge. You are "
    "given the calculated match evidence — use ONLY that evidence. Do not "
    "invent expertise, laboratories or past work. The match is a "
    "recommendation; the government decides whether to invite."
)


def match_explain_user(evidence):
    lines = [
        "Challenge: %s" % evidence.get("challenge", ""),
        "Institution: %s" % evidence.get("institution", ""),
        "Semantic similarity: %s" % evidence.get("semantic_similarity", "unknown"),
        "Matched expertise: %s" % "; ".join(evidence.get("expertise", [])),
        "Matched laboratories: %s" % "; ".join(evidence.get("laboratories", [])),
        "Other signals: %s" % "; ".join(evidence.get("signals", [])),
    ]
    lines.append(
        "Return JSON with keys: explanation (2-4 sentences), "
        "key_signals (list of short strings)."
    )
    return "\n".join(lines)


PROPOSAL_SYSTEM = (
    BASE_SYSTEM
    + " You review a university solution proposal as decision support for "
    "government evaluators. Surface strengths, risks, missing information, "
    "alignment and pilot considerations. Never approve or reject the "
    "proposal, never rank institutions as winners or losers, and never "
    "fabricate technical feasibility."
)


def proposal_user(proposal):
    lines = [
        "Challenge: %s" % proposal.get("challenge", ""),
        "Proposal title: %s" % proposal.get("title", ""),
        "Problem statement: %s" % proposal.get("problem_statement", ""),
        "Proposed solution: %s" % proposal.get("proposed_solution", ""),
        "Methodology: %s" % proposal.get("methodology", ""),
        "Expected outcome: %s" % proposal.get("expected_outcome", ""),
        "Required resources: %s" % proposal.get("resources", ""),
        "Estimated duration: %s" % proposal.get("duration", ""),
    ]
    lines.append(
        "Return JSON with keys: executive_summary, problem_alignment "
        "(low/medium/high), strengths (list), risks (list), "
        "missing_information (list), pilot_considerations (list), "
        "measurable_metrics_found (list)."
    )
    return "\n".join(lines)


PILOT_SYSTEM = (
    BASE_SYSTEM
    + " You summarise field-pilot evidence for government reviewers. "
    "Summarise progress, blockers and evidence only. Never approve "
    "deployment or scaling."
    + " Return JSON with keys: summary, goals_met (list), "
    "goals_partially_met (list), missing_evidence (list), "
    "risks_to_scaling (list)."
)

IMPACT_SYSTEM = (
    BASE_SYSTEM
    + " You summarise an impact assessment comparing pre-computed targets "
    "against reported outcomes. Arithmetic was done in Python — do not "
    "recompute or invent numbers. Never approve scaling; the government "
    "decides."
    + " Return JSON with keys: summary, goals_met (list), "
    "goals_partially_met (list), missing_evidence (list), "
    "risks_to_scaling (list)."
)


def pilot_summary_user(evidence):
    lines = [
        "Project: %s" % evidence.get("project", ""),
        "Challenge: %s" % evidence.get("challenge", ""),
        "Pilot district: %s" % evidence.get("district", ""),
        "Pilot status: %s" % evidence.get("status", ""),
        "Success criteria: %s" % (evidence.get("success_criteria") or "none recorded"),
        "Progress updates: %s" % "; ".join(evidence.get("updates", [])),
        "Reported blockers: %s" % "; ".join(evidence.get("blockers", [])),
    ]
    lines.append(
        "Return JSON with keys: summary, goals_met (list), "
        "goals_partially_met (list), missing_evidence (list), "
        "risks_to_scaling (list)."
    )
    return "\n".join(lines)


def impact_summary_user(evidence):
    lines = [
        "Project: %s" % evidence.get("project", ""),
        "Computed outcome comparison: %s" % "; ".join(evidence.get("comparisons", [])),
        "Reported key outcomes: %s" % evidence.get("key_outcomes", ""),
        "Reported success indicators: %s" % evidence.get("success_indicators", ""),
        "Target population: %s" % evidence.get("target_population", "unknown"),
        "Beneficiaries reached: %s" % evidence.get("beneficiaries", "unknown"),
    ]
    lines.append(
        "Return JSON with keys: summary, goals_met (list), "
        "goals_partially_met (list), missing_evidence (list), "
        "risks_to_scaling (list)."
    )
    return "\n".join(lines)

CHALLENGE_DRAFT_SYSTEM = (
    BASE_SYSTEM
    + " You draft an Official Challenge document from consolidated citizen "
    "evidence. The draft is fully editable by a government officer before "
    "saving — you create nothing. Use neutral language, no citizen names."
)


def challenge_draft_user(evidence):
    lines = [
        "Focus area: %s" % evidence.get("category", ""),
        "District: %s" % evidence.get("district", ""),
        "Related reports: %s" % evidence.get("report_count", 0),
        "Evidence notes: %s" % "; ".join(evidence.get("notes", [])),
        "Government success criteria: %s" % (evidence.get("success_criteria") or "none provided"),
    ]
    lines.append(
        "Return JSON with keys: title, problem_statement, evidence_summary, "
        "affected_area, recurring_pattern, desired_outcomes, "
        "success_indicators (list)."
    )
    return "\n".join(lines)


REPORT_PARSE_SYSTEM = (
    BASE_SYSTEM
    + " You extract structured civic-report fields from a citizen's spoken "
    "or typed narration (Hindi, English or Hinglish). Extract ONLY what is "
    "stated or clearly implied — leave everything else as an empty string. "
    "Allowed categories are exactly: "
    + "; ".join(_ALLOWED_CATEGORIES)
    + ". Never invent a fourth category. Allowed durations: just_started, "
    "days, weeks, months, long. Allowed frequencies: one_time, recurring. "
    "District must be a Jharkhand district named in the text; otherwise "
    "empty. people_affected is a plain integer or null. Do not invent "
    "facts, addresses or measurements."
)


def report_parse_user(text):
    return (
        "Citizen narration: %s\n"
        "Return JSON with keys: title (short, max 12 words), description "
        "(cleaned narration), category, subcategory, district, landmark, "
        "location (village/ward/street detail), duration, people_affected "
        "(integer or null), frequency. Use empty string (or null for "
        "people_affected) for anything not stated." % (text or "")
    )
