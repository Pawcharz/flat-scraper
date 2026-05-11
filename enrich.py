"""
Enrichment: compute distance to office (haversine) and find nearest
tram/bus stops via Overpass API (OpenStreetMap).

Stops are fetched once per run and cached in memory.
"""

import logging
import math
from typing import Optional

import httpx

import config
from models import Listing

log = logging.getLogger(__name__)

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_OVERPASS_UA = "flat-scraper/0.1 (personal project)"

# Bbox padding around Gdańsk city centre — degrees
_BBOX = (54.28, 18.45, 54.44, 18.76)


# ---------------------------------------------------------------------------
# Haversine
# ---------------------------------------------------------------------------

def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lng / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    return int(haversine_km(lat1, lng1, lat2, lng2) * 1000)


# ---------------------------------------------------------------------------
# Overpass
# ---------------------------------------------------------------------------

def _fetch_stops() -> tuple[list[dict], list[dict]]:
    """Return (tram_stops, bus_stops) as lists of {lat, lon} dicts."""
    s, w, n, e = _BBOX
    query = (
        f"[out:json][timeout:20];"
        f"("
        f"node[\"railway\"=\"tram_stop\"]({s},{w},{n},{e});"
        f"node[\"highway\"=\"bus_stop\"]({s},{w},{n},{e});"
        f");"
        f"out body;"
    )
    try:
        resp = httpx.get(
            _OVERPASS_URL,
            params={"data": query},
            headers={"User-Agent": _OVERPASS_UA},
            timeout=30,
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except Exception as exc:
        log.error("Overpass fetch failed: %s", exc)
        return [], []

    trams = [e for e in elements if e.get("tags", {}).get("railway") == "tram_stop"]
    buses = [e for e in elements if e.get("tags", {}).get("highway") == "bus_stop"]
    log.info("Overpass: %d tram stops, %d bus stops", len(trams), len(buses))
    return trams, buses


def _nearest_stop_m(
    lat: float, lng: float, stops: list[dict]
) -> Optional[int]:
    if not stops:
        return None
    return min(
        haversine_m(lat, lng, s["lat"], s["lon"]) for s in stops
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Module-level cache — populated on first call, reused for the rest of the run
_tram_stops: list[dict] = []
_bus_stops: list[dict] = []
_stops_loaded = False


def enrich(listings: list[Listing]) -> list[Listing]:
    """Mutates listings in-place: fills distance_km, nearest_tram_m, nearest_bus_m."""
    global _tram_stops, _bus_stops, _stops_loaded

    # Determine which listings actually have coordinates
    with_coords = [lst for lst in listings if lst.lat is not None and lst.lng is not None]

    if with_coords and not _stops_loaded:
        _tram_stops, _bus_stops = _fetch_stops()
        _stops_loaded = True

    for lst in listings:
        if lst.lat is None or lst.lng is None:
            continue

        lst.distance_km = round(
            haversine_km(lst.lat, lst.lng, config.OFFICE_LAT, config.OFFICE_LNG), 2
        )
        lst.nearest_tram_m = _nearest_stop_m(lst.lat, lst.lng, _tram_stops)
        lst.nearest_bus_m = _nearest_stop_m(lst.lat, lst.lng, _bus_stops)

    return listings
