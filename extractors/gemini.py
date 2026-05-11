"""
Gemini extractor — uses gemini-2.5-flash with structured JSON output to
parse rental listing data from cleaned OLX card text.

Cards are processed in batches of BATCH_SIZE to minimise API calls while
staying well within the free-tier rate limits (15 RPM for Flash).
"""

import json
import logging
from typing import Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

import config
from models import Listing

log = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"
BATCH_SIZE = 8  # cards per API call — ~6k input tokens, well within limits

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. "
                "Add it to .env or set it as an environment variable."
            )
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


# ---------------------------------------------------------------------------
# Structured output schema
# ---------------------------------------------------------------------------

class _ExtractedListing(BaseModel):
    title: str = Field(description="Property title / description")
    price_pln: Optional[float] = Field(
        None, description="Monthly rent in PLN (number only, no currency symbol)"
    )
    czynsz_pln: Optional[float] = Field(
        None,
        description=(
            "Building maintenance / admin fee (czynsz) in PLN if explicitly stated "
            "(e.g. 'Czynsz: 300 zł' → 300). Null if not mentioned."
        ),
    )
    area_m2: Optional[float] = Field(
        None, description="Flat area in square metres (number only)"
    )
    rooms: Optional[int] = Field(
        None,
        description=(
            "Number of rooms as integer. "
            "'kawalerka' or 'studio' = 1. "
            "'2 pokoje' / '2-pokojowe' = 2. Etc."
        ),
    )
    posted_at: Optional[str] = Field(
        None, description="Date string as found in the text, e.g. '10 maja 2026' or 'dzisiaj o 14:32'"
    )


_SYSTEM_PROMPT = """\
You are a data-extraction assistant for a Polish real-estate aggregator.
You will receive a numbered list of rental listing snippets scraped from OLX.pl.
Each snippet contains the raw visible text from a single listing card.

For EACH listing return one JSON object with these fields:
  title        – the property title / headline (string)
  price_pln    – monthly rent in PLN (float, digits only; null if missing)
  czynsz_pln   – extra building/admin fee "czynsz" in PLN (float; null if not stated)
  area_m2      – area in m² (float; null if missing)
  rooms        – number of rooms (integer; kawalerka/studio → 1; null if unclear)
  posted_at    – date string exactly as it appears in the text (string; null if missing)

Rules:
- Return a JSON ARRAY with exactly one object per input listing, in the same order.
- Use null (not 0) for any field that is genuinely absent from the text.
- Do NOT invent or guess values that are not present in the text.
- Prices are in PLN. Ignore any "zł" / "PLN" suffix — return numbers only.
- "Czynsz (dodatkowo)" means it is charged ON TOP of the rent — capture it separately.
"""


def _format_batch(cards: list[dict]) -> str:
    lines = []
    for i, card in enumerate(cards, 1):
        lines.append(f"--- Listing {i} ---")
        lines.append(card["text"])
    return "\n".join(lines)


def _call_gemini(cards: list[dict]) -> list[Optional[_ExtractedListing]]:
    client = _get_client()
    prompt = _format_batch(cards)

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=list[_ExtractedListing],
            ),
        )
    except Exception as exc:
        log.error("Gemini API call failed: %s", exc)
        return [None] * len(cards)

    raw = response.text or ""
    try:
        data = json.loads(raw)
        results = [_ExtractedListing.model_validate(item) for item in data]
    except Exception as exc:
        log.error("Gemini response parse failed: %s | raw: %.200s", exc, raw)
        return [None] * len(cards)

    # Guard against length mismatch
    if len(results) != len(cards):
        log.warning(
            "Gemini returned %d results for %d cards — padding with None",
            len(results), len(cards),
        )
        results += [None] * (len(cards) - len(results))

    return results[:len(cards)]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_olx(cleaned_cards: list[dict]) -> list[Listing]:
    """
    Takes a list of dicts from cleaners.olx.clean_card() and returns
    a list of Listing objects with fields populated by Gemini.
    """
    listings: list[Listing] = []

    for batch_start in range(0, len(cleaned_cards), BATCH_SIZE):
        batch = cleaned_cards[batch_start : batch_start + BATCH_SIZE]
        log.info(
            "Gemini: extracting batch %d–%d of %d",
            batch_start + 1,
            batch_start + len(batch),
            len(cleaned_cards),
        )
        extracted = _call_gemini(batch)

        for card, result in zip(batch, extracted):
            if result is None:
                # Gemini failed for this card — store a minimal stub
                log.warning("Gemini: no result for %s, storing stub", card["url"])
                listings.append(
                    Listing(
                        url=card["url"],
                        source="olx",
                        title="(parse failed)",
                        price_pln=None,
                        czynsz_pln=None,
                        area_m2=None,
                        rooms=None,
                        lat=None,
                        lng=None,
                        thumbnail_url=card["thumbnail_url"],
                        posted_at=None,
                    )
                )
            else:
                listings.append(
                    Listing(
                        url=card["url"],
                        source="olx",
                        title=result.title,
                        price_pln=result.price_pln,
                        czynsz_pln=result.czynsz_pln,
                        area_m2=result.area_m2,
                        rooms=result.rooms,
                        lat=None,
                        lng=None,
                        thumbnail_url=card["thumbnail_url"],
                        posted_at=result.posted_at,
                    )
                )

    return listings
