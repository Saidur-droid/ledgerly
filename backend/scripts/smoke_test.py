"""Run Ledgerly's complete MVP flow against a running API.

Usage:
    python scripts/smoke_test.py --api-url http://localhost:8000
    python scripts/smoke_test.py --api-url https://example.onrender.com --verify-database

The optional database check reads DATABASE_URL from the environment. The URL is
never printed.
"""

import argparse
import json
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
    "revenue": 5_453_000,
    "expenses": 3_919_000,
    "profit": 1_534_000,
    "cash": 245_000,
}
PROMPT_A = "Summarize my total revenue, expenses, profit, and net margin."
PROMPT_B = (
    "Analyze each monthly row in my uploaded CSV. Identify the five best and "
    "five worst months using profit, net margin, and revenue growth. Include "
    "the exact month and values in a table."
)
EXPECTED_RANKING_FORMULA = (
    "40% profit + 35% net margin + 25% revenue growth"
)


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

        aggregate_chat = response_json(
            client.post(
                "/api/v1/chat",
                headers=headers,
                json={"question": PROMPT_A},
            ),
            200,
        )
        period_chat = response_json(
            client.post(
                "/api/v1/chat",
                headers=headers,
                json={"question": PROMPT_B},
            ),
            200,
        )
        require(
            aggregate_chat["schema_version"] == 1
            and aggregate_chat["correlation_id"],
            "AI chat did not return the versioned response contract.",
        )
        require(
            aggregate_chat["content"] != period_chat["sections"],
            "Different questions returned the same answer.",
        )
        require(
            "$5,453,000.00" in aggregate_chat["content"],
            "Aggregate chat answer did not use persisted totals.",
        )
        require(
            period_chat["type"] == "structured",
            "Period chat answer was not serialized as structured analysis.",
        )
        sections = period_chat["sections"]
        tables = [
            section for section in sections if section.get("type") == "table"
        ]
        require(
            [section.get("heading") for section in tables]
            == ["5 best months", "5 worst months"]
            and tables[0]["rows"][0][1] == "December 2025"
            and tables[1]["rows"][0][1] == "March 2023",
            "Period chat answer did not analyze persisted monthly rows.",
        )
        scoring = next(
            section["markdown"]
            for section in sections
            if section.get("heading") == "Ranking method"
        )
        require(
            EXPECTED_RANKING_FORMULA in scoring
            and "min–max normalized" in scoring
            and "neutral normalized growth score of 0.50" in scoring,
            "Period chat answer did not explain its ranking methodology.",
        )

        report = client.get("/api/v1/reports/latest.pdf", headers=headers)
        require(report.status_code == 200, "PDF endpoint did not return 200.")
        require(report.content.startswith(b"%PDF"), "Report is not a PDF.")
        require(len(report.content) > 1_000, "Report PDF is unexpectedly small.")
        report_text = "\n".join(
            page.extract_text() or ""
            for page in PdfReader(BytesIO(report.content)).pages
        )
        require(
            "5,453,000.00" in report_text,
            "Report does not contain CSV revenue.",
        )

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

    print("PROMPT A RESPONSE:")
    print(aggregate_chat["content"])
    print("\nPROMPT B RESPONSE:")
    print(json.dumps(period_chat, indent=2))
    print("\nPASS: CSV -> persistence -> metrics -> Pulse -> dashboard -> question-aware chat -> PDF")


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
