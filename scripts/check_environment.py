"""Report real dependencies; optionally install official OCR data inside the project."""
import argparse
import importlib
import os
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def install_language_data():
    from dotenv import set_key
    from backend.services.ocr_service import ocr_status

    if ocr_status()["ready"]:
        print("Both OCR language packs are already available.")
        return
    target = ROOT / "backend" / "tessdata"
    target.mkdir(exist_ok=True)
    # Keep downloads outside Program Files: no administrator permission required.
    for language in ("eng", "mal"):
        destination = target / f"{language}.traineddata"
        temporary = destination.with_suffix(".download")
        try:
            print(f"Downloading official tessdata_fast/{language}.traineddata …")
            url = f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/{language}.traineddata"
            with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as stream:
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > 30 * 1024 * 1024:
                        raise RuntimeError("Language download exceeded 30 MB.")
                    stream.write(chunk)
            if total < 10000:
                raise RuntimeError("Downloaded language data was unexpectedly small.")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    env_path = ROOT / "backend" / ".env"
    if not env_path.exists():
        shutil.copyfile(ROOT / "backend" / ".env.example", env_path)
    set_key(str(env_path), "TESSDATA_PREFIX", str(target).replace("\\", "/"))
    os.environ["TESSDATA_PREFIX"] = str(target)
    print(f"Set TESSDATA_PREFIX in backend/.env to {target}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-language-data", action="store_true", help="Download official eng + mal data into backend/tessdata if either pack is missing")
    args = parser.parse_args()
    print("Smart Timetable Digitizer — environment report")
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    print(f"Node: {shutil.which('node') or 'MISSING'}")
    print(f"npm: {shutil.which('npm.cmd') or shutil.which('npm') or 'MISSING'}")
    imports = ["fastapi", "uvicorn", "multipart", "pymongo", "dotenv", "pytesseract", "cv2", "PIL", "pymupdf", "pandas", "numpy", "aiofiles"]
    missing = []
    for name in imports:
        try:
            importlib.import_module(name)
            print(f"  {name}: OK")
        except Exception as exc:
            print(f"  {name}: FAILED ({type(exc).__name__})")
            missing.append(name)
    if missing:
        print("Install dependencies: backend virtual-environment python -m pip install -r backend/requirements.txt")
        return 1
    if args.install_language_data:
        try:
            install_language_data()
        except Exception as exc:
            print(f"Language installation failed: {type(exc).__name__}: {exc}")
            print("Download eng.traineddata and mal.traineddata from https://github.com/tesseract-ocr/tessdata_fast into one folder, then set TESSDATA_PREFIX in backend/.env.")
    from backend.services.ocr_service import ocr_status
    from backend.database.connection import database_status
    ocr, db = ocr_status(), database_status()
    for key in ["tesseract_installed", "english_available", "malayalam_available"]:
        print(f"{key}: {'OK' if ocr[key] else 'MISSING'}")
    print(ocr["message"])
    if not ocr["ready"]:
        print(ocr["instructions"])
    print(db["message"])
    ready = ocr["ready"] and db["connected"]
    print("READY — all runtime services are available." if ready else "SETUP INCOMPLETE — the UI can start, but fix the missing services above before OCR/save.")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
