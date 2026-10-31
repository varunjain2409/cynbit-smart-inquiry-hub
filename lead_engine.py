"""
Cynbit Smart Inquiry Hub — Lead Qualification Engine

Two layers:
  1. score_lead()    — deterministic rule-based scoring (0-100) + tier + next step.
  2. intelligence()  — "Project Intelligence" preview. Uses OpenAI (GPT-4o mini)
                       when OPENAI_API_KEY is set; otherwise a grounded,
                       rule-based summary so the demo never depends on paid APIs.

Design principles:
  - Never fail the funnel because an optional LLM is unavailable.
  - Everything is explainable to the sales reviewer (rules, not a black box).
"""
import os
from openai import OpenAI

# ---------------------------------------------------------------- scoring ---

SERVICE_KEYWORDS = {
    "AI Automation": ["ai", "agent", "chatbot", "llm", "automation", "intelligent", "voice"],
    "Software Development": ["app", "website", "web", "mobile", "platform", "saas", "software", "dashboard"],
    "Cloud & Infrastructure": ["cloud", "aws", "azure", "devops", "migration", "infrastructure", "deploy", "kubernetes"],
    "Marketing & SEO": ["seo", "marketing", "ads", "leads", "growth", "funnel", "ranking"],
}

BUDGET_POINTS = {
    "Under ₹50k": 8,
    "₹50k – ₹2L": 16,
    "₹2L – ₹10L": 26,
    "₹10L+": 34,
    "Not sure yet": 6,
}

TIMELINE_POINTS = {
    "ASAP / this month": 24,
    "1–3 months": 16,
    "3–6 months": 8,
    "Just exploring": 3,
}


def _service_fit(service: str, message: str) -> tuple[int, str]:
    """Score how well the declared service matches the message content."""
    base = {"Under ₹50k": 0}.get(service, 0)  # placeholder to satisfy lints
    kw = SERVICE_KEYWORDS.get(service, [])
    text = (service + " " + message).lower()
    hits = sum(1 for k in kw if k in text)
    pts = 10 if hits >= 3 else (7 if hits >= 2 else (4 if hits == 1 else 0))
    return pts, "service keyword match: %d/4" % hits


def score_lead(data: dict) -> tuple[int, str, str, str]:
    """
    Returns (score_0_100, tier, next_step, debug_signals).
    Signals are combined into one string for full explainability.
    """
    signals = []
    score = 20  # baseline: a real human submitted the form

    # Detail in the brief
    words = len((data.get("message") or "").split())
    if words > 120:
        score += 14
        signals.append("detailed brief (%d words) +14" % words)
    elif words > 45:
        score += 9
        signals.append("solid brief (%d words) +9" % words)
    else:
        score += 2
        signals.append("brief brief (%d words) +2" % words)

    # Budget band
    b = data.get("budget") or "Not sure yet"
    score += BUDGET_POINTS.get(b, 6)
    signals.append("budget '%s' +%d" % (b, BUDGET_POINTS.get(b, 6)))

    # Timeline urgency
    t = data.get("timeline") or "Just exploring"
    score += TIMELINE_POINTS.get(t, 3)
    signals.append("timeline '%s' +%d" % (t, TIMELINE_POINTS.get(t, 3)))

    # Business email vs personal inbox
    email = (data.get("email") or "").lower()
    domain = email.split("@")[-1] if "@" in email else ""
    free_domains = ("gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "rediffmail.com")
    if domain and domain not in free_domains:
        score += 10
        signals.append("business domain +10")
    else:
        score += 3
        signals.append("personal inbox +3")

    # Company & industry provided
    if (data.get("company") or "").strip():
        score += 6
        signals.append("company given +6")
    if (data.get("industry") or "").strip():
        score += 4
        signals.append("industry given +4")

    # Service fit
    fit_pts, fit_sig = _service_fit(data.get("service", ""), data.get("message", ""))
    score += fit_pts
    signals.append(fit_sig)

    score = max(0, min(100, score))

    if score >= 70:
        tier, next_step = "Hot", "Priority discovery call within 24h (matches their SLA)"
    elif score >= 45:
        tier, next_step = "Warm", "Nurture sequence + offer a 15-min scoping call this week"
    else:
        tier, next_step = "Exploring", "Add to newsletter + BitElevate resource drip"

    return score, tier, next_step, "; ".join(signals)


# -------------------------------------------------------- intelligence -------

_TEMPLATES = {
    "AI Automation": (
        "Autonomous agent & cognitive-automation track. Discovery would map the "
        "targeted workflows, data sources and guardrails, then blueprint an "
        "LLM-agent stack (LangChain-class tooling) with human-in-the-loop checks."
    ),
    "Software Development": (
        "Custom software penetration. Discovery would audit user journeys and "
        "data model, then blueprint a scalable web/mobile platform with "
        "enterprise-grade backend foundations."
    ),
    "Cloud & Infrastructure": (
        "Zero-trust infrastructure track. Discovery would audit current hosting, "
        "costs and failure points, then blueprint an AWS/Azure migration plan "
        "targeting 99.9% uptime."
    ),
    "Marketing & SEO": (
        "ROI-engine track. Discovery would audit traffic, funnel leak points and "
        "technical SEO health, then blueprint a data-driven growth roadmap."
    ),
}


def _openai_overview(data: dict) -> str:
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "")) \
        if os.environ.get("OPENAI_API_KEY") else None
    if client is None:
        return None
    prompt = (
        "You are the intake analyst at Cynbit Technologies (Jaipur). A visitor "
        "submitted an inquiry. Write a 2-3 sentence 'Project Intelligence' "
        "strategic overview: what they likely need, which Cynbit service line "
        "fits, and the first discovery-phase focus. Keywords: {service}, "
        "industry: {industry}, budget: {budget}, timeline: {timeline}, brief: {message}".format(
            service=data.get("service"), industry=data.get("industry") or "unspecified",
            budget=data.get("budget"), timeline=data.get("timeline"),
            message=(data.get("message") or "")[:400],
        )
    )
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=140,
            temperature=0.4,
        )
        return r.choices[0].message.content.strip()
    except Exception:
        return None


def intelligence(data: dict, score: int, tier: str) -> tuple[str, str]:
    """
    Returns (intelligence_text, summary_type) where summary_type is
    'gpt-4o-mini' or 'rule-engine' (graceful degradation, always available).
    """
    ai = _openai_overview(data)
    if ai:
        return ai, "gpt-4o-mini"

    service = data.get("service") if data.get("service") in _TEMPLATES else \
        ("Software Development" if data.get("service") == "Other" else data.get("service"))
    base = _TEMPLATES.get(service, _TEMPLATES["Software Development"])
    industry = (data.get("industry") or "").strip()
    budget = data.get("budget") or "Not sure yet"
    timeline = data.get("timeline") or "Just exploring"

    text = (
        "{base} Fit level: {tier} ({score}/100). Scope signals: budget band "
        "'{budget}', timeline '{timeline}'{ind}. Recommended next step: align a "
        "discovery call with the right service-team lead on the timeline above."
        .format(base=base, tier=tier, score=score, budget=budget, timeline=timeline,
                ind=(" in %s" % industry) if industry else "")
    )
    return text, "rule-engine"
