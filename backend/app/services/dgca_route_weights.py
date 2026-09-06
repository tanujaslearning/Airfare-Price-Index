"""DGCA passenger-traffic route weighting service."""

from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Optional, Set

from backend.app.data.dgca_route_weights import (
    DGCA_ROUTE_WEIGHTS,
    DGCA_TABLE_5_01_PERIOD,
    DGCA_TABLE_5_01_SOURCE,
    DgcaRouteWeightRecord,
)


def route_code_for(route: Any) -> str:
    """Returns the canonical APIx route code for a route-like object."""
    if hasattr(route, "route_code"):
        return str(route.route_code).upper()
    if hasattr(route, "route_key"):
        return str(route.route_key).upper()
    return f"{route.origin_code}-{route.destination_code}".upper()


def get_dgca_route_weight_record(route: Any) -> DgcaRouteWeightRecord:
    """Returns the configured DGCA route-weight record or a NOT_MAPPED record."""
    route_code = route_code_for(route)
    configured = DGCA_ROUTE_WEIGHTS.get(route_code)
    if configured is not None:
        return configured

    return DgcaRouteWeightRecord(
        route_code=route_code,
        origin=str(getattr(route, "origin_code", "")).upper(),
        destination=str(getattr(route, "destination_code", "")).upper(),
        dgca_route_identifier=None,
        passenger_traffic=None,
        traffic_period=None,
        source="DGCA",
        source_reference=None,
        directionality=None,
        status="NOT_MAPPED",
    )


def calculate_dgca_route_weights(
    routes: Iterable[Any],
    *,
    normalization_routes: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    """Calculates DGCA route weights normalized over usable official traffic rows."""
    route_list = list(routes)
    records = [get_dgca_route_weight_record(route) for route in route_list]
    normalization_records = (
        [get_dgca_route_weight_record(route) for route in normalization_routes]
        if normalization_routes is not None
        else records
    )
    usable = [
        record
        for record in normalization_records
        if record.status == "AVAILABLE" and record.passenger_traffic is not None and record.passenger_traffic > 0
    ]
    total_passenger_traffic = sum(record.passenger_traffic or 0 for record in usable)
    missing_routes = [record.route_code for record in records if record.status == "MISSING"]
    unmapped_routes = [record.route_code for record in records if record.status == "NOT_MAPPED"]

    route_items: List[Dict[str, Any]] = []
    periods: Set[str] = set()
    sources: Set[str] = set()
    directionality: Set[str] = set()

    for record in records:
        weight: Optional[float] = None
        if (
            record.status == "AVAILABLE"
            and record.passenger_traffic is not None
            and record.passenger_traffic > 0
            and total_passenger_traffic > 0
        ):
            weight = record.passenger_traffic / total_passenger_traffic
            if record.traffic_period:
                periods.add(record.traffic_period)
            if record.source:
                sources.add(record.source)
            if record.directionality:
                directionality.add(record.directionality)

        item = asdict(record)
        item["weight"] = weight
        route_items.append(item)

    available_route_count = len(usable)
    total_route_count = len(route_list)

    return {
        "source": ", ".join(sorted(sources)) if sources else DGCA_TABLE_5_01_SOURCE,
        "traffic_period": ", ".join(sorted(periods)) if periods else DGCA_TABLE_5_01_PERIOD,
        "directionality": ", ".join(sorted(directionality)) if directionality else None,
        "routes": route_items,
        "coverage": {
            "available": available_route_count,
            "total": total_route_count,
            "percentage": round((available_route_count / total_route_count) * 100.0, 2) if total_route_count else 0.0,
        },
        "missing_routes": missing_routes,
        "unmapped_routes": unmapped_routes,
        "available_route_count": available_route_count,
        "total_route_count": total_route_count,
        "coverage_percentage": round((available_route_count / total_route_count) * 100.0, 2)
        if total_route_count
        else 0.0,
        "weight_period": ", ".join(sorted(periods)) if periods else DGCA_TABLE_5_01_PERIOD,
        "total_passenger_traffic": total_passenger_traffic,
    }


def weight_by_route_code(
    routes: Iterable[Any],
    *,
    normalization_routes: Optional[Iterable[Any]] = None,
) -> Dict[str, Optional[float]]:
    """Returns calculated DGCA weights keyed by route code."""
    result = calculate_dgca_route_weights(routes, normalization_routes=normalization_routes)
    return {item["route_code"]: item["weight"] for item in result["routes"]}
