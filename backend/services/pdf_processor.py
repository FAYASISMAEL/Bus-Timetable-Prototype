from pathlib import Path

import cv2
import numpy as np
import pymupdf

from backend import config
from backend.utils.errors import AppError


def extract_pdf_words(page, number: int) -> tuple[str, list[dict]]:
    """Read all three text representations; keep geometry in PDF points."""
    text = page.get_text("text")
    words = page.get_text("words")
    layout = page.get_text("dict", flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
    spans = [span for block in layout.get("blocks", []) for line in block.get("lines", [])
             for span in line.get("spans", [])]
    tokens = [{"text": word[4], "page": number, "confidence": 100.0,
               "bounding_box": {"left": word[0], "top": word[1],
                                "width": word[2] - word[0], "height": word[3] - word[1]},
               "block": word[5], "line": word[6]} for word in words if word[4].strip()]
    return text or "\n".join(span.get("text", "") for span in spans), tokens


def detect_pdf_mode(text: str, words: list[dict]) -> str:
    characters = [char for char in text if not char.isspace()]
    useful = sum(char.isalnum() for char in characters)
    corrupt = sum(char == "\ufffd" or ord(char) < 32 for char in characters)
    return "DIRECT_TEXT" if words and useful >= 3 and corrupt < max(1, len(characters) * .1) else "OCR_FALLBACK"


def extract_pdf_pages(path: Path):
    """Choose extraction independently per page. Never render readable text."""
    validate_pdf(path)
    with pymupdf.open(stream=path.read_bytes(), filetype="pdf") as document:
        for number, page in enumerate(document, start=1):
            text, tokens = extract_pdf_words(page, number)
            mode = detect_pdf_mode(text, tokens)
            result = {"page": number, "mode": mode, "text": text, "tokens": tokens,
                      "width": page.rect.width, "height": page.rect.height,
                      "coordinate_units": "pdf_points", "scale": 1.0}
            if mode == "OCR_FALLBACK":
                scale = min(300 / 72, 4500 / max(page.rect.width, page.rect.height))
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csGRAY, alpha=False)
                result.update(image=np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width), scale=scale)
            yield result


def validate_pdf(path: Path) -> int:
    try:
        # Opening from bytes avoids a leaked OS file handle when MuPDF rejects a
        # malformed PDF during construction (especially important on Windows).
        with pymupdf.open(stream=path.read_bytes(), filetype="pdf") as document:
            if not document.is_pdf or document.needs_pass:
                raise AppError(422, "locked_pdf", "Upload an unencrypted PDF that does not require a password.")
            if not 1 <= document.page_count <= config.MAX_PDF_PAGES:
                raise AppError(422, "pdf_page_limit", f"PDF must contain 1–{config.MAX_PDF_PAGES} pages.")
            for page in document:
                if not 1 <= min(page.rect.width, page.rect.height) or max(page.rect.width, page.rect.height) > 14400:
                    raise AppError(422, "pdf_dimensions", "This PDF has unsupported page dimensions.")
            return document.page_count
    except AppError:
        raise
    except Exception as exc:
        raise AppError(422, "unreadable_pdf", "Could not read this PDF. It may be corrupted.") from exc


def render_pdf_pages(path: Path):
    validate_pdf(path)
    try:
        with pymupdf.open(stream=path.read_bytes(), filetype="pdf") as document:
            for number, page in enumerate(document, start=1):
                scale = min(220 / 72, 3200 / max(page.rect.width, page.rect.height))
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB, alpha=False)
                rgb = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, 3)
                yield number, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(422, "pdf_render_failed", "Could not render this PDF. Try exporting it again or upload an image.") from exc
