from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Listing:
    url: str                          # canonical dedup key
    source: str                       # "otodom" | "olx"
    title: str
    price_pln: Optional[float]
    area_m2: Optional[float]
    rooms: Optional[int]
    lat: Optional[float]
    lng: Optional[float]
    thumbnail_url: Optional[str]
    posted_at: Optional[str]          # ISO-8601 string, source-provided
    # enriched fields — None until enrich.py runs
    distance_km: Optional[float] = field(default=None)
    nearest_tram_m: Optional[int] = field(default=None)
    nearest_bus_m: Optional[int] = field(default=None)
    seen: bool = field(default=False)
