"""Conservative, coordinate-based parsing of Sl. No. / Destination / Timing tables."""
import logging
import re
from collections import Counter

from backend import config

logger = logging.getLogger(__name__)
TIME_PATTERN = re.compile(r"(\d{1,2})\s*[:.]\s*(\d{2})(?:\s*([AP])\.?\s*M\.?)?", re.I)
HEADER_ALIASES = {
    "sl_no": {"slno", "sno", "sino", "serialno", "serialnumber"},
    "destination": {"destination", "busstop", "stop", "stopname", "busstopname"},
    "timing": {"timing", "time"},
}


def normalize_time(value: str | None) -> str | None:
    match = TIME_PATTERN.fullmatch((value or "").strip())
    if not match:
        return None
    hour, minute, meridiem = match.groups()
    hour, minute = int(hour), int(minute)
    if minute > 59:
        return None
    if meridiem:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if meridiem.upper() == "P" else 0)
    elif hour > 23:
        return None
    return f"{hour:02d}:{minute:02d}"


def center_y(word):
    box = word["bounding_box"]
    return box["top"] + box["height"] / 2


def bounding_box(words):
    boxes = [word["bounding_box"] for word in words]
    left, top = min(b["left"] for b in boxes), min(b["top"] for b in boxes)
    return {"left": left, "top": top,
            "width": max(b["left"] + b["width"] for b in boxes) - left,
            "height": max(b["top"] + b["height"] for b in boxes) - top}


def group_words_into_rows(words: list[dict], y_tolerance: float = 4) -> list[dict]:
    rows = []
    for word in sorted(words, key=lambda w: (w["page"], center_y(w), w["bounding_box"]["left"])):
        y = center_y(word)
        if not rows or rows[-1]["page"] != word["page"] or y - rows[-1]["y"] > y_tolerance:
            rows.append({"page": word["page"], "y": y, "words": [word]})
        else:
            rows[-1]["words"].append(word)
    for row in rows:
        row["words"].sort(key=lambda w: w["bounding_box"]["left"])
    return rows


def detect_table_headers(row: dict) -> dict | None:
    words, found, used = row["words"], {}, set()
    for index in range(len(words)):
        if index in used:
            continue
        # Prefer a complete multiword label (e.g. "Bus Stop Name") over its prefix.
        for count in range(3, 0, -1):
            chunk = words[index:index + count]
            if len(chunk) != count:
                continue
            label = re.sub(r"[^a-z]", "", "".join(w["text"].lower() for w in chunk))
            name = next((name for name, aliases in HEADER_ALIASES.items() if label in aliases), None)
            if name:
                if name in found:
                    return None
                found[name] = bounding_box(chunk)
                used.update(range(index, index + count))
                break
    # Extra headings imply a different schema. Do not absorb another column.
    if set(found) != {"sl_no", "destination", "timing"} or len(used) != len(words):
        return None
    ordered = [found[key] for key in ("sl_no", "destination", "timing")]
    if any(a["left"] + a["width"] >= b["left"] for a, b in zip(ordered, ordered[1:])):
        return None
    return found


def calculate_column_boundaries(headers: dict, page_width: float) -> dict:
    serial, destination, timing = (headers[key] for key in ("sl_no", "destination", "timing"))
    first = (serial["left"] + serial["width"] + destination["left"]) / 2
    second = (destination["left"] + destination["width"] + timing["left"]) / 2
    return {"sl_no": (0, first), "destination": (first, second), "timing": (second, page_width)}


def column_words(row, boundaries, name):
    left, right = boundaries[name]
    return [word for word in row["words"]
            if left <= word["bounding_box"]["left"]
            and word["bounding_box"]["left"] + word["bounding_box"]["width"] <= right]


def cell_text(words):
    return " ".join(word["text"].replace("\n", " ").replace("\r", " ") for word in words).strip()


def detect_serial_number_rows(row: dict, boundaries: dict) -> int | None:
    text = cell_text(column_words(row, boundaries, "sl_no"))
    return int(text) if re.fullmatch(r"[0-9]+", text) else None


def extract_destination_from_row(row: dict, boundaries: dict) -> str:
    return cell_text(column_words(row, boundaries, "destination"))


def extract_time_from_row(row: dict, boundaries: dict) -> tuple[str | None, str]:
    raw = cell_text(column_words(row, boundaries, "timing"))
    return normalize_time(raw), raw


def is_source_note(row: dict, boundaries: dict | None) -> bool:
    """Recognize an explicitly labelled note spanning columns, not a damaged table row."""
    if not boundaries or detect_serial_number_rows(row, boundaries) is not None:
        return False
    first = row["words"][0]
    return (first["bounding_box"]["left"] < boundaries["destination"][0]
            and re.fullmatch(r"notes?\s*:", first["text"], re.I) is not None)


def validate_row(row: dict, serial_counts: Counter, row_counts: Counter) -> dict:
    row, issues = dict(row), []
    serial = row.get("sl_no")
    if type(serial) is not int or serial < 1:
        issues.append("Missing or invalid row anchor")
    elif serial_counts[serial] > 1:
        issues.append("Duplicate row anchor")
    if not row["destination"]:
        issues.append("Missing destination")
    if row["timing"] is None:
        issues.append("Invalid or missing timing (use HH:MM)")
    if row_counts[(row["destination"], row["timing"])] > 1 and (row["destination"] or row["timing"]):
        issues.append("Duplicate row")
    if row.get("ambiguous") and not row.get("reviewed"):
        issues.append("Ambiguous layout; check source")
    if row.get("confidence", 0) < 60 and not row.get("reviewed"):
        issues.append("Low extraction confidence")
    row.update(issues=issues, needs_review=bool(issues))
    return row


