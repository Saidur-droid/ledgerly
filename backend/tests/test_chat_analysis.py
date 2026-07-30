from pathlib import Path

import pytest
from sqlalchemy import select

from app.ai.analysis import (
    MISSING_GROWTH_SCORE,
    RANKING_FORMULA,
    RANKING_WEIGHTS,
    _periods,
    _rank_scores,
    _ranking_groups,
)
from app.core.database import SessionLocal
from app.models import Upload

FIXTURE = Path(__file__).parent / "fixtures" / "sample_business_data.csv"
PROMPT_A = "Summarize my total revenue, expenses, profit, and net margin."
PROMPT_B = (
    "Analyze each monthly row in my uploaded CSV. Identify the five best and "
    "five worst months using profit, net margin, and revenue growth. Include "
    "the exact month and values in a table."
)


def _register(client, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": "Analysis Owner",
            "password": "strong-password",
        },
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _upload_fixture(client, headers: dict[str, str]):
    response = client.post(
        "/api/v1/uploads",
        headers=headers,
        files={
            "file": (
                FIXTURE.name,
                FIXTURE.read_bytes(),
                "text/csv",
            )
        },
    )
    assert response.status_code == 201
    return response


def test_36_row_upload_persists_period_analysis_and_cash_balance(client):
    headers = _register(client, "period-analysis@example.com")
    response = _upload_fixture(client, headers)

    assert response.json()["metrics"] == {
        "revenue": 5_453_000.0,
        "expenses": 3_919_000.0,
        "profit": 1_534_000.0,
        "cash": 245_000.0,
        "net_margin": 28.13,
    }
    with SessionLocal() as session:
        upload = session.scalar(
            select(Upload).where(Upload.filename == FIXTURE.name)
        )
        assert upload is not None
        records = upload.normalized_data["records"]
        assert len(records) == 36
        assert records[0] == {
            "date": "2023-01-31",
            "revenue": 100_000.0,
            "expenses": 78_000.0,
            "cash": 50_000.0,
            "customers": 1000,
            "profit": 22_000.0,
            "net_margin": 22.0,
            "revenue_growth": None,
        }
        assert records[-1]["date"] == "2025-12-31"
        assert records[-1]["profit"] == 82_000.0
        assert records[-1]["net_margin"] == 34.17
        assert records[-1]["revenue_growth"] == 11.63
        assert upload.normalized_data["metadata"]["cash"] == {
            "semantic": "period_ending_balance",
            "headline_calculation": "latest",
            "assumption": (
                "Cash is treated as a period-ending balance; the latest dated "
                "value is the headline and balances are not summed."
            ),
            "latest": 245_000.0,
            "average": 118_472.22,
            "minimum": 49_000.0,
            "maximum": 245_000.0,
            "change": 195_000.0,
        }


def test_chat_questions_use_persisted_rows_and_produce_distinct_answers(client):
    headers = _register(client, "question-aware@example.com")
    _upload_fixture(client, headers)

    aggregate = client.post(
        "/api/v1/chat",
        headers=headers,
        json={"question": PROMPT_A},
    )
    period_analysis = client.post(
        "/api/v1/chat",
        headers=headers,
        json={"question": PROMPT_B},
    )

    assert aggregate.status_code == 200
    assert period_analysis.status_code == 200
    aggregate_answer = aggregate.json()["answer"]
    period_answer = period_analysis.json()["answer"]
    assert aggregate_answer != period_answer
    assert "$5,453,000.00" in aggregate_answer
    assert "$3,919,000.00" in aggregate_answer
    assert "$1,534,000.00" in aggregate_answer
    assert "28.13%" in aggregate_answer
    assert "5 best months" in period_answer
    assert "5 worst months" in period_answer
    assert "| Rank | Month | Revenue | Expenses | Profit | Net margin | Revenue growth |" in period_answer
    assert (
        "| 1 | December 2025 | $240,000.00 | $158,000.00 | "
        "$82,000.00 | 34.17% | 11.63% |"
    ) in period_answer
    assert (
        "| 1 | March 2023 | $98,000.00 | $79,000.00 | "
        "$19,000.00 | 19.39% | -6.67% |"
    ) in period_answer
    assert "previous upload" not in aggregate_answer.lower()
    assert "previous upload" not in period_answer.lower()
    assert RANKING_FORMULA in period_answer
    assert "min–max normalized" in period_answer
    assert "highest-profit month may not rank first" in period_answer
    assert "neutral normalized growth score of 0.50" in period_answer
    assert aggregate.json()["confidence"] == "data-grounded"
    assert period_analysis.json()["confidence"] == "data-grounded"


