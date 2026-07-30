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


def _within_depth(value: object, limit: int = MAX_INPUT_DEPTH) -> bool:
    stack: list[tuple[object, int, frozenset[int]]] = [
        (value, 1, frozenset())
    ]
    while stack:
        current, depth, ancestors = stack.pop()
        if depth > limit:
            return False
        if isinstance(current, (dict, list, tuple)):
            identity = id(current)
            if identity in ancestors:
                return False
            branch = ancestors | {identity}
            children = current.values() if isinstance(current, dict) else current
            stack.extend((child, depth + 1, branch) for child in children)
    return True


def _log_failure(correlation_id: str, reason: str, raw: object) -> None:
    LOGGER.warning(
        "ask_response_contract_failure",
        extra={
            "event": "ask_response_contract_failure",
            "correlation_id": correlation_id,
            "reason": reason,
            "input_shape": type(raw).__name__,
        },
    )


def _safe_failure(correlation_id: str) -> ChatResponse:
    return ChatResponse(
        type="error",
        content=SAFE_FAILURE.format(correlation_id=correlation_id),
        sections=[],
        correlation_id=correlation_id,
    )


def _base_payload(raw: object, correlation_id: str) -> dict[str, Any]:
    if isinstance(raw, str):
        return {
            "type": "markdown",
            "content": raw,
            "sections": [],
            "correlation_id": correlation_id,
        }
    if isinstance(raw, Mapping) and raw.get("type") in {
        "markdown",
        "structured",
    }:
        return {
            **dict(raw),
            "correlation_id": correlation_id,
        }
    raise ValueError("unsupported_shape")


def _with_policy_notice(
    payload: dict[str, Any],
    policy_notice: str,
) -> dict[str, Any]:
    analysis_type = payload.get("type")
    if analysis_type == "markdown":
        markdown = payload.get("content")
        return {
            **payload,
            "type": "policy_notice",
            "content": policy_notice,
            "sections": [{"type": "text", "markdown": markdown}],
        }
    if analysis_type == "structured":
        return {
            **payload,
            "type": "policy_notice",
            "content": policy_notice,
        }
    raise ValueError("policy_notice_cannot_wrap_response")


def serialize_ask_response(
    raw: object,
    *,
    correlation_id: str,
    policy_notice: str | None = None,
) -> ChatResponse:
    try:
        if not _within_depth(raw):
            raise ValueError("input_depth_exceeded")
        payload = _base_payload(raw, correlation_id)
        if policy_notice:
            payload = _with_policy_notice(payload, policy_notice)
        response = ChatResponse.model_validate(payload)
        rendered = response.model_dump_json()
        if len(rendered.encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise ValueError("response_size_exceeded")
        json.loads(rendered)
        return response
    except (ValidationError, ValueError, TypeError) as error:
        reason = str(error).splitlines()[0][:120]
        _log_failure(correlation_id, reason, raw)
        return _safe_failure(correlation_id)
