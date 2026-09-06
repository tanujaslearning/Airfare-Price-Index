"""Unit tests for RobotsChecker and compliance logic."""

import pytest
import httpx
from urllib.robotparser import RobotFileParser
from scraper.base.robots_checker import RobotsChecker, RobotsInconclusiveException


@pytest.mark.asyncio
async def test_robots_checker_cache_and_rules():
    """Verify in-memory rule caching and path permission checking."""
    checker = RobotsChecker(cache_ttl_seconds=300)

    # Manually populate cache for a mock domain
    mock_parser = RobotFileParser()
    mock_parser.parse([
        "User-agent: *",
        "Disallow: /admin/",
        "Disallow: /private/api/",
        "Crawl-delay: 5",
        "Allow: /flights/",
    ])
    checker._cache["testairline.com"] = (mock_parser, 9999999999.0)

    # Allowed path
    allowed = await checker.is_allowed("https://testairline.com/flights/DEL-BOM")
    assert allowed is True

    # Disallowed path
    disallowed = await checker.is_allowed("https://testairline.com/admin/settings")
    assert disallowed is False

    # Crawl delay extraction
    delay = await checker.get_crawl_delay("https://testairline.com/flights")
    assert delay == 5.0

    # Clear cache test
    checker.clear_cache()
    assert "testairline.com" not in checker._cache


class _FakeAsyncClient:
    def __init__(self, response=None, exc=None, **kwargs):
        self.response = response
        self.exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url):
        if self.exc:
            raise self.exc
        return self.response


@pytest.mark.asyncio
async def test_robots_checker_fetches_allowed_policy(monkeypatch):
    checker = RobotsChecker(cache_ttl_seconds=0)
    response = httpx.Response(
        200,
        text="User-agent: *\nAllow: /flight-booking\nDisallow: /private\n",
    )
    monkeypatch.setattr("scraper.base.robots_checker.httpx.AsyncClient", lambda **kwargs: _FakeAsyncClient(response=response))

    assert await checker.is_allowed("https://example.com/flight-booking") is True


@pytest.mark.asyncio
async def test_robots_checker_fetches_disallowed_policy(monkeypatch):
    checker = RobotsChecker(cache_ttl_seconds=0)
    response = httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
    monkeypatch.setattr("scraper.base.robots_checker.httpx.AsyncClient", lambda **kwargs: _FakeAsyncClient(response=response))

    assert await checker.is_allowed("https://example.com/private/search") is False


@pytest.mark.asyncio
async def test_robots_checker_timeout_is_inconclusive(monkeypatch):
    checker = RobotsChecker(cache_ttl_seconds=0)
    monkeypatch.setattr(
        "scraper.base.robots_checker.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(exc=httpx.TimeoutException("timeout")),
    )

    with pytest.raises(RobotsInconclusiveException):
        await checker.is_allowed("https://example.com/flight-booking")


@pytest.mark.asyncio
async def test_robots_checker_http_failure_is_inconclusive(monkeypatch):
    checker = RobotsChecker(cache_ttl_seconds=0)
    response = httpx.Response(503, text="temporarily unavailable")
    monkeypatch.setattr("scraper.base.robots_checker.httpx.AsyncClient", lambda **kwargs: _FakeAsyncClient(response=response))

    with pytest.raises(RobotsInconclusiveException):
        await checker.is_allowed("https://example.com/flight-booking")


@pytest.mark.asyncio
async def test_robots_checker_malformed_response_is_inconclusive(monkeypatch):
    checker = RobotsChecker(cache_ttl_seconds=0)
    response = httpx.Response(200, text="<html>not robots</html>")
    monkeypatch.setattr("scraper.base.robots_checker.httpx.AsyncClient", lambda **kwargs: _FakeAsyncClient(response=response))

    with pytest.raises(RobotsInconclusiveException):
        await checker.is_allowed("https://example.com/flight-booking")
