def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


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
