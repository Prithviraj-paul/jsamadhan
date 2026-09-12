"""
Internationalisation for Jharkhand Samadhan.

Design:
- English and Hindi are the two primary, fully-translated UI languages.
- A third dropdown lets a citizen pick any other language — Jharkhand's own
  regional/tribal languages, and other major Indian languages.
- Every language has a `fallback` chain that ends at Hindi or English, so
  picking a language with partial coverage never breaks the UI or shows a
  raw key — it just shows the best available translation.

Honesty note: full, review-quality translation of every string into all of
Jharkhand's tribal languages (Santali, Ho, Mundari, Kurukh, Kharia) and every
major Indian language needs native-speaker review before real deployment.
This file translates the core navigation, actions, and status vocabulary for
all listed languages, and falls back gracefully for anything not yet
translated — the architecture is ready, coverage can be filled in per
language without touching any template.
"""

from flask import g

# (code, native_name, english_name, group, fallback_code)
# group: "primary" | "jharkhand" | "india"
LANGUAGES = [
    ("en", "English", "English", "primary", None),
    ("hi", "\u0939\u093f\u0928\u094d\u0926\u0940", "Hindi", "primary", None),

    # Jharkhand's own regional / tribal languages
    ("nag", "\u0928\u093e\u0917\u092a\u0941\u0930\u0940", "Nagpuri", "jharkhand", "hi"),
    ("khr", "\u0916\u094b\u0930\u0920\u093e", "Khortha", "jharkhand", "hi"),
    ("pnx", "\u092a\u0902\u091a\u092a\u0930\u0917\u0928\u093f\u092f\u093e", "Panchpargania", "jharkhand", "hi"),
    ("sat", "\u1c65\u1c6f\u1c58\u1c61\u1c76\u1c61 Santali", "Santali", "jharkhand", "hi"),
    ("hoc", "Ho", "Ho", "jharkhand", "hi"),
    ("unr", "Mundari", "Mundari", "jharkhand", "hi"),
    ("kru", "Kurukh (\u0909\u0930\u093e\u0901\u0935)", "Kurukh / Oraon", "jharkhand", "hi"),
    ("kha", "Kharia", "Kharia", "jharkhand", "hi"),

    # Other major Indian regional languages
    ("bn", "\u09ac\u09be\u0982\u09b2\u09be", "Bengali", "india", "en"),
    ("or", "\u0b21\u0b3c\u0b3f\u0b06", "Odia", "india", "en"),
    ("mr", "\u092e\u0930\u093e\u0920\u0940", "Marathi", "india", "hi"),
    ("gu", "\u0917\u0941\u091c\u0930\u093e\u0924\u0940", "Gujarati", "india", "hi"),
    ("pa", "\u0a2a\u0a70\u0a1c\u0a3e\u0a2c\u0a40", "Punjabi", "india", "hi"),
    ("ta", "\u0ba4\u0bae\u0bbf\u0bb4\u0bcd", "Tamil", "india", "en"),
    ("te", "\u0c24\u0c46\u0c32\u0c41\u0c17\u0c41", "Telugu", "india", "en"),
    ("kn", "\u0c95\u0ca8\u0ccd\u0ca8\u0ca1", "Kannada", "india", "en"),
    ("ml", "\u0d2e\u0d32\u0d2f\u0d3e\u0d33\u0d02", "Malayalam", "india", "en"),
    ("ur", "\u0627\u0631\u062f\u0648", "Urdu", "india", "hi"),
    ("as", "\u0985\u09b8\u09ae\u09c0\u09af\u09bc\u09be", "Assamese", "india", "bn"),
]

LANGUAGE_CODES = {code for code, *_ in LANGUAGES}
LANGUAGE_META = {code: {"native": native, "english": english, "group": group, "fallback": fb}
                  for code, native, english, group, fb in LANGUAGES}

DEFAULT_LANG = "en"


# ---------------------------------------------------------------------------
# translation strings
# ---------------------------------------------------------------------------

