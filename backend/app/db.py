import os
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .database_url import normalize_database_url

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "cinema_club.db"))

DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL", f"sqlite:///{SQLITE_PATH}"))

engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # Supabase Session pooler has a limit of 15 connections on free tier
    engine_kwargs["pool_size"] = 5
    engine_kwargs["max_overflow"] = 5
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 300

engine = create_engine(DATABASE_URL, **engine_kwargs)

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    module_name = dbapi_connection.__class__.__module__
    if "sqlite3" in module_name:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
