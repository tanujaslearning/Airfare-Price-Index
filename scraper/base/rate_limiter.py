"""Async-friendly and thread-safe per-domain rate limiter."""

import asyncio
import logging
from typing import Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger("apix.scraper.ratelimit")


class AsyncRateLimiter:
    """Enforces configurable polite scraping intervals per domain."""

    def __init__(self, default_delay_seconds: float = 3.0, domain_delays: Optional[Dict[str, float]] = None):
        self.default_delay_seconds = default_delay_seconds
        self.domain_delays: Dict[str, float] = domain_delays or {}
        self._last_request_times: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    def _extract_domain(self, target: str) -> str:
        """Extracts netloc/domain key from URL or hostname."""
        if "://" in target:
            parsed = urlparse(target)
            return parsed.netloc or parsed.path
        return target.split("/")[0]

    def set_domain_delay(self, domain: str, delay_seconds: float) -> None:
        """Configures a custom delay interval for a specific domain."""
        clean_domain = self._extract_domain(domain)
        self.domain_delays[clean_domain] = max(0.0, delay_seconds)
        logger.debug("Configured rate-limit delay for %s: %.2fs", clean_domain, delay_seconds)

    def get_configured_delay(self, domain: str) -> float:
        """Returns effective delay for the target domain."""
        clean_domain = self._extract_domain(domain)
        return self.domain_delays.get(clean_domain, self.default_delay_seconds)

    async def wait(self, target: str, override_delay: Optional[float] = None) -> float:
        """Enforces rate limit for target domain, sleeping asynchronously if needed.
        
        Returns the duration in seconds that the coroutine slept.
        """
        domain = self._extract_domain(target)
        required_delay = override_delay if override_delay is not None else self.get_configured_delay(domain)

        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            last_time = self._last_request_times.get(domain, 0.0)
            elapsed = now - last_time
            sleep_duration = 0.0

            if elapsed < required_delay and last_time > 0.0:
                sleep_duration = required_delay - elapsed
                logger.debug("Rate-limiting [%s]: sleeping for %.2fs", domain, sleep_duration)

            # Record next request timestamp after expected sleep
            self._last_request_times[domain] = now + sleep_duration

        if sleep_duration > 0:
            await asyncio.sleep(sleep_duration)

        return sleep_duration

    def reset(self, domain: Optional[str] = None) -> None:
        """Resets rate limit timestamps for a specific domain or all domains."""
        if domain:
            clean_domain = self._extract_domain(domain)
            self._last_request_times.pop(clean_domain, None)
        else:
            self._last_request_times.clear()
