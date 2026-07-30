import json
import random
from pathlib import Path

from app.ai.contract import SAFE_FAILURE, serialize_ask_response
from app.ai.service import DISCLAIMER
from app.schemas import ChatResponse

REPOSITORY = Path(__file__).parents[2]
FIXTURES = json.loads(
    (REPOSITORY / "contracts" / "ask-ledgerly-v1.fixtures.json").read_text(
        encoding="utf-8"
    )
)
CSV_FIXTURE = Path(__file__).parent / "fixtures" / "sample_business_data.csv"
LONG_REGRESSION_PROMPT = (
    "Audit every monthly row, identify the best and worst months in tables, "
    "explain the ranking method, model a +10% revenue scenario, forecast the "
    "next period, list risks, and provide an action plan based only on my "
    "uploaded data."
)
VARIED_PROMPTS = [
    "Summarize total revenue, expenses, profit, and margin.",
    "Identify the five best and five worst monthly rows.",
    "Explain the revenue trend over time.",
    "Is there seasonality in the uploaded history?",
    "Compare strongest and weakest net margins.",
    "Summarize ending cash balances over time.",
    "Flag observed loss and revenue-decline risks.",
    "Forecast the next period from observed growth.",
    "What if revenue changes by +5% and expenses stay constant?",
    "Explain the latest uploaded business data.",
]


def _common() -> dict:
    return {
        "correlation_id": "contract-test",
        "confidence": "data-grounded",
        "sources": ["sample.csv"],
        "disclaimer": DISCLAIMER,
    }


def _register_and_upload(client) -> dict[str, str]:
    auth = client.post(
        "/api/v1/auth/register",
        json={
            "email": "contract-owner@example.com",
            "full_name": "Contract Owner",
            "password": "strong-password",
        },
    )
    headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}
    uploaded = client.post(
        "/api/v1/uploads",
        headers=headers,
        files={
            "file": (
                CSV_FIXTURE.name,
                CSV_FIXTURE.read_bytes(),
                "text/csv",
            )
        },
    )
    assert uploaded.status_code == 201
    return headers


def test_shared_contract_fixtures_validate_every_section_type():
    markdown = ChatResponse.model_validate(FIXTURES["markdown"])
    structured = ChatResponse.model_validate(FIXTURES["structured"])
    assert markdown.schema_version == structured.schema_version == 1
    assert {section.type for section in structured.sections} == {
        "text",
        "metrics",
        "table",
        "list",
        "scenarios",
        "forecast",
        "risks",
        "actions",
        "notice",
    }


def test_unknown_deep_oversized_and_nested_values_fail_to_safe_contract(caplog):
    circular: list[object] = []
    circular.append(circular)
    inputs = [
        None,
        {"unexpected": "shape"},
        {"kind": "structured_analysis", "title": {"object": True}},
        {"response_type": "structured", "sections": [{"type": "unknown"}]},
        {"response_type": "markdown", "markdown": {"nested": True}},
        {"response_type": "markdown", "markdown": "x" * 100_001},
        {"response_type": "structured", "sections": [{"type": "table", "columns": [{"label": "A"}], "rows": [[{"nested": True}]]}]},
        circular,
    ]
    for index, raw in enumerate(inputs):
        correlation_id = f"contract-failure-{index}"
        response = serialize_ask_response(
            raw,
            **(_common() | {"correlation_id": correlation_id}),
        )
        assert response.schema_version == 1
        assert response.response_type == "structured"
        assert response.sections[0].type == "notice"
        assert correlation_id in response.sections[0].message
        assert SAFE_FAILURE.split("{", 1)[0] in response.sections[0].message
    assert "ask_response_contract_failure" in caplog.text
    assert "100001" not in caplog.text


def test_fuzzed_backend_shapes_always_return_a_valid_contract():
    generator = random.Random(20260731)
    atoms: list[object] = [None, True, False, 0, 1.5, "", "text"]
    candidates: list[object] = atoms.copy()
    for index in range(250):
        value: object = generator.choice(atoms)
        for _ in range(generator.randrange(0, 5)):
            value = (
                [value, {"index": index}]
                if generator.choice([True, False])
                else {f"key-{index}": value}
            )
        candidates.append(value)
    for index, raw in enumerate(candidates):
        response = serialize_ask_response(
            raw,
            **(_common() | {"correlation_id": f"fuzz-{index:04d}"}),
        )
        validated = ChatResponse.model_validate_json(response.model_dump_json())
        assert validated.schema_version == 1
        assert validated.markdown or validated.sections


def test_ten_varied_prompts_keep_one_versioned_api_shape(client):
    headers = _register_and_upload(client)
    responses = [
        client.post("/api/v1/chat", headers=headers, json={"question": prompt})
        for prompt in VARIED_PROMPTS
    ]
    assert all(response.status_code == 200 for response in responses)
    payloads = [response.json() for response in responses]
    assert all(ChatResponse.model_validate(payload) for payload in payloads)
    assert {payload["schema_version"] for payload in payloads} == {1}
    assert {payload["response_type"] for payload in payloads} >= {
        "markdown",
        "structured",
    }
    assert len({json.dumps(payload["markdown"] or payload["sections"], sort_keys=True) for payload in payloads}) >= 8


def test_long_audit_scenario_forecast_regression_has_explicit_sections(client):
    headers = _register_and_upload(client)
    response = client.post(
        "/api/v1/chat",
        headers=headers,
        json={"question": LONG_REGRESSION_PROMPT},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == 1
    assert payload["response_type"] == "structured"
    section_types = {section["type"] for section in payload["sections"]}
    assert {"text", "table", "scenarios", "forecast", "risks", "actions"} <= section_types
    assert any(section.get("heading") == "5 best months" for section in payload["sections"])
    assert any(section.get("heading") == "5 worst months" for section in payload["sections"])
