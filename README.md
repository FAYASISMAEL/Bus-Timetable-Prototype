# Smart Timetable Digitizer

A working SC-04 hackathon prototype that converts three-column destination timetables into editable data using **direct PDF text extraction with OCR for scans**.

Printed bus schedules vary in layout and often contain recognition errors. This application preserves the source, raw OCR, confidence, page numbers, and original text so a person can inspect and correct the extracted data before exporting it. There is no login or external AI service.

## Features

- JPG, JPEG, PNG, and PDF uploads with a 15 MB default limit, content validation, safe filenames, and useful errors.
- PyMuPDF text, word and layout extraction first; readable pages never run OCR. Scanned pages render at up to 300 DPI.
- Grayscale scan processing, light contrast adjustment and measured deskew for images; long table rules are removed only when a grid is detected.
- Tesseract `image_to_data()` with English (`eng`) by default. Malayalam (`eng+mal`) requires detected Malayalam text or explicit configuration; the Malayalam pack is optional.
- Header-derived columns and numeric row anchors preserve Destination/Timing relationships. AM/PM and dotted times normalize to HH:MM; invalid or missing times remain null.
- Editable rows, add/remove controls, review checkboxes, duplicate detection, invalid-time warnings, and confidence badges.
- MongoDB documents and timetables; drafts are persisted, corrections are saved explicitly, and reprocessing creates a separate draft.
- JSON preserves internal row anchors and source geometry. CSV exposes Destination, Timing, Confidence and Review information without serial numbers.
- Backend, MongoDB, Tesseract, and language-pack status indicators.
- Optimistic edit revisions prevent one browser from silently overwriting another browser's corrections.

## Architecture and stack

```text
React + JavaScript + Vite + basic CSS + Axios (5173)
  -> FastAPI + Uvicorn (8000)
     -> validated source file + MongoDB document metadata
     -> PyMuPDF text / words / dict per page
     -> scanned pages only: grayscale rendering -> Tesseract eng
     -> header columns + serial anchors + same-row geometry -> validation
     -> MongoDB via PyMongo -> editor / JSON / Pandas CSV
```

Configuration uses `.env` files and python-dotenv. Pillow safely decodes image files; NumPy supports image processing; aiofiles streams uploads. No framework in the requested stack is replaced.

## Project structure

```text
smart-timetable-digitizer/
  README.md, .gitignore, .env.example, package.json, pytest.ini
  setup.ps1, setup.sh, start.ps1, start.sh
  frontend/
    .env.example, index.html, package.json, package-lock.json, vite.config.js
    src/
      main.jsx, App.jsx
      api/client.js
      components/SystemStatus.jsx, SourcePreview.jsx
      pages/UploadPage.jsx, ProcessingPage.jsx, EditorPage.jsx, SavedPage.jsx
      styles/main.css
  backend/
    .env.example, requirements.txt, requirements-dev.txt, main.py, config.py
    database/connection.py
    models/timetable.py
    routes/system.py, documents.py, timetables.py
    services/image_processor.py, pdf_processor.py, ocr_service.py
    services/timetable_parser.py, validator.py, processing.py
    utils/errors.py, files.py
    tests/test_core.py, test_api.py
  scripts/
    check_environment.py, launch.mjs
```

Generated `.env`, `.venv`, uploads, local language packs, development data, and dependency folders are ignored by Git. The root `.env.example` is informational; actual settings belong in the backend/frontend files.

## Prerequisites

- Python **3.10 or newer** (3.12 tested).
- Node.js **22.x (22.12 or later)**, with npm. Vercel is pinned to this major version.
- Tesseract 5 with both `eng` and `mal` data.
- MongoDB Community locally, or a MongoDB Atlas database.

### Windows setup

Open PowerShell in `smart-timetable-digitizer`:

