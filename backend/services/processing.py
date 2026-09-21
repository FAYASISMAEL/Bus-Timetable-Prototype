import logging
from datetime import datetime, timedelta, timezone
from threading import BoundedSemaphore
from statistics import median

from pymongo import ReturnDocument

from backend import config
from backend.database.connection import object_id, public_record
from backend.services.image_processor import preprocess_image, read_image, remove_table_grid
from backend.services.ocr_service import extract_tokens, tokens_to_lines
from backend.services.pdf_processor import extract_pdf_pages
from backend.services.timetable_parser import parse_destination_timetable
from backend.utils.errors import AppError
from backend.utils.files import source_path

logger = logging.getLogger(__name__)
processing_slots = BoundedSemaphore(2)


def now() -> datetime:
    return datetime.now(timezone.utc)


def process_document(db, document_id: str) -> dict:
    identifier = object_id(document_id)
    document = db.documents.find_one({"_id": identifier})
    if not document:
        raise AppError(404, "not_found", "Document not found.")
    path = source_path(document)
    if not processing_slots.acquire(blocking=False):
        raise AppError(429, "processor_busy", "OCR is processing other documents. Please try again shortly.")
    acquired = False
    try:
        # A stale lease can be retried after a killed server; no permanent 'processing' state.
        document = db.documents.find_one_and_update(
            {"_id": identifier, "$or": [{"status": {"$ne": "processing"}},
              {"processing_started_at": {"$lt": now() - timedelta(minutes=45)}}]},
            {"$set": {"status": "processing", "processing_started_at": now(), "error": None}},
            return_document=ReturnDocument.AFTER)
        if not document:
            raise AppError(409, "already_processing", "This document is already being processed.")
        acquired = True
        if document["extension"] == ".pdf":
            pages = extract_pdf_pages(path)
        else:
            processed, metadata = preprocess_image(read_image(path))
            pages = [{"page": 1, "mode": "OCR_FALLBACK", "image": processed, "text": "",
                      "scale": 1.0, "coordinate_units": "pixels", **metadata}]
        all_tokens, page_results = [], []
        for result in pages:
            page, mode = result["page"], result["mode"]
            metadata = {key: value for key, value in result.items() if key not in {"image", "tokens", "scale"}}
            if mode == "DIRECT_TEXT":
                tokens = result["tokens"]
            else:
                language = "eng+mal" if any("\u0d00" <= c <= "\u0d7f" for c in result["text"]) else config.OCR_LANGUAGE
                scan, grid_removed = remove_table_grid(result["image"])
                metadata["grid_lines_removed"] = grid_removed
                tokens = extract_tokens(scan, page, language=language)
                # OCR PDF coordinates are converted back to points, so the same Y tolerance applies.
                for token in tokens:
                    token["bounding_box"] = {key: value / result["scale"] for key, value in token["bounding_box"].items()}
                metadata.update(ocr_language=language, text="\n".join(line["text"] for line in tokens_to_lines(tokens)))
                if result["coordinate_units"] == "pixels" and tokens:
                    metadata["row_scale"] = max(1, median(t["bounding_box"]["height"] for t in tokens) / 12)
            if config.EXTRACTION_DEBUG:
                logger.info("Page %s PDF extraction mode: %s", page, mode)
            all_tokens.extend(tokens)
            page_results.append({**metadata, "token_count": len(tokens)})
            if len(all_tokens) > 25000:
                raise AppError(422, "too_much_text", "This document contains too much text. Upload fewer pages at a time.")
        parsed = parse_destination_timetable(all_tokens, page_results)
        if len(parsed["entries"]) > 3000:
            raise AppError(422, "too_much_text", "This document contains too much text. Upload fewer pages at a time.")
        # Reprocessing creates a new draft so saved corrections are never overwritten.
        timetable = {"document_id": str(identifier), **parsed, "pages": page_results,
                     "created_at": now(), "updated_at": now(), "status": "draft", "revision": 1}
        result = db.timetables.insert_one(timetable)
        timetable["_id"] = result.inserted_id
        db.documents.update_one({"_id": identifier}, {"$set": {
            "status": "processed", "raw_ocr_text": parsed["raw_ocr_text"], "ocr_tokens": all_tokens,
            "pages": page_results, "latest_timetable_id": str(result.inserted_id), "error": None}})
        return public_record(timetable)
    except Exception as exc:
        if acquired:
            try:
                db.documents.update_one({"_id": identifier}, {"$set": {"status": "error", "error":
                    exc.message if isinstance(exc, AppError) else "Processing failed. Please try again."}})
            except Exception:
                logger.exception("Could not record processing failure")
        raise
    finally:
        processing_slots.release()
