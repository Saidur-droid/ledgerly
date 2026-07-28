import pytest


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


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
