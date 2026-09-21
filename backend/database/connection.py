from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from backend import config
from backend.utils.errors import AppError

client = MongoClient(config.MONGODB_URI, serverSelectionTimeoutMS=2500,
                     connectTimeoutMS=2500, socketTimeoutMS=15000)
database = client[config.MONGODB_DB]


def database_status() -> dict:
    try:
        client.admin.command("ping")
        return {"connected": True, "database": config.MONGODB_DB, "message": "MongoDB is connected."}
    except PyMongoError:
        return {"connected": False, "database": config.MONGODB_DB,
                "message": "MongoDB is currently unavailable. Start local MongoDB or set MONGODB_URI in backend/.env to your Atlas connection string."}


def get_database():
    if not database_status()["connected"]:
        raise AppError(503, "database_unavailable", "MongoDB is currently unavailable. Check MONGODB_URI and start MongoDB.")
    return database


def object_id(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise AppError(400, "invalid_id", "The document or timetable ID is invalid.")
    return ObjectId(value)


def public_record(record: dict) -> dict:
    return {key: str(value) if isinstance(value, ObjectId) else value
            for key, value in record.items() if key != "source_path"}
