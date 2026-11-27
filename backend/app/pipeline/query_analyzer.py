"""
Deterministic Query Understanding & Multilingual Concept Engine for ELORA.

Extracts structured search signals without expensive LLM calls:
  - Main subject, important keywords, multilingual tokens
  - Named entities, products, and versions (e.g., "GTA 6", "Python 3.13", "Windows 11", "GPT-6")
  - Search intent (news, academic, technical, tutorial, discussion, historical, comparison, books_datasets, general)
  - Time constraints (recent, historical, any)
  - Language detection (en, fr, ar, etc.)
  - Cross-lingual concept expansions (EN <-> FR <-> AR) preserving identifiers & versions
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from app.core.cache import query_analysis_cache

# ── Multilingual Stopwords ────────────────────────────────────────────────────
STOPWORDS: Set[str] = {
    # English
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "have", "has", "had", "not", "but", "what", "when", "where", "which", "who",
    "how", "why", "can", "could", "should", "would", "about", "into", "over",
    "after", "before", "between", "through", "during", "above", "below", "under",
    "all", "any", "both", "each", "more", "most", "other", "some", "such", "than",
    "too", "very", "just", "only", "also", "then", "now", "here", "there", "out",
    # French
    "les", "des", "une", "pour", "dans", "par", "sur", "avec", "sans", "sous",
    "est", "sont", "été", "être", "avoir", "qui", "que", "quoi", "dont", "où",
    "mais", "ou", "et", "donc", "or", "ni", "car", "ce", "cet", "cette", "ces",
    "mon", "ton", "son", "nos", "vos", "leurs", "aux", "du", "de", "la", "le", "un",
    # Arabic
    "في", "من", "إلى", "على", "عن", "مع", "هذا", "هذه", "التي", "الذي", "الذين",
    "ما", "هو", "هي", "هم", "كان", "كانت", "أن", "إن", "لا", "لم", "لن", "أو", "و",
}

# ── Cross-Lingual Concept Dictionary (EN <-> FR <-> AR) ───────────────────────
# Each tuple is a set of equivalent concepts across languages.
# Product names, versions, and technical identifiers are NEVER translated.
MULTILINGUAL_CONCEPTS: List[Dict[str, List[str]]] = [
    {
        "en": ["artificial intelligence", "ai"],
        "fr": ["intelligence artificielle", "ia"],
        "ar": ["الذكاء الاصطناعي", "ذكاء اصطناعي"],
    },
    {
        "en": ["machine learning", "ml"],
        "fr": ["apprentissage automatique", "apprentissage machine"],
        "ar": ["تعلم الآلة", "التعلم الآلي"],
    },
    {
        "en": ["deep learning"],
        "fr": ["apprentissage profond"],
        "ar": ["التعلم العميق"],
    },
    {
        "en": ["cybersecurity", "cyber security", "information security"],
        "fr": ["cybersécurité", "sécurité informatique"],
        "ar": ["الأمن السيبراني", "أمن المعلومات"],
    },
    {
        "en": ["quantum computing"],
        "fr": ["informatique quantique", "calcul quantique"],
        "ar": ["الحوسبة الكمومية", "الحوسبة الكمية"],
    },
    {
        "en": ["climate change", "global warming"],
        "fr": ["changement climatique", "réchauffement climatique"],
        "ar": ["تغير المناخ", "الاحتباس الحراري"],
    },
    {
        "en": ["data science"],
        "fr": ["science des données"],
        "ar": ["علم البيانات"],
    },
    {
        "en": ["neural network", "neural networks"],
        "fr": ["réseau de neurones", "réseaux de neurones"],
        "ar": ["الشبكات العصبية", "شبكة عصبية"],
    },
    {
        "en": ["memory management"],
        "fr": ["gestion de la mémoire", "gestion mémoire"],
        "ar": ["إدارة الذاكرة"],
    },
    {
        "en": ["release date"],
        "fr": ["date de sortie"],
        "ar": ["تاريخ الإصدار", "موعد الإصدار"],
    },
    {
        "en": ["latest news", "news"],
        "fr": ["dernières actualités", "actualités"],
        "ar": ["آخر الأخبار", "أخبار"],
    },
    {
        "en": ["research", "academic research"],
        "fr": ["recherche", "recherche scientifique"],
        "ar": ["بحث علمي", "أبحاث"],
    },
    {
        "en": ["security", "vulnerability"],
        "fr": ["sécurité", "vulnérabilité"],
        "ar": ["أمان", "ثغرة أمنية"],
    },
]

# ── Intent Signals ────────────────────────────────────────────────────────────
_INTENT_KEYWORDS: Dict[str, Set[str]] = {
    "comparison": {"vs", "versus", "compare", "comparison", "difference", "différence", "مقارنة", "أو"},
    "news": {"news", "latest", "breaking", "update", "updates", "announced", "release", "launch", "2025", "2026", "actualités", "nouvelles", "أخبار", "جديد"},
    "academic": {"paper", "papers", "study", "studies", "research", "journal", "arxiv", "doi", "survey", "citation", "recherche", "étude", "بحث", "دراسة"},
    "technical": {"api", "architecture", "memory", "kernel", "compiler", "implementation", "benchmark", "spec", "documentation", "docs", "performance", "algorithm"},
    "tutorial": {"tutorial", "guide", "how to", "howto", "walkthrough", "learn", "course", "example", "tutoriel", "دليل", "شرح"},
    "discussion": {"opinion", "opinions", "reddit", "forum", "discussion", "thoughts", "review", "reviews", "worth", "avis", "مناقشة"},
    "historical": {"history", "historical", "declassified", "archive", "foia", "cold war", "1950", "1960", "1970", "1980", "1990", "histoire", "تاريخ"},
    "books_datasets": {"book", "books", "dataset", "datasets", "corpus", "csv", "download", "repository", "livre", "كتاب", "بيانات"},
}

# Product/Entity + Version pattern: e.g. "GTA 6", "Python 3.13", "Windows 11", "iPhone 17", "GPT-6", "GPT 6", "iOS 18"
_ENTITY_VERSION_RE = re.compile(
    r"\b([A-Za-z][A-Za-z0-9+.#\-]{1,24})\s*[- ]?\s*(v?\d+(?:\.\d+){0,2})\b",
    re.IGNORECASE,
)

# Standalone version numbers like 3.13, 11, 17, 6 when paired with context
_ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF]")
_FRENCH_ACCENT_RE = re.compile(r"[àâäçéèêëîïôöùûüÿœæ]", re.IGNORECASE)
_FRENCH_MARKER_WORDS = {"le", "la", "les", "des", "une", "artificielle", "avec", "pour", "dans", "sur", "actualités", "recherche", "données", "système", "apprentissage"}


@dataclass
class EntityVersion:
    entity: str          # normalized lowercase entity base e.g. "gta", "python", "gpt"
    version: str         # normalized version string e.g. "6", "3.13", "11"
    full_phrase: str     # e.g. "gta 6", "python 3.13", "gpt-6"


@dataclass
class QueryAnalysis:
    original_query: str
    normalized_query: str
    language: str
    intent: str
    time_preference: str  # "recent", "historical", "any"
    is_comparison: bool
    entities: List[EntityVersion] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    qualifiers: List[str] = field(default_factory=list)
    multilingual_expansions: List[str] = field(default_factory=list)
    main_subject: str = ""

    def to_dict(self) -> Dict:
        return {
            "original_query": self.original_query,
            "normalized_query": self.normalized_query,
            "language": self.language,
            "intent": self.intent,
            "time_preference": self.time_preference,
            "is_comparison": self.is_comparison,
            "entities": [
                {"entity": e.entity, "version": e.version, "full_phrase": e.full_phrase}
                for e in self.entities
            ],
            "keywords": self.keywords,
            "qualifiers": self.qualifiers,
            "multilingual_expansions": self.multilingual_expansions,
            "main_subject": self.main_subject,
        }


def detect_language(text: str) -> str:
    """Lightweight deterministic language detection (en, fr, ar)."""
    if not text:
        return "en"
    if _ARABIC_CHAR_RE.search(text):
        return "ar"
    lower_words = set(re.findall(r"[^\W\d_]+", text.lower()))
    if _FRENCH_ACCENT_RE.search(text) or len(lower_words & _FRENCH_MARKER_WORDS) >= 1:
        return "fr"
    return "en"


def tokenize_multilingual(text: str, keep_short_versions: bool = True) -> List[str]:
    """
    Multilingual-aware tokenizer that preserves:
      - Arabic words (2+ chars)
      - French accented words
      - Dotted version strings like 3.13
      - Short version numbers & acronyms (6, 5, 11, 17, AI, ML, Go)
    """
    if not text:
        return []
    # Match dotted versions (3.13), hyphenated identifiers (gpt-6), or Unicode word tokens
    raw_tokens = re.findall(r"\d+\.\d+(?:\.\d+)?|[\w\u0600-\u06FF]+(?:-[\w\u0600-\u06FF]+)?", text.lower())
    tokens: List[str] = []
    for tok in raw_tokens:
        if tok in STOPWORDS:
            continue
        if len(tok) >= 2 or (keep_short_versions and tok.isdigit()):
            tokens.append(tok)
    return tokens


class QueryAnalyzer:
    """Lightweight deterministic query analyzer with caching."""

    @classmethod
    def analyze(cls, query: str) -> QueryAnalysis:
        clean_q = re.sub(r"\s+", " ", (query or "").strip())
        cache_key = clean_q.lower()
        cached = query_analysis_cache.get(cache_key)
        if cached is not None:
            return cached

        language = detect_language(clean_q)
        lower_q = clean_q.lower()
        tokens = tokenize_multilingual(clean_q)

        # 1. Extract Entity + Version pairs (e.g. GTA 6, Python 3.13, Windows 11, iPhone 17, GPT-6)
        entities: List[EntityVersion] = []
        seen_ev: Set[Tuple[str, str]] = set()
        for match in _ENTITY_VERSION_RE.finditer(clean_q):
            ent = match.group(1).lower().strip("-.")
            ver = match.group(2).lower().lstrip("v")
            # Ignore false positives like "top 10" or "2025" unless paired with product/tech
            if ent in {"top", "best", "first", "last", "next", "part", "year", "in", "on", "at", "vs"}:
                continue
            if len(ver) == 4 and ver.startswith(("19", "20")) and ent in {"year", "in", "since", "from"}:
                continue
            key = (ent, ver)
            if key not in seen_ev:
                seen_ev.add(key)
                entities.append(EntityVersion(entity=ent, version=ver, full_phrase=f"{ent} {ver}"))

        # 2. Detect Intent & Comparison
        is_comparison = any(
            re.search(rf"\b{re.escape(kw)}\b", lower_q) if kw.isascii() else (kw in lower_q)
            for kw in _INTENT_KEYWORDS["comparison"]
        )

        intent = "general"
        if is_comparison:
            intent = "comparison"
        else:
            best_intent = "general"
            best_hits = 0
            for cand_intent, kw_set in _INTENT_KEYWORDS.items():
                if cand_intent == "comparison":
                    continue
                hits = sum(1 for kw in kw_set if kw in lower_q)
                if hits > best_hits:
                    best_hits = hits
                    best_intent = cand_intent
            intent = best_intent

        # 3. Time Preference
        time_preference = "any"
        if intent == "news" or any(w in lower_q for w in ("latest", "recent", "newest", "today", "2025", "2026", "dernières", "أحدث", "آخر")):
            time_preference = "recent"
        elif intent == "historical" or re.search(r"\b19[0-9]{2}\b", lower_q):
            time_preference = "historical"

        # 4. Qualifiers (release date, security, benchmark, tutorial, etc.)
        qualifiers: List[str] = []
        qualifier_terms = {
            "release date", "date de sortie", "latest", "news", "security",
            "memory management", "benchmark", "tutorial", "review", "price", "specs"
        }
        for q_term in qualifier_terms:
            if q_term in lower_q:
                qualifiers.append(q_term)

        # 5. Multilingual Concept Expansion (preserving exact identifiers & versions)
        expansions: List[str] = []
        for concept_group in MULTILINGUAL_CONCEPTS:
            matched_lang = None
            for lang_code, phrases in concept_group.items():
                if any(p in lower_q for p in phrases):
                    matched_lang = lang_code
                    break
            if matched_lang:
                for lang_code, phrases in concept_group.items():
                    if lang_code != matched_lang and phrases:
                        expansions.append(phrases[0])

        # 6. Main subject (query minus intent/time boilerplate)
        main_subject = entities[0].full_phrase if entities else clean_q

        analysis = QueryAnalysis(
            original_query=query,
            normalized_query=clean_q,
            language=language,
            intent=intent,
            time_preference=time_preference,
            is_comparison=is_comparison,
            entities=entities,
            keywords=tokens,
            qualifiers=qualifiers,
            multilingual_expansions=expansions,
            main_subject=main_subject,
        )
        query_analysis_cache.set(cache_key, analysis)
        return analysis
