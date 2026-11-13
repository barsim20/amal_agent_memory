"""
Embeddings (halfvec 1024), 'simple' un-stemmed FTS tokenization, and pg_trgm similarity
for English, Kiswahili, and code-switched teacher memories.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Sequence

import numpy as np
from django.conf import settings


# Bilingual (English <-> Kiswahili) semantic concept anchors mapped into shared latent dimensions
BILINGUAL_CONCEPT_CLUSTERS: dict[str, tuple[int, list[str]]] = {
    "profile_school": (
        0,
        ["school", "primary", "secondary", "public", "kisumu", "nairobi", "kigali", "rwanda", "kenya", "shule", "msingi", "sekondari", "umma"],
    ),
    "profile_role": (
        16,
        ["head", "deputy", "senior", "teacher", "mentor", "patron", "mwalimu", "mkuu", "naibu", "mshauri"],
    ),
    "teaching_grades": (
        32,
        ["grade", "class", "standard", "form", "pp1", "pp2", "darasa", "gredi", "kidato"],
    ),
    "teaching_math_science": (
        48,
        ["math", "maths", "mathematics", "science", "algebra", "fractions", "geometry", "biology", "physics", "chemistry", "hisabati", "sayansi", "sehemu"],
    ),
    "teaching_languages": (
        64,
        ["english", "kiswahili", "swahili", "kinyarwanda", "french", "literacy", "reading", "kiingereza", "kusoma", "lugha"],
    ),
    "teaching_curriculum": (
        80,
        ["cbc", "competency", "curriculum", "reb", "knec", "syllabus", "mtaala", "umilisi"],
    ),
    "teaching_class_size": (
        96,
        ["learners", "students", "pupils", "class size", "large class", "crowded", "wanafunzi", "idadi", "watoto"],
    ),
    "classroom_resources": (
        112,
        ["projector", "textbook", "textbooks", "chalkboard", "blackboard", "electricity", "internet", "laptop", "manila", "vitabu", "ubao", "umeme", "rasilimali", "vifaa"],
    ),
    "practice_strategies": (
        128,
        ["group work", "peer assessment", "think-pair-share", "questioning", "scaffolding", "differentiation", "role play", "vikundi", "tathmini", "maswali", "mbinu"],
    ),
    "learning_journey": (
        144,
        ["course", "module", "certificate", "completed", "academy", "simulation", "foundations", "kozi", "moduli", "cheti", "amehitimu"],
    ),
    "ongoing_work": (
        160,
        ["scheme of work", "lesson plan", "term", "exam", "assessment", "preparing", "deadline", "azimio", "mpango", "muhula", "mtihani"],
    ),
    "people_colleagues": (
        176,
        ["colleague", "co-plan", "co-plans", "co-teaching", "department", "head teacher", "principal", "mwenzangu", "wenzake", "wanapanga"],
    ),
    "preferences_response": (
        192,
        ["prefers", "short", "concise", "bullet", "bullets", "step-by-step", "kiswahili", "english", "table", "anapendelea", "fupi", "orodha", "hatua"],
    ),
    "wellbeing_stress": (
        208,
        ["overwhelmed", "stress", "stressed", "tired", "burnout", "marking load", "workload", "exhausted", "msongo", "amechoka", "mzigo", "kuzidiwa"],
    ),
    "named_learners": (
        224,
        ["learner", "needs support", "struggles with", "dyslexia", "hearing", "vision", "attendance", "mwanafunzi", "msaada"],
    ),
    "life_area_masters": (
        240,
        ["master's", "masters", "degree", "university", "thesis", "postgraduate", "research", "med", "dissertation", "semester", "coursework", "shahada", "uzamili", "chuo kikuu", "utafiti"],
    ),
    "life_area_football": (
        272,
        ["football", "soccer", "coaching", "coach", "tournament", "team", "athletics", "sports", "training", "match", "mpira", "miguu", "kocha", "michezo", "mashindano"],
    ),
    "life_area_agriculture": (
        304,
        ["school garden", "farming", "agriculture", "poultry", "maize", "crops", "irrigation", "agribusiness", "kilimo", "bustani", "kuku", "mahindi"],
    ),
    "life_area_drama_music": (
        336,
        ["drama festival", "choir", "music", "theatre", "rehearsal", "performance", "script", "poetry", "tamasha", "igizo", "kwaya", "muziki"],
    ),
}

WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


def simple_tokenize(text: str) -> list[str]:
    """
    Tokenize text using Postgres 'simple' dictionary semantics:
    lowercased words without language-specific stemming so Kiswahili and code-switched tokens remain intact.
    """
    if not text:
        return []
    return [tok.lower() for tok in WORD_RE.findall(text.lower()) if len(tok) > 1 or tok.isdigit()]


def char_trigrams(text: str) -> set[str]:
    """
    Generate pg_trgm-style character trigrams (padded with two leading spaces and one trailing space per word).
    """
    tokens = simple_tokenize(text)
    trigrams: set[str] = set()
    for token in tokens:
        padded = f"  {token} "
        for idx in range(len(padded) - 2):
            trigrams.add(padded[idx : idx + 3])
    return trigrams


def trigram_similarity(text_a: str, text_b: str) -> float:
    """Compute pg_trgm similarity between two strings."""
    tri_a = char_trigrams(text_a)
    tri_b = char_trigrams(text_b)
    if not tri_a or not tri_b:
        return 0.0
    intersection = len(tri_a & tri_b)
    union = len(tri_a | tri_b)
    return float(intersection / union) if union else 0.0


def fulltext_simple_score(query: str, document: str) -> float:
    """
    Compute un-stemmed 'simple' full-text overlap score (ts_rank_cd equivalent).
    Supports prefix matching on tokens >= 4 chars for Kiswahili agglutinative morphology.
    """
    q_tokens = simple_tokenize(query)
    d_tokens = simple_tokenize(document)
    if not q_tokens or not d_tokens:
        return 0.0
    d_set = set(d_tokens)
    matched = 0.0
    for qt in q_tokens:
        if qt in d_set:
            matched += 1.0
        elif len(qt) >= 4:
            # Prefix/root match for Swahili verb/noun inflections
            if any(dt.startswith(qt[:4]) or qt.startswith(dt[:4]) for dt in d_set if len(dt) >= 4):
                matched += 0.65
    return matched / len(q_tokens)


def embed_text(text: str, dim: int | None = None) -> list[float]:
    """
    Produce a deterministic 1024-dim halfvec (float16 quantized) unit-normalized embedding.
    Combines bilingual semantic concept anchors (EN + SW) with hashed token and character-trigram projections.
    """
    target_dim = dim or getattr(settings, "AMAL_EMBED_DIM", 1024)
    vec = np.zeros(target_dim, dtype=np.float32)
    if not text or not text.strip():
        return vec.tolist()

    lowered = text.lower()
    tokens = simple_tokenize(lowered)

    # 1. Bilingual concept projection (dims 0..383)
    for cluster_name, (offset, keywords) in BILINGUAL_CONCEPT_CLUSTERS.items():
        hits = 0.0
        for kw in keywords:
            if " " in kw:
                if kw in lowered:
                    hits += 1.5
            elif kw in tokens:
                hits += 1.0
            elif len(kw) >= 5 and any(t.startswith(kw[:5]) for t in tokens):
                hits += 0.7
        if hits > 0 and offset + 16 <= target_dim:
            cluster_scale = 2.4 if cluster_name.startswith("life_area_") else 1.0
            for j in range(16):
                phase = (j + 1) * 0.37
                vec[offset + j] += float(hits * cluster_scale * math.cos(phase))

    # 2. Un-stemmed word token projection across full space
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
        for idx in range(0, 16, 4):
            bucket = int.from_bytes(digest[idx : idx + 2], "little") % target_dim
            sign = 1.0 if (digest[idx + 2] & 1) == 0 else -1.0
            weight = 0.35 + ((digest[idx + 3] % 100) / 200.0)
            vec[bucket] += sign * weight

    # 3. Character trigram projection for morphological & typo resilience
    for tri in char_trigrams(lowered):
        digest = hashlib.blake2b(tri.encode("utf-8"), digest_size=4).digest()
        bucket = int.from_bytes(digest[:2], "little") % target_dim
        sign = 1.0 if (digest[2] & 1) == 0 else -1.0
        vec[bucket] += sign * 0.12

    # Normalize and quantize to float16 (halfvec) precision
    norm = float(np.linalg.norm(vec))
    if norm > 1e-8:
        vec = vec / norm
    halfvec = vec.astype(np.float16).astype(np.float32)
    return [round(float(x), 6) for x in halfvec.tolist()]


def cosine_similarity(vec_a: Sequence[float] | None, vec_b: Sequence[float] | None) -> float:
    """Compute exact cosine similarity between two embedding vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    a = np.asarray(vec_a, dtype=np.float32)
    b = np.asarray(vec_b, dtype=np.float32)
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a < 1e-8 or norm_b < 1e-8:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def compute_centroid(vectors: Sequence[Sequence[float]]) -> list[float]:
    """Compute unit-normalized halfvec centroid of a list of embeddings."""
    valid = [v for v in vectors if v]
    if not valid:
        return []
    arr = np.asarray(valid, dtype=np.float32)
    mean_vec = np.mean(arr, axis=0)
    norm = float(np.linalg.norm(mean_vec))
    if norm > 1e-8:
        mean_vec = mean_vec / norm
    halfvec = mean_vec.astype(np.float16).astype(np.float32)
    return [round(float(x), 6) for x in halfvec.tolist()]
