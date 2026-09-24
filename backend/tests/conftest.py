"""Test-Setup: eigene, leere Datenbank in einem temporären Ordner."""

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="lifeos-test-")
os.environ["LIFEOS_DATA_DIR"] = _TMP
os.environ["LIFEOS_DEMO_DATA"] = "0"
os.environ["LIFEOS_AUTO_SYNC"] = "0"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["GARMIN_EMAIL"] = ""
os.environ["GARMIN_PASSWORD"] = ""

import pytest  # noqa: E402

from app.database import Base, SessionLocal, engine, init_db  # noqa: E402


@pytest.fixture()
def db():
    init_db()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
