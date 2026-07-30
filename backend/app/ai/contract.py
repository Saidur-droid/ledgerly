import json
import logging
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from app.schemas import ChatResponse

LOGGER = logging.getLogger("ledgerly.ask_contract")
MAX_RESPONSE_BYTES = 100_000
MAX_INPUT_DEPTH = 8
SAFE_FAILURE = (
    "Ledgerly could not safely format this analysis. Please try again. "
    "Reference: {correlation_id}"
)


def _shape_name(value: object) -> str:
    return type(value).__name__


def _within_depth(value: object, limit: int = MAX_INPUT_DEPTH) -> bool:
    stack: list[tuple[object, int]] = [(value, 1)]
    seen: set[int] = set()
    while stack:
        current, depth = stack.pop()
        if depth > limit:
            return False
        if isinstance(current, (dict, list, tuple)):
            identity = id(current)
            if identity in seen:
                return False
            seen.add(identity)
            children = current.values() if isinstance(current, dict) else current
            stack.extend((child, depth + 1) for child in children)
    return True


def _log_failure(correlation_id: str, reason: str, raw: object) -> None:
    LOGGER.warning(
        "ask_response_contract_failure",
        extra={
            "event": "ask_response_contract_failure",
            "correlation_id": correlation_id,
            "reason": reason,
            "input_shape": _shape_name(raw),
        },
    )


def _safe_failure(
    correlation_id: str,
    confidence: str,
    sources: list[str],
    disclaimer: str,
) -> ChatResponse:
    return ChatResponse(
        response_type="structured",
        correlation_id=correlation_id,
        sections=[
            {
                "type": "notice",
                "tone": "error",
                "heading": "Analysis unavailable",
                "message": SAFE_FAILURE.format(correlation_id=correlation_id),
            }
        ],
        confidence=confidence,
        sources=sources,
        disclaimer=disclaimer,
    )


def _legacy_table(table: Mapping[str, Any]) -> dict[str, Any]:
    columns = table.get("columns")
    rows = table.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        raise ValueError("Legacy table is malformed.")
    clean_columns: list[dict[str, str]] = []
    keys: list[str] = []
    for column in columns:
        if not isinstance(column, Mapping):
            raise ValueError("Legacy table column is malformed.")
        key = column.get("key")
        label = column.get("label")
        align = column.get("align", "left")
        if not isinstance(key, str) or not isinstance(label, str):
            raise ValueError("Legacy table column is malformed.")
        keys.append(key)
        clean_columns.append({"label": label, "align": align})
    clean_rows: list[list[Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("Legacy table row is malformed.")
        clean_rows.append([row.get(key) for key in keys])
    return {"columns": clean_columns, "rows": clean_rows}


def _adapt_legacy_structured(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    title = raw.get("title")
    summary = raw.get("summary")
    if not isinstance(title, str) or not title:
        raise ValueError("Legacy structured response title is malformed.")
    if isinstance(title, str) and title:
        heading_text = f"## {title}"
        if isinstance(summary, str) and summary:
            heading_text += f"\n\n{summary}"
        sections.append({"type": "text", "markdown": heading_text})
    for section in raw.get("sections", []):
        if not isinstance(section, Mapping):
            raise ValueError("Legacy section is malformed.")
        heading = section.get("heading")
        markdown = section.get("markdown")
        cards = section.get("cards", [])
        table = section.get("table")
        if isinstance(markdown, str) and markdown:
            sections.append(
                {"type": "text", "heading": heading, "markdown": markdown}
            )
        if cards:
            sections.append(
                {"type": "metrics", "heading": heading, "items": cards}
            )
        if isinstance(table, Mapping):
            sections.append(
                {
                    "type": "table",
                    "heading": heading,
                    **_legacy_table(table),
                }
            )
    scoring = raw.get("scoring")
    if isinstance(scoring, Mapping):
        formula = scoring.get("formula")
        details = [
            scoring.get("normalization"),
            scoring.get("interpretation"),
            scoring.get("first_period"),
        ]
        text = f"**Composite score:** `{formula}`"
        text += "\n\n" + "\n\n".join(
            item for item in details if isinstance(item, str) and item
        )
        sections.append(
            {"type": "text", "heading": "Ranking method", "markdown": text}
        )
        weights = scoring.get("weights")
        if isinstance(weights, Mapping):
            sections.append(
                {
                    "type": "metrics",
                    "heading": "Ranking weights",
                    "items": [
                        {
                            "label": str(label).replace("_", " ").title(),
                            "value": f"{value}%",
                        }
                        for label, value in weights.items()
                        if isinstance(value, (int, float)) and not isinstance(value, bool)
                    ],
                }
            )
    risks = raw.get("risks")
    if isinstance(risks, list) and risks:
        sections.append(
            {
                "type": "risks",
                "heading": "Risks",
                "items": [
                    {"label": item, "detail": item}
                    for item in risks
                    if isinstance(item, str)
                ],
            }
        )
    actions = raw.get("action_plan")
    if isinstance(actions, list) and actions:
        sections.append(
            {
                "type": "actions",
                "heading": "Action plan",
                "items": [
                    {"label": item}
                    for item in actions
                    if isinstance(item, str)
                ],
            }
        )
    return sections


def serialize_ask_response(
    raw: object,
    *,
    correlation_id: str,
    confidence: str,
    sources: list[str],
    disclaimer: str,
) -> ChatResponse:
    common = {
        "correlation_id": correlation_id,
        "confidence": confidence,
        "sources": sources,
        "disclaimer": disclaimer,
    }
    try:
        if not _within_depth(raw):
            raise ValueError("input_depth_exceeded")
        if isinstance(raw, str):
            payload: dict[str, Any] = {
                "response_type": "markdown",
                "markdown": raw,
                "sections": [],
                **common,
            }
        elif isinstance(raw, Mapping) and raw.get("kind") == "structured_analysis":
            payload = {
                "response_type": "structured",
                "markdown": None,
                "sections": _adapt_legacy_structured(raw),
                **common,
            }
        elif isinstance(raw, Mapping) and raw.get("response_type") in {
            "markdown",
            "structured",
        }:
            payload = {**dict(raw), **common}
        else:
            raise ValueError("unsupported_shape")
        response = ChatResponse.model_validate(payload)
        rendered = response.model_dump_json()
        if len(rendered.encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise ValueError("response_size_exceeded")
        # Canonical round trip prevents non-deterministic or non-JSON values.
        json.loads(rendered)
        return response
    except (ValidationError, ValueError, TypeError) as error:
        reason = str(error).splitlines()[0][:120]
        _log_failure(correlation_id, reason, raw)
        return _safe_failure(correlation_id, confidence, sources, disclaimer)
