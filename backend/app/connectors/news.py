"""
ELORA News Source Connectors.

Provides:
  - NewsConnector: Unified aggregator across all verified international news feeds
  - BBCNewsConnector: BBC News wire & specialized categories
  - AlJazeeraConnector: Al Jazeera English & Arabic
  - DeutscheWelleConnector: Deutsche Welle English & Arabic
  - France24Connector: France 24 English, French, & Arabic
  - TheGuardianConnector: The Guardian World, Tech & Business
  - EuronewsConnector: Euronews European & International wire
  - SkyNewsConnector: Sky News UK & International wire

All connectors search the local SQLite news index without blocking HTTP calls,
respecting the non-blocking architecture, with automatic fallback and health monitoring.
"""
from typing import List, Dict, Any, Optional
from app.connectors.base import BaseConnector, RawResult
from app.services.news_service import NewsService
from app.database.session import SessionLocal


class NewsConnector(BaseConnector):
    """Unified international news aggregator querying all indexed publisher feeds."""
    source_id = "news"
    name = "International News (BBC, Al Jazeera, DW, France 24, Guardian, Sky, etc.)"
    category = "news"
    requires_auth = False
    supported_content_types = ["news", "article"]
    rate_limit_per_minute = 120

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        return await NewsService.search_indexed_news(query=query, limit=limit, filters=filters)

    def check_health(self) -> Dict[str, Any]:
        with SessionLocal() as db:
            return NewsService.get_source_health(db)


class BBCNewsConnector(BaseConnector):
    """BBC News specialized wire connector."""
    source_id = "bbc_news"
    name = "BBC News"
    category = "news"
    requires_auth = False
    supported_content_types = ["news", "article"]
    rate_limit_per_minute = 60

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        f = dict(filters or {})
        f["publisher"] = "BBC News"
        return await NewsService.search_indexed_news(query=query, limit=limit, filters=f)

    def check_health(self) -> Dict[str, Any]:
        with SessionLocal() as db:
            from app.models.database import NewsFeed
            feeds = db.query(NewsFeed).filter(NewsFeed.publisher == "BBC News").all()
            op = sum(1 for f in feeds if f.health_status == "operational" and f.is_enabled)
            return {
                "status": "operational" if op > 0 else "degraded",
                "auth_status": "not_required",
                "message": f"BBC News feeds operational ({op}/{len(feeds)} channels)"
            }


class AlJazeeraConnector(BaseConnector):
    """Al Jazeera Media Network wire connector (EN & AR)."""
    source_id = "al_jazeera"
    name = "Al Jazeera"
    category = "news"
    requires_auth = False
    supported_content_types = ["news", "article"]
    rate_limit_per_minute = 60

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        f = dict(filters or {})
        f["publisher"] = "Al Jazeera"
        return await NewsService.search_indexed_news(query=query, limit=limit, filters=f)

    def check_health(self) -> Dict[str, Any]:
        with SessionLocal() as db:
            from app.models.database import NewsFeed
            feeds = db.query(NewsFeed).filter(NewsFeed.publisher == "Al Jazeera").all()
            op = sum(1 for f in feeds if f.health_status == "operational" and f.is_enabled)
            return {
                "status": "operational" if op > 0 else "degraded",
                "auth_status": "not_required",
                "message": f"Al Jazeera feeds operational ({op}/{len(feeds)} channels)"
            }


class DeutscheWelleConnector(BaseConnector):
    """Deutsche Welle (DW) international wire connector (EN & AR)."""
    source_id = "deutsche_welle"
    name = "Deutsche Welle (DW)"
    category = "news"
    requires_auth = False
    supported_content_types = ["news", "article"]
    rate_limit_per_minute = 60

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        f = dict(filters or {})
        f["publisher"] = "Deutsche Welle"
        return await NewsService.search_indexed_news(query=query, limit=limit, filters=f)

    def check_health(self) -> Dict[str, Any]:
        with SessionLocal() as db:
            from app.models.database import NewsFeed
            feeds = db.query(NewsFeed).filter(NewsFeed.publisher == "Deutsche Welle").all()
            op = sum(1 for f in feeds if f.health_status == "operational" and f.is_enabled)
            return {
                "status": "operational" if op > 0 else "degraded",
                "auth_status": "not_required",
                "message": f"Deutsche Welle feeds operational ({op}/{len(feeds)} channels)"
            }


