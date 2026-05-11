"""
Otodom source — parses __NEXT_DATA__ JSON from search results, then
fetches each detail page for coordinates (search results lack lat/lng).
"""

import json
import logging
import re
import time
from typing import Optional

import httpx

from models import Listing

log = logging.getLogger(__name__)

_BASE = "https://www.otodom.pl"
_SEARCH_URL = (
    "{base}/pl/wyniki/wynajem/mieszkanie/pomorskie/gdansk/gdansk/gdansk"
    "?page={page}"
)
_DETAIL_URL = "{base}/pl/oferta/{slug}"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_ROOMS_MAP = {
    "ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4,
    "FIVE": 5, "SIX": 6, "SEVEN": 7, "EIGHT": 8,
    "NINE": 9, "TEN": 10,
}

# Per-page request delay (seconds) to avoid rate limiting
_DETAIL_DELAY = 0.35
# Max listings fetched with coordinates per run (detail-page requests)
_MAX_WITH_COORDS = 30


def _extract_next_data(html: str) -> Optional[dict]:
    m = re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        log.warning("Otodom: failed to parse __NEXT_DATA__ JSON")
        return None


def _fetch_detail_coords(client: httpx.Client, slug: str) -> tuple[Optional[float], Optional[float]]:
    url = _DETAIL_URL.format(base=_BASE, slug=slug)
    try:
        resp = client.get(url, timeout=15)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("Otodom detail fetch failed for %s: %s", slug, exc)
        return None, None

    data = _extract_next_data(resp.text)
    if not data:
        return None, None

    try:
        coords = (
            data["props"]["pageProps"]["ad"]["location"]["coordinates"]
        )
        return float(coords["latitude"]), float(coords["longitude"])
    except (KeyError, TypeError, ValueError):
        return None, None


def _parse_item(item: dict, lat: Optional[float], lng: Optional[float]) -> Listing:
    slug = item.get("slug", "")
    url = f"{_BASE}/pl/oferta/{slug}"

    # totalPrice = asking rent; rentPrice = czynsz/admin fee on top
    price = None
    total = item.get("totalPrice") or {}
    if total.get("value"):
        price = float(total["value"])

    czynsz = None
    rent_price = item.get("rentPrice") or {}
    if rent_price.get("value"):
        czynsz = float(rent_price["value"])

    area = item.get("areaInSquareMeters")
    if area is not None:
        area = float(area)

    rooms_raw = item.get("roomsNumber")
    rooms = _ROOMS_MAP.get(rooms_raw) if rooms_raw else None

    images = item.get("images") or []
    thumbnail = images[0].get("medium") if images else None

    posted_at = item.get("dateCreated") or item.get("pushedUpAt")

    return Listing(
        url=url,
        source="otodom",
        title=item.get("title", ""),
        price_pln=price,
        czynsz_pln=czynsz,
        area_m2=area,
        rooms=rooms,
        lat=lat,
        lng=lng,
        thumbnail_url=thumbnail,
        posted_at=str(posted_at) if posted_at else None,
    )


def fetch(pages: int = 2) -> list[Listing]:
    """Fetch up to `pages` pages of Otodom Gdańsk rental listings."""
    listings: list[Listing] = []
    coords_fetched = 0

    with httpx.Client(headers=_HEADERS, follow_redirects=True) as client:
        for page_num in range(1, pages + 1):
            url = _SEARCH_URL.format(base=_BASE, page=page_num)
            log.info("Otodom: fetching search page %d", page_num)
            try:
                resp = client.get(url, timeout=20)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                log.error("Otodom search fetch failed (page %d): %s", page_num, exc)
                break

            data = _extract_next_data(resp.text)
            if not data:
                log.warning(
                    "Otodom: no __NEXT_DATA__ on page %d — possible anti-bot block",
                    page_num,
                )
                break

            try:
                items = data["props"]["pageProps"]["data"]["searchAds"]["items"]
            except KeyError:
                log.warning("Otodom: unexpected __NEXT_DATA__ structure on page %d", page_num)
                break

            if not items:
                log.warning("Otodom: page %d returned 0 items", page_num)
                break

            log.info("Otodom: page %d — %d items", page_num, len(items))

            for item in items:
                slug = item.get("slug", "")
                if coords_fetched < _MAX_WITH_COORDS:
                    time.sleep(_DETAIL_DELAY)
                    lat, lng = _fetch_detail_coords(client, slug)
                    coords_fetched += 1
                else:
                    lat, lng = None, None
                listings.append(_parse_item(item, lat, lng))

    log.info("Otodom: total listings fetched: %d", len(listings))
    return listings
