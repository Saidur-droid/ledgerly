from io import BytesIO

import pytest
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.business_engine.storage import get_business_store
from app.core.config import get_settings
from app.core.database import SessionLocal, get_db
from app.main import app
from app.models import Pulse, Upload


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "postgresql",
    }


def test_readiness_confirms_database_query(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "postgresql",
    }


def test_readiness_reports_database_unavailability(client):
    class UnavailableDatabase:
        def execute(self, _statement):
            raise SQLAlchemyError("connection unavailable")

    app.dependency_overrides[get_db] = lambda: UnavailableDatabase()
    try:
        response = client.get("/ready")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable."}
    assert "connection unavailable" not in response.text


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:3000",
        "https://ledgerly-one-xi.vercel.app",
    ],
)
def test_cors_allows_configured_frontend(client, origin):
    response = client.options(
        "/api/v1/auth/register",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_cors_rejects_unconfigured_origin(client):
    response = client.options(
        "/api/v1/auth/register",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_register_and_upload_csv(client):
    auth = client.post("/api/v1/auth/register", json={
        "email": "maya@example.com",
        "full_name": "Maya Patel",
        "password": "strong-password",
    })
    assert auth.status_code == 201
    token = auth.json()["access_token"]
    response = client.post(
        "/api/v1/uploads",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("june.csv", b"month,revenue,expenses\nJune,55842,29510\n", "text/csv")},
    )
    assert response.status_code == 201
    assert response.json()["metrics"]["revenue"] == 55842
    assert response.json()["score"] > 0

    with SessionLocal() as session:
        persisted_upload = session.scalar(
            select(Upload).where(Upload.filename == "june.csv")
        )
        assert persisted_upload is not None
        assert persisted_upload.normalized_data["records"][0]["revenue"] == 55842
        persisted_pulse = session.scalar(
            select(Pulse).where(Pulse.upload_id == persisted_upload.id)
        )
        assert persisted_pulse is not None
        assert persisted_pulse.metrics["revenue"] == 55842

    headers = {"Authorization": f"Bearer {token}"}
    uploads = client.get("/api/v1/uploads", headers=headers)
    assert uploads.status_code == 200
    assert uploads.json()[0]["filename"] == "june.csv"

    pulse = client.get("/api/v1/pulse/latest", headers=headers)
    assert pulse.status_code == 200
    assert pulse.json()["metrics"]["revenue"] == 55842

    chat = client.post(
        "/api/v1/chat",
        headers=headers,
        json={"question": "What was revenue?"},
    )
    assert chat.status_code == 200
    assert chat.json()["sources"] == ["june.csv"]

    report = client.get("/api/v1/reports/latest.pdf", headers=headers)
    assert report.status_code == 200
    assert report.headers["content-type"] == "application/pdf"
    assert report.content.startswith(b"%PDF")
    assert len(report.content) > 1_000
    report_text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(BytesIO(report.content)).pages
    )
    assert "55,842.00" in report_text
    assert "Business Pulse" in report_text

    second_auth = client.post("/api/v1/auth/register", json={
        "email": "second-owner@example.com",
        "full_name": "Second Owner",
        "password": "strong-password",
    })
    second_headers = {
        "Authorization": f"Bearer {second_auth.json()['access_token']}",
    }
    assert client.get("/api/v1/uploads", headers=second_headers).json() == []
    assert client.get("/api/v1/pulse/latest", headers=second_headers).status_code == 404

    login = client.post(
        "/api/v1/auth/login",
        data={"username": "maya@example.com", "password": "strong-password"},
    )
    refreshed_headers = {
        "Authorization": f"Bearer {login.json()['access_token']}",
    }
    persisted_uploads = client.get("/api/v1/uploads", headers=refreshed_headers)
    assert persisted_uploads.status_code == 200
    assert persisted_uploads.json()[0]["filename"] == "june.csv"


