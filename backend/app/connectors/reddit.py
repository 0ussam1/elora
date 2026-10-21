import httpx
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from app.connectors.base import BaseConnector, RawResult
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class RedditConnector(BaseConnector):
    """
    Reddit API connector using official OAuth2 Application-Only flow (client_credentials).
    
    Status states:
    - not_configured: Missing client_id or client_secret in .env
    - pending_authorization: OAuth application created on Reddit but access denied or pending approval
    - configured: Credentials present, connectivity not yet verified
    - connected: Successfully authenticated and verified lightweight query
    - rate_limited: Reddit rate limits (HTTP 429) encountered
    - error: Unexpected error during authorization or communication
    """
    source_id = "reddit"
    name = "Reddit Community Discussions"
    category = "community"
    requires_auth = True
    supported_content_types = ["post", "discussion"]

    TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
    OAUTH_API_BASE = "https://oauth.reddit.com"

    def __init__(self):
        self._cached_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._last_diagnostic: Optional[Dict[str, Any]] = None
        self._rate_limited_until: float = 0.0

    @property
    def rate_limit_per_minute(self) -> int:
        return settings.REDDIT_RATE_LIMIT_PER_MINUTE

    def is_configured(self) -> bool:
        return bool(settings.REDDIT_CLIENT_ID and settings.REDDIT_CLIENT_SECRET)

    async def _get_access_token(self, force_refresh: bool = False) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Retrieves or reuses a cached OAuth2 client_credentials token.
        Returns (token, status, error_message).
        """
        if not self.is_configured():
            return None, "not_configured", "Missing REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET in .env"

        # Check in-memory cache with 60s buffer
        now = time.time()
        if not force_refresh and self._cached_token and now < (self._token_expires_at - 60):
            return self._cached_token, "connected", None

        # Check if currently rate limited
        if now < self._rate_limited_until:
            wait_sec = int(self._rate_limited_until - now)
            return None, "rate_limited", f"Reddit rate limit active. Please retry in {wait_sec}s."

        auth = httpx.BasicAuth(settings.REDDIT_CLIENT_ID.strip(), settings.REDDIT_CLIENT_SECRET.strip())
        headers = {
            "User-Agent": settings.REDDIT_USER_AGENT
        }
        data = {
            "grant_type": "client_credentials"
        }

        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    self.TOKEN_URL,
                    auth=auth,
                    data=data,
                    headers=headers
                )

                if response.status_code == 401:
                    logger.warning("Reddit OAuth failed: 401 Unauthorized (Invalid client_id or secret)")
                    return None, "pending_authorization", "Invalid credentials or unauthorized application. Verify REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET."

                if response.status_code == 403:
                    logger.warning("Reddit OAuth failed: 403 Forbidden (Access Denied / Pending Approval)")
                    return None, "pending_authorization", "Access denied by Reddit. Check if your Reddit developer application requires manual approval or developer agreement."

                if response.status_code == 429:
                    retry_after = int(response.headers.get("retry-after", "60"))
                    self._rate_limited_until = time.time() + retry_after
                    logger.warning(f"Reddit OAuth rate limited: 429. Retry after {retry_after}s")
                    return None, "rate_limited", f"Reddit token endpoint rate limited. Retry after {retry_after}s"

                if response.status_code != 200:
                    logger.error(f"Reddit OAuth unexpected status {response.status_code}")
                    return None, "error", f"Reddit returned HTTP {response.status_code}"

                token_data = response.json()
                if "error" in token_data:
                    err_msg = token_data.get("error", "Unknown OAuth error")
                    return None, "pending_authorization", f"OAuth error: {err_msg}"

                token = token_data.get("access_token")
                expires_in = token_data.get("expires_in", 3600)

                self._cached_token = token
                self._token_expires_at = now + expires_in
                return token, "connected", None

        except httpx.TimeoutException:
            logger.warning("Reddit token request timed out")
            return None, "error", "Connection timed out while contacting Reddit OAuth"
        except httpx.ConnectError:
            logger.warning("Reddit connection error")
            return None, "error", "Network error: Unable to connect to reddit.com"
        except Exception as e:
            logger.error(f"Unexpected error getting Reddit token: {e}")
            return None, "error", "Unexpected error during Reddit authentication"

    async def test_connection(self) -> Dict[str, Any]:
        """
        Runs comprehensive diagnostic:
        1. Checks configuration
        2. Acquires OAuth token
        3. Makes lightweight read request to /api/v1/me or /subreddits/popular
        4. Verifies response validity and rate-limit headers
        """
        now_str = datetime.utcnow().isoformat()
        if not self.is_configured():
            diag = {
                "configured": False,
                "authorized": False,
                "connected": False,
                "status": "not_configured",
                "message": "Missing REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET in backend .env",
                "last_checked_at": now_str,
                "details": {
                    "client_id_set": bool(settings.REDDIT_CLIENT_ID),
                    "client_secret_set": bool(settings.REDDIT_CLIENT_SECRET),
                    "user_agent": settings.REDDIT_USER_AGENT
                }
            }
            self._last_diagnostic = diag
            return diag

        token, status, err_msg = await self._get_access_token(force_refresh=True)
        if not token:
            diag = {
                "configured": True,
                "authorized": False,
                "connected": False,
                "status": status,
                "message": err_msg or "Failed to obtain Reddit access token",
                "last_checked_at": now_str,
                "details": {
                    "client_id_set": True,
                    "client_secret_set": True
                }
            }
            self._last_diagnostic = diag
            return diag

        # Perform lightweight connectivity probe: check /subreddits/popular or search with limit=1
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": settings.REDDIT_USER_AGENT
        }

        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                probe_resp = await client.get(
                    f"{self.OAUTH_API_BASE}/subreddits/popular",
                    params={"limit": 1},
                    headers=headers
                )

                rate_remaining = probe_resp.headers.get("x-ratelimit-remaining")
                rate_reset = probe_resp.headers.get("x-ratelimit-reset")

                if probe_resp.status_code == 200:
                    diag = {
                        "configured": True,
                        "authorized": True,
                        "connected": True,
                        "status": "connected",
                        "message": "Successfully authenticated and connected to Reddit API",
                        "last_checked_at": now_str,
                        "details": {
                            "ratelimit_remaining": rate_remaining,
                            "ratelimit_reset_seconds": rate_reset
                        }
                    }
                    self._last_diagnostic = diag
                    return diag

                elif probe_resp.status_code == 429:
                    diag = {
                        "configured": True,
                        "authorized": True,
                        "connected": False,
                        "status": "rate_limited",
                        "message": "Reddit API rate limit exceeded. Please wait before retrying.",
                        "last_checked_at": now_str
                    }
                    self._last_diagnostic = diag
                    return diag

                elif probe_resp.status_code in (401, 403):
                    diag = {
                        "configured": True,
                        "authorized": False,
                        "connected": False,
                        "status": "pending_authorization",
                        "message": f"Reddit API rejected request (HTTP {probe_resp.status_code}). Application permission may be restricted.",
                        "last_checked_at": now_str
                    }
                    self._last_diagnostic = diag
                    return diag
                else:
                    diag = {
                        "configured": True,
                        "authorized": True,
                        "connected": False,
                        "status": "error",
                        "message": f"Reddit API returned HTTP {probe_resp.status_code}",
                        "last_checked_at": now_str
                    }
                    self._last_diagnostic = diag
                    return diag

        except Exception as e:
            diag = {
                "configured": True,
                "authorized": True,
                "connected": False,
                "status": "error",
                "message": f"Network error during Reddit connectivity test: {str(e)}",
                "last_checked_at": now_str
            }
            self._last_diagnostic = diag
            return diag

    def check_health(self) -> Dict[str, Any]:
        """
        Synchronous / light health representation for sources listing.
        Does not perform blocking network calls.
        """
        if not self.is_configured():
            return {
                "status": "not_configured",
                "auth_status": "not_configured",
                "message": "Missing REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in .env"
            }

        # If we have a cached diagnostic, reuse its verified state
        if self._last_diagnostic:
            return {
                "status": self._last_diagnostic.get("status", "configured"),
                "auth_status": "authorized" if self._last_diagnostic.get("authorized") else self._last_diagnostic.get("status"),
                "message": self._last_diagnostic.get("message", "Reddit OAuth configured"),
                "last_checked_at": self._last_diagnostic.get("last_checked_at")
            }

        # Credentials present but connectivity diagnostic has not been run yet
        return {
            "status": "configured",
            "auth_status": "configured",
            "message": "Reddit OAuth credentials configured (ready for connection test)"
        }

    async def search(self, query: str, limit: int = 15, filters: Optional[Dict[str, Any]] = None) -> List[RawResult]:
        """
        Executes search on Reddit's /search endpoint only if authorized and connected.
        Supports post title, content selftext, score, comments count, and permalink.
        """
        token, status, err_msg = await self._get_access_token()
        if not token:
            logger.info(f"Reddit search skipped: {err_msg} (status: {status})")
            return []

        results: List[RawResult] = []
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": settings.REDDIT_USER_AGENT
        }
        params = {
            "q": query,
            "limit": min(limit, 25),
            "sort": "relevance",
            "type": "link" # Searching posts
        }

        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.get(
                    f"{self.OAUTH_API_BASE}/search",
                    params=params,
                    headers=headers
                )

                if resp.status_code == 429:
                    logger.warning("Reddit search rate limited (429)")
                    return []
                elif resp.status_code in (401, 403):
                    logger.warning(f"Reddit search access denied ({resp.status_code})")
                    return []
                elif resp.status_code != 200:
                    logger.error(f"Reddit search returned status {resp.status_code}")
                    return []

                data = resp.json()
                for post in data.get("data", {}).get("children", []):
                    pdata = post.get("data", {})
                    title = pdata.get("title", "")
                    selftext = pdata.get("selftext", "")
                    permalink = pdata.get("permalink", "")
                    url = f"https://www.reddit.com{permalink}" if permalink else pdata.get("url", "")
                    
                    snippet = (selftext[:280] + "...") if len(selftext) > 280 else selftext
                    if not snippet:
                        snippet = f"Discussion in r/{pdata.get('subreddit')} with {pdata.get('score', 0)} upvotes and {pdata.get('num_comments', 0)} comments."

                    created_utc = pdata.get("created_utc")
                    pub = datetime.fromtimestamp(created_utc) if created_utc else None

                    results.append(
                        RawResult(
                            source_name="reddit",
                            source_item_id=str(pdata.get("id")),
                            title=title,
                            content_snippet=snippet,
                            source_url=url,
                            author=pdata.get("author"),
                            published_at=pub,
                            content_type="discussion",
                            engagement_metrics={
                                "score": pdata.get("score", 0),
                                "num_comments": pdata.get("num_comments", 0),
                                "subreddit": pdata.get("subreddit")
                            },
                            metadata={
                                "subreddit": pdata.get("subreddit"),
                                "upvote_ratio": pdata.get("upvote_ratio")
                            }
                        )
                    )

        except Exception as e:
            logger.error(f"Error during Reddit search execution: {e}")

        return results
