from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel

class RawResult(BaseModel):
    source_name: str
    source_item_id: Optional[str] = None
    title: str
    content_snippet: Optional[str] = None
    source_url: str
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    content_type: str = "article"
    engagement_metrics: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}

class BaseConnector(ABC):
    source_id: str
    name: str
    category: str
    requires_auth: bool = False
    supported_content_types: List[str] = []
    
    @abstractmethod
    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        """Perform search and return normalized RawResult items"""
        pass

    @abstractmethod
    def check_health(self) -> Dict[str, Any]:
        """Check availability and authorization status"""
        pass
