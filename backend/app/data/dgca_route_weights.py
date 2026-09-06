"""Official DGCA city-pair passenger traffic for APIx route weighting."""

from dataclasses import dataclass
from typing import Dict, Literal, Optional

DgcaRouteWeightStatus = Literal["AVAILABLE", "MISSING", "NOT_MAPPED"]
DgcaRouteWeightDirectionality = Literal["directional", "combined city-pair"]

DGCA_TABLE_5_01_SOURCE = "DGCA Table 5.01 Indian City-Wise Passenger Traffic"
DGCA_TABLE_5_01_PERIOD = "2024-25"
DGCA_TABLE_5_01_REFERENCE = (
    "https://public-prd-dgca.s3.ap-south-1.amazonaws.com/"
    "InventoryList/dataReports/aviationDataStatistics/airTransport/domestic/yearly/28/Normal/"
    "TABLE%205.01%20%28INDIAN%20CITY-WISE%20PASSENGER%20TRAFFIC%29.pdf"
)


@dataclass(frozen=True)
class DgcaRouteWeightRecord:
    """One official DGCA passenger-traffic mapping for a prototype route."""

    route_code: str
    origin: str
    destination: str
    dgca_route_identifier: Optional[str]
    passenger_traffic: Optional[int]
    traffic_period: Optional[str]
    source: str
    source_reference: Optional[str]
    directionality: Optional[DgcaRouteWeightDirectionality]
    status: DgcaRouteWeightStatus


DGCA_ROUTE_WEIGHTS: Dict[str, DgcaRouteWeightRecord] = {
    "DEL-BOM": DgcaRouteWeightRecord(
        route_code="DEL-BOM",
        origin="DEL",
        destination="BOM",
        dgca_route_identifier="DELHI-MUMBAI / PASSENGERS TO CITY 2",
        passenger_traffic=3426228,
        traffic_period=DGCA_TABLE_5_01_PERIOD,
        source=DGCA_TABLE_5_01_SOURCE,
        source_reference=DGCA_TABLE_5_01_REFERENCE,
        directionality="directional",
        status="AVAILABLE",
    ),
    "DEL-BLR": DgcaRouteWeightRecord(
        route_code="DEL-BLR",
        origin="DEL",
        destination="BLR",
        dgca_route_identifier="BENGALURU-DELHI / PASSENGERS FROM CITY 2",
        passenger_traffic=2350018,
        traffic_period=DGCA_TABLE_5_01_PERIOD,
        source=DGCA_TABLE_5_01_SOURCE,
        source_reference=DGCA_TABLE_5_01_REFERENCE,
        directionality="directional",
        status="AVAILABLE",
    ),
    "BOM-BLR": DgcaRouteWeightRecord(
        route_code="BOM-BLR",
        origin="BOM",
        destination="BLR",
        dgca_route_identifier="BENGALURU-MUMBAI / PASSENGERS FROM CITY 2",
        passenger_traffic=2083737,
        traffic_period=DGCA_TABLE_5_01_PERIOD,
        source=DGCA_TABLE_5_01_SOURCE,
        source_reference=DGCA_TABLE_5_01_REFERENCE,
        directionality="directional",
        status="AVAILABLE",
    ),
    "DEL-CCU": DgcaRouteWeightRecord(
        route_code="DEL-CCU",
        origin="DEL",
        destination="CCU",
        dgca_route_identifier="DELHI-KOLKATA / PASSENGERS TO CITY 2",
        passenger_traffic=1417339,
        traffic_period=DGCA_TABLE_5_01_PERIOD,
        source=DGCA_TABLE_5_01_SOURCE,
        source_reference=DGCA_TABLE_5_01_REFERENCE,
        directionality="directional",
        status="AVAILABLE",
    ),
    "BLR-HYD": DgcaRouteWeightRecord(
        route_code="BLR-HYD",
        origin="BLR",
        destination="HYD",
        dgca_route_identifier="BENGALURU-HYDERABAD / PASSENGERS TO CITY 2",
        passenger_traffic=1153136,
        traffic_period=DGCA_TABLE_5_01_PERIOD,
        source=DGCA_TABLE_5_01_SOURCE,
        source_reference=DGCA_TABLE_5_01_REFERENCE,
        directionality="directional",
        status="AVAILABLE",
    ),
    "MAA-DEL": DgcaRouteWeightRecord(
        route_code="MAA-DEL",
        origin="MAA",
        destination="DEL",
        dgca_route_identifier="CHENNAI-DELHI / PASSENGERS TO CITY 2",
        passenger_traffic=1222119,
        traffic_period=DGCA_TABLE_5_01_PERIOD,
        source=DGCA_TABLE_5_01_SOURCE,
        source_reference=DGCA_TABLE_5_01_REFERENCE,
        directionality="directional",
        status="AVAILABLE",
    ),
}
