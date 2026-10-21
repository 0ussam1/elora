from typing import Dict, List, Type
from app.connectors.base import BaseConnector
from app.connectors.hackernews import HackerNewsConnector
from app.connectors.web_search import WebSearchConnector
from app.connectors.github import GitHubConnector
from app.connectors.stack_exchange import StackExchangeConnector
from app.connectors.arxiv import ArxivConnector
from app.connectors.wikipedia import WikipediaConnector
from app.connectors.reddit import RedditConnector
from app.connectors.kaggle import KaggleConnector
from app.connectors.internet_archive import InternetArchiveConnector
from app.connectors.openalex import OpenAlexConnector
from app.connectors.crossref import CrossrefConnector
from app.connectors.openlibrary import OpenLibraryConnector

CONNECTOR_REGISTRY: Dict[str, BaseConnector] = {
    "hackernews": HackerNewsConnector(),
    "web_search": WebSearchConnector(),
    "github": GitHubConnector(),
    "stackexchange": StackExchangeConnector(),
    "arxiv": ArxivConnector(),
    "wikipedia": WikipediaConnector(),
    "reddit": RedditConnector(),
    "kaggle": KaggleConnector(),
    "internet_archive": InternetArchiveConnector(),
    "openalex": OpenAlexConnector(),
    "crossref": CrossrefConnector(),
    "openlibrary": OpenLibraryConnector(),
}

def get_connector(source_id: str) -> BaseConnector | None:
    return CONNECTOR_REGISTRY.get(source_id)

def list_all_sources() -> List[Dict]:
    sources = []
    for sid, conn in CONNECTOR_REGISTRY.items():
        health = conn.check_health()
        rate_limit = getattr(conn, "rate_limit_per_minute", 30)
        sources.append({
            "id": sid,
            "name": conn.name,
            "category": conn.category,
            "is_enabled": True,
            "requires_auth": conn.requires_auth,
            "auth_status": health.get("auth_status", "not_required"),
            "health_status": health.get("status", "operational"),
            "supported_content_types": conn.supported_content_types,
            "rate_limit_per_minute": rate_limit,
            "message": health.get("message", "")
        })
    return sources
