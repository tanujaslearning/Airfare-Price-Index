"""Deterministic mock airfare scraper generating realistic multi-route, multi-carrier quotes."""

import asyncio
import logging
import random
from datetime import datetime, date, time, timedelta, timezone
from typing import Any, List, Dict, Optional, Tuple

from backend.app.data.route_basket import APPROVED_ADVANCE_WINDOWS, ROUTE_PROFILES
from backend.app.schemas.quote import RawAirfareQuoteCreate
from scraper.base.base_scraper import BaseFlightScraper, ScraperConfig

logger = logging.getLogger("apix.scraper.mock")

# Standard advance booking windows (in days)
ADVANCE_WINDOWS = list(APPROVED_ADVANCE_WINDOWS)

# Carrier characteristics & pricing multipliers
CARRIER_PROFILES: Dict[str, Dict[str, Any]] = {
    "6E": {
        "name": "IndiGo Airlines",
        "multiplier": 1.00,
        "flights_per_day": 3,
        "flight_prefix": "6E",
    },
    "AI": {
        "name": "Air India",
        "multiplier": 1.10,
        "flights_per_day": 2,
        "flight_prefix": "AI",
    },
    "SG": {
        "name": "SpiceJet",
        "multiplier": 0.95,
        "flights_per_day": 2,
        "flight_prefix": "SG",
    },
    "QP": {
        "name": "Akasa Air",
        "multiplier": 0.92,
        "flights_per_day": 2,
        "flight_prefix": "QP",
    },
}

# Departure schedule templates (hour, minute, flight duration hours)
DAILY_SCHEDULE_SLOTS: List[Tuple[int, int, float]] = [
    (6, 15, 2.2),   # Early morning
    (9, 30, 2.2),   # Morning business
    (14, 45, 2.3),  # Afternoon
    (18, 20, 2.4),  # Evening peak
    (21, 10, 2.1),  # Late evening
]


