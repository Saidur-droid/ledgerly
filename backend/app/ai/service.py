import json
import re

from google import genai

from app.core.config import get_settings

PROHIBITED = re.compile(
    r"\b(should i|recommend|advice|invest|investment|stock|crypto|price|pricing|hire|hiring|fire|guarantee|forecast outcome)\b",
    re.IGNORECASE,
)
DISCLAIMER = "Ledgerly explains uploaded business data only and does not provide financial advice."
SYSTEM_INSTRUCTION = """You are Ledgerly, a careful business-data explainer.
Use only the supplied uploaded-data context. Explain, summarize, compare, and identify trends.
Never give investment, pricing, hiring, or financial recommendations. Never guarantee outcomes.
State when the data is insufficient. Keep the answer clear, concise, and evidence-based."""


def _fallback_answer(question: str, context: dict) -> str:
    metrics = context.get("metrics", {})
    if not metrics:
        return "I could not identify enough structured metrics in the latest upload to answer that confidently."
    rendered = ", ".join(f"{name.replace('_', ' ')}: {value:,.2f}" for name, value in metrics.items())
    return f"The latest upload shows {rendered}. I can explain changes once a previous upload contains matching metrics."


def answer_business_question(question: str, context: dict) -> tuple[str, str]:
    if PROHIBITED.search(question):
        return (
            "I can explain what your uploaded data shows, but I can’t provide investment, pricing, hiring, or outcome-guarantee advice.",
            "policy-limited",
        )
    settings = get_settings()
    if not settings.gemini_api_key:
        return _fallback_answer(question, context), "data-grounded"
    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = f"{SYSTEM_INSTRUCTION}\n\nDATA CONTEXT:\n{json.dumps(context, default=str)[:25000]}\n\nQUESTION:\n{question}"
    response = client.models.generate_content(model=settings.gemini_model, contents=prompt)
    return response.text or _fallback_answer(question, context), "high"
