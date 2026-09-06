"""Robots.txt compliance checker with caching and crawl-delay extraction."""

import logging
import time
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import httpx

logger = logging.getLogger("apix.scraper.robots")


class RobotsDisallowedException(Exception):
    """Raised when access to a URL path is prohibited by the target domain's robots.txt."""
    pass


class RobotsInconclusiveException(Exception):
    """Raised when robots.txt permission cannot be established reliably."""
    pass


class RobotsChecker:
    """Thread-safe / async-friendly robots.txt checker with in-memory TTL caching."""

    def __init__(self, cache_ttl_seconds: int = 3600, default_user_agent: str = "APIx-Research-Bot/0.1"):
        self.cache_ttl_seconds = cache_ttl_seconds
        self.default_user_agent = default_user_agent
        # Cache mapping: netloc -> (RobotFileParser, timestamp)
        self._cache: Dict[str, Tuple[RobotFileParser, float]] = {}

    def _get_robots_url(self, target_url: str) -> Tuple[str, str]:
        """Extracts domain netloc and robots.txt full URL."""
        parsed = urlparse(target_url)
        scheme = parsed.scheme or "https"
        netloc = parsed.netloc
        if not netloc and "/" not in target_url:
            netloc = target_url
        robots_url = f"{scheme}://{netloc}/robots.txt"
        return netloc, robots_url

    async def get_parser(self, target_url: str) -> Optional[RobotFileParser]:
        """Retrieves or fetches the cached RobotFileParser for a domain."""
        netloc, robots_url = self._get_robots_url(target_url)
        now = time.time()

        if netloc in self._cache:
            parser, timestamp = self._cache[netloc]
            if now - timestamp < self.cache_ttl_seconds:
                return parser

        # Fetch and parse robots.txt asynchronously
        parser = RobotFileParser()
        parser.set_url(robots_url)
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(robots_url)
                if response.status_code == 200:
                    if not self._has_parseable_policy(response.text):
                        raise RobotsInconclusiveException(f"Robots.txt response is malformed or empty: {robots_url}")
                    parser.parse(response.text.splitlines())
                    logger.debug("Successfully fetched and parsed %s", robots_url)
                else:
                    raise RobotsInconclusiveException(
                        f"Robots.txt returned HTTP {response.status_code}; permission is inconclusive: {robots_url}"
                    )
        except RobotsInconclusiveException:
            raise
        except Exception as err:
            logger.warning("Failed to fetch %s (%s); permission is inconclusive", robots_url, err)
            raise RobotsInconclusiveException(f"Could not retrieve robots.txt reliably: {robots_url}") from err

        self._cache[netloc] = (parser, now)
        return parser

    async def is_allowed(self, target_url: str, user_agent: Optional[str] = None) -> bool:
        """Checks whether the requested URL can be fetched by the user agent."""
        ua = user_agent or self.default_user_agent
        try:
            parser = await self.get_parser(target_url)
            if parser is None:
                raise RobotsInconclusiveException(f"Robots.txt permission is inconclusive: {target_url}")
            return parser.can_fetch(ua, target_url)
        except RobotsInconclusiveException:
            raise
        except Exception as err:
            logger.error("Error evaluating robots.txt rule for %s: %s", target_url, err)
            raise RobotsInconclusiveException(f"Could not evaluate robots.txt rule: {target_url}") from err

    async def get_crawl_delay(self, target_url: str, user_agent: Optional[str] = None) -> Optional[float]:
        """Extracts configured Crawl-Delay directive for the user agent if present."""
        ua = user_agent or self.default_user_agent
        try:
            parser = await self.get_parser(target_url)
            if parser is None:
                return None
            
            # Python's RobotFileParser supports crawl_delay(useragent)
            delay = parser.crawl_delay(ua)
            if delay is not None:
                return float(delay)
            # Check wildcard user-agent
            delay_wildcard = parser.crawl_delay("*")
            return float(delay_wildcard) if delay_wildcard is not None else None
        except RobotsInconclusiveException:
            raise
        except Exception as err:
            logger.debug("Could not determine crawl-delay for %s: %s", target_url, err)
            return None

    def clear_cache(self) -> None:
        """Clears in-memory parser cache."""
        self._cache.clear()

    @staticmethod
    def _has_parseable_policy(content: str) -> bool:
        """Returns true when robots.txt contains at least one user-agent directive."""
        return any(line.strip().lower().startswith("user-agent:") for line in content.splitlines())
