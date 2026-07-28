from pathlib import Path

import yaml

VERCEL_ORIGIN = "https://ledgerly-one-xi.vercel.app"


def test_render_blueprint_requires_managed_database_secret():
    blueprint_path = Path(__file__).parents[2] / "render.yaml"
    blueprint = yaml.safe_load(blueprint_path.read_text(encoding="utf-8"))
    service = blueprint["services"][0]
    environment = {item["key"]: item for item in service["envVars"]}

    assert service["type"] == "web"
    assert service["runtime"] == "python"
    assert service["rootDir"] == "backend"
    assert service["plan"] == "starter"
    assert service["healthCheckPath"] == "/health"
    assert service["autoDeployTrigger"] == "commit"
    assert "pip install --no-cache-dir -r requirements.txt" in service["buildCommand"]
    assert service["startCommand"].startswith("python -m uvicorn app.main:app ")
    assert "--host 0.0.0.0" in service["startCommand"]
    assert "--port $PORT" in service["startCommand"]

    assert environment["APP_ENV"]["value"] == "production"
    assert environment["SECRET_KEY"]["generateValue"] is True
    assert environment["CORS_ORIGINS"]["value"] == VERCEL_ORIGIN
    assert environment["DATABASE_URL"]["sync"] is False
    assert "value" not in environment["DATABASE_URL"]
    assert environment["STORAGE_PROVIDER"]["value"] == "postgres"
    assert "disk" not in service