class MockFlightScraper(BaseFlightScraper):
    """Generates synthetic, economically realistic airfare quotes without web requests."""

    def __init__(
        self,
        config: Optional[ScraperConfig] = None,
        random_seed: Optional[int] = 42,
    ):
        cfg = config or ScraperConfig(
            source_name="MockSyntheticEngine",
            base_url="https://mock.apix.internal",
            rate_limit_delay_seconds=0.0,
        )
        super().__init__(cfg)
        self.random_seed = random_seed
        self._rng = random.Random(random_seed)

    def set_seed(self, seed: Optional[int]) -> None:
        """Sets random seed for reproducible benchmark datasets."""
        self.random_seed = seed
        self._rng = random.Random(seed)

    def _calculate_advance_multiplier(self, advance_days: int) -> float:
        """Calculates dynamic pricing curve multiplier based on advance purchase window.
        
        - T+1 (Urgent): 1.60x - 2.10x (high price, higher volatility)
        - T+7 (Short): 1.25x - 1.45x
        - T+15 (Medium): 1.05x - 1.18x
        - T+30 (Baseline): 0.95x - 1.05x
        - T+45 (Far advance discount): 0.85x - 0.95x
        """
        if advance_days <= 1:
            base_m = 1.75
            jitter = self._rng.uniform(-0.15, 0.35)
        elif advance_days <= 7:
            base_m = 1.35
            jitter = self._rng.uniform(-0.08, 0.12)
        elif advance_days <= 15:
            base_m = 1.12
            jitter = self._rng.uniform(-0.05, 0.08)
        elif advance_days <= 30:
            base_m = 1.00
            jitter = self._rng.uniform(-0.04, 0.05)
        else:
            base_m = 0.90
            jitter = self._rng.uniform(-0.05, 0.05)

        return max(0.70, base_m + jitter)

    def generate_single_quote(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        carrier_code: str,
        flight_slot_idx: int,
        route_id: int = 1,
        source_id: Optional[int] = None,
        cabin_class: str = "ECONOMY",
        scraped_at: Optional[datetime] = None,
    ) -> RawAirfareQuoteCreate:
        """Generates a single realistic quote adhering to the economic curve."""
        route_key = f"{origin}-{destination}"
        rev_route_key = f"{destination}-{origin}"
        route_prof = ROUTE_PROFILES.get(route_key) or ROUTE_PROFILES.get(rev_route_key) or {"distance_km": 1000.0, "base_fare": 4000.0}
        carrier_prof = CARRIER_PROFILES.get(carrier_code, {"multiplier": 1.0, "flight_prefix": carrier_code})

        now_utc = scraped_at or datetime.now(timezone.utc)
        advance_window_days = max(0, (departure_date - now_utc.date()).days)

        # Economic curve calculation
        advance_multiplier = self._calculate_advance_multiplier(advance_window_days)
        carrier_multiplier = carrier_prof["multiplier"]

        # Base fare calculation with minor stochastic noise
        noise = self._rng.uniform(0.96, 1.04)
        raw_base_fare = route_prof["base_fare"] * carrier_multiplier * advance_multiplier * noise

        # Taxes and regulatory fees (UDF, Fuel Surcharge, GST ~ 22% of base fare + fixed ~650 INR)
        tax_pct = self._rng.uniform(0.18, 0.24)
        fixed_fees = 650.0
        calculated_taxes = round((raw_base_fare * tax_pct) + fixed_fees, 2)
        calculated_base = round(raw_base_fare, 2)
        total_fare = round(calculated_base + calculated_taxes, 2)

        # Flight schedule timing
        slot = DAILY_SCHEDULE_SLOTS[flight_slot_idx % len(DAILY_SCHEDULE_SLOTS)]
        dep_time = time(slot[0], slot[1])
        dep_dt = datetime.combine(departure_date, dep_time, tzinfo=timezone.utc)
        flight_duration_hrs = slot[2]
        arr_dt = dep_dt + timedelta(hours=flight_duration_hrs)

        flight_num_suffix = 100 + (hash(route_key) % 800) + (flight_slot_idx * 10)
        flight_number = f"{carrier_prof['flight_prefix']}-{abs(flight_num_suffix)}"

        return RawAirfareQuoteCreate(
            source_id=source_id,
            route_id=route_id,
            flight_number=flight_number,
            departure_datetime=dep_dt,
            arrival_datetime=arr_dt,
            advance_window_days=advance_window_days,
            base_fare=calculated_base,
            taxes_fees=calculated_taxes,
            total_fare=total_fare,
            cabin_class=cabin_class,
            scraped_at=now_utc,
        )

    async def fetch_quotes(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str = "ECONOMY",
        route_id: int = 1,
        source_id: Optional[int] = None,
        advance_window_days: Optional[int] = None,
    ) -> List[RawAirfareQuoteCreate]:
        """Generates mock quotes across all active carriers for given route and date."""
        quotes: List[RawAirfareQuoteCreate] = []

        slot_counter = 0
        for code, prof in CARRIER_PROFILES.items():
            num_flights = prof["flights_per_day"]
            for i in range(num_flights):
                quote = self.generate_single_quote(
                    origin=origin,
                    destination=destination,
                    departure_date=departure_date,
                    carrier_code=code,
                    flight_slot_idx=slot_counter,
                    route_id=route_id,
                    source_id=source_id,
                    cabin_class=cabin_class,
                )
                quotes.append(quote)
                slot_counter += 1

        logger.debug("Generated %d synthetic quotes for route %s-%s on %s", len(quotes), origin, destination, departure_date)
        return quotes

    async def generate_complete_matrix(
        self,
        collection_date: date,
        routes: List[Dict[str, Any]],
        carrier_id_map: Optional[Dict[str, int]] = None,
    ) -> List[RawAirfareQuoteCreate]:
        """Generates quotes for all routes across all 5 advance booking windows (T+1, T+7, T+15, T+30, T+45)."""
        carrier_map = carrier_id_map or {}
        all_quotes: List[RawAirfareQuoteCreate] = []

        for route in routes:
            origin = route["origin_code"]
            dest = route["destination_code"]
            route_id = route.get("id", 1)

            for adv_days in ADVANCE_WINDOWS:
                dep_date = collection_date + timedelta(days=adv_days)
                
                slot_counter = 0
                for code, prof in CARRIER_PROFILES.items():
                    s_id = carrier_map.get(code, 1)
                    num_flights = prof["flights_per_day"]
                    for _ in range(num_flights):
                        quote = self.generate_single_quote(
                            origin=origin,
                            destination=dest,
                            departure_date=dep_date,
                            carrier_code=code,
                            flight_slot_idx=slot_counter,
                            route_id=route_id,
                            source_id=s_id,
                            scraped_at=datetime.combine(collection_date, time(10, 0), tzinfo=timezone.utc),
                        )
                        all_quotes.append(quote)
                        slot_counter += 1

        logger.info("Generated comprehensive matrix: %d quotes across %d routes and %d windows", len(all_quotes), len(routes), len(ADVANCE_WINDOWS))
        return all_quotes


if __name__ == "__main__":
    import json

    async def run_standalone_demo():
        scraper = MockFlightScraper(random_seed=123)
        sample_quotes = await scraper.fetch_quotes(
            origin="DEL",
            destination="BOM",
            departure_date=date.today() + timedelta(days=7),
            route_id=1,
            source_id=1,
        )
        print(f"=== Standalone Mock Scraper Generated {len(sample_quotes)} Quotes for DEL-BOM (T+7) ===")
        for q in sample_quotes[:4]:
            print(f"- Flight: {q.flight_number} | Dep: {q.departure_datetime.strftime('%H:%M')} | Base: INR {q.base_fare:,.2f} | Taxes: INR {q.taxes_fees:,.2f} | Total: INR {q.total_fare:,.2f}")

    asyncio.run(run_standalone_demo())
