import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from backend import config
from backend.database.connection import client, database_status
from backend.routes import documents, system, timetables
from backend.services.ocr_service import ocr_status
from backend.utils.errors import AppError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("OCR: %s", (await run_in_threadpool(ocr_status))["message"])
    logger.info("Database: %s", (await run_in_threadpool(database_status))["message"])
    yield
    client.close()


app = FastAPI(title="Smart Timetable Digitizer", version="1.0.0", lifespan=lifespan)


def error_response(status, code, message):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


class UploadLimitMiddleware:
    """Bound bytes before Starlette's multipart parser writes spooled files."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        maximum = config.MAX_UPLOAD_BYTES + 65536 if scope["path"] == "/api/upload" else 4 * 1024 * 1024
        total = 0
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await error_response(400, "invalid_length", "Invalid request size.")(scope, receive, send)
        if declared > maximum:
            return await error_response(413, "file_too_large", "Upload exceeds the configured size limit.")(scope, receive, send)

        async def limited_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > maximum:
                # HTTPException reaches FastAPI's multipart cleanup and handler.
                from starlette.exceptions import HTTPException
                raise HTTPException(413, "Upload exceeds the configured size limit.")
            return message

        await self.app(scope, limited_receive, send)


app.add_middleware(UploadLimitMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS,
                   allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type"],
                   expose_headers=["Content-Disposition"])


@app.exception_handler(AppError)
async def app_error(request: Request, exc: AppError):
    return error_response(exc.status, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return error_response(422, "invalid_request", "Some fields are invalid. Check the timetable values and request format.")


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return error_response(exc.status_code, "http_error", str(exc.detail))


@app.exception_handler(PyMongoError)
async def mongo_error(request: Request, exc: PyMongoError):
    logger.error("Database operation failed (%s)", type(exc).__name__)
    return error_response(503, "database_unavailable", "MongoDB is currently unavailable. Check the connection and try again.")


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    logger.exception("Unexpected error on %s", request.url.path)
    return error_response(500, "internal_error", "Something went wrong while handling this file. Please try again or check the backend logs.")


app.include_router(system.router)
app.include_router(documents.router)
app.include_router(timetables.router)
