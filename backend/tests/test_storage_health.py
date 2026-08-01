from app.core.database import engine
from app.core.storage_health import REQUIRED_STORAGE_TABLES, storage_readiness


def test_storage_readiness_covers_upload_and_phase_1_to_5_schema(client):
    result = client.get("/ready/storage")
    assert result.status_code == 200
    assert result.json() == {
        "status": "ready",
        "database": "sqlite",
        "required_schema": "001-006",
        "missing_tables": [],
        "missing_migrations": [],
    }
    assert {"uploads", "pulses", "calculation_versions", "workspaces"} <= REQUIRED_STORAGE_TABLES
    assert storage_readiness(engine)["status"] == "ready"
