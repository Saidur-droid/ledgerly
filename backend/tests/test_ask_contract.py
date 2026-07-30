import json
import random
from pathlib import Path

from app.ai.contract import SAFE_FAILURE, serialize_ask_response
from app.ai.policy import route_policy
from app.schemas import ChatResponse

REPOSITORY = Path(__file__).parents[2]
FIXTURES = json.loads(
    (REPOSITORY / "contracts" / "ask-ledgerly-v1.fixtures.json").read_text(
        encoding="utf-8"
    )
)
CSV_FIXTURE = Path(__file__).parent / "fixtures" / "sample_business_data.csv"
PROMPT_A = "Summarize my total revenue, expenses, profit, and net margin."
PROMPT_B = (
    "Analyze each monthly row in my uploaded CSV. Identify the five best and "
    "five worst months using profit, net margin, and revenue growth. Include "
    "the exact month and values in a table."
)
PROMPT_C = (
    "Audit every monthly row, identify the best and worst months in tables, "
    "explain the ranking method, model a +10% revenue scenario, forecast the "
    "next period, list risks, and provide an action plan based only on my "
    "uploaded data."
)
PROMPT_D = (
    "Act as my CFO: review performance and cash, rank risks, discuss pricing "
    "and hiring implications supported by the upload, and recommend a "
    "30/60/90-day operational action plan."
)
PROMPT_E = (
    "Guarantee next quarter's revenue outcome and tell me which stock I should "
    "buy, while still showing the historical forecast supported by my data."
)
VARIED_PROMPTS = [
    PROMPT_A,
    PROMPT_B,
    "Reconcile all monthly rows chronologically.",
    "Explain the revenue trend over time.",
    "Is there seasonality in the uploaded history?",
    "Compare strongest and weakest net margins.",
    "Summarize ending cash balances over time.",
    "Rank observed loss and revenue-decline risks.",
    "Forecast the next period from observed growth.",
    "What if revenue changes by +5% and expenses stay constant?",
    PROMPT_D,
]


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


def _ask(client, headers: dict[str, str], prompt: str) -> dict:
    response = client.post(
        "/api/v1/chat",
        headers=headers,
        json={"question": prompt},
    )
    assert response.status_code == 200
    return response.json()


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
        {"type": "structured", "content": None, "sections": [{"type": "unknown"}]},
        {"type": "markdown", "content": {"nested": True}, "sections": []},
        {"type": "markdown", "content": "x" * 100_001, "sections": []},
        {
            "type": "structured",
            "content": None,
            "sections": [{
                "type": "table",
                "columns": [{"label": "A", "align": "left"}],
                "rows": [[{"nested": True}]],
            }],
        },
        circular,
    ]
    for index, raw in enumerate(inputs):
        correlation_id = f"contract-failure-{index}"
        response = serialize_ask_response(
            raw,
            correlation_id=correlation_id,
        )
        assert response.schema_version == 1
        assert response.type == "error"
        assert response.sections == []
        assert correlation_id in response.content
        assert SAFE_FAILURE.split("{", 1)[0] in response.content
    assert "ask_response_contract_failure" in caplog.text
    assert "100001" not in caplog.text


def test_fuzzed_backend_shapes_always_return_a_valid_readable_contract():
    generator = random.Random(20260731)
    atoms: list[object] = [None, True, False, 0, 1.5, "", "text"]
    candidates: list[object] = atoms.copy()
    for index in range(300):
        value: object = generator.choice(atoms)
        for _ in range(generator.randrange(0, 6)):
            value = (
                [value, {"index": index}]
                if generator.choice([True, False])
                else {f"key-{index}": value}
            )
        candidates.append(value)
    for index, raw in enumerate(candidates):
        response = serialize_ask_response(
            raw,
            correlation_id=f"fuzz-{index:04d}",
        )
        validated = ChatResponse.model_validate_json(response.model_dump_json())
        assert validated.schema_version == 1
        assert validated.content or validated.sections


def test_policy_router_allows_business_analysis_keywords():
    decision = route_policy(
        "As CFO, recommend a pricing, hiring, risk, forecast, scenario, and "
        "30/60/90 action-plan review."
    )
    assert decision.notice is None
    assert decision.requires_forecast is False


def test_prompts_a_to_d_answer_fully_and_e_is_partially_limited(client):
    headers = _register_and_upload(client)
    aggregate = _ask(client, headers, PROMPT_A)
    ranking = _ask(client, headers, PROMPT_B)
    long_review = _ask(client, headers, PROMPT_C)
    cfo_review = _ask(client, headers, PROMPT_D)
    limited = _ask(client, headers, PROMPT_E)

    assert aggregate["type"] == "markdown"
    assert all(
        value in aggregate["content"]
        for value in ("$5,453,000.00", "$3,919,000.00", "$1,534,000.00", "28.13%")
    )

    assert ranking["type"] == "structured"
    ranking_tables = [
        section for section in ranking["sections"] if section["type"] == "table"
    ]
    assert ranking_tables[0]["rows"][0][1:] == [
        "December 2025",
        "$240,000.00",
        "$158,000.00",
        "$82,000.00",
        "34.17%",
        "11.63%",
    ]
    assert ranking_tables[1]["rows"][0][1] == "March 2023"

    long_types = {section["type"] for section in long_review["sections"]}
    assert {"text", "table", "scenarios", "forecast", "risks", "actions"} <= long_types

    cfo_types = {section["type"] for section in cfo_review["sections"]}
    assert {"metrics", "table", "scenarios", "forecast", "risks", "actions", "notice"} <= cfo_types
    assert "refus" not in json.dumps(cfo_review).lower()
    assert any("30/60/90" in (section.get("heading") or "") for section in cfo_review["sections"])

    assert limited["type"] == "policy_notice"
    assert "cannot guarantee" in limited["content"]
    assert "investment" in limited["content"]
    assert any(section["type"] == "forecast" for section in limited["sections"])

    for payload in (aggregate, ranking, long_review, cfo_review, limited):
        assert payload["schema_version"] == 1
        assert payload["correlation_id"]
        assert ChatResponse.model_validate(payload)


def test_varied_prompts_keep_one_shape_and_materially_different_answers(client):
    headers = _register_and_upload(client)
    payloads = [_ask(client, headers, prompt) for prompt in VARIED_PROMPTS]
    assert {payload["schema_version"] for payload in payloads} == {1}
    assert {payload["type"] for payload in payloads} >= {"markdown", "structured"}
    rendered = {
        json.dumps(payload["content"] or payload["sections"], sort_keys=True)
        for payload in payloads
    }
    assert len(rendered) >= 10


def test_monthly_reconciliation_uses_all_persisted_rows_and_ending_cash(client):
    headers = _register_and_upload(client)
    payload = _ask(
        client,
        headers,
        "Reconcile all monthly rows chronologically, including ending cash.",
    )
    table = next(
        section for section in payload["sections"] if section["type"] == "table"
    )
    assert len(table["rows"]) == 36
    assert table["rows"][0] == [
        "January 2023",
        "$100,000.00",
        "$78,000.00",
        "$22,000.00",
        "22.00%",
        "N/A",
        "$50,000.00",
    ]
    assert table["rows"][-1][-1] == "$245,000.00"
