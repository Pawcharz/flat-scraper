"""
Gdańsk flat-scraper — Streamlit UI
Run: streamlit run app.py
"""

import datetime
import logging

import streamlit as st

import config
import enrich as enrich_mod
import storage
from filters import apply_filters
from sources import otodom, olx

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

st.set_page_config(page_title="Gdańsk Flat Scraper", layout="wide")
st.title("🏠 Gdańsk Flat Scraper")

storage.init_db()

# ---------------------------------------------------------------------------
# Sidebar — filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")
    max_price = st.number_input(
        "Max price (PLN/mo)", min_value=500, max_value=20_000,
        value=config.MAX_PRICE_PLN, step=100,
    )
    min_rooms = st.number_input(
        "Min rooms", min_value=1, max_value=10,
        value=config.MIN_ROOMS, step=1,
    )
    max_dist = st.slider(
        "Max distance to office (km)", min_value=0.5, max_value=15.0,
        value=config.MAX_DISTANCE_KM, step=0.5,
    )
    st.divider()
    st.header("Scraping")
    pages_to_fetch = st.number_input(
        "Pages per site", min_value=1, max_value=20,
        value=2, step=1,
        help="Each Otodom page ≈ 37 listings, each OLX page ≈ 52.",
    )
    gemini_enabled = st.toggle(
        "Use Gemini parser for OLX",
        value=False,
        help=(
            "Sends cleaned OLX card text to Gemini 2.5 Flash for extraction. "
            "Slower but more accurate — parses rooms, czynsz, and titles reliably. "
            "Requires GEMINI_API_KEY in .env."
        ),
        disabled=not bool(config.GEMINI_API_KEY),
    )
    if not config.GEMINI_API_KEY:
        st.caption("⚠️ Set GEMINI_API_KEY in .env.local to enable Gemini parser.")
    st.divider()
    st.header("Database")
    if st.button("🗑️ Reset database", help="Deletes all stored listings so the next refresh starts clean."):
        n = storage.clear_db()
        st.success(f"Deleted {n} listings.")
        st.rerun()
    st.caption(
        f"Office coords: {config.OFFICE_LAT}, {config.OFFICE_LNG}  \n"
        "_(edit config.py to change)_"
    )

# ---------------------------------------------------------------------------
# Refresh button
# ---------------------------------------------------------------------------
if st.button("🔄 Refresh listings", type="primary"):
    with st.spinner("Fetching Otodom…"):
        otodom_listings = otodom.fetch(pages=pages_to_fetch)
    with st.spinner(f"Fetching OLX {'(Gemini)' if gemini_enabled else ''}…"):
        olx_listings = olx.fetch(pages=pages_to_fetch, use_gemini=gemini_enabled)

    all_listings = otodom_listings + olx_listings

    with st.spinner("Enriching with distances and transit stops…"):
        enrich_mod._stops_loaded = False  # force re-fetch on manual refresh
        enrich_mod.enrich(all_listings)

    new_count = storage.save_listings(all_listings)
    st.success(
        f"Done! Fetched {len(all_listings)} listings "
        f"({new_count} new). Last refresh: {datetime.datetime.now().strftime('%H:%M:%S')}"
    )

# ---------------------------------------------------------------------------
# Load + filter from DB
# ---------------------------------------------------------------------------
all_db = storage.get_filtered_listings()
total_count = storage.get_total_count()

filtered = apply_filters(
    all_db,
    max_price=float(max_price),
    min_rooms=int(min_rooms),
    max_distance_km=float(max_dist),
)

# Sort by distance (None last)
filtered.sort(
    key=lambda r: (r["distance_km"] is None, r["distance_km"] or 0)
)

st.caption(
    f"**{total_count}** total in DB · **{len(filtered)}** matching filters"
)

# ---------------------------------------------------------------------------
# Listing cards
# ---------------------------------------------------------------------------
if not filtered:
    st.info("No listings match current filters. Try refreshing or loosening the filters.")
else:
    for row in filtered:
        with st.container(border=True):
            cols = st.columns([1, 3])
            with cols[0]:
                if row.get("thumbnail_url"):
                    st.image(row["thumbnail_url"], use_container_width=True)
                else:
                    st.markdown("_(no image)_")

            with cols[1]:
                # Price + czynsz
                if row.get("price_pln"):
                    price_str = f"**{int(row['price_pln'])} PLN/mo**"
                    if row.get("czynsz_pln"):
                        price_str += f" + {int(row['czynsz_pln'])} czynsz"
                else:
                    price_str = "price unknown"

                area_str  = f"{row['area_m2']} m²" if row.get("area_m2") else "?"
                rooms_str = str(row["rooms"]) if row.get("rooms") else "?"
                dist_str  = (
                    f"{row['distance_km']:.1f} km"
                    if row.get("distance_km") is not None
                    else "no coords"
                )
                tram_str = (
                    f"{row['nearest_tram_m']} m"
                    if row.get("nearest_tram_m") is not None
                    else "—"
                )
                bus_str = (
                    f"{row['nearest_bus_m']} m"
                    if row.get("nearest_bus_m") is not None
                    else "—"
                )

                st.markdown(
                    f"[{row['title']}]({row['url']}) "
                    f"<sub>({row['source'].upper()})</sub>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"{price_str} · {area_str} · {rooms_str} rooms · "
                    f"🏢 {dist_str} · 🚋 {tram_str} · 🚌 {bus_str}"
                )
                if row.get("posted_at"):
                    st.caption(f"Posted: {row['posted_at']}")
