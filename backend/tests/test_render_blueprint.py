from pathlib import Path

import yaml

VERCEL_ORIGIN = "https://ledgerly-one-xi.vercel.app"


def test_render_blueprint_is_deployable_without_configuration_prompts():
    blueprint_path = Path(__file__).parents[2] / "render.yaml"
    blueprint = yaml.safe_load(blueprint_path.read_text(encoding="utf-8"))
    service = blueprint["services"][0]
    environment = {item["key"]: item for item in service["envVars"]}

    assert service["type"] == "web"
    assert service["runtime"] == "python"
    assert service["rootDir"] == "backend"
    assert service["plan"] == "starter"
    assert service["healthCheckPath"] == "/health"
    assert service["autoDeployTrigger"] == "checksPass"
    assert "pip install --no-cache-dir -r requirements.txt" in service["buildCommand"]
    assert "uvicorn app.main:app" in service["startCommand"]
    assert "--host 0.0.0.0" in service["startCommand"]
    assert "--port $PORT" in service["startCommand"]

    assert environment["APP_ENV"]["value"] == "production"
    assert environment["SECRET_KEY"]["generateValue"] is True
    assert environment["CORS_ORIGINS"]["value"] == VERCEL_ORIGIN
    assert not any(item.get("sync") is False for item in service["envVars"])

    database_url = environment["DATABASE_URL"]["value"]
    assert service["disk"]["mountPath"] in database_url
    assert service["disk"]["sizeGB"] == 1