```powershell
python --version
node --version
npm --version
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

The script checks versions, creates and activates `backend\.venv`, upgrades pip, installs Python/frontend packages, copies missing environment files, and prints a real environment report. It attempts a current-user Tesseract installation through winget when necessary. Some Tesseract installers only support machine scope; in that case the script prints manual instructions rather than escalating privileges automatically.

When OCR language data is missing, setup downloads official `eng.traineddata` and `mal.traineddata` into `backend/tessdata` and sets `TESSDATA_PREFIX` in `backend/.env`. Existing working system language packs are used as-is. Setup never installs or modifies a MongoDB service automatically.

Verify the report. `SETUP INCOMPLETE` means the UI can start but some OCR/database operations cannot work yet. Follow the relevant section below, then run:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\check_environment.py
```

### macOS setup

Install Python/Node using your preferred method. If Homebrew is installed:

```bash
brew install python node tesseract tesseract-lang
bash ./setup.sh
```

The script detects macOS and Homebrew and prints matching instructions. It does not run apt commands or sudo. Use Atlas, or follow the official MongoDB Community macOS instructions linked below.

### Ubuntu / Debian setup

Install Python/venv and Tesseract, and install a supported Node.js release:

```bash
sudo apt-get update
sudo apt-get install python3 python3-venv tesseract-ocr tesseract-ocr-eng tesseract-ocr-mal
node --version
npm --version
bash ./setup.sh
```

Other distributions should use their own package manager. The script prints apt instructions only when `apt-get` is available.

## MongoDB configuration

### Local MongoDB

