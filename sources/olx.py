"""
OLX source — HTML scraping with selectolax.
Coordinates are not published by OLX; distance_km stays None for these listings.

Two extraction modes:
  use_gemini=False (default) — fast regex-based parsing (may miss fields)
  use_gemini=True            — cleans cards and sends them to Gemini 2.5 Flash
"""

import logging
import re
from typing import Optional

import httpx
from selectolax.parser import HTMLParser

from models import Listing

log = logging.getLogger(__name__)

_BASE = "https://www.olx.pl"
_SEARCH_URL = "{base}/nieruchomosci/mieszkania/wynajem/gdansk/?page={page}"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _rooms_from_title(title: str) -> Optional[int]:
    t = title.lower()
    if "kawalerka" in t or "studio" in t:
        return 1
    # Patterns: "2 pokoje", "2 pok.", "2-pokojowe", "2 pok)", "(2 pok"
    m = re.search(r"(\d)\s*[-]?\s*pok", t)
    if m:
        return int(m.group(1))
    return None


def _parse_price(text: str) -> Optional[float]:
    m = re.search(r"([\d\s]+)(?=\s*z)", text)
    if not m:
        return None
    try:
        return float(re.sub(r"\s", "", m.group(1).strip()))
    except ValueError:
        return None


def _parse_area(span_text: str) -> Optional[float]:
    # span may have embedded CSS (emotion.js); take the LAST m² match
    matches = re.findall(r"(\d+(?:[.,]\d+)?)\s*m²", span_text)
    if not matches:
        return None
    try:
        return float(matches[-1].replace(",", "."))
    except ValueError:
        return None


def _parse_card(card) -> Optional[Listing]:
    # Title
    h4 = card.css_first("h4")
    if not h4:
        return None
    title = h4.text(strip=True)
    if not title:
        return None

    # URL
    link = card.css_first("a[href]")
    if not link:
        return None
    href = link.attrs.get("href", "").split("?")[0]
    url = (_BASE + href) if href.startswith("/") else href

    # Price
    price_el = card.css_first('[data-testid="ad-price"]')
    price_pln = _parse_price(price_el.text(strip=True) if price_el else "")

    # Area
    area_span = card.css_first("span.css-h59g4b")
    area_m2 = _parse_area(area_span.text(strip=True) if area_span else "")

    # Rooms — inferred from title (OLX search cards don't expose rooms directly)
    rooms = _rooms_from_title(title)

    # Thumbnail
    img = card.css_first("img")
    thumbnail = img.attrs.get("src") if img else None

    # Date (location-date element)
    loc_el = card.css_first('[data-testid="location-date"]')
    posted_at: Optional[str] = None
    if loc_el:
        loc_text = loc_el.text(strip=True)
        # Strip the area part that leaks into this element
        loc_text = re.sub(r"\d+(?:[.,]\d+)?\s*m².*$", "", loc_text).strip()
        # Try to extract a date portion: "10 maja 2026" or "dzisiaj o HH:MM"
        date_m = re.search(r"(\d{1,2}\s+\w+\s+\d{4}|dzisiaj.*|wczoraj.*)", loc_text, re.I)
        posted_at = date_m.group(1).strip() if date_m else loc_text

    return Listing(
        url=url,
        source="olx",
        title=title,
        price_pln=price_pln,
        area_m2=area_m2,
        rooms=rooms,
        lat=None,
        lng=None,
        thumbnail_url=thumbnail,
        posted_at=posted_at,
    )


def fetch(pages: int = 2, use_gemini: bool = False) -> list[Listing]:
    """Fetch up to `pages` pages of OLX Gdańsk rental listings.

    Args:
        pages:      number of search-result pages to scrape
        use_gemini: when True, cards are cleaned and parsed by Gemini 2.5 Flash
                    instead of the built-in regex parser
    """
    from cleaners.olx import clean_card
    from extractors.gemini import extract_olx

    listings: list[Listing] = []
    cleaned_cards: list[dict] = []   # accumulated for Gemini path

    with httpx.Client(headers=_HEADERS, follow_redirects=True) as client:
        for page_num in range(1, pages + 1):
            url = _SEARCH_URL.format(base=_BASE, page=page_num)
            log.info("OLX: fetching page %d", page_num)
            try:
                resp = client.get(url, timeout=20)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                log.error("OLX fetch failed (page %d): %s", page_num, exc)
                break

            tree = HTMLParser(resp.text)
            cards = tree.css('[data-cy="l-card"]')

            if not cards:
                log.warning("OLX: no listing cards found on page %d", page_num)
                break

            log.info("OLX: page %d — %d cards", page_num, len(cards))

            if use_gemini:
                for card in cards:
                    cleaned_cards.append(clean_card(card))
            else:
                for card in cards:
                    lst = _parse_card(card)
                    if lst:
                        listings.append(lst)

    if use_gemini:
        log.info("OLX: sending %d cleaned cards to Gemini", len(cleaned_cards))
        listings = extract_olx(cleaned_cards)

    log.info("OLX: total listings fetched: %d", len(listings))
    return listings
