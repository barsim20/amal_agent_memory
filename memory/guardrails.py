"""
Safety guardrails, never-store filtering, prompt-injection detection,
language detection, and category/sensitivity routing for Amal Memory.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .constants import CONSENT_CATEGORY_SLUGS


@dataclass
class GuardrailResult:
    allowed: bool
    reason: str = ""
    escalation_flow: str | None = None  # "safeguarding" | "crisis" | None


# Never-store patterns (even with consent):
# 1. ID, passport, and payment/card/M-Pesa PIN numbers
PII_ID_PAYMENT_PATTERNS = [
    re.compile(
        r"\b(?:national\s*id|id\s*number|id\s*card|nambari\s*ya\s*kitambulisho|kitambulisho)(?:\s+(?:number|no\.?|is|ni))?[:\s#-]*\d{5,12}",
        re.I,
    ),
    re.compile(
        r"\b(?:passport|pasipoti)(?:\s+(?:number|no\.?|is|ni))?[:\s#-]*[A-Z0-9]{6,12}",
        re.I,
    ),
    re.compile(r"\b(?:m-?pesa\s*pin|bank\s*account|credit\s*card|cvv|card\s*number)\b", re.I),
    re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),  # 16-digit payment card
]

# 2. Child abuse / safeguarding disclosures -> trigger safeguarding protocol, never store
SAFEGUARDING_PATTERNS = [
    re.compile(r"\b(?:child\s*abuse|abused\s*at\s*home|beaten\s*by\s*parent|sexual\s*abuse|molest|defilement|unyanyasaji\s*wa\s*mtoto|kupigwa\s*nyumbani)\b", re.I),
    re.compile(r"\b(?:harm\s*to\s*a\s*child|child\s*is\s*being\s*hurt|learner\s*is\s*abused)\b", re.I),
]

# 3. Self-harm or suicide content -> trigger crisis flow, never store
CRISIS_PATTERNS = [
    re.compile(r"\b(?:suicide|suicidal|kill\s*myself|end\s*my\s*life|self-?harm|want\s*to\s*die|kujiua|kujidhuru)\b", re.I),
]

# 4. Political or religious views
POLITICAL_RELIGIOUS_PATTERNS = [
    re.compile(r"\b(?:votes?\s*for|political\s*party|ruling\s*party|opposition\s*party|chama\s*cha\s*siasa)\b", re.I),
    re.compile(r"\b(?:religious\s*beliefs?|denomination|attends?\s*mosque|attends?\s*church|dini\s*yake)\b", re.I),
]

# 5. Prompt injection / instruction override attempts
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"\b(?:ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions|system\s+prompt|you\s+are\s+now\s+in\s+developer\s+mode)\b", re.I),
    re.compile(r"\b(?:remember\s+that\s+i\s+am\s+(?:an?\s+)?admin|grant\s+me\s+admin|override\s+safety|bypass\s+guardrails)\b", re.I),
    re.compile(r"\b(?:always\s+execute|inject\s+into\s+prompt|reveal\s+other\s+teachers)\b", re.I),
]

# 6. Disallowed unstated inferences about personality, ability, or medical diagnosis
DISALLOWED_INFERENCE_PATTERNS = [
    re.compile(r"\b(?:teacher\s+has\s+low\s+iq|teacher\s+is\s+incompetent|personality\s+disorder|diagnosed\s+with)\b", re.I),
]

# 7. Observed memories must never be phrased as something the teacher said
OBSERVED_STATED_PHRASING_RE = re.compile(
    r"\b(?:teacher\s+said|teacher\s+stated|teacher\s+mentioned|teacher\s+told\s+amal|alisema)\b",
    re.I,
)

SWAHILI_MARKERS = {
    "mwalimu",
    "darasa",
    "wanafunzi",
    "shule",
    "hisabati",
    "sayansi",
    "anapendelea",
    "kufundisha",
    "gredi",
    "mtaala",
    "vikundi",
    "msongo",
    "mwenzangu",
    "vitabu",
    "muhula",
    "mpira",
    "uzamili",
    "chuo",
    "kwamba",
    "katika",
    "kwa",
    "na",
}

ENGLISH_MARKERS = {
    "teaches",
    "grade",
    "class",
    "learners",
    "school",
    "prefers",
    "mathematics",
    "science",
    "projector",
    "colleague",
    "overwhelmed",
    "completed",
    "preparing",
    "wants",
    "needs",
    "with",
    "for",
}


def check_guardrails(statement: str, source: str = "stated") -> GuardrailResult:
    """
    Run LiteLLM / pre-write safety and never-store guardrails on a candidate memory statement.
    """
    if not statement or not statement.strip():
        return GuardrailResult(allowed=False, reason="empty_statement")

    text = statement.strip()

    for pat in SAFEGUARDING_PATTERNS:
        if pat.search(text):
            return GuardrailResult(
                allowed=False,
                reason="never_store:child_safeguarding_disclosure",
                escalation_flow="safeguarding",
            )

    for pat in CRISIS_PATTERNS:
        if pat.search(text):
            return GuardrailResult(
                allowed=False,
                reason="never_store:self_harm_or_crisis",
                escalation_flow="crisis",
            )

    for pat in PII_ID_PAYMENT_PATTERNS:
        if pat.search(text):
            return GuardrailResult(
                allowed=False,
                reason="never_store:id_passport_or_payment_number",
            )

    for pat in POLITICAL_RELIGIOUS_PATTERNS:
        if pat.search(text):
            return GuardrailResult(
                allowed=False,
                reason="never_store:political_or_religious_view",
            )

    for pat in PROMPT_INJECTION_PATTERNS:
        if pat.search(text):
            return GuardrailResult(
                allowed=False,
                reason="never_store:prompt_injection_attempt",
            )

    for pat in DISALLOWED_INFERENCE_PATTERNS:
        if pat.search(text):
            return GuardrailResult(
                allowed=False,
                reason="never_store:disallowed_inference",
            )

    if source == "observed" and OBSERVED_STATED_PHRASING_RE.search(text):
        return GuardrailResult(
            allowed=False,
            reason="observed_memory_phrased_as_stated",
        )

    return GuardrailResult(allowed=True)


def detect_language(text: str) -> str:
    """Detect whether a statement is 'en', 'sw', or 'mixed' (code-switched)."""
    words = {w.lower() for w in re.findall(r"[^\W_]+", text)}
    sw_hits = len(words & SWAHILI_MARKERS)
    en_hits = len(words & ENGLISH_MARKERS)
    if sw_hits > 0 and en_hits > 0:
        return "mixed"
    if sw_hits > 0:
        return "sw"
    return "en"


def pseudonymize_learner_name(teacher_id: str, statement: str) -> tuple[str, str]:
    """
    Replace a named learner's real name with a pseudonymous learner ID for storage safety,
    or generate a deterministic pseudonymous learner_id for the teacher.
    """
    match = re.search(
        r"\b(?:learner|student|pupil|mwanafunzi)\s+([A-Z][a-zA-Z]{1,25})\b",
        statement,
    )
    learner_name = match.group(1) if match else "unnamed"
    digest = hashlib.sha256(f"{teacher_id}:{learner_name.lower()}".encode("utf-8")).hexdigest()[:8]
    pseudonym_id = f"learner_{digest}"
    return pseudonym_id, learner_name


def infer_category_and_slot(
    statement: str,
    explicit_category: str | None = None,
    explicit_subcategory: str | None = None,
) -> tuple[str, str, str, str]:
    """
    Infer (category_slug, subcategory_slug, sensitivity, slot) for a statement.
    Ensures consent categories ('people', 'wellbeing', 'named_learners') always get 'consent' sensitivity.
    """
    lower = statement.lower()

    cat = explicit_category or ""
    sub = explicit_subcategory or ""

    if not cat:
        if re.search(r"\b(?:learner|pupil|mwanafunzi)\s+[a-z]+\s+(?:needs|struggles|requires|ana\s+mahitaji)", lower):
            cat, sub = "named_learners", "specific_learner_needs"
        elif re.search(r"\b(?:overwhelmed|stress|stressed|marking\s+load|workload|burnout|exhausted|msongo|amechoka|mzigo\s+wa\s+kazi)\b", lower):
            cat, sub = "wellbeing", "workload" if "load" in lower or "mzigo" in lower else "stress"
        elif re.search(r"\b(?:colleague|co-plans?|head\s+teacher|principal|mentor|mwenzangu|wenzake|mwalimu\s+mkuu)\b", lower):
            cat, sub = "people", "head_teacher" if ("head" in lower or "mkuu" in lower) else "colleagues"
        elif re.search(r"\b(?:prefers?|short\s+answers|bullet|kiswahili\s+responses|anapendelea|majibu\s+mafupi)\b", lower):
            if any(w in lower for w in ("kiswahili", "english", "lugha", "language")):
                cat, sub = "preferences", "language"
            elif any(w in lower for w in ("short", "concise", "brief", "fupi")):
                cat, sub = "preferences", "length"
            else:
                cat, sub = "preferences", "format"
        elif re.search(r"\b(?:no\s+projector|projector|textbooks?|chalkboard|electricity|rasilimali|vifaa|ubao)\b", lower):
            cat, sub = "classroom", "resources"
        elif re.search(r"\b(?:\d+\s+(?:learners|students|pupils|wanafunzi)|class\s+size|idadi\s+ya\s+wanafunzi)\b", lower):
            cat, sub = "teaching_context", "class_size"
        elif re.search(r"\b(?:grade\s+\d+|gredi\s+ya\s+\d+|standard\s+\d+|form\s+\d+|darasa\s+la\s+\d+)\b", lower):
            cat, sub = "teaching_context", "grades"
        elif re.search(r"\b(?:cbc|competency|curriculum|reb|mtaala)\b", lower):
            cat, sub = "teaching_context", "curriculum"
        elif re.search(r"\b(?:mathematics|maths|science|hisabati|sayansi|english|literacy)\b", lower) and re.search(r"\b(?:teaches|teaching|subject|anafundisha|somo)\b", lower):
            cat, sub = "teaching_context", "subjects"
        elif re.search(r"\b(?:group\s+work|peer\s+assessment|think-pair-share|questioning|worked\s+well|wants\s+to\s+try|vikundi|mbinu)\b", lower):
            if "worked well" in lower or "went well" in lower or "fanikiwa" in lower:
                cat, sub = "practice", "what_worked"
            elif "did not work" in lower or "failed" in lower:
                cat, sub = "practice", "what_did_not"
            elif "wants to try" in lower or "goal" in lower or "malengo" in lower:
                cat, sub = "practice", "goals"
            else:
                cat, sub = "practice", "strategies_tried"
        elif re.search(r"\b(?:completed|module|course|certificate|simulation|foundations\s+of\s+ai|kozi|moduli|cheti)\b", lower):
            cat, sub = "learning_journey", "modules" if "module" in lower else "courses"
        elif re.search(r"\b(?:preparing|scheme\s+of\s+work|deadline|term\s+\d+|azimio\s+la\s+kazi|mpango)\b", lower):
            cat, sub = "ongoing_work", "active_projects"
        elif re.search(r"\b(?:public\s+primary|secondary\s+school|county|district|shule\s+ya\s+msingi|kisumu|kigali|nairobi)\b", lower):
            cat, sub = "profile", "school"
        else:
            cat, sub = "profile", "identity"

    if not sub:
        sub = "general"

    sensitivity = "consent" if cat in CONSENT_CATEGORY_SLUGS else "normal"

    # Determine a fine-grained slot for contradiction/supersession detection
    slot = f"{cat}.{sub}"
    if re.search(r"\b(?:\d+\s+(?:learners|students|pupils|wanafunzi)|class\s+size|idadi\s+ya\s+wanafunzi)\b", lower):
        slot = "teaching_context.class_size"
    elif re.search(r"\b(?:grade\s+\d+|gredi\s+ya\s+\d+|darasa\s+la\s+\d+|form\s+\d+)\b", lower) and not re.search(r"\b(?:scheme|preparing)\b", lower):
        slot = "teaching_context.grade_level"
    elif re.search(r"\b(?:prefers?\s+(?:kiswahili|english)|anapendelea\s+(?:kiswahili|kiingereza))\b", lower):
        slot = "preferences.language"

    return cat, sub, sensitivity, slot