Install [MongoDB Community](https://www.mongodb.com/docs/manual/administration/install-community/) and start its service, or run `mongod` manually with a dedicated data directory. On Windows, a service installation may require administrator permission; a foreground process with a project-local data directory does not.

For an existing Windows installation, in a separate PowerShell terminal at the project root:

```powershell
New-Item -ItemType Directory -Force -Path .runtime\mongo
& 'C:\Program Files\MongoDB\Server\7.0\bin\mongod.exe' --dbpath .runtime\mongo --bind_ip 127.0.0.1 --port 27017
```

Adjust the executable path to the installed MongoDB version. Keep this terminal open. On macOS/Linux with `mongod` installed:

```bash
mkdir -p .runtime/mongo
mongod --dbpath .runtime/mongo --bind_ip 127.0.0.1 --port 27017
```

The default URI is `mongodb://localhost:27017`. The database `smart_timetable` and its `documents` and `timetables` collections appear on the first successful upload/process. Database access is real; there is no memory-only fallback. If MongoDB is unavailable, the API returns 503 for database operations while the health and status endpoints remain accessible.

### MongoDB Atlas

1. Create an Atlas cluster and a database user with read/write access to `smart_timetable`.
2. Allow your development machine's IP in Atlas Network Access.
3. Copy the driver connection string from Connect → Drivers.
4. Put it only in `backend/.env`, for example:

```dotenv
MONGODB_URI=mongodb+srv://YOUR_USER:URL_ENCODED_PASSWORD@YOUR_CLUSTER.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB=smart_timetable
```

Replace every placeholder; percent-encode reserved characters in passwords. Restart the backend and check `/api/system/database-status`. Never commit `.env` or credentials. See [Atlas connection instructions](https://www.mongodb.com/docs/atlas/connect-to-database-deployment/).

## Tesseract and Malayalam

Check the engine and its system language directory:

```powershell
tesseract --version
tesseract --list-langs
```

On Windows, use the [UB Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki), also linked by [Tesseract's installation documentation](https://tesseract-ocr.github.io/tessdoc/Installation.html):

```powershell
winget install --id UB-Mannheim.TesseractOCR --exact
```

The backend checks PATH and common Windows install locations, including `C:\Program Files\Tesseract-OCR\tesseract.exe`. A custom path can be specified in `backend/.env`:

```dotenv
TESSERACT_CMD=C:/Program Files/Tesseract-OCR/tesseract.exe
```

`mal` is the official Malayalam model identifier ([Tesseract data documentation](https://tesseract-ocr.github.io/tessdoc/Data-Files.html)). English is the default OCR language. Set `OCR_LANGUAGE=eng+mal` only when Malayalam scan recognition is explicitly needed. Digital PDFs need neither OCR language pack.

To download official data into the project without editing Program Files:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\check_environment.py --install-language-data
```

macOS/Linux equivalent:

```bash
backend/.venv/bin/python scripts/check_environment.py --install-language-data
```

Manual alternative: download `eng.traineddata` and `mal.traineddata` from [tesseract-ocr/tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast), place both in one directory, and set `TESSDATA_PREFIX` to that directory. Restart the backend. `tesseract --list-langs` in another terminal may still show the system defaults; the environment checker and `/api/system/ocr-status` use the app's `.env` settings.

## Environment variables

`backend/.env`:

```dotenv
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=smart_timetable
TESSERACT_CMD=
TESSDATA_PREFIX=
UPLOAD_DIR=uploads
MAX_UPLOAD_MB=15
MAX_PDF_PAGES=10
OCR_TIMEOUT_SECONDS=60
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

`UPLOAD_DIR` is relative to `backend/` unless absolute. Upload limits are capped at 15 MB, PDF limits at 20 pages, and OCR timeouts at 120 seconds per page. The defaults use 10 PDF pages and 60 seconds. UI upload hints display the defaults; the API enforces the configured limits. `TESSDATA_PREFIX` is optional when the required language packs are in Tesseract's normal directory.

`frontend/.env`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

Restart Vite when changing frontend settings. CORS permits only the configured origins. Both development servers bind to loopback by default.

## Run

After setup and starting MongoDB:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

macOS/Linux:

```bash
bash ./start.sh
```

Cross-platform root commands:

```bash
npm run setup
npm run dev
npm run build
npm run check
```

The root launcher needs no additional npm dependencies. It verifies the virtual environment, `.env` files, imports, and ports; starts both servers; and stops its child processes with Ctrl+C. It does not start MongoDB for you.

- Frontend: **http://localhost:5173**
- Backend: **http://localhost:8000**
- Swagger API docs: **http://localhost:8000/docs**
- Health: **http://localhost:8000/api/health**

### Manual setup / separate terminals

Windows, from the project root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env # Only if .env does not already exist
cd ..\frontend
npm install
Copy-Item .env.example .env # Only if .env does not already exist
cd ..
.\backend\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In another terminal at the project root, run `npm --prefix frontend run dev`. On macOS/Linux use `python3 -m venv backend/.venv`, `source backend/.venv/bin/activate`, and `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`.

Verify actual exit codes and the environment report. Do not assume package or system installation succeeded.

## Demo flow

1. Open the frontend and check all five system indicators.
2. Drop or select a clear timetable image/PDF, inspect the preview, and click **Upload timetable**.
3. Click **Process timetable**. Digital pages use direct text; scanned pages use OCR. The editor shows the extraction method.
4. Inspect Destination, Timing, Confidence and Review against the source. Correct cells or add/remove rows; serial numbers stay internal and determine row order.
5. Low confidence is under 60%, medium is 60–79.99%, and high is 80% or more. Mark checked rows **Reviewed**. Review does not remove invalid-time, missing-name, duplicate, or suspicious-text warnings.
6. Click **Save Corrections**. The corrected values are persisted to MongoDB. Uncertain data is allowed to remain saved with review flags.
7. Export JSON or CSV. Export saves pending edits first, and refuses to export stale edits if saving fails.
8. Reopen the saved timetable from **Saved timetables**. **Process Again** creates a new draft without overwriting existing saved corrections.

No demo timetable or OCR output is hard-coded into the app. Tests generate their own images and submit them to the same real APIs.

## API

Interactive schemas and request examples are in Swagger. Core endpoints:

```text
GET    /
GET    /api/health
GET    /api/system/ocr-status
GET    /api/system/database-status
POST   /api/upload                       multipart field: file
POST   /api/process/{document_id}         extracts text or OCR synchronously in a worker thread
GET    /api/documents                    ?limit=50&skip=0
GET    /api/documents/{document_id}       includes OCR tokens and page data
GET    /api/documents/{document_id}/source
DELETE /api/documents/{document_id}       source + all related timetables
GET    /api/timetables                   ?limit=50&skip=0
GET    /api/timetables/{timetable_id}
PUT    /api/timetables/{timetable_id}      entries and current revision (legacy stops also supported)
DELETE /api/timetables/{timetable_id}     keeps the original source document
GET    /api/timetables/{timetable_id}/export/json
GET    /api/timetables/{timetable_id}/export/csv
```

Application errors use `{"error":{"code":"...","message":"..."}}`. Errors include 400 invalid IDs, 404 missing records, 409 concurrent edits/processing, 413 oversize, 415 unsupported/mismatched type, 422 corrupted/invalid files, 429 busy processing, and 503 unavailable services. Health returns HTTP 200 with `status: "degraded"` and accurate booleans if a dependency is unavailable; `status: "ok"` requires MongoDB and English OCR; direct PDF processing can still work without Tesseract.

## Data handling and limitations

- Staging files are removed on upload success/failure. Validated originals are **durable source files**, retained in `backend/uploads` for previews and reprocessing. Delete an original from the Saved page to remove its file, document metadata, and all extracted timetables. Back up this folder together with MongoDB.
- PDF word boxes use PDF points, including OCR boxes converted back from rendered pixels. Image uploads use processed-image pixels. Page metadata declares the coordinate system.
- The parser targets `Sl. No. | Destination | Timing` (including serial header variants, `Bus Stop` / `Stop` / `Stop Name` / `Bus Stop Name`, and `Time`). It does not infer routes, endpoints, translations or stop sequences. Unsupported headers/layouts remain raw review rows with bounding boxes; merged/multiline cells are not guessed.
- Missing cells, duplicate anchors, duplicate rows, low OCR confidence and ambiguous geometry are flagged. Repeated headers are detected per page. No time is borrowed from another row; no uncertain row is deduplicated away.
- Times without AM/PM are treated as 24-hour values; dates and overnight rollover are not inferred. Original values stay available separately.
- Destination spelling, case, punctuation and script are preserved; only edge whitespace and line breaks are trimmed. Route fields remain null. Older saved timetables retain their legacy editor schema until reprocessed.
- Reviewed rows retain the original confidence measurement. A 35% OCR row remains visibly low-confidence even after a person corrects it.
- CSV uses a UTF-8 BOM for spreadsheet compatibility. Potential formula cells are prefixed with an apostrophe; JSON preserves literal values.
- At most two OCR jobs run per backend process. OCR is request-based, without a background task queue. A disconnected browser does not necessarily stop its job; check Saved timetables before retrying. A stale processing lease expires after 45 minutes.
- This is a local hackathon prototype without authentication. Keep it on a trusted development machine/network. Original PDFs are served only as sources and are never executed by the backend.

## Extraction settings and debugging

In `backend/.env` set `EXTRACTION_DEBUG=true` to log each page's `DIRECT_TEXT` / `OCR_FALLBACK` mode, detected header boundaries, and each row's Y, internal serial anchor, destination and timing. `TABLE_Y_TOLERANCE=4` controls vertical grouping (1-6 PDF points; scaled to text size for image pixels). `OCR_LANGUAGE=eng` is the default; explicitly select `eng+mal` for Malayalam scans.

New results use `table_type: "destination_timetable"` and `entries` with `sl_no`, `destination`, `timing`, `confidence`, `needs_review` and source metadata. Submit `{ "entries": [...], "revision": 1 }` when saving. Confidence 100 on direct text means the embedded text was read without OCR; it does not verify the source's factual accuracy. Duplicate serials across pages stay flagged instead of being renumbered. Reprocess an old draft to use the new parser; existing saved corrections are preserved in their own records.

## Tests and verification

Install test dependencies and run from the project root:

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
.\backend\.venv\Scripts\python.exe -m pytest --basetemp=.runtime\pytest-temp -q
npm --prefix frontend run build
.\backend\.venv\Scripts\python.exe -c "import backend.main; print('Backend import OK')"
```

Tests cover time formats, Malayalam preservation, uncertain layouts, duplicate validation, malformed uploads, MIME/content mismatch, path traversal, request-size limits, CORS, real OCR, save/reopen/revision conflict, JSON/CSV, reprocessing, source cleanup, and multi-page/encrypted PDFs. Integration tests use a uniquely named `smart_timetable_test_<uuid>` database and remove **only that test database** afterward. They skip explicitly when MongoDB or the required OCR language is unavailable; a skipped test is not proof the dependency works.

Run `python -m pytest -m "not integration"` to exclude live-service checks. Tests create fixtures at runtime; no application behavior is mocked for the integration flow.

With the app and all services running, `npm --prefix frontend test` runs the React components in jsdom against the real API. It checks status indicators, invalid-file feedback, saved entries, editing Malayalam text, MongoDB persistence, JSON/CSV download actions, and console errors. It creates and deletes only its own test document. This validates DOM behavior, not browser layout. Install the Python test dependencies first because the test uses the image-fixture generator.

## Troubleshooting

- **Could not connect to backend:** open `/api/health`, check the terminal, and ensure ports 8000/5173 are free. Check `VITE_API_BASE_URL`. A failed backend import usually means setup installed dependencies into a different Python interpreter.
- **`'vite' is not recognized`:** the frontend installation is missing or incomplete. From the project root run `npm --prefix frontend install`, then use `npm run dev` or `start.ps1`. The npm scripts invoke Vite through its local module path and never require a global Vite installation.
- **MongoDB is currently unavailable:** start the local service/process, or check Atlas credentials, IP allowlist, DNS, and `MONGODB_URI`. Restart after editing `.env`.
- **Tesseract missing:** install it and set `TESSERACT_CMD` to the actual executable. Do not put extra command-line arguments in this variable.
- **Malayalam OCR language pack is missing:** run the language-data installer above. Both `eng.traineddata` and `mal.traineddata` must exist in `TESSDATA_PREFIX`.
- **Low-quality OCR:** use a sharper, upright image with even lighting and tightly cropped page margins. Try an image instead of an unusual PDF. Correct extracted data manually; preprocessing cannot restore missing detail.
- **Invalid/corrupted file:** re-export the source. Encrypted PDFs, extreme dimensions, files over the limit, and mismatched extensions are rejected intentionally.
- **PowerShell execution policy:** use the documented `powershell -ExecutionPolicy Bypass -File ...` command; no machine-wide policy change is required.
- **Virtual environment creation fails on Linux:** install `python3-venv` for your Python version.
- **No space left on device:** free space on the system temporary drive, or use a project-local temporary directory for installation:

  ```powershell
  New-Item -ItemType Directory -Force -Path .runtime\tmp
  $env:TEMP = Join-Path $PWD '.runtime\tmp'
  $env:TMP = $env:TEMP
  .\backend\.venv\Scripts\python.exe -m pip install --no-cache-dir -r backend\requirements.txt
  npm --prefix frontend install --cache .runtime\npm-cache
  ```

- **A sandbox blocks Vite/esbuild or Tesseract subprocesses:** run the project in a normal local terminal or approve the exact build/runtime command in your coding environment.
- **Revisions conflict:** reopen the latest version from Saved timetables, then reapply your edits. Export will not bypass this check.
- **Source file missing after moving a deployment:** move `uploads` with MongoDB data, or re-upload the original document.

## Setup and run commands — Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Frontend: http://localhost:5173  
Backend: http://localhost:8000  
API docs: http://localhost:8000/docs


## Deploy the frontend on Vercel

Set Vercel's Root Directory to the directory containing this README and the root `package.json` (not `frontend`). The root `vercel.json` configures:

- Install Command: `npm --prefix frontend ci --include=dev`
- Build Command: `npm run build`
- Output Directory: `frontend/dist`
- Framework: Vite

The root package pins Node.js to `22.x` so deployments cannot jump to a new major version. Commit `vercel.json`, both package manifests and `frontend/package-lock.json`, then redeploy. Dependencies are installed from the lockfile on Vercel; do not commit `node_modules`.

Set `VITE_API_BASE_URL` in Vercel to your deployed FastAPI backend's HTTPS URL before building. Add the Vercel frontend origin to the backend's `CORS_ORIGINS`. This configuration publishes the frontend; the Python backend still needs a running deployment with MongoDB, persistent uploads and Tesseract for scans. The default `http://localhost:8000` API URL is for local development.

See [Vercel build configuration](https://vercel.com/docs/builds/configure-a-build) and [supported Node.js versions](https://vercel.com/docs/functions/runtimes/node-js/node-js-versions).
