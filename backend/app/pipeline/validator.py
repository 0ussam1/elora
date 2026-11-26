"""
Multi-Layer Search Result Validator & Validation Cache
======================================================
Verifies that every search result returned by ELORA points to an accessible,
authentic, non-deleted, content-matching source before being presented to users.

Validation Statuses:
  - VERIFIED:           Original source and content successfully checked.
  - PARTIALLY_VERIFIED: Official API record exists, but external URL/full content
                        cannot be confirmed (e.g. publisher 403 or paywall).
  - INACCESSIBLE:       Technical block/timeout/403/429/CAPTCHA/login wall
                        (NOT marked deleted without evidence).
  - DELETED:            Confirmed deleted/dead via official API (e.g. HN deleted/dead).
  - NOT_FOUND:          Confirmed HTTP 404/410 or soft-404 page.
  - MISMATCH:           HTTP 200 page whose content is empty or unrelated to title/snippet.
  - UNCHECKED:          Not yet validated.
"""
import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models.database import ResearchResult, ValidationCache

logger = logging.getLogger(__name__)

# ── Status Constants ──────────────────────────────────────────────────────────
STATUS_VERIFIED = "VERIFIED"
STATUS_PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
STATUS_INACCESSIBLE = "INACCESSIBLE"
STATUS_DELETED = "DELETED"
STATUS_NOT_FOUND = "NOT_FOUND"
STATUS_MISMATCH = "MISMATCH"
STATUS_UNCHECKED = "UNCHECKED"

ACADEMIC_SOURCES = {
    "arxiv", "openalex", "crossref", "semantic_scholar", "core", "zenodo",
    "nara", "cia_reading_room", "fbi_vault", "nsa_archive", "nat_sec_archive",
}
DISCUSSION_SOURCES = {
    "hackernews", "reddit", "stackexchange", "discourse", "lemmy", "mastodon",
}

_MAX_BODY_BYTES = 131_072  # 128 KB cap so we never download large binaries
_REQUEST_TIMEOUT = 6.0
_DEFAULT_HEADERS = {
    "User-Agent": "ELORA-Validator/1.0 (+https://github.com/0ussam1/elora; research-verification)",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
}

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "have", "has", "had", "not", "but", "what", "when", "where", "which", "who",
    "how", "why", "all", "can", "will", "just", "more", "about", "into", "over",
    "your", "you", "our", "out", "use", "using", "used", "new", "via",
}

_CAPTCHA_PATTERNS = (
    "cf_chl_opt",
    "just a moment...",
    "verify you are human",
    "g-recaptcha",
    "hcaptcha",
    "turnstile",
    "are you a robot",
    "enable javascript and cookies to continue",
    "checking your browser before accessing",
)

_LOGIN_PATTERNS = (
    "sign in to continue",
    "log in to continue",
    "login to view",
    "please log in",
    "you must be logged in",
    "create an account to continue",
)

_SOFT_404_PATTERNS = (
    "page not found",
    "404 not found",
    "error 404",
    "404 error",
    "this page doesn't exist",
    "this page does not exist",
    "page cannot be found",
    "no longer available",
    "content has been removed",
    "this post was deleted",
    "410 gone",
    "nothing was found",
    "requested url was not found",
)


@dataclass
class ValidationOutcome:
    status: str
    http_status: Optional[int] = None
    final_url: Optional[str] = None
    canonical_url: Optional[str] = None
    method: str = "http_check"
    reason: Optional[str] = None
    extraction_status: str = "snippet_only"
    availability_status: str = "unknown"


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()


