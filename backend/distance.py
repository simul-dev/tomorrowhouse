"""Distance provider boundary; replace Haversine with a road matrix as needed."""
from math import asin, cos, radians, sin, sqrt
from typing import Protocol


class DistanceProvider(Protocol):
    def __call__(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float: ...


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a1, a2 = radians(lat1), radians(lat2)
    h = sin((a2-a1)/2)**2 + cos(a1)*cos(a2)*sin(radians(lon2-lon1)/2)**2
    return 2 * 6371.0088 * asin(min(1, sqrt(max(0, h))))