TR = {

"en": {
    "app_name": "Jharkhand Samadhan",
    "app_tagline": "AI-Verified Civic Problem Reporting",
    "language": "Language",
    "govt_of_jharkhand": "Government of Jharkhand",

    "nav_home": "Home",
    "nav_register": "Register as Citizen",
    "nav_my_complaints": "My Complaints",
    "nav_report": "Report a Problem",
"nav_queue": "Queue",
    "nav_overview": "Overview",
    "nav_map": "Live Map",
    "nav_logout": "Log out",
    "urgency_critical": "Critical",
    "urgency_high": "High",
    "urgency_normal": "Normal",
    "urgency_low": "Low",
    "severity_title": "AI severity score",
    "ai_analysis": "AI Analysis",
    "urgency_label": "Urgency",
    "severity_label": "Severity",
    "sla_label": "SLA deadline",
    "map_title": "Complaint Map",
    "map_subtitle": "Live map of complaints across Jharkhand: pin colours show status and urgency.",
    "map_legend_status": "Status",
    "map_legend_urgency": "Urgency",
    "map_unpinned": "No complaints with map coordinates yet.",
    "map_loading": "Loading map...",
    "nav_back_home": "\u2190 Back to Home",

    "hero_title": "Report it. Track it. See it fixed.",
    "hero_body": "Citizens report local problems with photo or video evidence. Road and infrastructure reports are automatically screened against recent satellite imagery; everything else is verified by an officer. Once accepted, officers must resolve the case within a set deadline \u2014 and a before/after image check decides whether it\u2019s really fixed before the case closes.",
    "stat_reported": "Problems Reported",
    "stat_open": "Currently Open",
    "stat_resolved": "Resolved & Verified",
    "login_heading": "Log in",
    "login_choose_role": "Choose how you are signing in.",
    "login_select_role": "Select login type",
    "role_citizen": "Citizen",
    "role_citizen_desc": "Report a problem and track its progress through verification and resolution.",
    "role_officer": "Officer",
    "role_officer_desc": "Verify reports, accept cases, and upload resolution evidence within deadline.",
    "role_admin": "Admin",
    "role_admin_desc": "Oversee every complaint, manage officers, and reassign overdue cases.",
    "demo_logins": "Demo logins",
    "or_register": "or register your own",

    "login_title": "Login",
    "email": "Email",
    "password": "Password",
    "btn_login": "Log in",
    "new_here": "New here?",
    "create_citizen_account": "Create a citizen account",
    "already_registered": "Already registered?",

    "register_title": "Create your account",
    "register_body": "We\u2019ll use your name, email and phone to auto-fill every problem you report, and to keep you updated on its progress.",
    "full_name": "Full Name",
    "phone": "Phone Number",
    "btn_create_account": "Create Account",

    "my_complaints": "My Complaints",
    "btn_new_report": "+ Report New Problem",
    "no_complaints_yet": "You haven\u2019t reported any problems yet.",
    "report_first": "Report your first one \u2192",

    "nav_account": "Account",
    "account_title": "My Account",
    "account_details": "Account Details",
    "profile_photo": "Profile Photo",
    "btn_upload_photo": "Upload photo",
    "photo_explain": "A small square photo, stored locally on the server.",
    "btn_remove_photo": "Remove photo",
    "btn_save_changes": "Save changes",
    "alternate_phone": "Alternate phone",
    "home_address": "Home address",
    "account_updated": "Account updated.",
    "photo_removed": "Profile photo removed.",
    "my_reports_sub": "Track every problem you have reported, in one place.",
    "gallery_title": "Fixed & Verified",
    "gallery_sub": "Resolved problems anyone can read about \u2014 reporter identities always stay hidden.",
    "gallery_before": "Before",
    "gallery_after": "After",
    "ai_photo_verify": "AI Photo Verification",
    "ai_confidence_label": "Confidence",
    "ai_threshold_label": "Threshold",
    "ai_signals_label": "Signals",
    "ai_auto_verified": "\u2713 Auto-verified by AI",
    "ai_manual_review": "Needs officer review",
    "ai_signals_none": "No additional signals extracted.",

    "report_heading": "Report a Societal Problem",
    "reported_by": "Reported By",
    "autofill_note": "Auto-filled from your account \u2014 no need to re-enter your details.",
    "problem_title": "Problem Title",
    "problem_title_ph": "e.g. Broken road near school",
    "describe_problem": "Describe the Problem",
    "describe_problem_ph": "What is happening, and how is it affecting people?",
    "category": "Category",
    "category_hint": "\"Roads & Infrastructure\" reports get an automatic satellite AI check.",
    "district": "District",
    "location_details": "Location details",
    "location_ph": "Village / ward / landmark",
    "evidence_label": "Photo or Video Evidence",
    "evidence_click": "Click to upload a photo or video of the problem",
    "evidence_hint": "JPG, PNG, WEBP, or MP4/MOV \u2014 required for verification",
    "btn_submit_problem": "Submit Problem",

    "banner_ai_verified": "\U0001f916 Verified by automated satellite screening ({conf}% confidence). Awaiting officer to begin resolution.",
    "banner_pending_officer": "\U0001f575\ufe0f Awaiting manual verification by a field officer.",
    "banner_overdue": "\u23f0 This case is past its resolution deadline ({deadline}).",
    "banner_accepted": "\u2713 Accepted by {officer}. Resolution due by {deadline} ({days} days left).",
    "banner_reopened": "\U0001f501 The uploaded resolution didn\u2019t show enough visible change \u2014 case has been reopened.",
    "banner_resolved": "\u2705 Resolved and verified on {date}.",
    "banner_rejected": "\u2715 This complaint was reviewed and rejected.",

    "problem_section": "Problem",
    "reported_by_section": "Reported By",
    "evidence_section": "Evidence",
    "evidence_before": "Before \u2014 submitted by citizen",
    "evidence_after_officer": "After \u2014 uploaded by officer",
    "evidence_after_pending": "Resolution photo not yet uploaded",
    "ai_resolution_check": "AI Resolution Check",
    "progress_timeline": "Progress Timeline",
    "change_score": "change score",

    "officer_queue_title": "Verification Queue",
    "needs_review": "Needs Review",
    "waiting": "waiting",
    "nothing_waiting": "Nothing waiting for review right now.",
    "my_active_cases": "My Active Cases",
    "in_progress": "in progress",
    "no_active_cases": "No active cases assigned to you.",
    "recently_resolved": "Recently Resolved by You",
    "no_resolved_yet": "No resolved cases yet.",
    "due": "Due",

    "take_action": "Take Action",
    "btn_verify_accept": "Verify & Accept Case",
    "btn_accept_begin": "Accept & Begin Resolution",
    "rejection_reason_label": "Rejection reason (if rejecting)",
    "rejection_reason_ph": "Explain why this isn\u2019t a valid / verifiable complaint",
    "btn_reject": "Reject Complaint",
    "upload_resolution": "Upload Resolution Evidence",
    "upload_resolution_hint": "Due by {deadline}. Upload an \"after\" photo of the same location \u2014 it will be automatically compared with the original.",
    "evidence_upload_after": "Click to upload the resolved-site photo",
    "evidence_after_hint": "JPG, PNG, or WEBP recommended for automated comparison",
    "btn_submit_resolution": "Submit Resolution for AI Verification",
    "case_resolved_on": "\u2705 Case resolved and verified on {date}.",
    "case_rejected": "\u2715 Rejected.",

    "admin_overview": "Admin Overview",
    "total_complaints": "Total Complaints",
    "open": "Open",
    "resolved": "Resolved",
    "overdue": "Overdue",
    "all_complaints": "All Complaints",
    "th_id": "ID",
    "th_title": "Title",
    "th_district": "District",
    "th_category": "Category",
    "th_officer": "Officer",
    "th_status": "Status",
    "no_complaints_filed": "No complaints filed yet.",
    "officers_count": "Officers",
    "no_officers_yet": "No officers yet.",
    "add_officer": "Add an Officer",
    "temp_password": "Temporary Password",
    "btn_create_officer": "Create Officer Account",
    "assignment": "Assignment",
    "currently": "Currently",
    "unassigned": "Unassigned",
    "due_label": "due",
    "assign_reassign": "Assign / reassign officer",
    "btn_assign": "Assign (resets a 5-day deadline)",
    "timeline": "Timeline",

    "status_submitted": "Submitted",
    "status_ai_verified": "\U0001f916 AI Verified",
    "status_pending_officer": "Pending Officer Review",
    "status_accepted": "In Progress",
    "status_resolved": "\u2713 Resolved",
    "status_reopened": "Reopened",
    "status_rejected": "Rejected",
    "status_overdue": "\u23f0 Overdue",

    "cat_roads": "Roads & Infrastructure",
    "cat_water": "Water Resources",
    "cat_electricity": "Electricity",
    "cat_sanitation": "Sanitation",
    "cat_health": "Healthcare",
    "cat_education": "Education",
    "cat_safety": "Public Safety",
    "cat_other": "Other",

    "dist_ranchi": "Ranchi",
    "dist_dhanbad": "Dhanbad",
    "dist_dumka": "Dumka",
    "dist_bokaro": "Bokaro",
    "dist_gumla": "Gumla",
    "dist_deoghar": "Deoghar",
    "dist_hazaribagh": "Hazaribagh",
    "dist_giridih": "Giridih",
    "dist_east_singhbhum": "East Singhbhum",
    "dist_west_singhbhum": "West Singhbhum",

    "hero_kicker": "Your every problem, solved",
    "sec_problems_title": "Problems this platform solves",
    "sec_problems_sub": "From crumbling roads to garbage piles \u2014 snap a photo, file a report, and watch it get fixed. These are the everyday problems Samadhan is built for.",
    "problem_road": "Broken roads & potholes",
    "problem_road_desc": "Crumbling village lanes, dangerous potholes, and damaged culverts that make travel risky.",
    "problem_water": "Water & handpumps",
    "problem_water_desc": "Dry handpumps, leaking pipes, and unsafe drinking water reaching homes.",
    "problem_electricity": "Electricity & lighting",
    "problem_electricity_desc": "Dead streetlights, frequent power cuts, and villages still waiting for electrification.",
    "problem_sanitation": "Sanitation & garbage",
    "problem_sanitation_desc": "Garbage piles on streets, choked drains, and public spaces that are never cleaned.",
    "problem_health": "Healthcare access",
    "problem_health_desc": "Neglected health centres, missing doctors, and medical facilities far from home.",
    "problem_education": "Schools & education",
    "problem_education_desc": "Broken school buildings, no drinking water or toilets, and missing supplies for children.",
    "sec_how_title": "How Samadhan works",
    "sec_how_sub": "Three simple steps from a problem to a solution.",
    "how_1": "Report with proof",
    "how_1_desc": "Snap a photo or video of the problem and pin its location. Road reports even get an automatic satellite check.",
    "how_2": "Verified & assigned",
    "how_2_desc": "A field officer verifies your complaint and accepts the case with a fixed resolution deadline.",
    "how_3": "Watch it get fixed",
    "how_3_desc": "The officer uploads the after photo. Our AI compares before and after, then closes the case for good.",
    "footer_note": "Jharkhand Samadhan \u2014 a Smart India Hackathon prototype.",
},

"hi": {
    "app_name": "\u091d\u093e\u0930\u0916\u0902\u0921 \u0938\u092e\u093e\u0927\u093e\u0928",
    "app_tagline": "AI-\u0938\u0924\u094d\u092f\u093e\u092a\u093f\u0924 \u0928\u093e\u0917\u0930\u093f\u0915 \u0938\u092e\u0938\u094d\u092f\u093e \u0930\u093f\u092a\u094b\u0930\u094d\u091f\u093f\u0902\u0917",
    "language": "\u092d\u093e\u0937\u093e",
    "govt_of_jharkhand": "\u091d\u093e\u0930\u0916\u0902\u0921 \u0938\u0930\u0915\u093e\u0930",

    "nav_home": "\u092e\u0941\u0916\u092a\u0943\u0937\u094d\u0920",
    "nav_register": "\u0928\u093e\u0917\u0930\u093f\u0915 \u0915\u0947 \u0930\u0942\u092a \u092e\u0947\u0902 \u092a\u0902\u091c\u0940\u0915\u0930\u0923 \u0915\u0930\u0947\u0902",
    "nav_my_complaints": "\u092e\u0947\u0930\u0940 \u0936\u093f\u0915\u093e\u092f\u0924\u0947\u0902",
    "nav_report": "\u0938\u092e\u0938\u094d\u092f\u093e \u0926\u0930\u094d\u091c \u0915\u0930\u0947\u0902",
    "nav_queue": "\u0915\u0924\u093e\u0930",
    "nav_overview": "\u0905\u0935\u0932\u094b\u0915\u0928",
    "nav_logout": "\u0932\u0949\u0917 \u0906\u0909\u091f",
    "nav_map": "\u0932\u093e\u0907\u0935 \u092e\u0948\u092a",
    "urgency_critical": "\u0905\u0924\u094d\u092f\u0902\u0924 \u0917\u0902\u092d\u0940\u0930",
    "urgency_high": "\u0909\u091a\u094d\u091a \u092a\u094d\u0930\u093e\u0925\u092e\u093f\u0915\u0924\u093e",
    "urgency_normal": "\u0938\u093e\u092e\u093e\u0928\u094d\u092f",
    "urgency_low": "\u0915\u092e \u092a\u094d\u0930\u093e\u0925\u092e\u093f\u0915\u0924\u093e",
    "severity_title": "AI \u0917\u0902\u092d\u0940\u0930\u0924\u093e \u0938\u094d\u0915\u094b\u0930",
    "ai_analysis": "AI \u0935\u093f\u0936\u094d\u0932\u0947\u0937\u0923",
    "urgency_label": "\u0905\u0924\u094d\u092f\u0902\u0924 \u0924\u094d\u0930\u0924\u0926\u0941\u0930",
    "severity_label": "\u0917\u0902\u092d\u0940\u0930\u0924\u093e",
    "sla_label": "SLA \u0926\u0947\u092f\u093e\u0928\u094d\u0924\u093f",
    "map_title": "\u0936\u093f\u0915\u093e\u092f\u0924 \u0905\u0935\u0932\u094b\u0915\u0928 \u0928\u0915\u094d\u0937\u093e",
    "map_subtitle": "\u091d\u093e\u0930\u0916\u0923\u094d\u0921 \u092d\u0930 \u0915\u0940 \u0936\u093f\u0915\u093e\u092f\u0924\u094b\u0902 \u0915\u093e \u0932\u093e\u0907\u0935 \u0928\u0915\u094d\u0937\u093e\u0903 \u0938\u094d\u0925\u093f\u0924\u093f \u0914\u0930 \u0905\u0924\u094d\u092f\u0902\u0924 \u0924\u094d\u0930\u0924\u0926\u0941\u0930 \u0915\u0947 \u0905\u0928\u0941\u0938\u093e\u0930 \u0930\u0902\u0917-\u0915\u094b\u0921\u093f\u0924 \u092a\u093f\u0928\u094d\u0938",
    "map_legend_status": "\u0938\u094d\u0925\u093f\u0924\u093f",
    "map_legend_urgency": "\u0905\u0924\u094d\u092f\u0902\u0924 \u0924\u094d\u0930\u0924\u0926\u0941\u0930",
    "map_unpinned": "\u0915\u094b\u0908 \u0928\u093f\u0930\u094d\u0926\u0947\u0936\u093e\u0902\u0915 \u0935\u093e\u0932\u0940 \u0938\u0915\u094d\u0930\u093f\u092f \u0936\u093f\u0915\u093e\u092f\u0924 \u0928\u0939\u0940\u0902",
    "map_loading": "\u0928\u0915\u094d\u0937\u093e \u0932\u094b\u0921 \u0939\u094b \u0930\u0939\u093e \u0939\u0948...",
    "nav_back_home": "\u2190 \u092e\u0941\u0916\u092a\u0943\u0937\u094d\u0920 \u092a\u0930 \u0935\u093e\u092a\u0938 \u091c\u093e\u090f\u0901",

    "hero_title": "\u0926\u0930\u094d\u091c \u0915\u0930\u0947\u0902\u0964 \u091f\u094d\u0930\u0948\u0915 \u0915\u0930\u0947\u0902\u0964 \u0938\u092e\u093e\u0927\u093e\u0928 \u0926\u0947\u0916\u0947\u0902\u0964",
    "hero_body": "\u0928\u093e\u0917\u0930\u093f\u0915 \u092b\u094b\u091f\u094b \u092f\u093e \u0935\u0940\u0921\u093f\u092f\u094b \u092a\u094d\u0930\u092e\u093e\u0923 \u0915\u0947 \u0938\u093e\u0925 \u0938\u094d\u0925\u093e\u0928\u0940\u092f \u0938\u092e\u0938\u094d\u092f\u093e\u090f\u0901 \u0926\u0930\u094d\u091c \u0915\u0930\u0924\u0947 \u0939\u0948\u0902\u0964 \u0938\u0921\u093c\u0915 \u0935 \u0905\u0935\u0938\u0902\u0930\u091a\u0928\u093e \u0938\u0947 \u091c\u0941\u0921\u093c\u0940 \u0936\u093f\u0915\u093e\u092f\u0924\u094b\u0902 \u0915\u0940 \u091c\u093e\u0901\u091a \u0939\u093e\u0932 \u0915\u0940 \u091c\u093e\u0924\u0940 \u0939\u0948; \u092c\u093e\u0915\u0940 \u0938\u092d\u0940 \u0915\u0940 \u092a\u0941\u0937\u094d\u091f\u093f \u090f\u0915 \u0905\u0927\u093f\u0915\u093e\u0930\u0940 \u0926\u094d\u0935\u093e\u0930\u093e \u0915\u0940 \u091c\u093e\u0924\u0940 \u091c\u093e\u0924\u0940 \u0939\u0948\u0964 \u0938\u094d\u0935\u0940\u0915\u0943\u0924\u093f \u0915\u0947 \u092c\u093e\u0926 \u0905\u0927\u093f\u0915\u093e\u0930\u0940 \u0915\u094b \u0924\u092f \u0938\u092e\u092f-\u0938\u0940\u092e\u093e \u092e\u0947\u0902 \u0938\u092e\u093e\u0927\u093e\u0928 \u0915\u0930\u0928\u093e \u0939\u094b\u0924\u093e \u0939\u0948 \u2014 \u0914\u0930 \u092a\u0939\u0932\u0947/\u092c\u093e\u0926 \u0915\u0940 \u0924\u0938\u094d\u0935\u0940\u0930\u094b\u0902 \u0915\u0940 \u0924\u0941\u0932\u0928\u093e \u0938\u0947 \u0924\u092f \u0939\u094b\u0924\u093e \u0939\u0948 \u0915\u093f \u092e\u093e\u092e\u0932\u093e \u0935\u093e\u0915\u0908 \u0939\u0932 \u0939\u0941\u0906 \u0939\u0948 \u092f\u093e \u0928\u0939\u0940\u0902\u0964",
    "stat_reported": "\u0926\u0930\u094d\u091c \u0915\u0940 \u0917\u0908 \u0938\u092e\u0938\u094d\u092f\u093e\u090f\u0901",
    "stat_open": "\u0935\u0930\u094d\u0924\u092e\u093e\u0928 \u092e\u0947\u0902 \u0916\u0941\u0932\u0940",
    "stat_resolved": "\u0939\u0932 \u0935 \u0938\u0924\u094d\u092f\u093e\u092a\u093f\u0924",
    "login_heading": "\u0932\u0949\u0917 \u0907\u0928 \u0915\u0930\u0947\u0902",
    "login_choose_role": "\u091a\u0941\u0928\u0947\u0902 \u0915\u093f \u0906\u092a \u0915\u093f\u0938 \u0930\u0942\u092a \u092e\u0947\u0902 \u0932\u0949\u0917 \u0907\u0928 \u0915\u0930 \u0930\u0939\u0947 \u0939\u0948\u0902\u0964",
    "login_select_role": "\u0932\u0949\u0917\u093f\u0928 \u092a\u094d\u0930\u0915\u093e\u0930 \u091a\u0941\u0928\u0947\u0902",
    "role_citizen": "\u0928\u093e\u0917\u0930\u093f\u0915",
    "role_citizen_desc": "\u0938\u092e\u0938\u094d\u092f\u093e \u0926\u0930\u094d\u091c \u0915\u0930\u0947\u0902 \u0914\u0930 \u0938\u0924\u094d\u092f\u093e\u092a\u0928 \u0938\u0947 \u0932\u0947\u0915\u0930 \u0938\u092e\u093e\u0927\u093e\u0928 \u0924\u0915 \u0909\u0938\u0915\u0940 \u092a\u094d\u0930\u0917\u0924\u093f \u0926\u0947\u0916\u0947\u0902\u0964",
    "role_officer": "\u0905\u0927\u093f\u0915\u093e\u0930\u0940",
    "role_officer_desc": "\u0936\u093f\u0915\u093e\u092f\u0924\u094b\u0902 \u0915\u0940 \u092a\u0941\u0937\u094d\u091f\u093f \u0915\u0930\u0947\u0902, \u092e\u093e\u092e\u0932\u0947 \u0938\u094d\u0935\u0940\u0915\u093e\u0930 \u0915\u0930\u0947\u0902, \u0914\u0930 \u0938\u092e\u092f-\u0938\u0940\u092e\u093e \u0915\u0947 \u092d\u0940\u0924\u0930 \u0938\u092e\u093e\u0927\u093e\u0928 \u0915\u093e \u092a\u094d\u0930\u092e\u093e\u0923 \u0905\u092a\u0932\u094b\u0921 \u0915\u0930\u0947\u0902\u0964",
    "role_admin": "\u090f\u0921\u092e\u093f\u0928",
    "role_admin_desc": "\u0938\u092d\u0940 \u0936\u093f\u0915\u093e\u092f\u0924\u094b\u0902 \u0915\u0940 \u0928\u093f\u0917\u0930\u093e\u0928 \u0915\u0930\u0947\u0902, \u0905\u0927\u093f\u0915\u093e\u0930\u093f\u092f\u094b\u0902 \u0915\u093e \u092a\u094d\u0930\u092c\u0902\u0927\u0928 \u0915\u0930\u0947\u0902, \u0914\u0930 \u0932\u0902\u092c\u093f\u0924 \u092e\u093e\u092e\u0932\u0947 \u092a\u0941\u0928\u0939 \u0938\u094c\u0902\u092a\u0947\u0902\u0964",
    "demo_logins": "\u0921\u0947\u092e\u094b \u0932\u0949\u0917\u093f\u0928",
    "or_register": "\u092f\u093e \u0905\u092a\u0928\u093e \u0916\u093e\u0924\u093e \u092c\u0928\u093e\u090f\u0902",

    "login_title": "\u0932\u0949\u0917\u093f\u0928",
    "email": "\u0908\u092e\u0947\u0932",
    "password": "\u092a\u093e\u0938\u0935\u0930\u094d\u0921",
    "btn_login": "\u0932\u0949\u0917 \u0907\u0928 \u0915\u0930\u0947\u0902",
    "new_here": "\u0928\u090f \u0939\u0948\u0902?",
    "create_citizen_account": "\u0928\u093e\u0917\u0930\u093f\u0915 \u0916\u093e\u0924\u093e \u092c\u0928\u093e\u090f\u0902",
    "already_registered": "\u092a\u0939\u0932\u0947 \u0938\u0947 \u092a\u0902\u091c\u0940\u0915\u0930\u0940\u0924 \u0939\u0948\u0902?",

    "register_title": "\u0905\u092a\u0928\u093e \u0916\u093e\u0924\u093e \u092c\u0928\u093e\u090f\u0902",
    "register_body": "\u0906\u092a\u0915\u0947 \u0928\u093e\u092e, \u0908\u092e\u0947\u0932 \u0914\u0930 \u092b\u093c\u094b\u0928 \u0915\u093e \u0909\u092a\u092f\u094b\u0917 \u0939\u0930 \u0936\u093f\u0915\u093e\u092f\u0924 \u092e\u0947\u0902 \u0905\u092a\u0928\u0947-\u0906\u092a \u092d\u0930\u0928\u0947 \u0914\u0930 \u0906\u092a\u0915\u094b \u092a\u094d\u0930\u0917\u0924\u093f \u0915\u0940 \u091c\u093e\u0928\u0915\u093e\u0930\u0940 \u0926\u0947\u0928\u0947 \u0915\u0947 \u0932\u093f\u090f \u0915\u093f\u092f\u093e \u091c\u093e\u090f\u0917\u093e\u0964",
    "full_name": "\u092a\u0942\u0930\u093e \u0928\u093e\u092e",
    "phone": "\u092b\u093c\u094b\u0928 \u0928\u0902\u092c\u0930",
    "btn_create_account": "\u0916\u093e\u0924\u093e \u092c\u0928\u093e\u090f\u0902",

    "my_complaints": "\u092e\u0947\u0930\u0940 \u0936\u093f\u0915\u093e\u092f\u0924\u0947\u0902",
    "btn_new_report": "+ \u0928\u0908 \u0938\u092e\u0938\u094d\u092f\u093e \u0926\u0930\u094d\u091c \u0915\u0930\u0947\u0902",
    "no_complaints_yet": "\u0906\u092a\u0928\u0947 \u0905\u092d\u0940 \u0924\u0915 \u0915\u094b\u0908 \u0938\u092e\u0938\u094d\u092f\u093e \u0926\u0930\u094d\u091c \u0928\u0939\u0940\u0902 \u0915\u0940 \u0939\u0948\u0964",
    "report_first": "\u0905\u092a\u0928\u0940 \u092a\u0939\u0932\u0940 \u0936\u093f\u0915\u093e\u092f\u0924 \u0926\u0930\u094d\u091c \u0915\u0930\u0947\u0902 \u2192",

    "nav_account": "\u0916\u093e\u0924\u093e",
    "account_title": "\u092e\u0947\u0930\u093e \u0916\u093e\u0924\u093e",
    "account_details": "\u0916\u093e\u0924\u093e \u0935\u093f\u0935\u0930\u0923",
    "profile_photo": "\u092a\u094d\u0930\u094b\u092b\u093c\u093e\u0907\u0932 \u092b\u093c\u094b\u091f\u094b",
    "btn_upload_photo": "\u092b\u093c\u094b\u091f\u094b \u0905\u092a\u0932\u094b\u0921 \u0915\u0930\u0947\u0902",
    "photo_explain": "\u090f\u0915 \u091b\u094b\u091f\u0940 \u091a\u094c\u0915\u094b\u0930 \u092b\u093c\u094b\u091f\u094b, \u0938\u0930\u094d\u0935\u0930 \u092a\u0930 \u0938\u094d\u0925\u093e\u0928\u0940\u092f \u0930\u0942\u092a \u0938\u0947 \u0938\u0939\u0947\u091c\u0940 \u091c\u093e\u0924\u0940 \u0939\u0948\u0964",
    "btn_remove_photo": "\u092b\u093c\u094b\u091f\u094b \u0939\u091f\u093e\u090f\u0902",
    "btn_save_changes": "\u092c\u0926\u0932\u093e\u0935 \u0938\u0939\u0947\u091c\u0947\u0902",
    "alternate_phone": "\u0935\u0948\u0915\u0932\u094d\u092a\u093f\u0915 \u092b\u093c\u094b\u0928",
    "home_address": "\u0918\u0930 \u0915\u093e \u092a\u0924\u093e",
    "account_updated": "\u0916\u093e\u0924\u093e \u0905\u092a\u0921\u0947\u091f \u0939\u094b \u0917\u092f\u093e\u0964",
    "photo_removed": "\u092a\u094d\u0930\u094b\u092b\u093c\u093e\u0907\u0932 \u092b\u093c\u094b\u091f\u094b \u0939\u091f\u093e \u0926\u0940 \u0917\u0908\u0964",
    "my_reports_sub": "\u0905\u092a\u0928\u0940 \u0926\u0930\u094d\u091c \u0915\u0940 \u0917\u0908 \u0939\u0930 \u0938\u092e\u0938\u094d\u092f\u093e \u090f\u0915 \u091c\u0917\u0939 \u091f\u094d\u0930\u0948\u0915 \u0915\u0930\u0947\u0902\u0964",
    "gallery_title": "\u0939\u0932 \u0939\u094b \u0917\u092f\u093e \u0914\u0930 \u0938\u0924\u094d\u092f\u093e\u092a\u093f\u0924",
    "gallery_sub": "\u0939\u0932 \u0939\u0941\u0908 \u0938\u092e\u0938\u094d\u092f\u093e\u090f\u0902 \u091c\u093f\u0928\u094d\u0939\u0947\u0902 \u0915\u094b\u0908 \u092d\u0940 \u092a\u0922\u093c \u0938\u0915\u0924\u093e \u0939\u0948 \u2014 \u0930\u093f\u092a\u094b\u0930\u094d\u091f \u0915\u0930\u0928\u0947 \u0935\u093e\u0932\u0947 \u0915\u0940 \u092a\u0939\u091a\u093e\u0928 \u0939\u092e\u0947\u0936\u093e \u091b\u093f\u092a\u0940 \u0930\u0939\u0924\u0940 \u0939\u0948\u0964",
    "gallery_before": "\u092a\u0939\u0932\u0947",
    "gallery_after": "\u092c\u093e\u0926 \u092e\u0947\u0902",
    "ai_photo_verify": "AI \u092b\u093c\u094b\u091f\u094b \u0938\u0924\u094d\u092f\u093e\u092a\u0928",
    "ai_confidence_label": "\u0935\u093f\u0936\u094d\u0935\u093e\u0938",
    "ai_threshold_label": "\u0938\u0940\u092e\u093e",
    "ai_signals_label": "\u0938\u0902\u0915\u0947\u0924",
    "ai_auto_verified": "\u2713 AI \u0926\u094d\u0935\u093e\u0930\u093e \u0938\u094d\u0935\u0924\u0903 \u0938\u0924\u094d\u092f\u093e\u092a\u093f\u0924",
    "ai_manual_review": "\u0905\u0927\u093f\u0915\u093e\u0930\u0940 \u0938\u092e\u0940\u0915\u094d\u0937\u093e \u0906\u0935\u0936\u094d\u092f\u0915",
    "ai_signals_none": "\u0915\u094b\u0908 \u0905\u0924\u093f\u0930\u093f\u0915\u094d\u0924 \u0938\u0902\u0915\u0947\u0924 \u0928\u0939\u0940\u0902 \u092e\u093f\u0932\u093e\u0964",

    "report_heading": "\u0938\u093e\u092e\u093e\u091c\u093f\u0915 \u0938\u092e\u0938\u094d\u092f\u093e \u0926\u0930\u094d\u091c \u0915\u0930\u0947\u0902",
    "reported_by": "\u0936\u093f\u0915\u093e\u092f\u0924\u0915\u0930\u094d\u0924\u093e",
    "autofill_note": "\u0906\u092a\u0915\u0947 \u0916\u093e\u0924\u0947 \u0938\u0947 \u0905\u092a\u0928\u0947-\u0906\u092a \u092d\u0930\u093e \u0917\u092f\u093e \u2014 \u0935\u093f\u0935\u0930\u0923 \u0926\u094b\u092c\u093e\u0930\u093e \u092d\u0930\u0928\u0947 \u0915\u0940 \u091c\u093c\u0930\u0942\u0930\u0924 \u0928\u0939\u0940\u0902\u0964",
    "problem_title": "\u0938\u092e\u0938\u094d\u092f\u093e \u0915\u093e \u0936\u0940\u0930\u094d\u0937\u0915",
    "problem_title_ph": "\u091c\u0948\u0938\u0947: \u0938\u094d\u0915\u0942\u0932 \u0915\u0947 \u092a\u093e\u0938 \u091f\u0942\u091f\u0940 \u0938\u0921\u093c\u0915",
    "describe_problem": "\u0938\u092e\u0938\u094d\u092f\u093e \u0915\u093e \u0935\u093f\u0935\u0930\u0923 \u0926\u0947\u0902",
    "describe_problem_ph": "\u0915\u094d\u092f\u093e \u0939\u094b \u0930\u0939\u093e \u0939\u0948, \u0914\u0930 \u0907\u0938\u0938\u0947 \u0932\u094b\u0917\u094b\u0902 \u092a\u0930 \u0915\u094d\u092f\u093e \u0905\u0938\u0930 \u092a\u0921\u093c \u0930\u0939\u093e \u0939\u0948?",
    "category": "\u0936\u094d\u0930\u0947\u0923\u0940",
    "category_hint": "\"\u0938\u0921\u093c\u0915 \u0935 \u0905\u0935\u0938\u0902\u0930\u091a\u0928\u093e\" \u0936\u093f\u0915\u093e\u092f\u0924\u094b\u0902 \u0915\u0940 \u0938\u094d\u0935\u0924\u0903 \u0938\u0948\u091f\u0947\u0932\u093e\u0907\u091f AI \u091c\u093e\u0901\u091a \u0939\u094b\u0924\u0940 \u0939\u0948\u0964",
    "district": "\u091c\u093c\u093f\u0932\u093e",
    "location_details": "\u0938\u094d\u0925\u093e\u0928 \u0935\u093f\u0935\u0930\u0923",
    "location_ph": "\u0917\u093e\u0901\u0935 / \u0935\u093e\u0930\u094d\u0921 / \u0932\u0948\u0902\u0921\u092e\u093e\u0930\u094d\u0915",
    "evidence_label": "\u092b\u094b\u091f\u094b \u092f\u093e \u0935\u0940\u0921\u093f\u092f\u094b \u092a\u094d\u0930\u092e\u093e\u0923",
    "evidence_click": "\u0938\u092e\u0938\u094d\u092f\u093e \u0915\u0940 \u092b\u094b\u091f\u094b \u092f\u093e \u0935\u0940\u0921\u093f\u092f\u094b \u0905\u092a\u0932\u094b\u0921 \u0915\u0930\u0928\u0947 \u0915\u0947 \u0932\u093f\u090f \u0915\u094d\u0932\u093f\u0915 \u0915\u0930\u0947\u0902",
    "evidence_hint": "JPG, PNG, WEBP, \u092f\u093e MP4/MOV \u2014 \u0938\u0924\u094d\u092f\u093e\u092a\u0928 \u0915\u0947 \u0932\u093f\u090f \u0906\u0935\u0936\u094d\u092f\u0915",
    "btn_submit_problem": "\u0938\u092e\u0938\u094d\u092f\u093e \u0926\u0930\u094d\u091c \u0915\u0930\u0947\u0902",

    "banner_ai_verified": "\U0001f916 \u0938\u094d\u0935\u091a\u093e\u0932\u093f\u0924 \u0938\u0948\u091f\u0947\u0932\u093e\u0907\u091f \u091c\u093e\u0901\u091a \u0938\u0947 \u0938\u0924\u094d\u092f\u093e\u092a\u093f\u0924 ({conf}% \u0935\u093f\u0936\u094d\u0935\u093e\u0938)\u0964 \u0905\u0927\u093f\u0915\u093e\u0930\u0940 \u0926\u094d\u0935\u093e\u0930\u093e \u0938\u092e\u093e\u0927\u093e\u0928 \u0936\u0941\u0930\u0942 \u0939\u094b\u0928\u0947 \u0915\u0940 \u092a\u094d\u0930\u0924\u0940\u0915\u094d\u0937\u093e \u0939\u0948\u0964",
    "banner_pending_officer": "\U0001f575\ufe0f \u0915\u094d\u0937\u0947\u0924\u094d\u0930\u0940\u092f \u0905\u0927\u093f\u0915\u093e\u0930\u0940 \u0926\u094d\u0935\u093e\u0930\u093e \u092e\u0948\u0928\u094d\u092f\u0941\u0905\u0932 \u0938\u0924\u094d\u092f\u093e\u092a\u0928 \u0915\u0940 \u092a\u094d\u0930\u0924\u0940\u0915\u094d\u0937\u093e \u0939\u0948\u0964",
    "banner_overdue": "\u23f0 \u092f\u0939 \u092e\u093e\u092e\u0932\u093e \u0905\u092a\u0928\u0940 \u0938\u092e\u093e\u0927\u093e\u0928 \u0938\u092e\u092f-\u0938\u0940\u092e\u093e ({deadline}) \u092a\u093e\u0930 \u0915\u0930 \u091a\u0941\u0915\u093e \u0939\u0948\u0964",
    "banner_accepted": "\u2713 {officer} \u0926\u094d\u0935\u093e\u0930\u093e \u0938\u094d\u0935\u0940\u0915\u0943\u0924\u0964 \u0938\u092e\u093e\u0927\u093e\u0928 \u0915\u0940 \u0938\u092e\u092f-\u0938\u0940\u092e\u093e {deadline} \u0939\u0948 ({days} \u0926\u093f\u0928 \u0936\u0947\u0937)\u0964",
    "banner_reopened": "\U0001f501 \u0905\u092a\u0932\u094b\u0921 \u0915\u093f\u090f \u0917\u090f \u0938\u092e\u093e\u0927\u093e\u0928 \u092e\u0947\u0902 \u092a\u0930\u094d\u092f\u093e\u092a\u094d\u0924 \u092c\u0926\u0932\u093e\u0935 \u0928\u0939\u0940\u0902 \u0926\u093f\u0916\u093e \u2014 \u092e\u093e\u092e\u0932\u093e \u092b\u093f\u0930 \u0938\u0947 \u0916\u094b\u0932\u093e \u0917\u092f\u093e \u0939\u0948\u0964",
    "banner_resolved": "\u2705 {date} \u0915\u094b \u0939\u0932 \u0914\u0930 \u0938\u0924\u094d\u092f\u093e\u092a\u093f\u0924\u0964",
    "banner_rejected": "\u2715 \u0907\u0938 \u0936\u093f\u0915\u093e\u092f\u0924 \u0915\u0940 \u0938\u092e\u0940\u0915\u094d\u0937\u093e \u0915\u0930 \u0907\u0938\u0947 \u0905\u0938\u094d\u0935\u0940\u0915\u093e\u0930 \u0915\u0930 \u0926\u093f\u092f\u093e \u0917\u092f\u093e\u0964",

    "problem_section": "\u0938\u092e\u0938\u094d\u092f\u093e",
    "reported_by_section": "\u0936\u093f\u0915\u093e\u092f\u0924\u0915\u0930\u094d\u0924\u093e",
    "evidence_section": "\u092a\u094d\u0930\u092e\u093e\u0923",
    "evidence_before": "\u092a\u0939\u0932\u0947 \u2014 \u0928\u093e\u0917\u0930\u093f\u0915 \u0926\u094d\u0935\u093e\u0930\u093e \u092a\u094d\u0930\u0938\u094d\u0924\u0941\u0924",
    "evidence_after_officer": "\u092c\u093e\u0926 \u092e\u0947\u0902 \u2014 \u0905\u0927\u093f\u0915\u093e\u0930\u0940 \u0926\u094d\u0935\u093e\u0930\u093e \u0905\u092a\u0932\u094b\u0921",
    "evidence_after_pending": "\u0938\u092e\u093e\u0927\u093e\u0928 \u0915\u0940 \u092b\u094b\u091f\u094b \u0905\u092d\u0940 \u0905\u092a\u0932\u094b\u0921 \u0928\u0939\u0940\u0902 \u0939\u0941\u0908 \u0939\u0948",
    "ai_resolution_check": "AI \u0938\u092e\u093e\u0927\u093e\u0928 \u091c\u093e\u0901\u091a",
    "progress_timeline": "\u092a\u094d\u0930\u0917\u0924\u093f \u0938\u092e\u092f\u0930\u0947\u0916\u093e",
    "change_score": "\u092a\u0930\u093f\u0935\u0930\u094d\u0924\u0928 \u0938\u094d\u0915\u094b\u0930",

    "officer_queue_title": "\u0938\u0924\u094d\u092f\u093e\u092a\u0928 \u0915\u0924\u093e\u0930",
    "needs_review": "\u0938\u092e\u0940\u0915\u094d\u0937\u093e \u0906\u0935\u0936\u094d\u092f\u0915",
    "waiting": "\u092a\u094d\u0930\u0924\u0940\u0915\u094d\u0937\u093e\u0930\u0924",
    "nothing_waiting": "\u0905\u092d\u0940 \u0938\u092e\u0940\u0915\u094d\u0937\u093e \u0939\u0947\u0924\u0941 \u0915\u0941\u091b \u092d\u0940 \u092a\u094d\u0930\u0924\u0940\u0915\u094d\u0937\u093e\u0930\u0924 \u0928\u0939\u0940\u0902 \u0939\u0948\u0964",
    "my_active_cases": "\u092e\u0947\u0930\u0947 \u0938\u0915\u094d\u0930\u093f\u092f \u092e\u093e\u092e\u0932\u0947",
    "in_progress": "\u092a\u094d\u0930\u0917\u0924\u093f \u092e\u0947\u0902",
    "no_active_cases": "\u0906\u092a\u0915\u094b \u0915\u094b\u0908 \u0938\u0915\u094d\u0930\u093f\u092f \u092e\u093e\u092e\u0932\u093e \u0928\u0939\u0940\u0902 \u0938\u094c\u0902\u092a\u093e \u0917\u092f\u093e \u0939\u0948\u0964",
    "recently_resolved": "\u0906\u092a\u0915\u0947 \u0926\u094d\u0935\u093e\u0930\u093e \u0939\u093e\u0932 \u092e\u0947\u0902 \u0939\u0932 \u0915\u093f\u090f \u0917\u090f",
    "no_resolved_yet": "\u0905\u092d\u0940 \u0924\u0915 \u0915\u094b\u0908 \u092e\u093e\u092e\u0932\u093e \u0939\u0932 \u0928\u0939\u0940\u0902 \u0939\u0941\u0906 \u0939\u0948\u0964",
    "due": "\u0928\u093f\u092f\u0924 \u0924\u093f\u0925\u093f",

    "take_action": "\u0915\u093e\u0930\u094d\u0930\u0935\u093e\u0908 \u0915\u0930\u0947\u0902",
    "btn_verify_accept": "\u0938\u0924\u094d\u092f\u093e\u092a\u093f\u0924 \u0915\u0930\u0947\u0902 \u0935 \u0938\u094d\u0935\u0940\u0915\u093e\u0930 \u0915\u0930\u0947\u0902",
    "btn_accept_begin": "\u0938\u094d\u0935\u0940\u0915\u093e\u0930 \u0915\u0930\u0947\u0902 \u0935 \u0938\u092e\u093e\u0927\u093e\u0928 \u0936\u0941\u0930\u0942 \u0915\u0930\u0947\u0902",
    "rejection_reason_label": "\u0905\u0938\u094d\u0935\u0940\u0915\u0943\u0924\u093f \u0915\u093e \u0915\u093e\u0930\u0923 (\u092f\u0926\u093f \u0905\u0938\u094d\u0935\u0940\u0915\u093e\u0930 \u0930\u0939\u0947 \u0939\u0948\u0902)",
    "rejection_reason_ph": "\u092c\u0924\u093e\u090f\u0902 \u0915\u093f \u092f\u0939 \u0936\u093f\u0915\u093e\u092f\u0924 \u092e\u093e\u0928\u094d\u092f / \u0938\u0924\u094d\u092f\u093e\u092a\u0928 \u092f\u094b\u0917\u094d\u092f \u0915\u094d\u092f\u094b\u0902 \u0928\u0939\u0940\u0902 \u0939\u0948",
    "btn_reject": "\u0936\u093f\u0915\u093e\u092f\u0924 \u0905\u0938\u094d\u0935\u0940\u0915\u093e\u0930 \u0915\u0930\u0947\u0902",
    "upload_resolution": "\u0938\u092e\u093e\u0927\u093e\u0928 \u092a\u094d\u0930\u092e\u093e\u0923 \u0905\u092a\u0932\u094b\u0921 \u0915\u0930\u0947\u0902",
    "upload_resolution_hint": "\u0938\u092e\u092f-\u0938\u0940\u092e\u093e: {deadline}\u0964 \u0909\u0938\u0940 \u0938\u094d\u0925\u093e\u0928 \u0915\u0940 \"\u092c\u093e\u0926 \u0915\u0940\" \u092b\u094b\u091f\u094b \u0905\u092a\u0932\u094b\u0921 \u0915\u0930\u0947\u0902 \u2014 \u0907\u0938\u0915\u0940 \u0938\u094d\u0935\u0924\u0903 \u0924\u0941\u0932\u0928\u093e \u092e\u0942\u0932 \u092b\u094b\u091f\u094b \u0938\u0947 \u0915\u0940 \u091c\u093e\u090f\u0917\u0940\u0964",
    "evidence_upload_after": "\u0939\u0932 \u0915\u093f\u090f \u0917\u092f\u0947 \u0938\u094d\u0925\u093e\u0928 \u0915\u0940 \u092b\u094b\u091f\u094b \u0905\u092a\u0932\u094b\u0921 \u0915\u0930\u0928\u0947 \u0915\u0947 \u0932\u093f\u090f \u0915\u094d\u0932\u093f\u0915 \u0915\u0930\u0947\u0902",
    "evidence_after_hint": "\u0938\u094d\u0935\u091a\u093e\u0932\u093f\u0924 \u0924\u0941\u0932\u0928\u093e \u0915\u0947 \u0932\u093f\u090f JPG, PNG, \u092f\u093e WEBP \u0909\u092a\u092f\u0941\u0915\u094d\u0924",
    "btn_submit_resolution": "AI \u0938\u0924\u094d\u092f\u093e\u092a\u0928 \u0939\u0947\u0924\u0941 \u0938\u092e\u093e\u0927\u093e\u0928 \u091c\u092e\u093e \u0915\u0930\u0947\u0902",
    "case_resolved_on": "\u2705 \u092e\u093e\u092e\u0932\u093e {date} \u0915\u094b \u0939\u0932 \u0935 \u0938\u0924\u094d\u092f\u093e\u092a\u093f\u0924 \u0939\u0941\u0906\u0964",
    "case_rejected": "\u2715 \u0905\u0938\u094d\u0935\u0940\u0915\u0930\u094d\u0924\u0964",

    "admin_overview": "\u090f\u0921\u092e\u093f\u0928 \u0905\u0935\u0932\u094b\u0915\u0928",
    "total_complaints": "\u0915\u0941\u0932 \u0936\u093f\u0915\u093e\u092f\u0924\u0947\u0902",
    "open": "\u0916\u0941\u0932\u0940",
    "resolved": "\u0939\u0932 \u0939\u0941\u0908\u0902",
    "overdue": "\u0938\u092e\u092f-\u0938\u0940\u092e\u093e \u092a\u093e\u0930",
    "all_complaints": "\u0938\u092d\u0940 \u0936\u093f\u0915\u093e\u092f\u0924\u0947\u0902",
    "th_id": "\u0906\u0908\u0921\u0940",
    "th_title": "\u0936\u0940\u0930\u094d\u0937\u0915",
    "th_district": "\u091c\u093c\u093f\u0932\u093e",
    "th_category": "\u0936\u094d\u0930\u0947\u0923\u0940",
    "th_officer": "\u0905\u0927\u093f\u0915\u093e\u0930\u0940",
    "th_status": "\u0938\u094d\u0925\u093f\u0924\u093f",
    "no_complaints_filed": "\u0905\u092d\u0940 \u0924\u0915 \u0915\u094b\u0908 \u0936\u093f\u0915\u093e\u092f\u0924 \u0926\u0930\u094d\u091c \u0928\u0939\u0940\u0902 \u0939\u0941\u0906\u0964",
    "officers_count": "\u0905\u0927\u093f\u0915\u093e\u0930\u0940",
    "no_officers_yet": "\u0905\u092d\u0940 \u0915\u094b\u0908 \u0905\u0927\u093f\u0915\u093e\u0930\u0940 \u0928\u0939\u0940\u0902 \u0939\u0948\u0964",
    "add_officer": "\u0905\u0927\u093f\u0915\u093e\u0930\u0940 \u091c\u094b\u0921\u0947\u0902",
    "temp_password": "\u0905\u0938\u094d\u0925\u093e\u092f\u0940 \u092a\u093e\u0938\u0935\u0930\u094d\u0921",
    "btn_create_officer": "\u0905\u0927\u093f\u0915\u093e\u0930\u0940 \u0916\u093e\u0924\u093e \u092c\u0928\u093e\u090f\u0902",
    "assignment": "\u0905\u0938\u093e\u0907\u0928\u092e\u0947\u0901\u091f",
    "currently": "\u0935\u0930\u094d\u0924\u092e\u093e\u0928 \u092e\u0947\u0902",
    "unassigned": "\u0905\u0938\u093e\u0907\u0928 \u0928\u0939\u0940\u0902 \u0915\u093f\u092f\u093e \u0917\u092f\u093e",
    "due_label": "\u0928\u093f\u092f\u0924",
    "assign_reassign": "\u0905\u0927\u093f\u0915\u093e\u0930\u0940 \u0905\u0938\u093e\u0907\u0928 / \u092a\u0941\u0928\u0939 \u0905\u0938\u093e\u0907\u0928 \u0915\u0930\u0947\u0902",
    "btn_assign": "\u0905\u0938\u093e\u0907\u0928 \u0915\u0930\u0947\u0902 (5-\u0926\u093f\u0928 \u0915\u0940 \u0938\u092e\u092f-\u0938\u0940\u092e\u093e \u092b\u093f\u0930 \u0938\u0947 \u0936\u0941\u0930\u0942 \u0939\u094b\u0917\u0940)",
    "timeline": "\u0938\u092e\u092f\u0930\u0947\u0916\u093e",

    "status_submitted": "\u0926\u0930\u094d\u091c \u0915\u0940 \u0917\u0908",
    "status_ai_verified": "\U0001f916 AI \u0938\u0924\u094d\u092f\u093e\u092a\u093f\u0924",
    "status_pending_officer": "\u0905\u0927\u093f\u0915\u093e\u0930\u0940 \u0938\u092e\u0940\u0915\u094d\u0937\u093e \u0932\u0902\u092c\u093f\u0924",
    "status_accepted": "\u092a\u094d\u0930\u0917\u0924\u093f \u092e\u0947\u0902",
    "status_resolved": "\u2713 \u0939\u0932 \u0939\u0941\u0908",
    "status_reopened": "\u092b\u093f\u0930 \u0938\u0947 \u0916\u094b\u0932\u0940 \u0917\u0908",
    "status_rejected": "\u0905\u0938\u094d\u0935\u0940\u0915\u0930\u094d\u0924",
    "status_overdue": "\u23f0 \u0938\u092e\u092f-\u0938\u0940\u092e\u093e \u092a\u093e\u0930",

    "cat_roads": "\u0938\u0921\u093c\u0915 \u0935 \u0905\u0935\u0938\u0902\u0930\u091a\u0928\u093e",
    "cat_water": "\u091c\u0932 \u0938\u0902\u0938\u093e\u0927\u0928",
    "cat_electricity": "\u092c\u093f\u091c\u0932\u0940",
    "cat_sanitation": "\u0938\u094d\u0935\u091a\u094d\u0927\u0924\u093e",
    "cat_health": "\u0938\u094d\u0935\u093e\u0938\u094d\u0925\u094d\u092f \u0938\u0947\u0935\u093e",
    "cat_education": "\u0936\u093f\u0915\u094d\u0937\u093e",
    "cat_safety": "\u0938\u093e\u0930\u094d\u0935\u091c\u0928\u093f\u0915 \u0938\u0941\u0930\u0915\u094d\u0937\u093e",
    "cat_other": "\u0905\u0928\u094d\u092f",

    "dist_ranchi": "\u0930\u093e\u0901\u091a\u0940",
    "dist_dhanbad": "\u0927\u0928\u092c\u093e\u0926",
    "dist_dumka": "\u0926\u0941\u092e\u0915\u093e",
    "dist_bokaro": "\u092c\u094b\u0915\u093e\u0930\u094b",
    "dist_gumla": "\u0917\u0941\u092e\u0932\u093e",
    "dist_deoghar": "\u0926\u0947\u0935\u0918\u0930",
    "dist_hazaribagh": "\u0939\u091c\u093c\u093e\u0930\u0940\u092c\u093e\u0917",
    "dist_giridih": "\u0917\u093f\u0930\u093f\u0921\u0940\u0939",
    "dist_east_singhbhum": "\u092a\u0942\u0930\u094d\u0935\u0940 \u0938\u093f\u0902\u0939\u092d\u0942\u092e",
    "dist_west_singhbhum": "\u092a\u0936\u094d\u091a\u093f\u092e\u0940 \u0938\u093f\u0902\u0939\u092d\u0942\u092e",

    "hero_kicker": "\u0906\u092a\u0915\u0940 \u0939\u0930 \u0938\u092e\u0938\u094d\u092f\u093e \u0915\u093e \u0938\u092e\u093e\u0927\u093e\u0928",
    "sec_problems_title": "\u092f\u0939 \u092a\u094d\u0932\u0947\u091f\u092b\u0949\u0930\u094d\u092e \u0907\u0928 \u0938\u092e\u0938\u094d\u092f\u093e\u0913\u0902 \u0915\u093e \u0938\u092e\u093e\u0927\u093e\u0928 \u0915\u0930\u0924\u093e \u0939\u0948",
    "sec_problems_sub": "\u091f\u0942\u091f\u0940 \u0938\u0921\u093c\u0915\u094b\u0902 \u0938\u0947 \u0932\u0947\u0915\u0930 \u0915\u091a\u0930\u0947 \u0915\u0947 \u0922\u0947\u0930 \u0924\u0915 \u2014 \u092b\u094b\u091f\u094b \u0932\u0947\u0902, \u0930\u093f\u092a\u094b\u0930\u094d\u091f \u0926\u0930\u094d\u091c \u0915\u0930\u0947\u0902, \u0914\u0930 \u0938\u092e\u093e\u0927\u093e\u0928 \u0926\u0947\u0916\u0947\u0902\u0964 \u092f\u0947 \u0935\u094b \u0906\u092e \u0938\u092e\u0938\u094d\u092f\u093e\u090f\u0901 \u0939\u0948\u0902 \u091c\u093f\u0928\u0915\u0947 \u0932\u093f\u090f \u0938\u092e\u093e\u0927\u093e\u0928 \u092c\u0928\u093e \u0939\u0948\u0964",
    "problem_road": "\u091f\u0942\u091f\u0940 \u0938\u0921\u093c\u0915\u0947\u0902 \u0935 \u0917\u0921\u094d\u0922\u0947",
    "problem_road_desc": "\u0917\u093e\u0902\u0935 \u0915\u0940 \u091f\u0942\u091f\u0940 \u0938\u0921\u093c\u0915\u0947\u0902, \u0916\u0924\u0930\u0928\u093e\u0915 \u0917\u0921\u094d\u0922\u0947, \u0914\u0930 \u091f\u0942\u091f\u0947 \u092a\u0941\u0932 \u091c\u093f\u0928\u0938\u0947 \u0906\u0935\u093e\u0917\u092e\u0928 \u092e\u0941\u0936\u094d\u0915\u093f\u0932 \u0939\u0948\u0964",
    "problem_water": "\u092a\u093e\u0928\u0940 \u0935 \u0939\u0948\u0902\u0921\u092a\u0902\u092a",
    "problem_water_desc": "\u0938\u0942\u0916\u0947 \u0939\u0948\u0902\u0921\u092a\u0902\u092a, \u091f\u092a\u0915\u0924\u0947 \u092a\u093e\u0907\u092a, \u0914\u0930 \u0918\u0930\u094b\u0902 \u0924\u0915 \u092a\u0939\u0941\u0902\u091a\u0928\u0947 \u0935\u093e\u0932\u093e \u0905\u0938\u0941\u0930\u0915\u094d\u0937\u093f\u0924 \u092a\u0947\u092f\u091c\u0932\u0964",
    "problem_electricity": "\u092c\u093f\u091c\u0932\u0940 \u0935 \u0930\u094b\u0936\u0928\u0940",
    "problem_electricity_desc": "\u092c\u0902\u0926 \u0938\u094d\u091f\u094d\u0930\u0940\u091f \u0932\u093e\u0907\u091f, \u0932\u0917\u093e\u0924\u093e\u0930 \u092c\u093f\u091c\u0932\u0940 \u0915\u091f\u094c\u0924\u0940, \u0914\u0930 \u092c\u093f\u091c\u0932\u0940 \u0938\u0947 \u0935\u0902\u091a\u093f\u0924 \u0917\u093e\u0902\u0935\u0964",
    "problem_sanitation": "\u0938\u094d\u0935\u091a\u094d\u091b\u0924\u093e \u0935 \u0915\u091a\u0930\u093e",
    "problem_sanitation_desc": "\u0938\u0921\u093c\u0915\u094b\u0902 \u092a\u0930 \u0915\u091a\u0930\u0947 \u0915\u0947 \u0922\u0947\u0930, \u092c\u0902\u0926 \u0928\u093e\u0932\u093f\u092f\u093e\u0901, \u0914\u0930 \u0915\u092d\u0940 \u0928 \u0938\u093e\u092b \u0939\u094b\u0928\u0947 \u0935\u093e\u0932\u0940 \u091c\u0917\u0939\u0947\u0902\u0964",
    "problem_health": "\u0938\u094d\u0935\u093e\u0938\u094d\u0925\u094d\u092f \u0938\u0947\u0935\u093e\u090f\u0902",
    "problem_health_desc": "\u0909\u092a\u0947\u0915\u094d\u0937\u093f\u0924 \u0938\u094d\u0935\u093e\u0938\u094d\u0925\u094d\u092f \u0915\u0947\u0902\u0926\u094d\u0930, \u0926\u0942\u0930 \u0915\u0947 \u0905\u0938\u094d\u092a\u0924\u093e\u0932, \u0914\u0930 \u0917\u093e\u0902\u0935 \u0924\u0915 \u0928 \u092a\u0939\u0941\u0902\u091a\u0928\u0947 \u0935\u093e\u0932\u0940 \u091a\u093f\u0915\u093f\u0924\u094d\u0938\u093e\u0964",
    "problem_education": "\u0938\u094d\u0915\u0942\u0932 \u0935 \u0936\u093f\u0915\u094d\u0937\u093e",
    "problem_education_desc": "\u091f\u0942\u091f\u0940 \u0938\u094d\u0915\u0942\u0932 \u0907\u092e\u093e\u0930\u0924\u0947\u0902, \u092a\u093e\u0928\u0940-\u0936\u094c\u091a\u093e\u0932\u092f \u0915\u0940 \u0915\u092e\u0940, \u0914\u0930 \u092c\u091a\u094d\u091a\u094b\u0902 \u0915\u0947 \u0932\u093f\u090f \u0928 \u0939\u094b\u0928\u0947 \u0935\u093e\u0932\u0940 \u0938\u0941\u0935\u093f\u0927\u093e\u090f\u0902\u0964",
    "sec_how_title": "\u0938\u092e\u093e\u0927\u093e\u0928 \u0915\u0948\u0938\u0947 \u0915\u093e\u092e \u0915\u0930\u0924\u093e \u0939\u0948",
    "sec_how_sub": "\u0938\u092e\u0938\u094d\u092f\u093e \u0938\u0947 \u0938\u092e\u093e\u0927\u093e\u0928 \u0924\u0915 \u0924\u0940\u0928 \u0938\u0930\u0932 \u0915\u0926\u092e\u0964",
    "how_1": "\u0938\u092c\u0942\u0924 \u0915\u0947 \u0938\u093e\u0925 \u0930\u093f\u092a\u094b\u0930\u094d\u091f \u0915\u0930\u0947\u0902",
    "how_1_desc": "\u0938\u092e\u0938\u094d\u092f\u093e \u0915\u0940 \u092b\u094b\u091f\u094b \u092f\u093e \u0935\u0940\u0921\u093f\u092f\u094b \u0932\u0947\u0902 \u0914\u0930 \u0932\u094b\u0915\u0947\u0936\u0928 \u092a\u093f\u0928 \u0915\u0930\u0947\u0902\u0964 \u0938\u0921\u093c\u0915 \u0915\u0940 \u0930\u093f\u092a\u094b\u0930\u094d\u091f \u0915\u0940 \u0938\u094d\u0935\u0924\u0903 \u0938\u0948\u091f\u0947\u0932\u093e\u0907\u091f \u091c\u093e\u0901\u091a \u092d\u0940 \u0939\u094b\u0924\u0940 \u0939\u0948\u0964",
    "how_2": "\u0938\u0924\u094d\u092f\u093e\u092a\u0928 \u0935 \u0905\u0938\u093e\u0907\u0928\u092e\u0947\u0902\u091f",
    "how_2_desc": "\u0915\u094d\u0937\u0947\u0924\u094d\u0930\u0940\u092f \u0905\u0927\u093f\u0915\u093e\u0930\u0940 \u0906\u092a\u0915\u0940 \u0936\u093f\u0915\u093e\u092f\u0924 \u0915\u093e \u0938\u0924\u094d\u092f\u093e\u092a\u0928 \u0915\u0930 \u0924\u092f \u0938\u0940\u092e\u093e \u0915\u0947 \u0938\u093e\u0925 \u092e\u093e\u092e\u0932\u093e \u0938\u094d\u0935\u0940\u0915\u093e\u0930 \u0915\u0930\u0924\u0947 \u0939\u0948\u0902\u0964",
    "how_3": "\u092e\u0941\u0930\u092e\u094d\u092e\u0924 \u0926\u0947\u0916\u0947\u0902",
    "how_3_desc": "\u0905\u0927\u093f\u0915\u093e\u0930\u0940 \u092c\u093e\u0926 \u0915\u0940 \u092b\u094b\u091f\u094b \u0905\u092a\u0932\u094b\u0921 \u0915\u0930\u0924\u0947 \u0939\u0948\u0902\u0964 AI \u092a\u0939\u0932\u0947/\u092c\u093e\u0926 \u0915\u0940 \u0924\u0941\u0932\u0928\u093e \u0915\u0930 \u092e\u093e\u092e\u0932\u093e \u092c\u0902\u0926 \u0915\u0930\u0924\u093e \u0939\u0948\u0964",
    "footer_note": "\u091d\u093e\u0930\u0916\u0902\u0921 \u0938\u092e\u093e\u0927\u093e\u0928 \u2014 \u090f\u0915 Smart India Hackathon \u092a\u094d\u0930\u094b\u091f\u094b\u091f\u093e\u0907\u092a\u0964",
},

# --- Core navigation/status/category vocabulary for other languages.
# Anything not listed here falls back along the chain defined in LANGUAGES.

"nag": {
    "app_name": "\u091d\u093e\u0930\u0916\u0902\u0921 \u0938\u092e\u093e\u0927\u093e\u0928", "language": "\u092c\u094b\u0932\u0940",
    "nav_home": "\u0918\u0930", "nav_my_complaints": "\u0939\u092e\u093e\u0930 \u0936\u093f\u0915\u093e\u092f\u0924", "nav_report": "\u0938\u092e\u0938\u094d\u092f\u093e \u0932\u093f\u0916\u093e\u0907\u0901",
    "btn_login": "\u0932\u0949\u0917\u093f\u0928 \u0915\u0930\u0940\u0901", "btn_submit_problem": "\u0938\u092e\u0938\u094d\u092f\u093e \u092d\u0947\u091c\u0940\u0901",
    "role_citizen": "\u0928\u093e\u0917\u0930\u093f\u0915", "role_officer": "\u0905\u092b\u0938\u093e\u0930", "role_admin": "\u090f\u0921\u092e\u093f\u0928",
},

"khr": {
    "app_name": "\u091d\u093e\u0930\u0916\u0902\u0921 \u0938\u092e\u093e\u0927\u093e\u0928", "language": "\u092c\u094b\u0932\u0940",
    "nav_home": "\u0918\u0930", "nav_my_complaints": "\u0939\u092e\u0930 \u0936\u093f\u0915\u093e\u092f\u0924", "nav_report": "\u0938\u092e\u0938\u094d\u092f\u093e \u0932\u093f\u0916\u094b",
    "btn_login": "\u0932\u0949\u0917\u093f\u0928 \u0915\u0930\u094b", "btn_submit_problem": "\u0938\u092e\u0938\u094d\u092f\u093e \u092d\u0947\u091c\u094b",
    "role_citizen": "\u0928\u093e\u0917\u0930\u093f\u0915", "role_officer": "\u0905\u092b\u0938\u093e\u0930", "role_admin": "\u090f\u0921\u092e\u093f\u0928",
},

"pnx": {
    "app_name": "\u091d\u093e\u0930\u0916\u0902\u0921 \u0938\u092e\u093e\u0927\u093e\u0928", "language": "\u092d\u093e\u0937\u093e",
    "nav_home": "\u0918\u0930", "nav_my_complaints": "\u0939\u092e\u0930 \u0936\u093f\u0915\u093e\u092f\u0924", "nav_report": "\u0938\u092e\u0938\u094d\u092f\u093e \u0932\u093f\u0916\u0948",
    "btn_login": "\u0932\u0949\u0917\u093f\u0928 \u0915\u0930\u0942", "btn_submit_problem": "\u0938\u092e\u0938\u094d\u092f\u093e \u092a\u0920\u093e\u090a",
    "role_citizen": "\u0928\u093e\u0917\u0930\u093f\u0915", "role_officer": "\u0905\u092b\u0938\u093e\u0930", "role_admin": "\u090f\u0921\u092e\u093f\u0928",
},

"sat": {
    "app_name": "\u1c65\u1c7f\u1c6b\u1c6f\u1c75\u1c76 \u1c61\u1c56\u1c6c\u1c58\u1c61\u1c76\u1c61", "language": "\u1c65\u1c68\u1c67\u1c73\u1c64",
    "nav_home": "\u1c66\u1c76\u1c60", "role_citizen": "\u1c67\u1c6f\u1c76",
},

"hoc": {"app_name": "\u091d\u093e\u0930\u0916\u0902\u0921 \u0938\u092e\u093e\u0927\u093e\u0928"},
"unr": {"app_name": "\u091d\u093e\u0930\u0916\u0902\u0921 \u0938\u092e\u093e\u0927\u093e\u0928"},
"kru": {"app_name": "\u091d\u093e\u0930\u0916\u0902\u0921 \u0938\u092e\u093e\u0927\u093e\u0928"},
"kha": {"app_name": "\u091d\u093e\u0930\u0916\u0902\u0921 \u0938\u092e\u093e\u0927\u093e\u0928"},

"bn": {
    "app_name": "\u099d\u09be\u09b0\u0996\u09a3\u09cd\u09a1 \u09b8\u09ae\u09be\u09a7\u09be\u09a8", "language": "\u09ad\u09be\u09b7\u09be",
    "nav_home": "\u09b9\u09cb\u09ae", "nav_register": "\u09a8\u09be\u0997\u09b0\u09bf\u0995 \u09b9\u09bf\u09b8\u09c7\u09ac\u09c7 \u09a8\u09bf\u09ac\u09a8\u09cd\u09a7\u09a8 \u0995\u09b0\u09c1\u09a8",
    "nav_my_complaints": "\u0986\u09ae\u09be\u09b0 \u0985\u09ad\u09bf\u09af\u09cb\u0997", "nav_report": "\u09b8\u09ae\u09b8\u09cd\u09af\u09be \u09b0\u09bf\u09aa\u09cb\u09b0\u09cd\u099f \u0995\u09b0\u09c1\u09a8",
    "nav_queue": "\u09b8\u09be\u09b0\u09bf", "nav_overview": "\u09b8\u0982\u0995\u09cd\u09b7\u09bf\u09aa\u09cd\u099a \u09ac\u09bf\u09ac\u09b0\u09a3", "nav_logout": "\u09b2\u09b9 \u0986\u0989\u099f",
    "login_title": "\u09b2\u0997\u0987\u09a8", "email": "\u0987\u09ae\u09c7\u09b2", "password": "\u09aa\u09be\u09b8\u0993\u09af\u09bc\u09be\u09b0\u09cd\u09a1", "btn_login": "\u09b2\u0997 \u0987\u09a8 \u0995\u09b0\u09c1\u09a8",
    "full_name": "\u09aa\u09c2\u09b0\u09cd\u09a3 \u09a8\u09be\u09ae", "phone": "\u09ab\u09cb\u09a8 \u09a8\u09ae\u09cd\u09ac\u09b0", "btn_create_account": "\u0985\u09cd\u09af\u09be\u0995\u09be\u0989\u09a8\u09cd\u099f \u09a4\u09c8\u09b0\u09bf \u0995\u09b0\u09c1\u09a8",
    "my_complaints": "\u0986\u09ae\u09be\u09b0 \u0985\u09ad\u09bf\u09af\u09cb\u0997", "btn_new_report": "+ \u09a8\u09a4\u09c1\u09a8 \u09b8\u09ae\u09b8\u09cd\u09af\u09be \u09b0\u09bf\u09aa\u09cb\u09b0\u09cd\u099f \u0995\u09b0\u09c1\u09a8",
    "role_citizen": "\u09a8\u09be\u0997\u09b0\u09bf\u0995", "role_officer": "\u0985\u09ab\u09bf\u09b8\u09be\u09b0", "role_admin": "\u0985\u09cd\u09af\u09be\u09a1\u09ae\u09bf\u09a8",
    "status_submitted": "\u099c\u09ae\u09be \u09a6\u09c7\u0993\u09af\u09bc\u09be \u09b9\u09af\u09bc\u09c7\u099b\u09c7", "status_resolved": "\u2713 \u09b8\u09ae\u09be\u09a7\u09be\u09a8 \u09b9\u09af\u09bc\u09c7\u099b\u09c7",
    "status_pending_officer": "\u0985\u09ab\u09bf\u09b8\u09be\u09b0\u09c7\u09b0 \u09aa\u09b0\u09cd\u09af\u09be\u09b2\u09cb\u099a\u09a8\u09be \u09ac\u09be\u0995\u09bf", "status_rejected": "\u09aa\u09cd\u09b0\u09a4\u09cd\u09af\u09be\u0996\u09cd\u09af\u09be\u09a4",
},

"or": {
    "app_name": "\u0b1c\u0b3e\u0b21\u0b3c\u0b39\u0b3e\u0b31\u0b15\u0b23\u0b4d\u0b21 \u0b38\u0b2e\u0b3e\u0b27\u0b3e\u0b28", "language": "\u0b2d\u0b3e\u0b37\u0b3e",
    "nav_home": "\u0b2e\u0b42\u0b33\u0b2a\u0b43\u0b37\u0b4d\u0b20\u0b3e", "nav_my_complaints": "\u0b2e\u0b4b\u0b30 \u0b05\u0cad\u0bf9\u0b2f\u0b4b\u0b17", "nav_report": "\u0b38\u0b2e\u0b38\u0b4d\u0b2f\u0b3e \u0b30\u0b3f\u0b2a\u0b4b\u0b30\u0b4d\u0b1f \u0b15\u0b30\u0ba8\u0bcd\u0b24\u0b41",
    "login_title": "\u0b32\u0b17\u0b3f\u0b28", "email": "\u0b07\u0b2e\u0b47\u0b32", "password": "\u0b2a\u0b3e\u0b38\u0b4d\u0b13\u0b30\u0b4d\u0b21", "btn_login": "\u0b32\u0b17 \u0b07\u0b28",
    "role_citizen": "\u0b28\u0b3e\u0b17\u0b30\u0b3f\u0b15", "role_officer": "\u0b05\u0b27\u0b3f\u0b15\u0b3e\u0b30\u0b40", "role_admin": "\u0b06\u0b21\u0b2e\u0b3f\u0b28",
},

"mr": {
    "app_name": "\u091d\u093e\u0930\u0916\u0902\u0921 \u0938\u092e\u093e\u0927\u093e\u0928", "language": "\u092d\u093e\u0937\u093e",
    "nav_home": "\u092e\u0941\u0916\u094d\u092f\u092a\u0943\u0937\u094d\u0920", "nav_my_complaints": "\u092e\u093e\u091d\u094d\u092f\u093e \u0924\u0915\u094d\u0930\u093e\u0930\u0940", "nav_report": "\u0938\u092e\u0938\u094d\u092f\u093e \u0928\u094b\u0902\u0926\u0935\u093e",
    "login_title": "\u0932\u0949\u0917\u093f\u0928", "email": "\u0908\u092e\u0947\u0932", "password": "\u092a\u093e\u0938\u0935\u0930\u094d\u0921", "btn_login": "\u0932\u0949\u0917 \u0907\u0928 \u0915\u0930\u093e",
    "full_name": "\u092a\u0942\u0930\u094d\u0923 \u0928\u093e\u0935", "phone": "\u092b\u094b\u0928 \u0928\u0902\u092c\u0930", "btn_create_account": "\u0916\u093e\u0924\u0947 \u0924\u092f\u093e\u0930 \u0915\u0930\u093e",
    "role_citizen": "\u0928\u093e\u0917\u0930\u093f\u0915", "role_officer": "\u0905\u0927\u093f\u0915\u093e\u0930\u0940", "role_admin": "\u092a\u094d\u0930\u0936\u093e\u0938\u0915",
    "status_resolved": "\u2713 \u0928\u093f\u0915\u093e\u0932\u0940", "status_rejected": "\u0928\u093e\u0915\u093e\u0930\u0932\u0947",
},

"gu": {
    "app_name": "\u0a9d\u0abe\u0ab0\u0a96\u0a82\u0aa1 \u0ab8\u0aae\u0abe\u0aa7\u0abe\u0a28", "language": "\u0aad\u0abe\u0b37\u0abe",
    "nav_home": "\u0ab9\u0acb\u0aae", "nav_my_complaints": "\u0aae\u0abe\u0ab0\u0ac0 \u0ab2\u0ab0\u0abf\u0aaf\u0abe\u0aa6\u0acb", "nav_report": "\u0ab8\u0aae\u0ab8\u0acd\u0a2f\u0abe\u0aa8\u0bc0 \u0a9c\u0abe\u0aa3 \u0a95\u0ab0\u0acb",
    "login_title": "\u0ab2\u0949\u0a97\u0abf\u0aa8", "email": "\u0a87\u0aae\u0ac7\u0a87\u0ab2", "password": "\u0aaa\u0abe\u0ab8\u0ab5\u0ab0\u0acd\u0aa1", "btn_login": "\u0ab2\u0949\u0a97 \u0a87\u0aa8 \u0a95\u0ab0\u0acb",
    "role_citizen": "\u0aa8\u0abe\u0a97\u0ab0\u0abf\u0a95", "role_officer": "\u0a85\u0aa7\u0abf\u0a95\u0abe\u0ab0\u0ac0", "role_admin": "\u0a8f\u0aa1\u0aae\u0abf\u0a28",
},

"pa": {
    "app_name": "\u0a1d\u0a3e\u0a30\u0a16\u0a70\u0a21 \u0a38\u0a2e\u0a3e\u0a27\u0a3e\u0a28", "language": "\u0a2d\u0a3e\u0a38\u0a3c\u0a3e",
    "nav_home": "\u0a39\u0a4b\u0a2e", "nav_my_complaints": "\u0a2e\u0a47\u0a30\u0a40\u0a06\u0a02 \u0a38\u0a3c\u0a3f\u0a15\u0a3e\u0a07\u0a24\u0a3e\u0a02", "nav_report": "\u0b38\u0a2e\u0a38\u0a4d\u0a3f\u0a3e \u0a26\u0a30\u0a1c \u0a15\u0a30\u0a4b",
    "login_title": "\u0a32\u0a49\u0a17\u0a18\u0a3f\u0a28", "email": "\u0a08\u0a2e\u0a47\u0a32", "password": "\u0a2a\u0a3e\u0a38\u0a35\u0a30\u0a4d\u0a21", "btn_login": "\u0a32\u0a49\u0a17 \u0a07\u0a28 \u0a15\u0a30\u0a4b",
    "role_citizen": "\u0a28\u0a3e\u0a17\u0a30\u0a3f\u0a15", "role_officer": "\u0a05\u0a2b\u0a3c\u0a38\u0a30", "role_admin": "\u0a0f\u0a21\u0a2e\u0a3f\u0a28",
},

"ta": {
    "app_name": "\u0b9c\u0bbe\u0bb0\u0bcd\u0b95\u0bcd\u0b95\u0ba3\u0bcd\u0b9f\u0bcd \u0b9a\u0bae\u0bbe\u0ba4\u0bbe\u0ba9\u0bcd", "language": "\u0bae\u0bcb\u0bb4\u0bbf",
    "nav_home": "\u0bae\u0bc1\u0b95\u0baa\u0bcd\u0baa\u0bc1", "nav_my_complaints": "\u0b8e\u0ba9\u0ba4\u0bc1 \u0baa\u0bc1\u0b95\u0bbe\u0bb0\u0bcd\u0b95\u0bb3\u0bcd", "nav_report": "\u0baa\u0bbf\u0bb0\u0b9a\u0bcd\u0b9a\u0ba9\u0bc8\u0baa\u0bcd \u0b9a\u0bc6\u0baf\u0bcd\u0b95\u0bca\u0b99\u0bcd\u0b95\u0bb5\u0bc1\u0bae\u0bcd",
    "login_title": "\u0b89\u0bb3\u0bcd\u0ba9\u0bc1\u0bb3\u0bc8\u0baf", "email": "\u0bae\u0bbf\u0ba9\u0bcd\u0ba9\u0b9e\u0bcd\u0b9a\u0bb2\u0bcd", "password": "\u0b95\u0b9f\u0bb5\u0bc1\u0b9a\u0bcd\u0b9a\u0bcb\u0bb2\u0bcd", "btn_login": "\u0b89\u0bb3\u0bcd\u0ba9\u0bc1\u0bb3\u0bc8\u0b95",
    "role_citizen": "\u0b95\u0bc1\u0b9f\u0bbf\u0bae\u0b95\u0ba9\u0bcd", "role_officer": "\u0b85\u0ba4\u0bbf\u0b95\u0bbe\u0bb0\u0bbf", "role_admin": "\u0ba8\u0bbf\u0bb0\u0bcd\u0bb5\u0bbe\u0b9a\u0b95\u0bbf",
},

"te": {
    "app_name": "\u0c1d\u0c3e\u0c30\u0c4d\u0c16\u0c02\u0c21\u0c4d \u0c38\u0c2e\u0c3e\u0c27\u0c3e\u0c28\u0c4d", "language": "\u0c2d\u0c3e\u0c37",
    "nav_home": "\u0c39\u0c4b\u0c2e\u0c4d", "nav_my_complaints": "\u0c28\u0c3e \u0c2b\u0c3f\u0c30\u0c4d\u0c2f\u0c3e\u0c26\u0c41\u0c32\u0c41", "nav_report": "\u0c38\u0c2e\u0c38\u0c4d\u0c2f\u0c3e\u0c28\u0c41 \u0c28\u0c3f\u0c35\u0c47\u0c26\u0c3f\u0c02\u0c1a\u0c02\u0c21\u0c3f",
    "login_title": "\u0c32\u0c3e\u0c17\u0c3f\u0c28\u0c4d", "email": "\u0c07\u0c2e\u0c46\u0c2f\u0c3f\u0c32\u0c4d", "password": "\u0c2a\u0c3e\u0c38\u0c4d\u200c\u0c35\u0c30\u0c4d\u0c21\u0c4d", "btn_login": "\u0c32\u0c3e\u0c17\u0c3f\u0c28\u0c4d \u0c1a\u0c47\u0c2f\u0c02\u0c21\u0c3f",
    "role_citizen": "\u0c2a\u0c4c\u0c30\u0c41\u0c21\u0c41", "role_officer": "\u0c05\u0c27\u0c3f\u0c15\u0c3e\u0c30\u0c3f", "role_admin": "\u0c05\u0c21\u0c4d\u0c2e\u0c3f\u0c28\u0c4d",
},

"kn": {
    "app_name": "\u0c9d\u0cbe\u0cb0\u0ccd\u0c96\u0c82\u0ca1\u0ccd \u0cb8\u0cae\u0cbe\u0ca7\u0cbe\u0ca8\u0ccd", "language": "\u0cad\u0cbe\u0cb7\u0cc6",
    "nav_home": "\u0cae\u0cc1\u0c96\u0caa\u0cc1\u0c9f", "nav_my_complaints": "\u0ca8\u0ca8\u0ccd \u0ca6\u0cc2\u0cb0\u0cc1\u0c97\u0eb3\u0cc1", "nav_report": "\u0cb8\u0cae\u0cb8\u0ccd\u0caf\u0cc6 \u0cb5\u0cb0\u0ca6\u0cbf \u0cae\u0cbe\u0c9f\u0cbf",
    "login_title": "\u0cb2\u0cbe\u0c97\u0cbf\u0ca8\u0ccd", "email": "\u0c87\u0cae\u0cc7\u0cb2\u0ccd", "password": "\u0caa\u0cbe\u0cb8\u0ccd\u200c\u0cb5\u0cb0\u0ccd\u0ca1\u0ccd", "btn_login": "\u0cb2\u0cbe\u0c97\u0cbf\u0ca8\u0ccd \u0cae\u0cbe\u0c91\u0cb2\u0cbf",
    "role_citizen": "\u0ca8\u0cbe\u0c97\u0cb0\u0cbf\u0c95", "role_officer": "\u0c85\u0ca7\u0cbf\u0c95\u0cbe\u0cb0\u0cbf", "role_admin": "\u0ca8\u0cbf\u0cb0\u0ccd\u0cb5\u0cbe\u0cb9\u0c95",
},

"ml": {
    "app_name": "\u0d1d\u0d3e\u0d7c\u0d16\u0d23\u0d4d\u0d21\u0d4d \u0d38\u0d2e\u0d3e\u0d27\u0d3e\u0d28\u0d4d", "language": "\u0d2d\u0d3e\u0d37",
    "nav_home": "\u0d39\u0d4b\u0d2e\u0d4d", "nav_my_complaints": "\u0d0e\u0d23\u0d4d\u0d1f\u0d46 \u0d2a\u0d30\u0d3e\u0d24\u0d3f\u0d15\u0d3e\u0d33\u0d4d", "nav_report": "\u0d2a\u0d4d\u0d30\u0d36\u0d4d\u0d28\u0d02 \u0d31\u0d3f\u0d2a\u0d4b\u0d30\u0d4d\u0d1f\u0d4d \u0d1a\u0d46\u0d2f\u0d4d\u0d2f\u0d41\u0d15",
    "login_title": "\u0d32\u0d4b\u0d17\u0d3f\u0d28\u0d4d", "email": "\u0d07\u0d2e\u0d48\u0d32\u0d4d", "password": "\u0d2a\u0d3e\u0d38\u0d4d\u200c\u0d35\u0d47\u0d21\u0d4d", "btn_login": "\u0d32\u0d4b\u0d17\u0d3f\u0d28\u0d4d \u0d1a\u0d46\u0d2f\u0d4d\u0d2f\u0d41\u0d15",
    "role_citizen": "\u0d2a\u0d4d\u0d17\u0d30\u0d28\u0d4d", "role_officer": "\u0d13\u0d2b\u0d40\u0d38\u0d30\u0d4d", "role_admin": "\u0d05\u0d21\u0d4d\u0d2e\u0d3f\u0d28\u0d4d",
},

"ur": {
    "app_name": "\u062c\u06be\u0627\u0631\u06a9\u06be\u0646\u0689 \u0633\u0645\u0627\u062f\u06be\u0627\u0646", "language": "\u0632\u0628\u0627\u0646",
    "nav_home": "\u06c1\u0648\u0645", "nav_my_complaints": "\u0645\u06cc\u0631\u06cc \u0634\u06a9\u0627\u064a\u0627\u062a", "nav_report": "\u0645\u0633\u0626\u0644\u06c9 \u062f\u0631\u062c \u06a9\u0631\u06cc\u0646",
    "login_title": "\u0644\u0627\u06af \u0627\u0646", "email": "\u0627\u06cc \u0645\u06cc\u0644", "password": "\u067e\u0627\u0633 \u0648\u0631\u0688", "btn_login": "\u0644\u0627\u06af \u0627\u0646 \u06a9\u0631\u06cc\u0646",
    "role_citizen": "\u0634\u0647\u0631\u06cc", "role_officer": "\u0627\u0641\u0633\u0631", "role_admin": "\u0627\u06cc\u0688\u0645\u0646",
},

"as": {
    "app_name": "\u099d\u09be\u09b0\u0996\u09a3\u09cd\u09a1 \u09b8\u09ae\u09be\u09a7\u09be\u09a8", "language": "\u09ad\u09be\u09b7\u09be",
    "nav_home": "\u09b9\u09cb\u09ae", "nav_my_complaints": "\u09ae\u09cb\u09b0 \u0985\u09ad\u09bf\u09af\u09cb\u0997", "nav_report": "\u09b8\u09ae\u09b8\u09cd\u09af\u09be \u09aa\u09cd\u09b0\u09a4\u09bf\u09ac\u09c7\u09a6\u09a8 \u0995\u09b0\u0995",
    "login_title": "\u09b2\u0997\u0987\u09a8", "email": "\u0987\u09ae\u09c7\u0987\u09b2", "password": "\u09aa\u09be\u099a\u09c1\u0993\u09b0\u09cd\u09a1", "btn_login": "\u09b2\u0997 \u0987\u09a8 \u0995\u09b0\u0995",
    "role_citizen": "\u09a8\u09be\u0997\u09b0\u09bf\u0995", "role_officer": "\u09ac\u09bf\u09b7\u09df\u09be", "role_admin": "\u09aa\u09cd\u09b0\u09be\u09b6\u09be\u09b8\u0995",
},

}


