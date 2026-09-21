import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env")


def positive_int(name: str, default: int, maximum: int) -> int:
    try:
        return min(max(1, int(os.getenv(name, default))), maximum)
    except ValueError:
        return default


MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "smart_timetable")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
if not UPLOAD_DIR.is_absolute():
    UPLOAD_DIR = BACKEND_DIR / UPLOAD_DIR
UPLOAD_DIR = UPLOAD_DIR.resolve()
MAX_UPLOAD_BYTES = positive_int("MAX_UPLOAD_MB", 15, 15) * 1024 * 1024
MAX_PDF_PAGES = positive_int("MAX_PDF_PAGES", 10, 20)
OCR_TIMEOUT = positive_int("OCR_TIMEOUT_SECONDS", 60, 120)
TABLE_Y_TOLERANCE = positive_int("TABLE_Y_TOLERANCE", 4, 6)
EXTRACTION_DEBUG = os.getenv("EXTRACTION_DEBUG", "").lower() in {"1", "true", "yes"}
OCR_LANGUAGE = os.getenv("OCR_LANGUAGE", "eng").strip() or "eng"
CORS_ORIGINS = [s.strip() for s in os.getenv(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",") if s.strip()]
