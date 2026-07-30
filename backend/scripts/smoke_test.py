"""Run Ledgerly's complete MVP flow against a running API.

Usage:
    python scripts/smoke_test.py --api-url http://localhost:8000
    python scripts/smoke_test.py --api-url https://example.onrender.com --verify-database

The optional database check reads DATABASE_URL from the environment. The URL is
never printed.
"""

import argparse
import os
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import httpx
from pypdf import PdfReader
from sqlalchemy import create_engine, text


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "sample_business_data.csv"
)
EXPECTED_METRICS = {
    "revenue": 41_250,
    "expenses": 24_350,
    "profit": 16_900,
    "cash": 59_350,
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def response_json(response: httpx.Response, expected_status: int) -> dict:
    require(
        response.status_code == expected_status,
        f"{response.request.method} {response.request.url.path} returned "
        f"{response.status_code}: {response.text[:300]}",
    )
    return response.json()


def normalized_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def verify_database(email: str) -> None:
    database_url = os.environ.get("DATABASE_URL")
    require(
        bool(database_url),
        "DATABASE_URL is required when --verify-database is used.",
    )
    engine = create_engine(
        normalized_database_url(database_url or ""),
        pool_pre_ping=True,
    )
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT COUNT(DISTINCT uploads.id), COUNT(DISTINCT pulses.id)
                    FROM users
                    JOIN uploads ON uploads.user_id = users.id
                    JOIN pulses ON pulses.upload_id = uploads.id
                    WHERE users.email = :email
                    """
                ),
                {"email": email},
            ).one()
        require(row[0] >= 1, "No persisted upload row was found.")
        require(row[1] >= 1, "No persisted Pulse row was found.")
    finally:
        engine.dispose()


def run_smoke_test(api_url: str, check_database: bool) -> None:
    email = f"ledgerly-smoke-{uuid4().hex[:12]}@example.com"
    password = f"Smoke-{uuid4().hex}-A1!"
    fixture = FIXTURE_PATH.read_bytes()

    with httpx.Client(
        base_url=api_url.rstrip("/"),
        timeout=60,
        follow_redirects=True,
    ) as client:
        health = response_json(client.get("/health"), 200)
        require(
            health == {"status": "ok", "database": "postgresql"},
            "Health response does not describe the PostgreSQL service.",
        )
        ready = response_json(client.get("/ready"), 200)
        require(ready["status"] == "ready", "Database readiness check failed.")

        registration = response_json(
            client.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "full_name": "Ledgerly Smoke Test",
                    "password": password,
                },
            ),
            201,
        )
        require(registration["user"]["email"] == email, "Registration mismatch.")

        login = response_json(
            client.post(
                "/api/v1/auth/login",
                data={"username": email, "password": password},
            ),
            200,
        )
        headers = {"Authorization": f"Bearer {login['access_token']}"}

        current_user = response_json(client.get("/api/v1/me", headers=headers), 200)
        require(current_user["email"] == email, "Authenticated user mismatch.")

        pulse = response_json(
            client.post(
                "/api/v1/uploads",
                headers=headers,
                files={
                    "file": (
                        FIXTURE_PATH.name,
                        fixture,
                        "text/csv",
                    )
                },
            ),
            201,
        )
        for name, expected in EXPECTED_METRICS.items():
            require(
                pulse["metrics"].get(name) == expected,
                f"Unexpected {name} metric: {pulse['metrics'].get(name)}",
            )
        require(0 <= pulse["score"] <= 100, "Pulse score is out of bounds.")
        require(bool(pulse["factors"]), "Pulse factors are missing.")

        uploads = response_json(
            client.get("/api/v1/uploads", headers=headers),
            200,
        )
        require(
            uploads[0]["filename"] == FIXTURE_PATH.name,
            "Persisted upload was not returned by Business Memory.",
        )
        latest_pulse = response_json(
            client.get("/api/v1/pulse/latest", headers=headers),
            200,
        )
        require(
            latest_pulse["metrics"]["revenue"] == EXPECTED_METRICS["revenue"],
            "Persisted dashboard metrics do not match the uploaded CSV.",
        )

        chat = response_json(
            client.post(
                "/api/v1/chat",
                headers=headers,
                json={"question": "What revenue is present in my latest upload?"},
            ),
            200,
        )
        require(
            chat["sources"] == [FIXTURE_PATH.name],
            "AI chat did not use the uploaded file as its source.",
        )

        report = client.get("/api/v1/reports/latest.pdf", headers=headers)
        require(report.status_code == 200, "PDF endpoint did not return 200.")
        require(report.content.startswith(b"%PDF"), "Report is not a PDF.")
        require(len(report.content) > 1_000, "Report PDF is unexpectedly small.")
        report_text = "\n".join(
            page.extract_text() or ""
            for page in PdfReader(BytesIO(report.content)).pages
        )
        require("41,250.00" in report_text, "Report does not contain CSV revenue.")

        second_login = response_json(
            client.post(
                "/api/v1/auth/login",
                data={"username": email, "password": password},
            ),
            200,
        )
        persisted_headers = {
            "Authorization": f"Bearer {second_login['access_token']}",
        }
        persisted_uploads = response_json(
            client.get("/api/v1/uploads", headers=persisted_headers),
            200,
        )
        require(
            persisted_uploads[0]["filename"] == FIXTURE_PATH.name,
            "Upload did not survive a new authenticated session.",
        )

    if check_database:
        verify_database(email)

    print("PASS: CSV -> persistence -> metrics -> Pulse -> dashboard -> chat -> PDF")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Ledgerly MVP smoke test.")
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="Running Ledgerly API origin.",
    )
    parser.add_argument(
        "--verify-database",
        action="store_true",
        help="Verify upload and Pulse rows using DATABASE_URL.",
    )
    arguments = parser.parse_args()
    run_smoke_test(arguments.api_url, arguments.verify_database)


if __name__ == "__main__":
    main()
