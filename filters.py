from typing import Any, Optional


def apply_filters(
    listings: list[dict[str, Any]],
    max_price: Optional[float] = None,
    min_rooms: Optional[int] = None,
    max_distance_km: Optional[float] = None,
) -> list[dict[str, Any]]:
    """Filter a list of listing dicts (as returned by storage.get_filtered_listings)."""
    out = []
    for lst in listings:
        if max_price is not None and lst.get("price_pln") is not None:
            if lst["price_pln"] > max_price:
                continue
        if min_rooms is not None and lst.get("rooms") is not None:
            if lst["rooms"] < min_rooms:
                continue
        if max_distance_km is not None and lst.get("distance_km") is not None:
            if lst["distance_km"] > max_distance_km:
                continue
        out.append(lst)
    return out
