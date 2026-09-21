from fastapi import APIRouter

from backend import config
from backend.database.connection import database_status
from backend.services.ocr_service import ocr_status

router = APIRouter()


@router.get("/")
def root():
    return {"name": "Smart Timetable Digitizer", "docs": "/docs", "health": "/api/health"}


@router.get("/api/system/ocr-status")
def get_ocr_status():
    return ocr_status()


@router.get("/api/system/database-status")
def get_database_status():
    return database_status()


@router.get("/api/health")
def health():
    ocr, db = ocr_status(), database_status()
    return {"status": "ok" if ocr["ready"] and db["connected"] else "degraded", "backend": True,
            "mongodb": db["connected"], "tesseract": ocr["tesseract_installed"],
            "english_ocr": ocr["english_available"], "malayalam_ocr": ocr["malayalam_available"],
            "max_upload_mb": config.MAX_UPLOAD_BYTES // (1024 * 1024), "max_pdf_pages": config.MAX_PDF_PAGES}
