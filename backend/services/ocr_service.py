import os
import shutil
import subprocess
from pathlib import Path

import pytesseract

from backend import config
from backend.utils.errors import AppError

INSTALL_HELP = (
    "Install Tesseract and the eng language pack (mal is optional for Malayalam). Windows: use the UB Mannheim "
    "installer and set TESSERACT_CMD in backend/.env. Ubuntu/Debian: sudo apt install "
    "tesseract-ocr tesseract-ocr-eng tesseract-ocr-mal. macOS: brew install tesseract tesseract-lang. "
    "See README.md for language data installation."
)


def find_tesseract() -> str | None:
    custom = os.getenv("TESSERACT_CMD", "").strip().strip('"')
    if custom:
        return custom if Path(custom).is_file() else shutil.which(custom)
    located = shutil.which("tesseract")
    if located:
        return located
    for path in [Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
                 Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
                 Path(os.getenv("LOCALAPPDATA", "")) / "Programs/Tesseract-OCR/tesseract.exe"]:
        if path.is_file():
            return str(path)
    return None


def ocr_status() -> dict:
    path = find_tesseract()
    result = {"tesseract_installed": False, "english_available": False,
              "malayalam_available": False, "ready": False, "instructions": INSTALL_HELP,
              "message": "Tesseract OCR is not installed or could not be found."}
    if not path:
        return result
    if not os.getenv("TESSDATA_PREFIX", "").strip():
        os.environ.pop("TESSDATA_PREFIX", None)
    try:
        subprocess.run([path, "--version"], capture_output=True, check=True, timeout=10)
        result["tesseract_installed"] = True
        languages = subprocess.run([path, "--list-langs"], capture_output=True, text=True,
                                   check=True, timeout=10).stdout.splitlines()
        languages = {line.strip() for line in languages}
        result.update(english_available="eng" in languages, malayalam_available="mal" in languages)
        result["ready"] = result["english_available"]
        result["message"] = "English OCR is ready." if result["ready"] else "English (eng) OCR language pack is missing."
        pytesseract.pytesseract.tesseract_cmd = path
    except (OSError, subprocess.SubprocessError):
        result["message"] = "Tesseract could not be started or its language data could not be read. Check TESSERACT_CMD and TESSDATA_PREFIX."
    return result


def require_ocr(language="eng"):
    status = ocr_status()
    if not status["ready"]:
        raise AppError(503, "ocr_unavailable", status["message"] + " " + INSTALL_HELP)
    if "mal" in language and not status["malayalam_available"]:
        raise AppError(503, "ocr_unavailable", "Malayalam OCR was requested but the mal language pack is missing.")


def extract_tokens(image, page: int, language="eng") -> list[dict]:
    if language not in {"eng", "eng+mal"}:
        raise AppError(422, "ocr_language", "OCR_LANGUAGE must be eng or eng+mal.")
    require_ocr(language)
    try:
        data = pytesseract.image_to_data(image, lang=language, config="--oem 1 --psm 6",
                                         output_type=pytesseract.Output.DICT, timeout=config.OCR_TIMEOUT)
    except (pytesseract.TesseractError, pytesseract.TesseractNotFoundError) as exc:
        raise AppError(503, "ocr_failed", "Tesseract could not process this page. Check the OCR status and language data.") from exc
    except RuntimeError as exc:
        raise AppError(422, "ocr_timeout", "OCR took too long. Try a smaller or clearer image, or fewer PDF pages.") from exc
    tokens = []
    for i, value in enumerate(data["text"]):
        value = str(value).strip()
        if not value:
            continue
        try:
            confidence = min(100.0, max(0.0, float(data["conf"][i])))
        except (ValueError, TypeError):
            confidence = 0.0
        tokens.append({"text": value, "confidence": round(confidence, 1), "page": page,
                       "bounding_box": {key: int(data[key][i]) for key in ("left", "top", "width", "height")},
                       "block": int(data["block_num"][i]), "line": int(data["line_num"][i])})
    return tokens


def tokens_to_lines(tokens: list[dict]) -> list[dict]:
    """Group by visual row, including columns Tesseract puts in different blocks."""
    rows = []
    for token in sorted(tokens, key=lambda t: (t["page"], t["bounding_box"]["top"])):
        box = token["bounding_box"]
        center = box["top"] + box["height"] / 2
        matching = next((row for row in reversed(rows[-10:])
                         if row["page"] == token["page"]
                         and abs(row["center"] - center) <= max(5, min(row["height"], box["height"]) * 0.5)), None)
        if matching is None:
            rows.append({"page": token["page"], "center": center, "height": box["height"], "tokens": [token]})
        else:
            matching["tokens"].append(token)
    lines = []
    for row in rows:
        ordered = sorted(row["tokens"], key=lambda t: t["bounding_box"]["left"])
        lines.append({"text": " ".join(t["text"] for t in ordered), "page": row["page"],
                      "confidence": round(sum(t["confidence"] for t in ordered) / len(ordered), 1), "tokens": ordered})
    return lines
