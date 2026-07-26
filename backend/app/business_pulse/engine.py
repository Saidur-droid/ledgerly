from dataclasses import dataclass


@dataclass(frozen=True)
class PulseResult:
    score: int
    confidence: float
    summary: str
    factors: list[dict]
    metrics: dict


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0


def calculate_pulse(metrics: dict[str, float], confidence: float) -> PulseResult:
    revenue = metrics.get("revenue", 0)
    expenses = metrics.get("expenses", 0)
    profit = metrics.get("profit", revenue - expenses)
    margin = _ratio(profit, revenue)

    profitability_score = max(0, min(35, round(17 + margin * 38)))
    cost_score = max(0, min(25, round(25 * (1 - min(_ratio(expenses, revenue), 1)))))
    completeness_score = min(25, len(metrics) * 6)
    reliability_score = round(confidence * 15)
    score = max(0, min(100, profitability_score + cost_score + completeness_score + reliability_score))

    factors = [
        {"name": "Profitability", "score": profitability_score, "weight": 35, "explanation": f"Net margin is {margin:.1%}."},
        {"name": "Cost balance", "score": cost_score, "weight": 25, "explanation": f"Expenses represent {_ratio(expenses, revenue):.1%} of revenue." if revenue else "Revenue was not detected."},
        {"name": "Data completeness", "score": completeness_score, "weight": 25, "explanation": f"{len(metrics)} core KPIs were identified."},
        {"name": "Data confidence", "score": reliability_score, "weight": 15, "explanation": f"Parser confidence is {confidence:.0%}."},
    ]
    if score >= 80:
        summary = "Your business looks strong based on the uploaded data."
    elif score >= 60:
        summary = "Your business appears stable, with a few areas worth monitoring."
    else:
        summary = "The uploaded data shows pressure or limited evidence; review the factors below."
    enriched = {**metrics, "net_margin": round(margin * 100, 2)}
    return PulseResult(score, confidence, summary, factors, enriched)


def compare_metrics(current: dict[str, float], previous: dict[str, float] | None) -> dict | None:
    if not previous:
        return None
    changes = {}
    for name, value in current.items():
        old_value = previous.get(name)
        if old_value not in (None, 0):
            changes[name] = {
                "current": value,
                "previous": old_value,
                "percent_change": round((value - old_value) / abs(old_value) * 100, 1),
            }
    return {"changes": changes, "message": "Compared with your previous upload."}
