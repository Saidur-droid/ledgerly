import json
from dataclasses import dataclass

from google import genai

from app.ai.analysis import deterministic_answer
from app.ai.policy import route_policy
from app.core.config import get_settings

SYSTEM_INSTRUCTION = """You are Ledgerly, a careful business-data analyst.
Answer only the exact question asked, using only the supplied authenticated
uploaded-data context and deterministic calculations present in that context.
Never invent a financial value or silently infer missing data. If the evidence
is insufficient, state precisely which fields, periods, rows, or documents are
missing. Preserve the source currency and numerical values. Detect the language
of the question and answer in that same language. Use plain business language
by default and professional accounting terminology only when the question
clearly calls for it. Keep the default response concise and direct.
Do not guarantee outcomes or provide personalized investment, legal, or tax
advice. Do not add unrelated recommendations, summaries, education, KPIs, or
sections. Keep every claim grounded in the uploaded rows and return Markdown
text only."""


@dataclass(frozen=True)
class AnalysisResult:
    answer: str | dict
    policy_notice: str | None = None


def _provider_answer(question: str, context: dict) -> str | None:
    settings = get_settings()
    if not settings.gemini_api_key:
        return None
    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        prompt = (
            f"{SYSTEM_INSTRUCTION}\n\nDATA CONTEXT:\n"
            f"{json.dumps(context, default=str)[:25000]}\n\nQUESTION:\n{question}"
        )
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
        )
    except Exception:
        return None
    return response.text or None


def answer_business_question(question: str, context: dict) -> AnalysisResult:
    policy = route_policy(question)
    analysis_question = (
        f"{question}\nProvide a cautious historical forecast."
        if policy.requires_forecast
        else question
    )
    analyzed = deterministic_answer(analysis_question, context)
    if analyzed is None:
        analyzed = _provider_answer(analysis_question, context)
    if analyzed is None:
        analyzed = deterministic_answer("Provide a CFO-style business review.", context)
    return AnalysisResult(answer=analyzed, policy_notice=policy.notice)
