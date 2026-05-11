"""
Storage interface — v0 implementation: SQLite.

Rule: ALL cursor.execute() calls live here. No other module touches SQL.
To swap to Supabase (v1): replace the bodies of these functions only;
callers don't change.
"""

import sqlite3
from pathlib import Path
from typing import Any, Optional
from models import Listing

_DB_PATH = Path("data") / "listings.db"


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS listings (
                url           TEXT PRIMARY KEY,
                source        TEXT NOT NULL,
                title         TEXT,
                price_pln     REAL,
                czynsz_pln    REAL,
                area_m2       REAL,
                rooms         INTEGER,
                lat           REAL,
                lng           REAL,
                thumbnail_url TEXT,
                posted_at     TEXT,
                distance_km   REAL,
                nearest_tram_m INTEGER,
                nearest_bus_m  INTEGER,
                seen          INTEGER NOT NULL DEFAULT 0,
                fetched_at    TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Migration: add czynsz_pln to existing databases that predate this column
        try:
            conn.execute("ALTER TABLE listings ADD COLUMN czynsz_pln REAL")
        except sqlite3.OperationalError:
            pass  # column already exists
        conn.commit()


def save_listings(listings: list[Listing]) -> int:
    """Upsert listings. Returns number of new rows inserted."""
    new_count = 0
    with _connect() as conn:
        for lst in listings:
            cur = conn.execute(
                "SELECT url FROM listings WHERE url = ?", (lst.url,)
            )
            exists = cur.fetchone() is not None
            if exists:
                conn.execute(
                    """UPDATE listings SET
                        title=?, price_pln=?, czynsz_pln=?, area_m2=?, rooms=?,
                        lat=?, lng=?, thumbnail_url=?, posted_at=?,
                        distance_km=?, nearest_tram_m=?, nearest_bus_m=?
                    WHERE url=?""",
                    (
                        lst.title, lst.price_pln, lst.czynsz_pln, lst.area_m2, lst.rooms,
                        lst.lat, lst.lng, lst.thumbnail_url, lst.posted_at,
                        lst.distance_km, lst.nearest_tram_m, lst.nearest_bus_m,
                        lst.url,
                    ),
                )
            else:
                conn.execute(
                    """INSERT INTO listings
                        (url, source, title, price_pln, czynsz_pln, area_m2, rooms,
                         lat, lng, thumbnail_url, posted_at,
                         distance_km, nearest_tram_m, nearest_bus_m, seen)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        lst.url, lst.source, lst.title, lst.price_pln, lst.czynsz_pln,
                        lst.area_m2, lst.rooms, lst.lat, lst.lng,
                        lst.thumbnail_url, lst.posted_at,
                        lst.distance_km, lst.nearest_tram_m, lst.nearest_bus_m,
                        int(lst.seen),
                    ),
                )
                new_count += 1
        conn.commit()
    return new_count


def get_filtered_listings(
    max_price: Optional[float] = None,
    min_rooms: Optional[int] = None,
    max_distance_km: Optional[float] = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if max_price is not None:
        clauses.append("price_pln <= ?")
        params.append(max_price)
    if min_rooms is not None:
        clauses.append("(rooms IS NULL OR rooms >= ?)")
        params.append(min_rooms)
    if max_distance_km is not None:
        clauses.append("(distance_km IS NULL OR distance_km <= ?)")
        params.append(max_distance_km)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM listings {where} ORDER BY distance_km ASC NULLS LAST"

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_total_count() -> int:
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]


def mark_seen(url: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE listings SET seen=1 WHERE url=?", (url,))
        conn.commit()