def validate_entries(entries: list[dict]) -> list[dict]:
    cleaned = [{**entry, "destination": (entry.get("destination") or "").replace("\n", " ").replace("\r", " ").strip(),
                "timing": normalize_time(entry.get("timing"))} for entry in entries]
    serials = Counter(row.get("sl_no") for row in cleaned)
    values = Counter((row["destination"], row["timing"]) for row in cleaned)
    return sorted([validate_row(row, serials, values) for row in cleaned],
                  key=lambda row: row["sl_no"] if type(row.get("sl_no")) is int else float("inf"))


def parse_destination_timetable(words: list[dict], pages: list[dict], *, y_tolerance=None, debug=None) -> dict:
    tolerance = config.TABLE_Y_TOLERANCE if y_tolerance is None else y_tolerance
    debug = config.EXTRACTION_DEBUG if debug is None else debug
    entries, warnings, unparsed = [], [], []
    for page in pages:
        number = page["page"]
        rows = group_words_into_rows([word for word in words if word["page"] == number], tolerance * page.get("row_scale", 1))
        header_indexes = {index: header for index, row in enumerate(rows)
                          if (header := detect_table_headers(row))}
        boundaries = None
        page["headers"] = []
        if not header_indexes:
            warnings.append(f"Page {number}: table headers could not be determined. Raw rows retained for review.")
        for index, row in enumerate(rows):
            if index in header_indexes:
                boundaries = calculate_column_boundaries(header_indexes[index], page["width"])
                page["headers"].append({"y": row["y"], "columns": boundaries})
                if debug:
                    logger.info("Page %s HEADERS Y: %.2f columns: %s", number, row["y"], boundaries)
                continue
            if header_indexes and index < min(header_indexes):
                continue
            serial = detect_serial_number_rows(row, boundaries) if boundaries else None
            destination = extract_destination_from_row(row, boundaries) if boundaries else ""
            timing, raw_time = extract_time_from_row(row, boundaries) if boundaries else (None, "")
            raw = cell_text(row["words"])
            if is_source_note(row, boundaries):
                unparsed.append({"page": number, "text": raw, "kind": "source_note",
                                 "bounding_box": bounding_box(row["words"])})
                continue
            if serial is None:
                unparsed.append({"page": number, "text": raw, "bounding_box": bounding_box(row["words"])})
                destination, timing = "", None
            selected = [w for name in boundaries or {} for w in column_words(row, boundaries, name)]
            ambiguous = not boundaries or len(selected) != len(row["words"]) or serial is None
            # A word crossing a boundary must not become a partial place name/time.
            crossing = [w for w in row["words"] if w not in selected] if boundaries else []
            for word in crossing:
                box = word["bounding_box"]
                for name in ("destination", "timing"):
                    left, right = boundaries[name]
                    if box["left"] < right and box["left"] + box["width"] > left:
                        if name == "destination":
                            destination = ""
                        else:
                            timing = None
            entry = {"sl_no": serial, "destination": destination, "timing": timing,
                     "confidence": min(w["confidence"] for w in row["words"]),
                     "needs_review": ambiguous, "ambiguous": ambiguous, "reviewed": False,
                     "page": number, "y": row["y"], "original_destination": destination,
                     "original_time": raw_time, "raw_text": raw,
                     "bounding_box": bounding_box(row["words"]), "source_words": row["words"]}
            entries.append(entry)
            if debug:
                logger.info("ROW %s PAGE: %s Y: %.2f SL: %s DESTINATION: %s TIME: %s",
                            len(entries), number, row["y"], serial, destination, timing)
    entries = validate_entries(entries)
    if not entries:
        warnings.append("No table rows detected. Check the source or add rows manually.")
    modes = list(dict.fromkeys(page["mode"] for page in pages))
    return {"table_type": "destination_timetable", "entries": entries,
            "route_name": None, "origin": None, "destination_route": None, "destination": None,
            "confidence": round(sum(row["confidence"] for row in entries) / len(entries), 1) if entries else 0,
            "needs_review": bool(warnings) or any(row["needs_review"] for row in entries),
            "warnings": warnings, "unparsed_lines": unparsed,
            "extraction_method": modes[0] if len(modes) == 1 else "MIXED",
            "raw_ocr_text": "\n".join(f"[Page {page['page']}] {page['text']}" for page in pages)}


def parse_timetable(lines: list[dict]) -> dict:
    """Text-only lines cannot establish table columns; preserve source for review."""
    words = [word for line in lines for word in line.get("tokens", [])]
    pages = [{"page": page, "width": max((w["bounding_box"]["left"] + w["bounding_box"]["width"]
               for w in words if w["page"] == page), default=1), "mode": "OCR_FALLBACK",
              "text": "\n".join(line["text"] for line in lines if line["page"] == page)}
             for page in sorted({line["page"] for line in lines})]
    return parse_destination_timetable(words, pages)
