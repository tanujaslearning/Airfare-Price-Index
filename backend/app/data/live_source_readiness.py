"""Readiness configuration for compliant LIVE airfare sources."""

from dataclasses import dataclass
from typing import Dict, Literal, Optional

SourceReadinessStatus = Literal[
    "READY",
    "NO_AVAILABILITY",
    "INCONCLUSIVE",
    "SOURCE_NOT_FEASIBLE",
]


@dataclass(frozen=True)
class LiveSourceReadiness:
    """Collection readiness metadata for one source."""

    key: str
    display_name: str
    source_code: Optional[str]
    status: SourceReadinessStatus
    enabled_by_default: bool
    reason: str


LIVE_SOURCE_READINESS: Dict[str, LiveSourceReadiness] = {
    "akasa": LiveSourceReadiness(
        key="akasa",
        display_name="Akasa Air",
        source_code="QP",
        status="READY",
        enabled_by_default=True,
        reason="Proven controlled LIVE source for the prototype.",
    ),
    "air_india": LiveSourceReadiness(
        key="air_india",
        display_name="Air India",
        source_code="AI",
        status="INCONCLUSIVE",
        enabled_by_default=False,
        reason="Read-only feasibility was inconclusive because robots.txt retrieval timed out.",
    ),
    "spicejet": LiveSourceReadiness(
        key="spicejet",
        display_name="SpiceJet",
        source_code="SG",
        status="NO_AVAILABILITY",
        enabled_by_default=False,
        reason="Controlled searches reached results but repeatedly showed no visible availability.",
    ),
    "indigo": LiveSourceReadiness(
        key="indigo",
        display_name="IndiGo Airlines",
        source_code="6E",
        status="SOURCE_NOT_FEASIBLE",
        enabled_by_default=False,
        reason="Public booking UI feasibility diagnostics did not expose usable booking interaction.",
    ),
}