def test_invalid_csv_returns_a_clear_validation_error(client):
    auth = client.post(
        "/api/v1/auth/register",
        json={
            "email": "invalid-upload@example.com",
            "full_name": "Invalid Upload",
            "password": "strong-password",
        },
    )
    response = client.post(
        "/api/v1/uploads",
        headers={"Authorization": f"Bearer {auth.json()['access_token']}"},
        files={"file": ("empty.csv", b"", "text/csv")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "The CSV is empty or does not contain readable columns."
    )


@pytest.mark.parametrize(
    ("filename", "content", "expected_detail"),
    [
        (
            "notes.txt",
            b"revenue,expenses\n100,50\n",
            "Unsupported file type. Use CSV, XLSX, PDF, or JSON.",
        ),
        (
            "broken.csv",
            b'revenue,expenses\n"100,50\n',
            "The CSV is malformed and could not be parsed.",
        ),
    ],
)
def test_invalid_uploads_return_clear_errors(
    client,
    filename,
    content,
    expected_detail,
):
    auth = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{filename}@example.com",
            "full_name": "Invalid Upload",
            "password": "strong-password",
        },
    )
    response = client.post(
        "/api/v1/uploads",
        headers={"Authorization": f"Bearer {auth.json()['access_token']}"},
        files={"file": (filename, content, "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == expected_detail


def test_upload_without_standard_kpis_returns_low_evidence_pulse(client):
    auth = client.post(
        "/api/v1/auth/register",
        json={
            "email": "unmapped@example.com",
            "full_name": "Unmapped Columns",
            "password": "strong-password",
        },
    )
    response = client.post(
        "/api/v1/uploads",
        headers={"Authorization": f"Bearer {auth.json()['access_token']}"},
        files={
            "file": (
                "inventory.csv",
                b"sku,description\nA-1,Widget\n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 201
    assert response.json()["metrics"] == {"net_margin": 0.0}
    assert response.json()["confidence"] < 0.6
    completeness = next(
        factor
        for factor in response.json()["factors"]
        if factor["name"] == "Data completeness"
    )
    assert completeness["score"] == 0


def test_duplicate_uploads_create_distinct_history_entries(client):
    auth = client.post(
        "/api/v1/auth/register",
        json={
            "email": "duplicates@example.com",
            "full_name": "Duplicate Uploads",
            "password": "strong-password",
        },
    )
    headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}
    file_content = b"date,revenue,expenses\n2026-01-31,1000,700\n"

    first = client.post(
        "/api/v1/uploads",
        headers=headers,
        files={"file": ("month.csv", file_content, "text/csv")},
    )
    second = client.post(
        "/api/v1/uploads",
        headers=headers,
        files={"file": ("month.csv", file_content, "text/csv")},
    )
    uploads = client.get("/api/v1/uploads", headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert len(uploads.json()) == 2
    assert uploads.json()[0]["id"] != uploads.json()[1]["id"]
    assert second.json()["comparison"]["changes"]["revenue"]["percent_change"] == 0


def test_upload_size_limit_and_filename_sanitization(client):
    settings = get_settings()
    original_limit = settings.max_upload_mb
    settings.max_upload_mb = 1
    auth = client.post(
        "/api/v1/auth/register",
        json={
            "email": "upload-boundaries@example.com",
            "full_name": "Upload Boundaries",
            "password": "strong-password",
        },
    )
    headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}
    try:
        too_large = client.post(
            "/api/v1/uploads",
            headers=headers,
            files={"file": ("large.csv", b"x" * (1024 * 1024 + 1), "text/csv")},
        )
        sanitized = client.post(
            "/api/v1/uploads",
            headers=headers,
            files={
                "file": (
                    "../../safe.csv",
                    b"revenue,expenses\n100,40\n",
                    "text/csv",
                )
            },
        )
    finally:
        settings.max_upload_mb = original_limit

    assert too_large.status_code == 413
    assert too_large.json()["detail"] == "The file exceeds the 1 MB upload limit."
    assert sanitized.status_code == 201
    uploads = client.get("/api/v1/uploads", headers=headers).json()
    assert uploads[0]["filename"] == "safe.csv"


def test_storage_failure_returns_safe_service_error(client):
    class UnavailableStore:
        rolled_back = False

        def create_upload(self, **_kwargs):
            raise RuntimeError("database password leaked here")

        def rollback(self):
            self.rolled_back = True

    store = UnavailableStore()
    app.dependency_overrides[get_business_store] = lambda: store
    auth = client.post(
        "/api/v1/auth/register",
        json={
            "email": "storage-failure@example.com",
            "full_name": "Storage Failure",
            "password": "strong-password",
        },
    )
    try:
        response = client.post(
            "/api/v1/uploads",
            headers={"Authorization": f"Bearer {auth.json()['access_token']}"},
            files={
                "file": (
                    "business.csv",
                    b"revenue,expenses\n100,40\n",
                    "text/csv",
                )
            },
        )
    finally:
        app.dependency_overrides.pop(get_business_store, None)

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Business data storage is temporarily unavailable."
    }
    assert "password" not in response.text
    assert store.rolled_back


def test_register_login_and_authenticated_session(client):
    credentials = {
        "email": "founder@example.com",
        "full_name": "Ledgerly Founder",
        "password": "strong-password",
    }
    registration = client.post("/api/v1/auth/register", json=credentials)
    assert registration.status_code == 201

    login = client.post(
        "/api/v1/auth/login",
        data={
            "username": credentials["email"],
            "password": credentials["password"],
        },
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    current_user = client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert current_user.status_code == 200
    assert current_user.json()["email"] == credentials["email"]

    settings = client.get(
        "/api/v1/settings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert settings.status_code == 200
    assert settings.json()["profile"]["full_name"] == credentials["full_name"]

    updated_profile = client.patch(
        "/api/v1/settings/profile",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": "updated-founder@example.com",
            "full_name": "Updated Founder",
        },
    )
    assert updated_profile.status_code == 200
    assert updated_profile.json()["email"] == "updated-founder@example.com"
    assert updated_profile.json()["full_name"] == "Updated Founder"

    updated_user = client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert updated_user.status_code == 200
    assert updated_user.json()["full_name"] == "Updated Founder"
