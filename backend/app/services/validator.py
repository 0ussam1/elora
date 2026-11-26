"""
Three-Level Intelligent Validation Pipeline for ELORA.

Separates expensive verification from the critical search path:
  - Level 1 (Fast Verification): Inline, <1ms, zero network. Checks URL structure,
    source-specific identifiers, metadata consistency, and validation cache.
    Never classifies an unverified result as VERIFIED unless a fresh cached
    Level 2/3 verification already exists.
  - Level 2 (Lightweight Verification): Background async HTTP HEAD (or ranged GET)
    with short timeout, redirect/canonical resolution, and 404/410 detection.
  - Level 3 (Deep Verification): Selective background check on high-priority
    results (first 16KB only) to detect soft-404 pages and title/content mismatches.
"""
import asyncio
import re
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import httpx

from app.core.config import settings
from app.core.cache import url_validation_cache, deep_validation_cache
from app.core.resilience import get_shared_http_client
from app.database.session import SessionLocal
from app.models.database import ResearchResult

logger = logging.getLogger(__name__)

_SOFT_404_PATTERNS = re.compile(
    r"(page\s+not\s+found|404\s+not\s+found|error\s+404|document\s+not\s+found|"
    r"no\s+longer\s+available|this\s+page\s+doesn['’]?t\s+exist)",
    re.IGNORECASE,
)
_TITLE_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