def _tokenize(text: str) -> set[str]:
    if not text:
        return set()
    words = re.findall(r"[a-zA-Z0-9]{3,}", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def _ttl_for(source_name: str, status: str) -> timedelta:
    if status in (STATUS_DELETED, STATUS_NOT_FOUND):
        return timedelta(hours=24)
    if status == STATUS_INACCESSIBLE:
        return timedelta(minutes=30)
    if source_name in ACADEMIC_SOURCES:
        return timedelta(days=7)
    if source_name in DISCUSSION_SOURCES:
        return timedelta(hours=6)
    return timedelta(hours=12)


def _is_valid_http_url(url: str) -> bool:
    try:
        p = urlparse(url.strip())
        return p.scheme in ("http", "https") and bool(p.netloc) and "." in p.netloc
    except Exception:
        return False


def _detect_false_positive_html(
    html: str, final_url: str, expected_title: str, expected_snippet: Optional[str]
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Inspect HTML content for CAPTCHAs, login walls, soft 404s, empty bodies,
    and title/content mismatches.
    Returns (failure_status, reason, canonical_url).
    """
    lower_raw = html.lower()

    # 1. Anti-bot / CAPTCHA detection
    for pat in _CAPTCHA_PATTERNS:
        if pat in lower_raw:
            return STATUS_INACCESSIBLE, f"Blocked by anti-bot/CAPTCHA challenge ({pat})", None

    soup = BeautifulSoup(html, "html.parser")

    # Extract canonical URL if present
    canon_tag = soup.find("link", rel=lambda v: v and "canonical" in v.lower() if isinstance(v, str) else False)
    if not canon_tag:
        for link in soup.find_all("link"):
            rel = link.get("rel") or []
            if isinstance(rel, list) and any(r.lower() == "canonical" for r in rel):
                canon_tag = link
                break
    canonical_url = canon_tag.get("href") if canon_tag and canon_tag.get("href") else None

    # Remove script/style noise for text analysis
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
    body_text = soup.get_text(" ", strip=True)
    body_lower = body_text.lower()
    title_lower = page_title.lower()

    # 2. Empty HTML detection
    if len(body_text) < 50:
        return STATUS_MISMATCH, "Page returned HTTP 200 with empty or near-empty content", canonical_url

    # 3. Login wall detection (only when redirected to /login or short gated body)
    parsed_final = urlparse(final_url)
    if "/login" in parsed_final.path.lower() or "/signin" in parsed_final.path.lower():
        return STATUS_INACCESSIBLE, f"Redirected to login page ({parsed_final.path})", canonical_url
    if len(body_text) < 1500:
        for pat in _LOGIN_PATTERNS:
            if pat in body_lower:
                return STATUS_INACCESSIBLE, f"Content gated behind login prompt ({pat})", canonical_url

    # 4. Soft-404 detection (check <title>, <h1>, or short error body)
    h1_text = " ".join(h.get_text(" ", strip=True).lower() for h in soup.find_all("h1")[:2])
    header_surface = f"{title_lower} {h1_text}"
    for pat in _SOFT_404_PATTERNS:
        if pat in header_surface or (len(body_text) < 1200 and pat in body_lower):
            return STATUS_NOT_FOUND, f"Soft 404 detected ({pat})", canonical_url

    # 5. Title / content correspondence check
    expected_tokens = _tokenize(expected_title)
    if expected_tokens:
        page_tokens = _tokenize(f"{page_title} {h1_text} {body_text[:4000]}")
        overlap = expected_tokens.intersection(page_tokens)
        overlap_ratio = len(overlap) / len(expected_tokens)
        if overlap_ratio == 0.0:
            # Also check snippet tokens as secondary signal
            snippet_tokens = _tokenize(expected_snippet or "")
            snippet_overlap = len(snippet_tokens.intersection(page_tokens)) / max(len(snippet_tokens), 1)
            if snippet_overlap < 0.15:
                return (
                    STATUS_MISMATCH,
                    "Original page content does not match expected title or description",
                    canonical_url,
                )

    return None, None, canonical_url


class ResultValidator:
    """Multi-layer result validator with DB-backed TTL caching."""

    @classmethod
    def _read_cache(cls, db: Optional[Session], url: str) -> Optional[ValidationCache]:
        if db is None or not url:
            return None
        try:
            entry = db.query(ValidationCache).filter(ValidationCache.url_hash == _url_hash(url)).first()
            if not entry:
                return None
            expires_at = entry.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at > datetime.now(timezone.utc):
                return entry
        except Exception as e:
            logger.debug(f"ValidationCache read error: {e}")
        return None

    @classmethod
    def _write_cache(
        cls,
        db: Optional[Session],
        url: str,
        source_name: str,
        outcome: ValidationOutcome,
    ) -> None:
        if db is None or not url:
            return
        try:
            now = datetime.now(timezone.utc)
            expires = now + _ttl_for(source_name, outcome.status)
            uhash = _url_hash(url)
            entry = db.query(ValidationCache).filter(ValidationCache.url_hash == uhash).first()
            if entry:
                entry.validation_status = outcome.status
                entry.http_status = outcome.http_status
                entry.final_url = outcome.final_url
                entry.canonical_url = outcome.canonical_url
                entry.validation_method = outcome.method
                entry.failure_reason = outcome.reason
                entry.validated_at = now
                entry.expires_at = expires
            else:
                entry = ValidationCache(
                    url_hash=uhash,
                    url=url[:1000],
                    source_name=source_name,
                    validation_status=outcome.status,
                    http_status=outcome.http_status,
                    final_url=outcome.final_url[:1000] if outcome.final_url else None,
                    canonical_url=outcome.canonical_url[:1000] if outcome.canonical_url else None,
                    validation_method=outcome.method,
                    failure_reason=outcome.reason,
                    validated_at=now,
                    expires_at=expires,
                )
                db.add(entry)
            db.flush()
        except Exception as e:
            logger.debug(f"ValidationCache write error: {e}")

    @classmethod
    async def _verify_url_http(
        cls,
        client: httpx.AsyncClient,
        url: str,
        expected_title: str,
        expected_snippet: Optional[str],
    ) -> ValidationOutcome:
        """Layer A + B: URL reachability, redirects, bounded GET, and content validation."""
        if not _is_valid_http_url(url):
            return ValidationOutcome(
                status=STATUS_NOT_FOUND,
                method="url_syntax",
                reason="Invalid or malformed URL",
                extraction_status="unavailable",
                availability_status="missing",
            )

        try:
            # 1. Try lightweight HEAD first
            head_resp = await client.head(
                url, headers=_DEFAULT_HEADERS, follow_redirects=True, timeout=_REQUEST_TIMEOUT
            )
            if head_resp.status_code in (404, 410):
                return ValidationOutcome(
                    status=STATUS_NOT_FOUND,
                    http_status=head_resp.status_code,
                    final_url=str(head_resp.url),
                    method="http_head",
                    reason=f"HTTP {head_resp.status_code}",
                    extraction_status="unavailable",
                    availability_status="missing",
                )

            # 2. Always perform a bounded GET for HTML content check (or when HEAD is rejected)
            async with client.stream(
                "GET", url, headers=_DEFAULT_HEADERS, follow_redirects=True, timeout=_REQUEST_TIMEOUT
            ) as resp:
                final_url = str(resp.url)
                http_status = resp.status_code

                if http_status in (404, 410):
                    return ValidationOutcome(
                        status=STATUS_NOT_FOUND,
                        http_status=http_status,
                        final_url=final_url,
                        method="http_get",
                        reason=f"HTTP {http_status}",
                        extraction_status="unavailable",
                        availability_status="missing",
                    )

                if http_status in (401, 403, 429) or http_status >= 500:
                    return ValidationOutcome(
                        status=STATUS_INACCESSIBLE,
                        http_status=http_status,
                        final_url=final_url,
                        method="http_get",
                        reason=f"Server returned HTTP {http_status}",
                        extraction_status="unavailable",
                        availability_status="restricted",
                    )

                if http_status != 200:
                    return ValidationOutcome(
                        status=STATUS_INACCESSIBLE,
                        http_status=http_status,
                        final_url=final_url,
                        method="http_get",
                        reason=f"Unexpected HTTP {http_status}",
                        extraction_status="unavailable",
                        availability_status="restricted",
                    )

                content_type = (resp.headers.get("content-type") or "").lower()
                # Non-HTML documents (PDF, JSON, plain text) — verify non-empty without downloading huge binaries
                chunks: List[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes(chunk_size=16384):
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= _MAX_BODY_BYTES:
                        break
                raw_bytes = b"".join(chunks)

                if "html" not in content_type and "xml" not in content_type:
                    if len(raw_bytes) == 0:
                        return ValidationOutcome(
                            status=STATUS_MISMATCH,
                            http_status=http_status,
                            final_url=final_url,
                            method="http_get",
                            reason="Empty response body",
                            extraction_status="unavailable",
                            availability_status="missing",
                        )
                    return ValidationOutcome(
                        status=STATUS_VERIFIED,
                        http_status=http_status,
                        final_url=final_url,
                        canonical_url=final_url,
                        method="http_get_binary",
                        extraction_status="extracted" if "pdf" not in content_type else "snippet_only",
                        availability_status="available",
                    )

                html_text = raw_bytes.decode("utf-8", errors="replace")
                fail_status, fail_reason, canon_url = _detect_false_positive_html(
                    html_text, final_url, expected_title, expected_snippet
                )
                if fail_status:
                    return ValidationOutcome(
                        status=fail_status,
                        http_status=http_status,
                        final_url=final_url,
                        canonical_url=canon_url,
                        method="http_get_content",
                        reason=fail_reason,
                        extraction_status="unavailable",
                        availability_status="missing" if fail_status == STATUS_NOT_FOUND else "restricted",
                    )

                return ValidationOutcome(
                    status=STATUS_VERIFIED,
                    http_status=http_status,
                    final_url=final_url,
                    canonical_url=canon_url or final_url,
                    method="http_get_content",
                    extraction_status="extracted",
                    availability_status="available",
                )

        except httpx.TimeoutException:
            return ValidationOutcome(
                status=STATUS_INACCESSIBLE,
                method="http_timeout",
                reason="Request timed out",
                extraction_status="unavailable",
                availability_status="restricted",
            )
        except Exception as e:
            return ValidationOutcome(
                status=STATUS_INACCESSIBLE,
                method="http_error",
                reason=f"Connection failed: {str(e)[:120]}",
                extraction_status="unavailable",
                availability_status="restricted",
            )

    @classmethod
    async def _verify_source_api(
        cls, client: httpx.AsyncClient, item: ResearchResult
    ) -> Optional[ValidationOutcome]:
        """
        Layer C: Source-specific official API verification where available.
        Returns ValidationOutcome if the official API gives a definitive answer
        (e.g. DELETED / NOT_FOUND / API-verified), or None to fall through to HTTP check.
        """
        sid = item.source_item_id
        sname = item.source_name

        try:
            if sname == "hackernews" and sid and sid.isdigit():
                r = await client.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                    timeout=_REQUEST_TIMEOUT,
                )
                if r.status_code == 200:
                    data = r.json()
                    if data is None:
                        return ValidationOutcome(
                            status=STATUS_DELETED,
                            http_status=200,
                            method="hn_firebase_api",
                            reason="Hacker News item no longer exists",
                            extraction_status="unavailable",
                            availability_status="missing",
                        )
                    if data.get("deleted") or data.get("dead"):
                        return ValidationOutcome(
                            status=STATUS_DELETED,
                            http_status=200,
                            method="hn_firebase_api",
                            reason="Hacker News item is deleted or dead",
                            extraction_status="unavailable",
                            availability_status="missing",
                        )
                    # Item is alive; check external URL if different from HN item URL
                    hn_url = f"https://news.ycombinator.com/item?id={sid}"
                    if item.source_url and "news.ycombinator.com/item" not in item.source_url:
                        ext = await cls._verify_url_http(client, item.source_url, item.title, item.content_snippet)
                        if ext.status == STATUS_VERIFIED:
                            ext.method = "hn_api+http_get"
                            return ext
                        return ValidationOutcome(
                            status=STATUS_PARTIALLY_VERIFIED,
                            http_status=ext.http_status,
                            final_url=ext.final_url,
                            canonical_url=hn_url,
                            method="hn_firebase_api",
                            reason=f"HN discussion exists, but linked URL is {ext.status.lower()} ({ext.reason or 'unavailable'})",
                            extraction_status="snippet_only",
                            availability_status="restricted",
                        )
                    return ValidationOutcome(
                        status=STATUS_VERIFIED,
                        http_status=200,
                        final_url=hn_url,
                        canonical_url=hn_url,
                        method="hn_firebase_api",
                        extraction_status="extracted",
                        availability_status="available",
                    )

            elif sname == "wikipedia" and item.title:
                r = await client.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "titles": item.title,
                        "prop": "info",
                        "inprop": "url",
                        "format": "json",
                    },
                    headers=_DEFAULT_HEADERS,
                    timeout=_REQUEST_TIMEOUT,
                )
                if r.status_code == 200:
                    pages = r.json().get("query", {}).get("pages", {})
                    for pid, pinfo in pages.items():
                        if pid == "-1" or "missing" in pinfo:
                            return ValidationOutcome(
                                status=STATUS_NOT_FOUND,
                                http_status=404,
                                method="wikipedia_api",
                                reason="Wikipedia article does not exist",
                                extraction_status="unavailable",
                                availability_status="missing",
                            )
                        canon = pinfo.get("canonicalurl") or item.source_url
                        return ValidationOutcome(
                            status=STATUS_VERIFIED,
                            http_status=200,
                            final_url=canon,
                            canonical_url=canon,
                            method="wikipedia_api",
                            extraction_status="extracted",
                            availability_status="available",
                        )

            elif sname == "arxiv" and sid:
                arxiv_id = sid.split("/")[-1].replace("abs/", "")
                r = await client.get(
                    "https://export.arxiv.org/api/query",
                    params={"id_list": arxiv_id},
                    timeout=_REQUEST_TIMEOUT,
                )
                if r.status_code == 200 and "<entry>" in r.text:
                    canon = f"https://arxiv.org/abs/{arxiv_id}"
                    return ValidationOutcome(
                        status=STATUS_VERIFIED,
                        http_status=200,
                        final_url=canon,
                        canonical_url=canon,
                        method="arxiv_api",
                        extraction_status="extracted",
                        availability_status="available",
                    )

            elif sname in ("openalex", "crossref", "semantic_scholar"):
                doi = (item.metadata_fields or {}).get("doi")
                api_verified = False
                if doi:
                    cr = await client.get(
                        f"https://api.crossref.org/works/{doi}",
                        headers=_DEFAULT_HEADERS,
                        timeout=_REQUEST_TIMEOUT,
                    )
                    if cr.status_code == 200:
                        api_verified = True
                    elif cr.status_code == 404:
                        return ValidationOutcome(
                            status=STATUS_NOT_FOUND,
                            http_status=404,
                            method="crossref_doi_api",
                            reason=f"DOI {doi} not found in Crossref",
                            extraction_status="unavailable",
                            availability_status="missing",
                        )
                if api_verified:
                    ext = await cls._verify_url_http(client, item.source_url, item.title, item.content_snippet)
                    if ext.status == STATUS_VERIFIED:
                        ext.method = f"{sname}_doi+http_get"
                        return ext
                    return ValidationOutcome(
                        status=STATUS_PARTIALLY_VERIFIED,
                        http_status=ext.http_status,
                        final_url=ext.final_url,
                        canonical_url=f"https://doi.org/{doi}" if doi else item.source_url,
                        method="crossref_doi_api",
                        reason=f"Official bibliographic record verified, but external URL is {ext.status.lower()} ({ext.reason or 'restricted'})",
                        extraction_status="snippet_only",
                        availability_status="restricted",
                    )

            elif sname == "internet_archive" and sid:
                r = await client.get(f"https://archive.org/metadata/{sid}", timeout=_REQUEST_TIMEOUT)
                if r.status_code == 200:
                    data = r.json()
                    if not data or data.get("is_dark"):
                        return ValidationOutcome(
                            status=STATUS_DELETED if data.get("is_dark") else STATUS_NOT_FOUND,
                            http_status=200,
                            method="ia_metadata_api",
                            reason="Internet Archive item is unavailable or darkened",
                            extraction_status="unavailable",
                            availability_status="missing",
                        )
                    canon = f"https://archive.org/details/{sid}"
                    return ValidationOutcome(
                        status=STATUS_VERIFIED,
                        http_status=200,
                        final_url=canon,
                        canonical_url=canon,
                        method="ia_metadata_api",
                        extraction_status="extracted",
                        availability_status="available",
                    )

            elif sname == "github" and "github.com/" in (item.source_url or ""):
                parsed = urlparse(item.source_url)
                parts = [p for p in parsed.path.strip("/").split("/") if p]
                if len(parts) >= 2:
                    owner, repo = parts[0], parts[1]
                    api_url = f"https://api.github.com/repos/{owner}/{repo}"
                    if len(parts) >= 4 and parts[2] in ("issues", "pull"):
                        api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{parts[3]}"
                    r = await client.get(api_url, headers=_DEFAULT_HEADERS, timeout=_REQUEST_TIMEOUT)
                    if r.status_code == 404:
                        return ValidationOutcome(
                            status=STATUS_NOT_FOUND,
                            http_status=404,
                            method="github_api",
                            reason="GitHub repository or issue returned 404",
                            extraction_status="unavailable",
                            availability_status="missing",
                        )
                    if r.status_code == 200:
                        html_url = r.json().get("html_url") or item.source_url
                        return ValidationOutcome(
                            status=STATUS_VERIFIED,
                            http_status=200,
                            final_url=html_url,
                            canonical_url=html_url,
                            method="github_api",
                            extraction_status="extracted",
                            availability_status="available",
                        )
        except Exception as e:
            logger.debug(f"Source API verification fallback for {sname}/{sid}: {e}")

        return None

    @classmethod
    async def validate_result(
        cls,
        item: ResearchResult,
        client: httpx.AsyncClient,
        db: Optional[Session] = None,
    ) -> ValidationOutcome:
        """Validate a single ResearchResult using cache -> source API -> HTTP+content check."""
        url = item.source_url or ""
        cached = cls._read_cache(db, url)
        if cached:
            outcome = ValidationOutcome(
                status=cached.validation_status,
                http_status=cached.http_status,
                final_url=cached.final_url,
                canonical_url=cached.canonical_url,
                method=f"cache:{cached.validation_method or 'cached'}",
                reason=cached.failure_reason,
                extraction_status="extracted" if cached.validation_status == STATUS_VERIFIED else "snippet_only",
                availability_status="available" if cached.validation_status == STATUS_VERIFIED else "restricted",
            )
            cls._apply_outcome(item, outcome)
            return outcome

        # Try source-specific API verification first
        outcome = await cls._verify_source_api(client, item)
        if outcome is None:
            outcome = await cls._verify_url_http(client, url, item.title, item.content_snippet)

        cls._apply_outcome(item, outcome)
        cls._write_cache(db, url, item.source_name, outcome)
        return outcome

    @staticmethod
    def _apply_outcome(item: ResearchResult, outcome: ValidationOutcome) -> None:
        item.validation_status = outcome.status
        item.http_status = outcome.http_status
        item.final_url = outcome.final_url
        item.canonical_url = outcome.canonical_url
        item.validation_method = outcome.method
        item.validation_reason = outcome.reason
        item.validated_at = datetime.now(timezone.utc)
        item.content_extraction_status = outcome.extraction_status
        item.content_availability_status = outcome.availability_status

    @classmethod
    async def validate_batch(
        cls,
        items: List[ResearchResult],
        db: Optional[Session] = None,
        max_concurrency: int = 8,
    ) -> List[ResearchResult]:
        """Validate all non-duplicate results concurrently and sort VERIFIED first."""
        if not items:
            return items

        sem = asyncio.Semaphore(max_concurrency)

        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            async def _run(item: ResearchResult):
                if item.is_duplicate:
                    return
                async with sem:
                    await cls.validate_result(item, client, db=db)

            await asyncio.gather(*(_run(it) for it in items), return_exceptions=True)

        priority = {
            STATUS_VERIFIED: 0,
            STATUS_PARTIALLY_VERIFIED: 1,
            STATUS_UNCHECKED: 2,
            STATUS_INACCESSIBLE: 3,
            STATUS_MISMATCH: 4,
            STATUS_NOT_FOUND: 5,
            STATUS_DELETED: 6,
        }
        items.sort(
            key=lambda x: (priority.get(x.validation_status or STATUS_UNCHECKED, 9), -(x.relevance_score or 0.0))
        )
        return items