def test_cash_answer_uses_latest_balance_instead_of_sum(client):
    headers = _register(client, "cash-semantics@example.com")
    _upload_fixture(client, headers)

    response = client.post(
        "/api/v1/chat",
        headers=headers,
        json={"question": "Summarize cash flow and cash balance over time."},
    )

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert "Latest period-ending cash was $245,000.00" in answer
    assert "Average balance was $118,472.22" in answer
    assert "monthly balances are not summed" in answer
    assert "$4,265,000.00" not in answer


def test_chat_response_is_derived_from_current_upload_values(client):
    headers = _register(client, "derived-response@example.com")
    uploaded = client.post(
        "/api/v1/uploads",
        headers=headers,
        files={
            "file": (
                "custom.csv",
                (
                    b"date,revenue,expenses,cash\n"
                    b"2026-01-31,3210,1110,8000\n"
                    b"2026-02-28,4560,1560,9200\n"
                ),
                "text/csv",
            )
        },
    )
    assert uploaded.status_code == 201

    response = client.post(
        "/api/v1/chat",
        headers=headers,
        json={"question": PROMPT_A},
    )

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert "$7,770.00" in answer
    assert "$2,670.00" in answer
    assert "$5,100.00" in answer
    assert "65.64%" in answer
    assert "$5,453,000.00" not in answer


def test_chat_empty_upload_behavior_remains_clear(client):
    headers = _register(client, "empty-chat@example.com")

    response = client.post(
        "/api/v1/chat",
        headers=headers,
        json={"question": PROMPT_A},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Upload business data first."}


def test_ranking_sorts_dates_normalizes_inputs_and_handles_first_growth():
    periods = _periods(
        {
            "data": {
                "records": [
                    {
                        "date": "2026-03-31",
                        "revenue": 90,
                        "expenses": 50,
                    },
                    {
                        "date": "2026-01-31",
                        "revenue": 100,
                        "expenses": 70,
                    },
                    {
                        "date": "2026-02-28",
                        "revenue": 80,
                        "expenses": 65,
                    },
                ]
            }
        }
    )
    ranked = _rank_scores(periods)

    assert [period["label"] for period in periods] == [
        "January 2026",
        "February 2026",
        "March 2026",
    ]
    assert periods[0]["revenue_growth"] is None
    assert periods[1]["revenue_growth"] == -20
    assert periods[2]["revenue_growth"] == 12.5
    first = next(period for period in ranked if period["label"] == "January 2026")
    declining = next(
        period for period in ranked if period["label"] == "February 2026"
    )
    growing = next(period for period in ranked if period["label"] == "March 2026")
    assert RANKING_WEIGHTS == {
        "profit": 0.40,
        "net_margin": 0.35,
        "revenue_growth": 0.25,
    }
    assert sum(RANKING_WEIGHTS.values()) == pytest.approx(1.0)
    assert first["revenue_growth_normalized"] == MISSING_GROWTH_SCORE
    assert declining["revenue_growth_normalized"] == 0
    assert growing["revenue_growth_normalized"] == 1
    assert all(
        0 <= period[f"{metric}_normalized"] <= 1
        for period in ranked
        for metric in RANKING_WEIGHTS
    )
    assert all(
        period["ranking_score"]
        == pytest.approx(
            sum(
                period[f"{metric}_normalized"] * weight
                for metric, weight in RANKING_WEIGHTS.items()
            )
        )
        for period in ranked
    )


def test_ranking_ties_are_stable_and_best_worst_do_not_overlap():
    tied_periods = [
        {
            "position": position,
            "label": f"Period {position}",
            "date": f"2026-0{position + 1}-28",
            "revenue": 100.0,
            "expenses": 50.0,
            "profit": 50.0,
            "net_margin": 50.0,
            "revenue_growth": 0.0,
        }
        for position in range(6)
    ]
    ranked = _rank_scores(tied_periods)
    best, worst = _ranking_groups(ranked)

    assert [period["position"] for period in ranked] == list(range(6))
    assert {period["position"] for period in best}.isdisjoint(
        {period["position"] for period in worst}
    )
    assert len(best) == 3
    assert len(worst) == 3
