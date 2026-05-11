import os
from dotenv import load_dotenv

load_dotenv(".env.local")  # picks up .env.local in project root (gitignored)

# ---------------------------------------------------------------------------
# UPDATE OFFICE_LAT / OFFICE_LNG to your actual office before first use.
# Current placeholder: Gdańsk Główny train station.
# ---------------------------------------------------------------------------

# Coordinates: 54°22'32.0"N 18°36'33.8"E
OFFICE_LAT: float = 54.375556
OFFICE_LNG: float = 18.609389
CITY: str = "Gdańsk"

# ---------------------------------------------------------------------------
# Gemini — set GEMINI_API_KEY in .env or as an environment variable.
# Get a key at https://aistudio.google.com/app/apikey
# ---------------------------------------------------------------------------
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")

# Default filter values — can be overridden in the UI
MAX_PRICE_PLN: int = 2000
MIN_ROOMS: int = 1
MAX_DISTANCE_KM: float = 3.0
