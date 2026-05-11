"""
OLX card cleaner.

Takes a raw selectolax card node and returns a minimal dict ready to be
sent to an LLM extractor. URL and thumbnail are pre-extracted with reliable
CSS selectors so we don't burn tokens asking the model for those.
"""

import re
from typing import Optional

_BASE = "https://www.olx.pl"


def clean_card(card) -> dict:
    """
    Returns:
        {
            "url":          str   — canonical listing URL (no query string)
            "thumbnail_url": str | None
            "text":         str   — all human-readable text from the card,
                                    style/script blobs stripped, whitespace normalised
        }
    """
    # --- URL ---
    link = card.css_first("a[href]")
    href = (link.attrs.get("href") or "") if link else ""
    url = (_BASE + href.split("?")[0]) if href.startswith("/") else href.split("?")[0]

    # --- Thumbnail (check both src and data-src for lazy-loaded images) ---
    thumbnail_url: Optional[str] = None
    img = card.css_first("img")
    if img:
        thumbnail_url = (
            img.attrs.get("src")
            or img.attrs.get("data-src")
            or img.attrs.get("data-lazy-src")
        )
        # Reject placeholder blobs / inline SVGs
        if thumbnail_url and (
            thumbnail_url.startswith("data:") or len(thumbnail_url) < 20
        ):
            thumbnail_url = None

    # --- Text: strip <style> and <script> nodes, then collect text ---
    for node in card.css("style, script"):
        node.decompose()

    raw_text = card.text(separator=" ", strip=True)

    # Collapse runs of whitespace to a single space
    clean_text = re.sub(r"\s+", " ", raw_text).strip()

    return {
        "url": url,
        "thumbnail_url": thumbnail_url,
        "text": clean_text,
    }
