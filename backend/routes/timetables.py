import io
import json

import pandas as pd
from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from pymongo import ReturnDocument

from backend.database.connection import get_database, object_id, public_record
from backend.models.timetable import TimetableUpdate
from backend.services.processing import now
from backend.services.timetable_parser import normalize_time, validate_entries
from backend.services.validator import validate_stops
from backend.utils.errors import AppError

router = APIRouter(prefix="/api/timetables", tags=["Timetables"])


@router.get("")
def list_timetables(limit: int = Query(50, ge=1, le=100), skip: int = Query(0, ge=0), db=Depends(get_database)):
    cursor = db.timetables.find({}, {"raw_ocr_text": 0, "pages": 0, "unparsed_lines": 0}).sort("updated_at", -1).skip(skip).limit(limit)
    return {"items": [public_record(t) for t in cursor], "total": db.timetables.count_documents({})}


@router.get("/{timetable_id}")
def get_timetable(timetable_id: str, db=Depends(get_database)):
    timetable = db.timetables.find_one({"_id": object_id(timetable_id)})
    if not timetable:
        raise AppError(404, "not_found", "Timetable not found.")
    return public_record(timetable)


@router.put("/{timetable_id}")
def update_timetable(timetable_id: str, payload: TimetableUpdate, db=Depends(get_database)):
    identifier = object_id(timetable_id)
    existing = db.timetables.find_one({"_id": identifier})
    if not existing:
        raise AppError(404, "not_found", "Timetable not found.")
    structured = existing.get("table_type") == "destination_timetable"
    if structured != (payload.entries is not None):
        raise AppError(422, "invalid_schema", "Use the entry schema returned by this timetable.")
    if structured:
        entries = validate_entries([entry.model_dump() for entry in payload.entries])
        changes = {"entries": entries, "route_name": None, "origin": None,
                   "destination": None, "destination_route": None,
                   "confidence": round(sum(row["confidence"] for row in entries) / len(entries), 1) if entries else 0,
                   "needs_review": not entries or any(row["needs_review"] for row in entries)}
    else:
        changes = payload.model_dump(exclude={"revision", "entries"})
        for row in changes["stops"]:
            row["time"] = normalize_time(row["time"]) or row["time"].strip()
        changes["stops"] = validate_stops(changes["stops"])
        changes["needs_review"] = not changes["stops"] or any(s["needs_review"] for s in changes["stops"])
    changes.update(updated_at=now(), status="saved")
    timetable = db.timetables.find_one_and_update({"_id": identifier, "revision": payload.revision},
        {"$set": changes, "$inc": {"revision": 1}}, return_document=ReturnDocument.AFTER)
    if not timetable:
        if db.timetables.find_one({"_id": identifier}):
            raise AppError(409, "revision_conflict", "This timetable changed in another editor. Reopen it from Saved timetables before saving.")
        raise AppError(404, "not_found", "Timetable not found.")
    return public_record(timetable)


@router.delete("/{timetable_id}")
def delete_timetable(timetable_id: str, db=Depends(get_database)):
    timetable = db.timetables.find_one_and_delete({"_id": object_id(timetable_id)})
    if not timetable:
        raise AppError(404, "not_found", "Timetable not found.")
    latest = db.timetables.find_one({"document_id": timetable["document_id"]}, sort=[("created_at", -1)])
    db.documents.update_one({"_id": object_id(timetable["document_id"]), "latest_timetable_id": timetable_id},
                            {"$set": {"latest_timetable_id": str(latest["_id"]) if latest else None}})
    return {"deleted": True}


@router.get("/{timetable_id}/export/json")
def export_json(timetable_id: str, db=Depends(get_database)):
    timetable = get_timetable(timetable_id, db)
    return Response(json.dumps(jsonable_encoder(timetable), ensure_ascii=False, indent=2),
                    media_type="application/json", headers={"Content-Disposition": f'attachment; filename="timetable-{timetable_id}.json"'})


def spreadsheet_safe(value):
    # CSVs are commonly opened in Excel; quoted cells can still execute formulas.
    return "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value


@router.get("/{timetable_id}/export/csv")
def export_csv(timetable_id: str, db=Depends(get_database)):
    timetable = get_timetable(timetable_id, db)
    columns = ["route_name", "origin", "destination", "stop_name", "time", "confidence", "confidence_level",
               "page", "trip_index", "original_text", "original_time", "normalized_text", "reviewed", "needs_review", "issues"]
    rows = []
    if timetable.get("table_type") == "destination_timetable":
        columns = ["destination", "timing", "confidence", "needs_review", "issues"]
    for stop in timetable.get("entries", timetable.get("stops", [])):
        row = {**{key: timetable[key] for key in ("route_name", "origin", "destination")}, **stop}
        row["issues"] = "; ".join(row.get("issues", []))
        rows.append({key: spreadsheet_safe(row.get(key, "")) for key in columns})
    stream = io.StringIO()
    pd.DataFrame(rows, columns=columns).to_csv(stream, index=False, lineterminator="\r\n")
    return Response(stream.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="timetable-{timetable_id}.csv"'})