# ---------------------------------------------------------------------------
# category / district canonical-value -> translation-key maps
# ---------------------------------------------------------------------------

CATEGORY_KEYS = {
    "Roads & Infrastructure": "cat_roads",
    "Water Resources": "cat_water",
    "Electricity": "cat_electricity",
    "Sanitation": "cat_sanitation",
    "Healthcare": "cat_health",
    "Education": "cat_education",
    "Public Safety": "cat_safety",
    "Other": "cat_other",
}

DISTRICT_KEYS = {
    "Ranchi": "dist_ranchi", "Dhanbad": "dist_dhanbad", "Dumka": "dist_dumka",
    "Bokaro": "dist_bokaro", "Gumla": "dist_gumla", "Deoghar": "dist_deoghar",
    "Hazaribagh": "dist_hazaribagh", "Giridih": "dist_giridih",
    "East Singhbhum": "dist_east_singhbhum", "West Singhbhum": "dist_west_singhbhum",
}


# ---------------------------------------------------------------------------
# lookup with fallback chain
# ---------------------------------------------------------------------------

def _chain(lang):
    """[lang, lang's fallback, that fallback's fallback, ..., 'en']"""
    seen, code, out = set(), lang, []
    while code and code not in seen:
        out.append(code)
        seen.add(code)
        code = LANGUAGE_META.get(code, {}).get("fallback")
    if "en" not in out:
        out.append("en")
    return out


def current_lang():
    return getattr(g, "lang", DEFAULT_LANG)


def t(key, **kwargs):
    for code in _chain(current_lang()):
        val = TR.get(code, {}).get(key)
        if val is not None:
            return val.format(**kwargs) if kwargs else val
    return key  # last resort — only hit for a genuinely undefined key (a bug)


def cat_label(category):
    return t(CATEGORY_KEYS.get(category, "cat_other"))


def dist_label(district):
    key = DISTRICT_KEYS.get(district)
    return t(key) if key else district
