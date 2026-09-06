"""Central APIx prototype route basket and booking-window configuration."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Sequence


@dataclass(frozen=True)
class ApprovedRoute:
    """One approved APIx route with seed and baseline metadata."""

    origin_code: str
    destination_code: str
    distance_km: float
    dgca_weight: float
    baseline_fare: float
    is_active: bool = True

    @property
    def route_code(self) -> str:
        return f"{self.origin_code}-{self.destination_code}"

    def seed_dict(self) -> Dict[str, object]:
        return {
            "origin_code": self.origin_code,
            "destination_code": self.destination_code,
            "distance_km": self.distance_km,
            "dgca_weight": self.dgca_weight,
            "is_active": self.is_active,
        }


@dataclass(frozen=True)
class RouteWindowTarget:
    """A planned route/window cell for a daily collection run."""

    route_code: str
    advance_window_days: int
    departure_date: date


APPROVED_ROUTE_BASKET = (
    ApprovedRoute("DEL", "BOM", 1148.0, 0.25, 4200.0),
    ApprovedRoute("DEL", "BLR", 1740.0, 0.20, 5400.0),
    ApprovedRoute("BOM", "BLR", 842.0, 0.18, 3600.0),
    ApprovedRoute("DEL", "CCU", 1305.0, 0.14, 4600.0),
    ApprovedRoute("BLR", "HYD", 502.0, 0.12, 2800.0),
    ApprovedRoute("MAA", "DEL", 1757.0, 0.11, 5500.0),
)

APPROVED_ROUTE_CODES = tuple(route.route_code for route in APPROVED_ROUTE_BASKET)
APPROVED_ADVANCE_WINDOWS = (1, 7, 15, 30, 45)
APPROVED_ROUTE_WINDOW_COUNT = len(APPROVED_ROUTE_CODES) * len(APPROVED_ADVANCE_WINDOWS)

DEFAULT_ROUTE_BASELINES: Dict[str, float] = {
    route.route_code: route.baseline_fare
    for route in APPROVED_ROUTE_BASKET
}

ROUTE_PROFILES: Dict[str, Dict[str, float]] = {
    route.route_code: {
        "distance_km": route.distance_km,
        "base_fare": route.baseline_fare,
    }
    for route in APPROVED_ROUTE_BASKET
}


def normalize_route_code(route_code: str) -> str:
    """Normalizes DEL-BOM and DELBOM style route codes to DEL-BOM."""
    clean = route_code.strip().upper()
    if "-" in clean:
        parts = clean.split("-")
        if len(parts) == 2 and len(parts[0]) == 3 and len(parts[1]) == 3:
            return f"{parts[0]}-{parts[1]}"
    if len(clean) == 6 and clean.isalpha():
        return f"{clean[:3]}-{clean[3:]}"
    raise ValueError("route_code must be in DEL-BOM or DELBOM format")


def resolve_approved_route_code(route_code: str) -> str:
    """Returns a normalized approved route code or raises ValueError."""
    normalized = normalize_route_code(route_code)
    if normalized not in APPROVED_ROUTE_CODES:
        raise ValueError(f"Route {normalized} is not in the approved APIx route basket.")
    return normalized


def validate_advance_windows(advance_windows: Iterable[int]) -> List[int]:
    """Returns requested windows after validating against the approved basket."""
    windows = list(advance_windows)
    for window in windows:
        if window not in APPROVED_ADVANCE_WINDOWS:
            raise ValueError(f"Unsupported advance_window_days {window}; expected {APPROVED_ADVANCE_WINDOWS}.")
    return windows


def build_route_window_targets(
    collection_date: date,
    *,
    route_codes: Optional[Sequence[str]] = None,
    advance_windows: Optional[Sequence[int]] = None,
) -> List[RouteWindowTarget]:
    """Builds the daily route-window target matrix from central configuration."""
    routes = (
        [resolve_approved_route_code(route_code) for route_code in route_codes]
        if route_codes is not None
        else list(APPROVED_ROUTE_CODES)
    )
    windows = validate_advance_windows(advance_windows or APPROVED_ADVANCE_WINDOWS)

    return [
        RouteWindowTarget(
            route_code=route_code,
            advance_window_days=window,
            departure_date=collection_date + timedelta(days=window),
        )
        for route_code in routes
        for window in windows
    ]