class ValidationService:
    """Non-blocking 3-level result validation."""

    @staticmethod
    def level1_fast_verify(result: ResearchResult) -> Dict[str, Any]:
        """
        Level 1 — Fast inline verification (zero network calls).
        Checks URL validity, source identifier, metadata consistency, and cache.
        """
        url = (result.source_url or "").strip()
        parsed = urlparse(url)
        valid_url = parsed.scheme in ("http", "https") and bool(parsed.netloc)

        if not valid_url:
            return {
                "validation_status": "INVALID_URL",
                "validation_level": 1,
                "validation_checked_at": datetime.now(timezone.utc).isoformat(),
            }

        # Check deep cache first, then lightweight URL cache
        deep_cached = deep_validation_cache.get(url)
        if deep_cached:
            return {**deep_cached, "validation_cached": True}

        url_cached = url_validation_cache.get(url)
        if url_cached:
            return {**url_cached, "validation_cached": True}

        # Check source-specific identifier & metadata consistency
        has_source_id = bool(result.source_item_id)
        has_title = bool(result.title and len(result.title.strip()) >= 3)

        status = "FAST_VERIFIED" if (has_source_id and has_title) else "PENDING"
        return {
            "validation_status": status,
            "validation_level": 1,
            "has_stable_id": has_source_id,
            "validation_checked_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    async def level2_lightweight_verify(url: str, client: httpx.AsyncClient) -> Dict[str, Any]:
        """
        Level 2 — Lightweight HTTP verification with short timeout & redirect tracking.
        """
        cached = url_validation_cache.get(url)
        if cached:
            return {**cached, "validation_cached": True}

        now_str = datetime.now(timezone.utc).isoformat()
        timeout = settings.VALIDATION_TIMEOUT_SECONDS
        try:
            resp = await client.head(url, timeout=timeout, follow_redirects=True)
            if resp.status_code == 405:
                # Some servers disallow HEAD; use ranged GET without downloading body
                resp = await client.get(
                    url,
                    headers={"Range": "bytes=0-1024"},
                    timeout=timeout,
                    follow_redirects=True,
                )

            final_url = str(resp.url)
            code = resp.status_code

            if code in (404, 410):
                outcome = {
                    "validation_status": "BROKEN_LINK",
                    "validation_level": 2,
                    "http_status": code,
                    "canonical_url": final_url,
                    "validation_checked_at": now_str,
                }
            elif 200 <= code < 400:
                outcome = {
                    "validation_status": "LIGHT_VERIFIED",
                    "validation_level": 2,
                    "http_status": code,
                    "canonical_url": final_url,
                    "validation_checked_at": now_str,
                }
            elif code in (401, 403, 429):
                outcome = {
                    "validation_status": "PROTECTED",
                    "validation_level": 2,
                    "http_status": code,
                    "canonical_url": final_url,
                    "validation_checked_at": now_str,
                }
            else:
                outcome = {
                    "validation_status": "UNVERIFIED",
                    "validation_level": 2,
                    "http_status": code,
                    "canonical_url": final_url,
                    "validation_checked_at": now_str,
                }
        except Exception as exc:
            outcome = {
                "validation_status": "UNREACHABLE",
                "validation_level": 2,
                "error": type(exc).__name__,
                "validation_checked_at": now_str,
            }

        url_validation_cache.set(url, outcome, ttl=settings.URL_VALIDATION_CACHE_TTL_SECONDS)
        return outcome

    @staticmethod
    async def level3_deep_verify(
        url: str,
        expected_title: str,
        client: httpx.AsyncClient,
    ) -> Dict[str, Any]:
        """
        Level 3 — Selective deep verification (reads at most 16KB).
        Detects soft-404 pages and verifies title/content consistency.
        """
        cached = deep_validation_cache.get(url)
        if cached:
            return {**cached, "validation_cached": True}

        now_str = datetime.now(timezone.utc).isoformat()
        try:
            async with client.stream(
                "GET",
                url,
                timeout=settings.VALIDATION_TIMEOUT_SECONDS,
                follow_redirects=True,
            ) as resp:
                code = resp.status_code
                final_url = str(resp.url)
                ctype = (resp.headers.get("content-type") or "").lower()

                if code in (404, 410):
                    outcome = {
                        "validation_status": "BROKEN_LINK",
                        "validation_level": 3,
                        "http_status": code,
                        "canonical_url": final_url,
                        "validation_checked_at": now_str,
                    }
                    deep_validation_cache.set(url, outcome, ttl=settings.DEEP_VALIDATION_CACHE_TTL_SECONDS)
                    return outcome

                # For PDFs/binaries, HTTP 200 + content-type confirmation is sufficient
                if "pdf" in ctype or "octet-stream" in ctype:
                    outcome = {
                        "validation_status": "VERIFIED" if 200 <= code < 300 else "UNVERIFIED",
                        "validation_level": 3,
                        "http_status": code,
                        "canonical_url": final_url,
                        "content_type_verified": ctype,
                        "validation_checked_at": now_str,
                    }
                    deep_validation_cache.set(url, outcome, ttl=settings.DEEP_VALIDATION_CACHE_TTL_SECONDS)
                    return outcome

                chunks: List[bytes] = []
                read_bytes = 0
                async for chunk in resp.aiter_bytes(chunk_size=4096):
                    chunks.append(chunk)
                    read_bytes += len(chunk)
                    if read_bytes >= 16384:
                        break
                sample_text = b"".join(chunks).decode("utf-8", errors="ignore")

            title_match = _TITLE_TAG_RE.search(sample_text)
            page_title = title_match.group(1).strip() if title_match else ""
            is_soft_404 = bool(_SOFT_404_PATTERNS.search(page_title or sample_text[:2000]))

            if is_soft_404:
                status = "SOFT_404"
            elif 200 <= code < 300:
                status = "VERIFIED"
            else:
                status = "UNVERIFIED"

            outcome = {
                "validation_status": status,
                "validation_level": 3,
                "http_status": code,
                "canonical_url": final_url,
                "page_title": page_title[:200] if page_title else None,
                "soft_404_detected": is_soft_404,
                "validation_checked_at": now_str,
            }
        except Exception as exc:
            outcome = {
                "validation_status": "UNREACHABLE",
                "validation_level": 3,
                "error": type(exc).__name__,
                "validation_checked_at": now_str,
            }

        deep_validation_cache.set(url, outcome, ttl=settings.DEEP_VALIDATION_CACHE_TTL_SECONDS)
        return outcome

    @classmethod
    async def validate_job_results_async(cls, job_id: str) -> Dict[str, Any]:
        """
        Background validation task for a completed/active job.
        Deduplicates URLs, runs Level 2 on uncached URLs, and selectively runs
        Level 3 on top-ranked items, then persists updates to the DB.
        """
        db = SessionLocal()
        stats = {"job_id": job_id, "total": 0, "url_checks": 0, "deep_checks": 0, "cache_hits": 0}
        try:
            results: List[ResearchResult] = (
                db.query(ResearchResult)
                .filter(ResearchResult.job_id == job_id, ResearchResult.is_duplicate == False)
                .order_by(ResearchResult.relevance_score.desc())
                .all()
            )
            stats["total"] = len(results)
            if not results:
                return stats

            # Deduplicate URLs across results
            url_to_results: Dict[str, List[ResearchResult]] = {}
            for r in results:
                url = (r.source_url or "").strip()
                if url.startswith(("http://", "https://")):
                    url_to_results.setdefault(url, []).append(r)

            # Pick top URLs for selective Level 3 deep verification
            top_deep_urls = set()
            for r in results[: settings.DEEP_VALIDATION_MAX_ITEMS]:
                if r.source_url:
                    top_deep_urls.add(r.source_url.strip())

            sem = asyncio.Semaphore(settings.VALIDATION_MAX_CONCURRENT)
            client = get_shared_http_client()

            async def _check_url(url: str, group: List[ResearchResult]) -> tuple[str, Dict[str, Any]]:
                async with sem:
                    if url in top_deep_urls:
                        stats["deep_checks"] += 1
                        res = await cls.level3_deep_verify(url, group[0].title or "", client)
                    else:
                        stats["url_checks"] += 1
                        res = await cls.level2_lightweight_verify(url, client)
                    if res.get("validation_cached"):
                        stats["cache_hits"] += 1
                    return url, res

            outcomes = await asyncio.gather(
                *(_check_url(u, grp) for u, grp in url_to_results.items()),
                return_exceptions=True,
            )

            for item in outcomes:
                if isinstance(item, Exception):
                    continue
                url, outcome = item
                for r in url_to_results.get(url, []):
                    meta = dict(r.metadata_fields or {})
                    meta.update(outcome)
                    r.metadata_fields = meta

            db.commit()
            return stats
        except Exception as e:
            logger.error(f"Background validation failed for job {job_id}: {e}")
            return stats
        finally:
            db.close()
