import logging
import tempfile
from pathlib import Path

import aiofiles
from bson import ObjectId
from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from backend import config
from backend.database.connection import get_database, object_id, public_record
from backend.services.processing import now, process_document
from backend.utils.errors import AppError
from backend.utils.files import MIME_TYPES, inspect_upload, source_path, validate_filename

router = APIRouter(prefix="/api", tags=["Documents"])
logger = logging.getLogger(__name__)


@router.post("/upload", status_code=201)
async def upload(file: UploadFile = File(...), db=Depends(get_database)):
    temporary = final_path = None
    inserted = False
    try:
        filename, suffix = validate_filename(file.filename or "", file.content_type)
        config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=config.UPLOAD_DIR, prefix="staging-", suffix=suffix, delete=False) as handle:
            temporary = Path(handle.name)
        size = 0
        async with aiofiles.open(temporary, "wb") as stream:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > config.MAX_UPLOAD_BYTES:
                    raise AppError(413, "file_too_large", f"File is too large. Maximum size is {config.MAX_UPLOAD_BYTES // 1048576} MB.")
                await stream.write(chunk)
        if not size:
            raise AppError(422, "empty_file", "The uploaded file is empty.")
        pages = await run_in_threadpool(inspect_upload, temporary, suffix)
        identifier = ObjectId()
        final_path = config.UPLOAD_DIR / f"{identifier}{suffix}"
        temporary.replace(final_path)
        document = {"_id": identifier, "original_filename": filename, "extension": suffix,
                    "file_type": MIME_TYPES[suffix], "uploaded_at": now(), "raw_ocr_text": "",
                    "status": "uploaded", "size_bytes": size, "page_count": pages,
                    "latest_timetable_id": None, "error": None}
        await run_in_threadpool(db.documents.insert_one, document)
        inserted = True
        return public_record(document)
    finally:
        await file.close()
        if temporary:
            temporary.unlink(missing_ok=True)
        if final_path and not inserted:
            final_path.unlink(missing_ok=True)


@router.get("/documents")
def list_documents(limit: int = Query(50, ge=1, le=100), skip: int = Query(0, ge=0), db=Depends(get_database)):
    cursor = db.documents.find({}, {"ocr_tokens": 0, "raw_ocr_text": 0, "pages": 0}).sort("uploaded_at", -1).skip(skip).limit(limit)
    return {"items": [public_record(d) for d in cursor], "total": db.documents.count_documents({})}


@router.get("/documents/{document_id}")
def get_document(document_id: str, db=Depends(get_database)):
    document = db.documents.find_one({"_id": object_id(document_id)})
    if not document:
        raise AppError(404, "not_found", "Document not found.")
    return public_record(document)


@router.get("/documents/{document_id}/source")
def get_source(document_id: str, db=Depends(get_database)):
    document = get_document(document_id, db)
    return FileResponse(source_path(document), media_type=document["file_type"],
                        filename=document["original_filename"], content_disposition_type="inline",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


@router.post("/process/{document_id}", status_code=201)
def process(document_id: str, db=Depends(get_database)):
    return process_document(db, document_id)


@router.delete("/documents/{document_id}")
def delete_document(document_id: str, db=Depends(get_database)):
    identifier = object_id(document_id)
    document = db.documents.find_one_and_delete({"_id": identifier, "status": {"$ne": "processing"}})
    if not document:
        if db.documents.find_one({"_id": identifier}):
            raise AppError(409, "already_processing", "Wait for processing to finish before deleting the document.")
        raise AppError(404, "not_found", "Document not found.")
    db.timetables.delete_many({"document_id": document_id})
    try:
        source_path(document).unlink(missing_ok=True)
    except AppError as exc:
        if exc.status != 410:
            raise
    return {"deleted": True}
