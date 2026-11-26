import json
import logging
import re
import uuid
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.discovery import (
    DiscoveryChatMessage, DiscoveryChatRequest, DiscoveryChatResponse,
    DiscoveryIntent, DiscoverySearchPlan, DiscoverySearchResponse
)
from app.models.database import ResearchJob, ResearchResult, CollectionLog
from app.connectors.registry import get_connector, CONNECTOR_REGISTRY
from app.pipeline.normalizer import Normalizer
from app.pipeline.deduplicator import Deduplicator
from app.pipeline.ranker import Ranker
from app.pipeline.validator import ResultValidator

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are ELORA Discovery Assistant, an intelligent exploration and search planning engine powered by Agnes AI for the ELORA Multi-Source Search Engine.
Your mission is to help users who have an idea, a goal, a problem, or a curiosity, but do not know exactly what to search for, which keywords to use, or which sources to explore.

CORE CAPABILITIES & RULES:
1. Multilingual & Script Intelligence:
   - Automatically detect the user's language: Arabic, Moroccan Darija, French, English, German, Spanish, etc.
   - Fully understand Moroccan Darija written in either Arabic script or Latin/Arabizi script (e.g. "bghit chi handasa dyal tomobilat", "fin nelqa cours dyal data", "bghit nchri pc").
   - Understand mixed-language messages (e.g., French or English technical words inside Darija or Arabic).
   - ALWAYS reply in the user's language and script by default. If the user writes in Latin Darija, answer in friendly, natural Latin Darija or clear Arabic script. Keep established technical terms in their standard form.
   - For example, if user asks: "bghit chi handasa dyal tomobilat":
     * Recognize intent: Automotive Engineering / Vehicle Design.
     * Suggest related subtopics: Automotive engineering, Mechanical engineering, Electric vehicles, Automotive electronics, Vehicle design.
     * Answer naturally in Darija explaining these directions.

2. Intent Understanding:
   - Identify:
     * objective: What the user is trying to accomplish.
     * category: One of ['shopping', 'education', 'books', 'developer', 'academic', 'tools', 'business', 'troubleshooting', 'general'].
     * main_topic: Primary topic or discipline (e.g. "Automotive Engineering", "Data Processing", "Machine Learning").
     * related_topics: 3-5 subtopics or adjacent disciplines.
     * detected_language: Language code/name (e.g. "darija", "fr", "ar", "en", "de").

3. Clarification Rules:
   - Ask at most ONE important clarification question ONLY IF the goal is truly ambiguous or essential info is missing (e.g., user asks for a physical store without mentioning any location).
   - If the user's goal is already clear enough to search (e.g., "bghit chi handasa dyal tomobilat", "courses for data processing", "I want to buy a laptop online", "learn AI from scratch"), DO NOT force questions. Set needs_clarification to false and produce the search plan immediately!

4. Search Plan Generation (Targeting ELORA Connectors):
   - queries: 2 to 4 optimized search queries. For non-English inputs, include English/French query translations where technical or academic materials are predominantly indexed in English/French, ensuring maximum search recall.
   - recommended_sources: Choose only among ELORA's actual connectors:
     * 'web_search': General web discovery, stores, products, courses, blogs, platforms
     * 'wikipedia': Background concepts, definitions, encyclopedic knowledge
     * 'github': Open-source repositories, developer tools, software code
     * 'stackexchange': Technical questions, troubleshooting, developer Q&A
     * 'arxiv': Academic preprints, AI/math/physics research papers
     * 'openalex': Global scholarly publications, citations, researchers
     * 'crossref': Scientific papers and DOI references
     * 'openlibrary': Books, authors, published reading lists
     * 'internet_archive': Historical documents, books, public media
     * 'kaggle': Datasets, data science projects, machine learning notebooks
     * 'hackernews': Tech community sentiment, startup discussions
   - resource_types: e.g. ["courses", "tutorials"], ["online stores", "products"], ["libraries", "documentation"], ["academic papers", "books"].
   - reasoning: Brief sentence in the user's language explaining why these sources and queries were chosen.

