import os
import pytest
from fastapi.testclient import TestClient

@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("TICKET_SECRET", "test-secret-for-tests")
    # Reload modules so settings and engine use isolated test database.
    import app.config, app.database, app.main
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False, "timeout": 30})
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    def override_db():
        db = TestingSession()
        try: yield db
        finally: db.close()
    app.main.app.dependency_overrides[app.database.get_db] = override_db
    with TestClient(app.main.app) as c:
        yield c
    app.main.app.dependency_overrides.clear()
    engine.dispose()

@pytest.fixture()
def service_payload():
    return {
        "name": "Andromeda Express",
        "category": "GALACTIC_WORMHOLE",
        "source": "Luna Port",
        "destination": "Kepler-22",
        "departure_at": "2030-01-01T10:00:00Z",
        "arrival_at": "2030-01-01T12:00:00Z",
        "capacity": 3,
        "price": 100
    }
