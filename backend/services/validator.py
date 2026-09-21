import re
from collections import Counter


def confidence_level(confidence: float) -> str:
    return "high" if confidence >= 80 else "medium" if confidence >= 60 else "low"


def normalize_stop(value: str) -> str:
    cleaned = " ".join(value.split()).strip(" |,;:")
    # Preserve Malayalam and mixed-script values without transliteration.
    return cleaned.title() if cleaned.isascii() else cleaned


def validate_stops(stops: list[dict]) -> list[dict]:
    keys = [(s.get("stop_name", "").strip().casefold(), s.get("time", ""), s.get("trip_index", 1)) for s in stops]
    duplicates = Counter(keys)
    output = []
    for row, key in zip(stops, keys):
        row = dict(row)
        name = row.get("stop_name", "").strip()
        issues = []
        if not name:
            issues.append("Missing stop name")
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", row.get("time", "")):
            issues.append("Invalid or missing time (use HH:MM)")
        if duplicates[key] > 1:
            issues.append("Duplicate row")
        if name and (not any(c.isalpha() for c in name) or re.search(r"[�?@#=]|(.)\1{4,}", name)):
            issues.append("Suspicious stop text")
        level = confidence_level(row.get("confidence", 0))
        if level == "low" and not row.get("reviewed"):
            issues.append("Low OCR confidence")
        if row.get("ambiguous") and not row.get("reviewed"):
            issues.append("Ambiguous layout; check source")
        row.update(stop_name=name, normalized_text=normalize_stop(name), issues=issues,
                   confidence_level=level, needs_review=bool(issues))
        output.append(row)
    return output
