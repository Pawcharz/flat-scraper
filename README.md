# flat-scraper

Personal scraper for Gdańsk rental listings (OLX + Otodom). Filters by price, room count, and walking distance to your office. Shows nearest tram and bus stops.

## Quick start

```bash
cp .env.example .env.local   # add your GEMINI_API_KEY (optional)
uv sync
uv run streamlit run app.py
```

## Configuration

Edit `config.py` before first use:

| Setting | Default | Description |
|---|---|---|
| `OFFICE_LAT` / `OFFICE_LNG` | Gdańsk Główny station | **Update to your actual office coords** |
| `MAX_PRICE_PLN` | 4500 | Default price filter |
| `MIN_ROOMS` | 1 | Default minimum rooms |
| `MAX_DISTANCE_KM` | 2.0 | Default max walking distance |

All filter values can also be adjusted live in the Streamlit sidebar.

## Usage

1. Launch the app with `streamlit run app.py`
2. Click **Refresh listings** to scrape Otodom + OLX and enrich with distances
3. Use sidebar sliders to filter by price, rooms, distance
4. Click any listing title to open the original ad

## Architecture

```
app.py          Streamlit UI
storage.py      Storage interface — SQLite v0, swap to Supabase later
config.py       User-tunable settings
sources/
  otodom.py     Parses __NEXT_DATA__ JSON + fetches detail pages for coords
  olx.py        Selectolax HTML scraping (no coords available from OLX)
enrich.py       Haversine distance + Overpass API (OSM) for transit stops
filters.py      Filter application logic
models.py       Listing dataclass
```

### Notes on sources

- **Otodom**: coordinates come from individual listing pages (one extra request per listing). Up to 30 listings get coordinates per run; the rest have `distance_km=null`.
- **OLX**: does not publish coordinates — `distance_km` is always `null` for OLX listings. Rooms are inferred from title text.
- **Transit stops**: fetched once per run from Overpass API (OpenStreetMap). No API key required.

## Data

The SQLite database is stored at `data/listings.db` (gitignored). Run `streamlit run app.py` and click Refresh to populate it.
