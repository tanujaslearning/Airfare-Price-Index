"""Unit tests for AsyncRateLimiter."""

import asyncio
import pytest
import time
from scraper.base.rate_limiter import AsyncRateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_initial_request_no_delay():
    """Verify first request to a new domain executes immediately without delay."""
    limiter = AsyncRateLimiter(default_delay_seconds=2.0)
    slept = await limiter.wait("https://air.example.com/search")
    assert slept == 0.0


@pytest.mark.asyncio
async def test_rate_limiter_subsequent_request_delay():
    """Verify rapid consecutive requests to the same domain are rate-limited."""
    limiter = AsyncRateLimiter(default_delay_seconds=0.1)
    # First request
    await limiter.wait("https://api.airline.com/quote")

    # Second request immediately afterwards
    slept = await limiter.wait("https://api.airline.com/quote")
    assert slept > 0.05
    assert slept <= 0.11


@pytest.mark.asyncio
async def test_rate_limiter_multi_domain_isolation():
    """Verify rate limits for different domains operate independently."""
    limiter = AsyncRateLimiter(default_delay_seconds=0.2)
    # Request to Domain A
    await limiter.wait("https://domain-a.com/search")

    # Request to Domain B immediately afterwards should not wait for Domain A
    slept_b = await limiter.wait("https://domain-b.com/search")
    assert slept_b == 0.0


@pytest.mark.asyncio
async def test_rate_limiter_custom_domain_override():
    """Verify custom domain delays and override parameters."""
    limiter = AsyncRateLimiter(default_delay_seconds=1.0)
    limiter.set_domain_delay("slow-airline.com", 0.08)
    assert limiter.get_configured_delay("slow-airline.com") == 0.08

    await limiter.wait("https://slow-airline.com/search")
    slept = await limiter.wait("https://slow-airline.com/search")
    assert slept > 0.04
    assert slept <= 0.09

    # Test reset
    limiter.reset("slow-airline.com")
    slept_after_reset = await limiter.wait("https://slow-airline.com/search")
    assert slept_after_reset == 0.0
