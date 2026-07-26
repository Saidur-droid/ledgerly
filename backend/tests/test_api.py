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