5. JSON OUTPUT FORMAT:
You MUST respond with valid JSON matching this exact structure:
{
  "detected_language": "darija",
  "understanding": "Clear summary of what you understood, in the user's language",
  "message": "Friendly response to the user, in their language",
  "needs_clarification": false,
  "clarification_question": null,
  "intent": {
    "objective": "Short summary of objective",
    "category": "education",
    "main_topic": "Automotive Engineering",
    "related_topics": ["Mechanical Engineering", "Electric Vehicles", "Automotive Electronics", "Vehicle Design"],
    "detected_language": "darija",
    "missing_information": null
  },
  "search_plan": {
    "queries": ["automotive engineering courses", "vehicle design mechanical engineering tutorial", "electric vehicles engineering fundamentals"],
    "recommended_sources": ["web_search", "wikipedia", "openalex", "openlibrary"],
    "resource_types": ["courses", "tutorials", "books"],
    "reasoning": "Combining web courses, academic references, and book catalogs for automotive engineering."
  }
}
"""

class DiscoveryService:
    @classmethod
    def get_provider_status(cls) -> Dict[str, Any]:
        """Check whether Agnes AI (or fallback OpenAI) is configured and active."""
        if settings.AGNES_API_KEY:
            return {
                "configured": True,
                "provider": "Agnes AI",
                "model": settings.AGNES_MODEL,
                "base_url": settings.AGNES_BASE_URL
            }
        elif settings.OPENAI_API_KEY:
            return {
                "configured": True,
                "provider": "OpenAI",
                "model": settings.OPENAI_MODEL,
                "base_url": settings.OPENAI_BASE_URL
            }
        else:
            return {
                "configured": False,
                "provider": "None",
                "model": None,
                "base_url": None,
                "message": "Agnes AI API key is not configured. Add AGNES_API_KEY to your backend .env file."
            }

    @classmethod
    async def process_chat(cls, request: DiscoveryChatRequest) -> DiscoveryChatResponse:
        """
        Process a user discovery message using Agnes AI.
        Maintains conversation context and outputs a structured discovery plan.
        """
        provider = cls.get_provider_status()
        if not provider["configured"]:
            return DiscoveryChatResponse(
                status="not_configured",
                configured=False,
                message="ELORA Discovery Assistant requires an Agnes AI API key. Please configure AGNES_API_KEY in your backend .env file to enable natural-language discovery.",
                error_detail=provider["message"],
                needs_clarification=False
            )

        api_key = settings.AGNES_API_KEY or settings.OPENAI_API_KEY
        base_url = settings.AGNES_BASE_URL if settings.AGNES_API_KEY else settings.OPENAI_BASE_URL
        model = settings.AGNES_MODEL if settings.AGNES_API_KEY else settings.OPENAI_MODEL

        # Prepare messages
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for m in request.history[-8:]: # keep reasonable context window
            messages.append({"role": m.role, "content": m.content})
        messages.append({"role": "user", "content": request.message})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "response_format": {"type": "json_object"}
        }

        endpoint = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # Network execution with transient error retry
        max_attempts = 2
        last_error = None

        for attempt in range(max_attempts):
            try:
                async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS) as client:
                    res = await client.post(endpoint, json=payload, headers=headers)

                    if res.status_code == 401:
                        logger.error("Agnes AI returned 401 Unauthorized")
                        return DiscoveryChatResponse(
                            status="error",
                            configured=True,
                            message="Invalid Agnes AI credentials. Please verify your AGNES_API_KEY in the backend .env file.",
                            error_detail="401 Unauthorized from Agnes AI endpoint.",
                            needs_clarification=False
                        )
                    elif res.status_code == 402:
                        logger.error("Agnes AI returned 402 Payment Required")
                        return DiscoveryChatResponse(
                            status="error",
                            configured=True,
                            message="Agnes AI account has insufficient credits or quota. Please check your account balance.",
                            error_detail="402 Payment Required: Insufficient balance on Agnes AI account.",
                            needs_clarification=False
                        )
                    elif res.status_code == 404:
                        logger.error(f"Agnes AI returned 404: {res.text}")
                        return DiscoveryChatResponse(
                            status="error",
                            configured=True,
                            message=f"Configured model '{model}' was not found on Agnes AI endpoint.",
                            error_detail=f"404 Not Found from {endpoint} for model {model}",
                            needs_clarification=False
                        )
                    elif res.status_code == 429:
                        logger.warning("Agnes AI returned 429 Rate Limit")
                        return DiscoveryChatResponse(
                            status="error",
                            configured=True,
                            message="Agnes AI rate limit reached. Please wait a moment and try again.",
                            error_detail="429 Rate limited by Agnes AI provider.",
                            needs_clarification=False
                        )
                    elif res.status_code >= 400:
                        logger.error(f"Agnes AI error {res.status_code}: {res.text}")
                        return DiscoveryChatResponse(
                            status="error",
                            configured=True,
                            message="An error occurred while contacting Agnes AI. Please try again.",
                            error_detail=f"HTTP {res.status_code}: {res.text[:200]}",
                            needs_clarification=False
                        )

                    data = res.json()
                    raw_content = data["choices"][0]["message"]["content"]
                    parsed = cls._clean_and_parse_json(raw_content)

                    if not parsed:
                        return DiscoveryChatResponse(
                            status="error",
                            configured=True,
                            message="Failed to parse structured discovery response from Agnes AI. Please rephrase your request.",
                            error_detail="Malformed JSON from AI model.",
                            needs_clarification=False
                        )

                    # Validate and construct DiscoveryIntent & DiscoverySearchPlan
                    intent_data = parsed.get("intent") or {}
                    intent = DiscoveryIntent(
                        objective=intent_data.get("objective") or parsed.get("understanding", request.message),
                        category=intent_data.get("category", "general"),
                        main_topic=intent_data.get("main_topic", "General Discovery"),
                        related_topics=intent_data.get("related_topics", []),
                        detected_language=intent_data.get("detected_language") or parsed.get("detected_language", "en"),
                        missing_information=intent_data.get("missing_information")
                    )

                    plan_data = parsed.get("search_plan")
                    search_plan = None
                    if plan_data and isinstance(plan_data, dict):
                        queries = plan_data.get("queries") or [request.message]
                        recommended = plan_data.get("recommended_sources") or ["web_search", "wikipedia"]
                        # filter to only real registered connectors
                        valid_sources = [s for s in recommended if s in CONNECTOR_REGISTRY]
                        if not valid_sources:
                            valid_sources = ["web_search", "wikipedia"]

                        search_plan = DiscoverySearchPlan(
                            queries=queries,
                            recommended_sources=valid_sources,
                            resource_types=plan_data.get("resource_types", ["general"]),
                            reasoning=plan_data.get("reasoning", "")
                        )

                    needs_clarification = bool(parsed.get("needs_clarification", False))
                    clarification_question = parsed.get("clarification_question")

                    # If clarification is required
                    status = "clarification" if (needs_clarification and clarification_question) else "success"

                    return DiscoveryChatResponse(
                        status=status,
                        configured=True,
                        message=parsed.get("message") or parsed.get("understanding") or "Here is what I found for your exploration.",
                        understanding=parsed.get("understanding"),
                        needs_clarification=needs_clarification,
                        clarification_question=clarification_question,
                        intent=intent,
                        search_plan=search_plan
                    )

            except httpx.TimeoutException as e:
                logger.warning(f"Timeout connecting to Agnes AI (attempt {attempt+1}/{max_attempts})")
                last_error = e
                if attempt < max_attempts - 1:
                    await asyncio.sleep(1.0)
                    continue
                return DiscoveryChatResponse(
                    status="error",
                    configured=True,
                    message="Agnes AI request timed out. Please try again.",
                    error_detail="Timeout connecting to Agnes AI provider.",
                    needs_clarification=False
                )
            except httpx.ConnectError as e:
                logger.warning(f"Connection error to Agnes AI (attempt {attempt+1}/{max_attempts}): {e}")
                last_error = e
                if attempt < max_attempts - 1:
                    await asyncio.sleep(1.0)
                    continue
                return DiscoveryChatResponse(
                    status="error",
                    configured=True,
                    message="Unable to connect to Agnes AI server. Please check your network connection.",
                    error_detail=f"ConnectError: {str(e)}",
                    needs_clarification=False
                )
            except Exception as e:
                logger.exception(f"Unexpected error in DiscoveryService.process_chat: {e}")
                return DiscoveryChatResponse(
                    status="error",
                    configured=True,
                    message="An unexpected error occurred during discovery processing.",
                    error_detail=str(e),
                    needs_clarification=False
                )

        return DiscoveryChatResponse(
            status="error",
            configured=True,
            message="An unexpected network error occurred while communicating with Agnes AI.",
            error_detail=str(last_error) if last_error else "Max attempts reached",
            needs_clarification=False
        )

    @classmethod
    async def execute_discovery_search(
        cls,
        queries: List[str],
        sources: Optional[List[str]],
        mode: str,
        limit_per_source: int,
        original_objective: Optional[str],
        db: Session
    ) -> DiscoverySearchResponse:
        """
        Execute real search queries across ELORA's connectors.
        Normalizes, deduplicates, and ranks results.
        Saves research job and results in database.
        """
        job_id = str(uuid.uuid4())
        primary_query = queries[0] if queries else (original_objective or "discovery")

        target_sources = sources or [
            "web_search", "wikipedia", "github", "stackexchange",
            "arxiv", "openalex", "crossref", "openlibrary", "internet_archive"
        ]
        # Filter to existing registered connectors
        valid_sources = [s for s in target_sources if s in CONNECTOR_REGISTRY]
        if not valid_sources:
            valid_sources = ["web_search", "wikipedia"]

        # Create ResearchJob for traceability & history
        job = ResearchJob(
            id=job_id,
            query=f"[Discovery] {original_objective or primary_query}",
            mode=mode or "general",
            status="running",
            progress=20.0,
            selected_sources=valid_sources,
            filters={"discovery_queries": queries},
            limit_per_source=limit_per_source,
            total_results_count=0
        )
        db.add(job)
        db.commit()

        # Collect from connectors concurrently across all queries
        tasks = []
        task_meta = []
        for sid in valid_sources:
            conn = get_connector(sid)
            if not conn:
                continue
            for q in queries[:3]: # execute up to top 3 discovery queries
                tasks.append(conn.search(q, limit=limit_per_source, filters={}))
                task_meta.append((sid, q))

        raw_batches = await asyncio.gather(*tasks, return_exceptions=True)

        all_normalized: List[ResearchResult] = []
        successful_sources = set()

        for idx, res in enumerate(raw_batches):
            sid, q = task_meta[idx]
            if isinstance(res, Exception):
                logger.warning(f"Error querying {sid} for query '{q}': {res}")
                log = CollectionLog(
                    job_id=job.id,
                    source_name=sid,
                    status="error",
                    message=f"Query '{q}' failed: {str(res)}",
                    items_collected=0,
                    duration_ms=0
                )
                db.add(log)
            else:
                raw_items = res or []
                if raw_items:
                    successful_sources.add(sid)
                for item in raw_items:
                    norm = Normalizer.normalize(item, job.id)
                    all_normalized.append(norm)

        # Deduplicate
        deduped = Deduplicator.deduplicate(all_normalized)

        # Rank by relevance against the original objective and primary query
        ranking_target = f"{original_objective or ''} {primary_query}".strip()
        ranked = Ranker.rank(ranking_target, deduped, mode=mode)

        # Multi-layer validation
        validated = await ResultValidator.validate_batch(ranked, db=db)

        # Persist results
        for r in validated:
            db.add(r)

        job.total_results_count = len(validated)
        job.status = "completed"
        job.progress = 100.0
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

        # Group results by resource/content type (prioritize verified/partially verified)
        grouped: Dict[str, List[Any]] = {}
        for r in validated:
            if r.validation_status in ("DELETED", "NOT_FOUND", "MISMATCH", "INACCESSIBLE"):
                continue
            ctype = r.content_type or "web"
            group_key = cls._map_to_resource_group(ctype, r.source_name)
            if group_key not in grouped:
                grouped[group_key] = []
            grouped[group_key].append(r)

        verified_count = sum(1 for r in validated if r.validation_status in ("VERIFIED", "PARTIALLY_VERIFIED"))
        summary = (
            f"Collected {verified_count} verified results ({len(validated)} total) across {len(successful_sources)} engines "
            f"matching your discovery objective."
        )

        return DiscoverySearchResponse(
            job_id=job_id,
            queries_executed=queries,
            total_results=len(ranked),
            results=ranked,
            grouped_by_type=grouped,
            summary=summary,
            sources_queried=valid_sources
        )

    @staticmethod
    def _map_to_resource_group(content_type: str, source_name: str) -> str:
        s = source_name.lower()
        c = content_type.lower()
        if "github" in s or c in ("repository", "code", "issue"):
            return "Repositories & Code"
        if "arxiv" in s or "openalex" in s or "crossref" in s or c in ("paper", "preprint", "journal"):
            return "Research Papers & Academic"
        if "openlibrary" in s or c in ("book", "edition"):
            return "Books & Literature"
        if "kaggle" in s or c in ("dataset", "notebook"):
            return "Datasets & Experiments"
        if "stack" in s or c in ("question", "answer"):
            return "Discussions & Q&A"
        if "wikipedia" in s:
            return "Knowledge Base & Concepts"
        if any(w in c for w in ("course", "tutorial", "learning", "education")):
            return "Courses & Tutorials"
        return "Web & Resources"

    @staticmethod
    def _clean_and_parse_json(text: str) -> Optional[Dict[str, Any]]:
        """Safely extract and parse JSON from model output."""
        try:
            return json.loads(text)
        except Exception:
            pass

        # Try regex search for markdown fenced json or general { ... }
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass

        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass

        return None