class France24Connector(BaseConnector):
    """France 24 multilingual international news connector (EN, FR, AR)."""
    source_id = "france24"
    name = "France 24"
    category = "news"
    requires_auth = False
    supported_content_types = ["news", "article"]
    rate_limit_per_minute = 60

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        f = dict(filters or {})
        f["publisher"] = "France 24"
        return await NewsService.search_indexed_news(query=query, limit=limit, filters=f)

    def check_health(self) -> Dict[str, Any]:
        with SessionLocal() as db:
            from app.models.database import NewsFeed
            feeds = db.query(NewsFeed).filter(NewsFeed.publisher == "France 24").all()
            op = sum(1 for f in feeds if f.health_status == "operational" and f.is_enabled)
            return {
                "status": "operational" if op > 0 else "degraded",
                "auth_status": "not_required",
                "message": f"France 24 multilingual feeds operational ({op}/{len(feeds)} channels)"
            }


class TheGuardianConnector(BaseConnector):
    """The Guardian international news connector."""
    source_id = "the_guardian"
    name = "The Guardian"
    category = "news"
    requires_auth = False
    supported_content_types = ["news", "article"]
    rate_limit_per_minute = 60

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        f = dict(filters or {})
        f["publisher"] = "The Guardian"
        return await NewsService.search_indexed_news(query=query, limit=limit, filters=f)

    def check_health(self) -> Dict[str, Any]:
        with SessionLocal() as db:
            from app.models.database import NewsFeed
            feeds = db.query(NewsFeed).filter(NewsFeed.publisher == "The Guardian").all()
            op = sum(1 for f in feeds if f.health_status == "operational" and f.is_enabled)
            return {
                "status": "operational" if op > 0 else "degraded",
                "auth_status": "not_required",
                "message": f"The Guardian feeds operational ({op}/{len(feeds)} channels)"
            }


class EuronewsConnector(BaseConnector):
    """Euronews international news connector."""
    source_id = "euronews"
    name = "Euronews"
    category = "news"
    requires_auth = False
    supported_content_types = ["news", "article"]
    rate_limit_per_minute = 60

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        f = dict(filters or {})
        f["publisher"] = "Euronews"
        return await NewsService.search_indexed_news(query=query, limit=limit, filters=f)

    def check_health(self) -> Dict[str, Any]:
        with SessionLocal() as db:
            from app.models.database import NewsFeed
            feeds = db.query(NewsFeed).filter(NewsFeed.publisher == "Euronews").all()
            op = sum(1 for f in feeds if f.health_status == "operational" and f.is_enabled)
            return {
                "status": "operational" if op > 0 else "degraded",
                "auth_status": "not_required",
                "message": f"Euronews feeds operational ({op}/{len(feeds)} channels)"
            }


class SkyNewsConnector(BaseConnector):
    """Sky News international news connector."""
    source_id = "sky_news"
    name = "Sky News"
    category = "news"
    requires_auth = False
    supported_content_types = ["news", "article"]
    rate_limit_per_minute = 60

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        f = dict(filters or {})
        f["publisher"] = "Sky News"
        return await NewsService.search_indexed_news(query=query, limit=limit, filters=f)

    def check_health(self) -> Dict[str, Any]:
        with SessionLocal() as db:
            from app.models.database import NewsFeed
            feeds = db.query(NewsFeed).filter(NewsFeed.publisher == "Sky News").all()
            op = sum(1 for f in feeds if f.health_status == "operational" and f.is_enabled)
            return {
                "status": "operational" if op > 0 else "degraded",
                "auth_status": "not_required",
                "message": f"Sky News feeds operational ({op}/{len(feeds)} channels)"
            }
