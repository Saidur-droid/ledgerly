import re
from dataclasses import dataclass

GUARANTEE_REQUEST = re.compile(
    r"\b(guarantee|guaranteed|promise|certain(?:ty)?|assure)\b",
    re.IGNORECASE,
)
REGULATED_ADVICE = re.compile(
    r"\b("
    r"which|what|tell me (?:exactly )?(?:which|what)"
    r")\s+(stock|security|crypto|investment)\b|"
    r"\b(buy|sell|invest in)\s+(?:this|a|the|which|what)?\s*"
    r"(stock|security|crypto|investment)\b|"
    r"\b(personalized|specific)\s+(legal|tax|investment)\s+advice\b|"
    r"\b(evade|avoid paying)\s+tax(?:es)?\b",
    re.IGNORECASE,
)

GUARANTEE_NOTICE = (
    "Ledgerly cannot guarantee future outcomes. Forecasts and scenarios below "
    "are cautious, mechanical explanations of uploaded historical data."
)
REGULATED_NOTICE = (
    "Ledgerly cannot provide personalized investment, legal, or tax advice. "
    "It can still explain the business patterns supported by your upload."
)


@dataclass(frozen=True)
class PolicyDecision:
    notices: tuple[str, ...] = ()
    requires_forecast: bool = False

    @property
    def notice(self) -> str | None:
        return " ".join(self.notices) or None


def route_policy(question: str) -> PolicyDecision:
    notices: list[str] = []
    guarantee = bool(GUARANTEE_REQUEST.search(question))
    if guarantee:
        notices.append(GUARANTEE_NOTICE)
    if REGULATED_ADVICE.search(question):
        notices.append(REGULATED_NOTICE)
    return PolicyDecision(
        notices=tuple(notices),
        requires_forecast=guarantee,
    )
