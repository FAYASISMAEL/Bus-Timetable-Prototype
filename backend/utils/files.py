import re
from pathlib import Path

from PIL import Image

from backend import config
from backend.services.image_processor import read_image
from backend.services.pdf_processor import validate_pdf
from backend.utils.errors import AppError

MIME_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".pdf": "application/pdf"}


def sanitize_filename(filename: str) -> str:
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[^\w.() -]", "_", name, flags=re.UNICODE).strip(" .")
    return name[-160:] or "upload"


def validate_filename(filename: str, mime: str | None) -> tuple[str, str]:
    name = sanitize_filename(filename)
    suffix = Path(name).suffix.lower()
    if suffix not in MIME_TYPES:
        raise AppError(415, "unsupported_file", "Unsupported file type. Use JPG, JPEG, PNG, or PDF.")
    if mime not in (MIME_TYPES[suffix], "application/octet-stream", None, ""):
        raise AppError(415, "type_mismatch", "The file type does not match its extension.")
    return name, suffix


def inspect_upload(path: Path, suffix: str) -> int:
    if suffix == ".pdf":
        with path.open("rb") as stream:
            if b"%PDF-" not in stream.read(1024):
                raise AppError(422, "unreadable_pdf", "Could not read this PDF. The file content is not a PDF.")
        return validate_pdf(path)
    read_image(path)
    with Image.open(path) as image:
        expected = "PNG" if suffix == ".png" else "JPEG"
        if image.format != expected:
            raise AppError(415, "type_mismatch", "The image content does not match its extension.")
    return 1


def source_path(document: dict) -> Path:
    # Paths always derive from a validated database ID, never the client filename.
    path = (config.UPLOAD_DIR / f"{document['_id']}{document['extension']}").resolve()
    if path.parent != config.UPLOAD_DIR:
        raise AppError(400, "invalid_path", "Invalid source file path.")
    if not path.is_file():
        raise AppError(410, "source_missing", "The original upload is missing. Upload the file again.")
    return path
