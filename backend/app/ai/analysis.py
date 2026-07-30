import math
import re
from datetime import datetime
from typing import Any

PERIOD_ANALYSIS = re.compile(
    r"\b(best|worst|top|bottom|monthly row|each month|each period)\b",
    re.IGNORECASE,
)
AGGREGATE_ANALYSIS = re.compile(
    r"\b(total|aggregate|overall|summari[sz]e|headline)\b",
    re.IGNORECASE,
)
TREND_ANALYSIS = re.compile(
    r"\b(trend|change over time|increasing|decreasing|growth)\b",
    re.IGNORECASE,
)
SEASONALITY_ANALYSIS = re.compile(
    r"\b(season|seasonality|seasonal|month of year)\b",
    re.IGNORECASE,
)
MARGIN_ANALYSIS = re.compile(r"\b(margin|profitability)\b", re.IGNORECASE)
CASH_ANALYSIS = re.compile(
    r"\b(cash|liquidity|balance)\b",
    re.IGNORECASE,
)
RISK_ANALYSIS = re.compile(
    r"\b(risk|volatil|decline|loss|negative)\b",
    re.IGNORECASE,
)
FORECAST_ANALYSIS = re.compile(
    r"\b(forecast|projection|project|outlook|run rate)\b",
    re.IGNORECASE,
)
SCENARIO_ANALYSIS = re.compile(
    r"\b(scenario|what if|sensitivity)\b",
    re.IGNORECASE,
)
RECONCILIATION_ANALYSIS = re.compile(
    r"\b(reconcile|reconciliation|each monthly row|all monthly rows|month by month)\b",
    re.IGNORECASE,
)
CFO_ANALYSIS = re.compile(
    r"\b(cfo|executive review|management review|board summary)\b",
    re.IGNORECASE,
)
ACTION_ANALYSIS = re.compile(
    r"\b(action plan|30[/ -]60[/ -]90|recommend|operational action|next steps?)\b",
    re.IGNORECASE,
)
PRICING_OR_HIRING = re.compile(
    r"\b(pric(?:e|ing)|hir(?:e|ing)|headcount|staffing)\b",
    re.IGNORECASE,
)
RANKING_WEIGHTS = {
    "profit": 0.40,
    "net_margin": 0.35,
    "revenue_growth": 0.25,
}
MISSING_GROWTH_SCORE = 0.50
RANKING_FORMULA = "40% profit + 35% net margin + 25% revenue growth"


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _date(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    for pattern in ("%Y-%m-%d", "%Y-%m", "%b %Y", "%B %Y"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _period_label(record: dict[str, Any], position: int) -> str:
    value = record.get("date") or record.get("month") or record.get("period")
    parsed = _date(value)
    if parsed is not None:
        return parsed.strftime("%B %Y")
    return str(value).strip() if value not in (None, "") else f"Period {position + 1}"


def _periods(context: dict[str, Any]) -> list[dict[str, Any]]:
    data = context.get("data", {})
    source_records = data.get("records", []) if isinstance(data, dict) else []
    periods: list[dict[str, Any]] = []
    for position, source in enumerate(source_records):
        if not isinstance(source, dict):
            continue
        revenue = _number(source.get("revenue"))
        expenses = _number(source.get("expenses"))
        profit = _number(source.get("profit"))
        if profit is None and revenue is not None and expenses is not None:
            profit = revenue - expenses
        margin = _number(source.get("net_margin"))
        if margin is None and revenue not in (None, 0) and profit is not None:
            margin = profit / revenue * 100
        periods.append(
            {
                "position": position,
                "date": source.get("date")
                or source.get("month")
                or source.get("period"),
                "label": _period_label(source, position),
                "revenue": revenue,
                "expenses": expenses,
                "profit": profit,
                "net_margin": margin,
                "revenue_growth": _number(source.get("revenue_growth")),
                "cash": _number(source.get("cash")),
            }
        )
    periods.sort(key=lambda item: (_date(item["date"]) is None, _date(item["date"]) or item["position"]))

    previous_revenue: float | None = None
    for period in periods:
        if period["revenue_growth"] is None:
            revenue = period["revenue"]
            if revenue is not None and previous_revenue not in (None, 0):
                period["revenue_growth"] = (
                    (revenue - previous_revenue) / previous_revenue * 100
                )
        if period["revenue"] is not None:
            previous_revenue = period["revenue"]
    return periods


def _money(value: float | None) -> str:
    return "N/A" if value is None else f"${value:,.2f}"


def _percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value:,.2f}%"


def _range_description(periods: list[dict[str, Any]]) -> str:
    if not periods:
        return "the latest upload"
    if len(periods) == 1:
        return periods[0]["label"]
    return f"{periods[0]['label']} through {periods[-1]['label']}"


def _aggregate_answer(context: dict[str, Any], periods: list[dict[str, Any]]) -> str:
    metrics = context.get("metrics", {})
    revenue = _number(metrics.get("revenue"))
    expenses = _number(metrics.get("expenses"))
    profit = _number(metrics.get("profit"))
    margin = _number(metrics.get("net_margin"))
    if margin is None and revenue not in (None, 0) and profit is not None:
        margin = profit / revenue * 100
    period_count = len(periods)
    scope = (
        f"Across {period_count} persisted periods ({_range_description(periods)})"
        if period_count
        else "In the latest persisted upload"
    )
    return (
        f"{scope}, total revenue was {_money(revenue)}, total expenses were "
        f"{_money(expenses)}, and total profit was {_money(profit)}. Net margin "
        f"was {_percent(margin)} (total profit divided by total revenue)."
    )


def _rank_scores(periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    analyzable = [
        {**period}
        for period in periods
        if period["profit"] is not None
        and period["net_margin"] is not None
        and period["revenue"] is not None
    ]
    if not analyzable:
        return []
    for metric, weight in RANKING_WEIGHTS.items():
        available = [
            float(period[metric])
            for period in analyzable
            if period[metric] is not None
        ]
        minimum = min(available)
        maximum = max(available)
        value_range = maximum - minimum
        for period in analyzable:
            value = period[metric]
            normalized = (
                MISSING_GROWTH_SCORE
                if value is None
                else (
                    (float(value) - minimum) / value_range
                    if value_range
                    else MISSING_GROWTH_SCORE
                )
            )
            period[f"{metric}_normalized"] = normalized
            period[f"{metric}_weighted"] = normalized * weight
    for period in analyzable:
        period["ranking_score"] = sum(
            float(period[f"{metric}_weighted"])
            for metric in RANKING_WEIGHTS
        )
    return sorted(
        analyzable,
        key=lambda item: item["ranking_score"],
        reverse=True,
    )


def _period_section(
    title: str,
    periods: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "type": "table",
        "heading": title,
        "columns": [
            {"label": "Rank", "align": "right"},
            {"label": "Month", "align": "left"},
            {"label": "Revenue", "align": "right"},
            {"label": "Expenses", "align": "right"},
            {"label": "Profit", "align": "right"},
            {"label": "Net margin", "align": "right"},
            {"label": "Revenue growth", "align": "right"},
        ],
        "rows": [
            [
                rank,
                period["label"],
                _money(period["revenue"]),
                _money(period["expenses"]),
                _money(period["profit"]),
                _percent(period["net_margin"]),
                _percent(period["revenue_growth"]),
            ]
            for rank, period in enumerate(periods, 1)
        ],
    }


def _ranking_groups(
    ranked: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    best_count = min(5, (len(ranked) + 1) // 2)
    worst_count = min(5, len(ranked) - best_count)
    best = ranked[:best_count]
    bottom = ranked[-worst_count:] if worst_count else []
    worst = sorted(bottom, key=lambda item: item["ranking_score"])
    return best, worst


def _best_worst_answer(periods: list[dict[str, Any]]) -> str | dict[str, Any]:
    ranked = _rank_scores(periods)
    if not ranked:
        return (
            "The latest upload does not contain enough row-level revenue, "
            "expenses, and profit data to rank periods."
        )
    best, worst = _ranking_groups(ranked)
    sections = [_period_section(f"{len(best)} best months", best)]
    if worst:
        sections.append(_period_section(f"{len(worst)} worst months", worst))
    return {
        "type": "structured",
        "content": None,
        "sections": [
            {
                "type": "text",
                "heading": "Monthly performance ranking",
                "markdown": (
                    f"I analyzed **{len(ranked)} persisted rows** from "
                    f"{_range_description(periods)}."
                ),
            },
            *sections,
            {
                "type": "text",
                "heading": "Ranking method",
                "markdown": (
                    f"**Composite score:** `{RANKING_FORMULA}`\n\n"
                    "Each input is min–max normalized to a 0–1 score across the "
                    "persisted months before its weight is applied. Negative "
                    "growth remains negative before normalization and is ranked "
                    "relative to the other observed growth values.\n\n"
                    "The first chronological month has no prior-period growth "
                    f"value, so it receives a neutral normalized growth score "
                    f"of {MISSING_GROWTH_SCORE:.2f}.\n\n"
                    "Rankings use a composite score, so the highest-profit month "
                    "may not rank first when its margin or growth is weaker."
                ),
            },
            {
                "type": "metrics",
                "heading": "Ranking weights",
                "items": [
                    {
                        "label": metric.replace("_", " ").title(),
                        "value": f"{weight * 100:.0f}%",
                    }
                    for metric, weight in RANKING_WEIGHTS.items()
                ],
            },
        ],
    }


def _trend_answer(periods: list[dict[str, Any]]) -> str:
    revenue_periods = [period for period in periods if period["revenue"] is not None]
    if len(revenue_periods) < 2:
        return "At least two dated revenue rows are required to analyze a trend."
    first, latest = revenue_periods[0], revenue_periods[-1]
    change = (
        (latest["revenue"] - first["revenue"]) / first["revenue"] * 100
        if first["revenue"] != 0
        else None
    )
    growth_rates = [
        period["revenue_growth"]
        for period in revenue_periods
        if period["revenue_growth"] is not None
    ]
    average_growth = sum(growth_rates) / len(growth_rates) if growth_rates else None
    peak = max(revenue_periods, key=lambda item: item["revenue"])
    trough = min(revenue_periods, key=lambda item: item["revenue"])
    return (
        f"Revenue moved from {_money(first['revenue'])} in {first['label']} to "
        f"{_money(latest['revenue'])} in {latest['label']}, a total change of "
        f"{_percent(change)}. Average period-over-period growth was "
        f"{_percent(average_growth)}. The highest revenue period was "
        f"{peak['label']} at {_money(peak['revenue'])}; the lowest was "
        f"{trough['label']} at {_money(trough['revenue'])}."
    )


def _seasonality_answer(periods: list[dict[str, Any]]) -> str:
    buckets: dict[int, list[float]] = {}
    for period in periods:
        parsed = _date(period["date"])
        if parsed is not None and period["revenue"] is not None:
            buckets.setdefault(parsed.month, []).append(period["revenue"])
    repeated = {month: values for month, values in buckets.items() if len(values) >= 2}
    if len(repeated) < 2:
        return (
            "The current upload does not contain enough repeated calendar months "
            "to identify seasonality confidently."
        )
    averages = {
        month: sum(values) / len(values)
        for month, values in repeated.items()
    }
    strongest = max(averages, key=averages.get)
    weakest = min(averages, key=averages.get)
    return (
        f"Across repeated calendar months, "
        f"{datetime(2000, strongest, 1).strftime('%B')} had the highest average "
        f"revenue at {_money(averages[strongest])}, while "
        f"{datetime(2000, weakest, 1).strftime('%B')} had the lowest at "
        f"{_money(averages[weakest])}. This describes the uploaded history; it "
        "does not guarantee future seasonality."
    )


def _margin_answer(context: dict[str, Any], periods: list[dict[str, Any]]) -> str:
    margins = [period for period in periods if period["net_margin"] is not None]
    aggregate = _number(context.get("metrics", {}).get("net_margin"))
    if not margins:
        return f"The latest upload's aggregate net margin is {_percent(aggregate)}."
    best = max(margins, key=lambda item: item["net_margin"])
    worst = min(margins, key=lambda item: item["net_margin"])
    return (
        f"Aggregate net margin was {_percent(aggregate)}. The strongest monthly "
        f"margin was {_percent(best['net_margin'])} in {best['label']}; the "
        f"weakest was {_percent(worst['net_margin'])} in {worst['label']}."
    )


def _cash_answer(context: dict[str, Any]) -> str:
    data = context.get("data", {})
    metadata = data.get("metadata", {}) if isinstance(data, dict) else {}
    cash = metadata.get("cash", {}) if isinstance(metadata, dict) else {}
    if not cash:
        source_records = data.get("records", []) if isinstance(data, dict) else []
        cash_column = next(
            (
                str(column)
                for column in data.get("columns", [])
                if "cash" in str(column).lower()
                or "balance" in str(column).lower()
            ),
            None,
        )
        if cash_column is not None:
            values = [
                value
                for record in source_records
                if isinstance(record, dict)
                and (value := _number(record.get(cash_column))) is not None
            ]
            if values:
                is_flow = "flow" in cash_column.lower()
                cash = {
                    "semantic": (
                        "period_cash_flow"
                        if is_flow
                        else "period_ending_balance"
                    ),
                    "latest": values[-1],
                    "average": sum(values) / len(values),
                    "minimum": min(values),
                    "maximum": max(values),
                    "change": values[-1] - values[0],
                }
        if not cash:
            value = _number(context.get("metrics", {}).get("cash"))
            return (
                f"The latest upload's headline cash value is {_money(value)}. "
                "The source does not explicitly define whether cash is a "
                "balance or flow."
            )
    if cash.get("semantic") == "period_cash_flow":
        total = _number(context.get("metrics", {}).get("cash"))
        return (
            f"The source explicitly identifies period cash flow, so the headline "
            f"cash-flow total is {_money(total)}. Latest period flow was "
            f"{_money(_number(cash.get('latest')))}."
        )
    return (
        f"Latest period-ending cash was {_money(_number(cash.get('latest')))}. "
        f"Average balance was {_money(_number(cash.get('average')))}, the minimum "
        f"was {_money(_number(cash.get('minimum')))}, the maximum was "
        f"{_money(_number(cash.get('maximum')))}, and the first-to-latest change "
        f"was {_money(_number(cash.get('change')))}. Assumption: cash is a "
        "period-ending balance, so monthly balances are not summed."
    )


def _risk_answer(periods: list[dict[str, Any]]) -> dict[str, Any]:
    losses = [period for period in periods if period["profit"] is not None and period["profit"] < 0]
    declines = [
        period
        for period in periods
        if period["revenue_growth"] is not None and period["revenue_growth"] < 0
    ]
    worst_growth = (
        min(declines, key=lambda item: item["revenue_growth"])
        if declines
        else None
    )
    risks = [
        {
            "label": "Loss-making periods",
            "detail": f"{len(losses)} period(s) had negative profit.",
            "severity": "high" if losses else "low",
        },
        {
            "label": "Revenue declines",
            "detail": (
                f"{len(declines)} period(s) had negative revenue growth."
                + (
                    f" The steepest decline was "
                    f"{_percent(worst_growth['revenue_growth'])} in "
                    f"{worst_growth['label']}."
                    if worst_growth is not None
                    else ""
                )
            ),
            "severity": "medium" if declines else "low",
        },
    ]
    return {
        "type": "structured",
        "content": None,
        "sections": [
            {
                "type": "text",
                "heading": "Observed risk review",
                "markdown": (
                    "Risks are ranked from patterns in the persisted rows; "
                    "they are not predictions or regulated recommendations."
                ),
            },
            {
                "type": "risks",
                "heading": "Ranked data risks",
                "items": risks,
            },
        ],
    }


def _forecast_answer(periods: list[dict[str, Any]]) -> str | dict[str, Any]:
    revenue_periods = [period for period in periods if period["revenue"] is not None]
    growth_rates = [
        period["revenue_growth"]
        for period in revenue_periods[-7:]
        if period["revenue_growth"] is not None
    ]
    if not revenue_periods or not growth_rates:
        return "The current upload does not contain enough consecutive revenue rows for a projection."
    latest = revenue_periods[-1]
    average_growth = sum(growth_rates) / len(growth_rates)
    projected = latest["revenue"] * (1 + average_growth / 100)
    return {
        "type": "structured",
        "content": None,
        "sections": [{
            "type": "forecast",
            "heading": "Historical run-rate forecast",
            "summary": (
                "A cautious one-period projection based on uploaded historical "
                "growth; it is not a guarantee."
            ),
            "horizon": "One period",
            "methodology": (
                f"Average of the latest {len(growth_rates)} observed growth "
                f"rates ({_percent(average_growth)})."
            ),
            "metrics": [
                {"label": "Latest revenue", "value": _money(latest["revenue"])},
                {"label": "Projected revenue", "value": _money(projected)},
            ],
            "caveats": ["Uploaded historical growth may not repeat."],
        }],
    }


def _scenario_answer(context: dict[str, Any], question: str) -> str | dict[str, Any]:
    metrics = context.get("metrics", {})
    revenue = _number(metrics.get("revenue"))
    expenses = _number(metrics.get("expenses"))
    changes = re.findall(r"([+-]?\d+(?:\.\d+)?)\s*%", question)
    change = float(changes[0]) if changes else 10.0
    if revenue is None or expenses is None:
        return "Revenue and expenses are required for a scenario calculation."
    scenario_revenue = revenue * (1 + change / 100)
    scenario_profit = scenario_revenue - expenses
    scenario_margin = scenario_profit / scenario_revenue * 100 if scenario_revenue else None
    return {
        "type": "structured",
        "content": None,
        "sections": [{
            "type": "scenarios",
            "heading": "Scenario analysis",
            "scenarios": [{
                "name": f"Revenue {change:+.2f}%",
                "assumptions": [
                    f"Expenses remain {_money(expenses)}.",
                    "All other uploaded relationships remain unchanged.",
                ],
                "outcomes": [
                    {"label": "Revenue", "value": _money(scenario_revenue)},
                    {"label": "Profit", "value": _money(scenario_profit)},
                    {"label": "Net margin", "value": _percent(scenario_margin)},
                ],
            }],
        }],
    }


def _reconciliation_answer(
    periods: list[dict[str, Any]],
) -> str | dict[str, Any]:
    if not periods:
        return "The latest upload does not contain row-level periods to reconcile."
    return {
        "type": "structured",
        "content": None,
        "sections": [
            {
                "type": "text",
                "heading": "Monthly reconciliation",
                "markdown": (
                    f"I reconciled **{len(periods)} chronological rows** from "
                    f"{_range_description(periods)}. Profit equals revenue minus "
                    "expenses where both values are available."
                ),
            },
            {
                "type": "table",
                "heading": "Persisted monthly rows",
                "columns": [
                    {"label": "Month", "align": "left"},
                    {"label": "Revenue", "align": "right"},
                    {"label": "Expenses", "align": "right"},
                    {"label": "Profit", "align": "right"},
                    {"label": "Net margin", "align": "right"},
                    {"label": "Revenue growth", "align": "right"},
                    {"label": "Ending cash", "align": "right"},
                ],
                "rows": [
                    [
                        period["label"],
                        _money(period["revenue"]),
                        _money(period["expenses"]),
                        _money(period["profit"]),
                        _percent(period["net_margin"]),
                        _percent(period["revenue_growth"]),
                        _money(period["cash"]),
                    ]
                    for period in periods
                ],
            },
        ],
    }


def _comprehensive_answer(
    context: dict[str, Any],
    question: str,
    periods: list[dict[str, Any]],
) -> dict[str, Any]:
    ranked = _rank_scores(periods)
    best, worst = _ranking_groups(ranked)
    metrics = context.get("metrics", {})
    revenue = _number(metrics.get("revenue"))
    expenses = _number(metrics.get("expenses"))
    change_match = re.search(r"([+-]?\d+(?:\.\d+)?)\s*%", question)
    change = float(change_match.group(1)) if change_match else 10.0
    scenario_revenue = revenue * (1 + change / 100) if revenue is not None else None
    scenario_profit = (
        scenario_revenue - expenses
        if scenario_revenue is not None and expenses is not None
        else None
    )
    scenario_margin = (
        scenario_profit / scenario_revenue * 100
        if scenario_profit is not None and scenario_revenue
        else None
    )
    revenue_periods = [item for item in periods if item["revenue"] is not None]
    recent_growth = [
        item["revenue_growth"]
        for item in revenue_periods[-7:]
        if item["revenue_growth"] is not None
    ]
    average_growth = (
        sum(recent_growth) / len(recent_growth) if recent_growth else None
    )
    projected = (
        revenue_periods[-1]["revenue"] * (1 + average_growth / 100)
        if revenue_periods and average_growth is not None
        else None
    )
    losses = [item for item in periods if item["profit"] is not None and item["profit"] < 0]
    declines = [
        item
        for item in periods
        if item["revenue_growth"] is not None and item["revenue_growth"] < 0
    ]
    return {
        "type": "structured",
        "content": None,
        "sections": [
            {
                "type": "text",
                "heading": "Business data audit",
                "markdown": (
                    f"I analyzed **{len(periods)} persisted periods** from "
                    f"{_range_description(periods)}."
                ),
            },
            _period_section(f"{len(best)} best months", best),
            _period_section(f"{len(worst)} worst months", worst),
            {
                "type": "text",
                "heading": "Ranking method",
                "markdown": (
                    f"**Composite score:** `{RANKING_FORMULA}`\n\n"
                    "Each input is min–max normalized before weighting. The "
                    "first chronological period receives a neutral 0.50 growth "
                    "score because no prior period exists."
                ),
            },
            {
                "type": "scenarios",
                "heading": "Scenario analysis",
                "scenarios": [{
                    "name": f"Revenue {change:+.2f}%",
                    "assumptions": ["Aggregate expenses remain unchanged."],
                    "outcomes": [
                        {"label": "Revenue", "value": _money(scenario_revenue)},
                        {"label": "Profit", "value": _money(scenario_profit)},
                        {"label": "Net margin", "value": _percent(scenario_margin)},
                    ],
                }],
            },
            {
                "type": "forecast",
                "heading": "Historical run-rate forecast",
                "summary": (
                    "A mechanical one-period projection based on recent "
                    "observed revenue growth; it is not a guarantee."
                ),
                "horizon": "One period",
                "methodology": (
                    f"Average of {len(recent_growth)} recent observed growth rates."
                ),
                "metrics": [
                    {"label": "Average growth", "value": _percent(average_growth)},
                    {"label": "Projected revenue", "value": _money(projected)},
                ],
                "caveats": ["Uploaded historical patterns may not repeat."],
            },
            {
                "type": "risks",
                "heading": "Observed risks",
                "items": [
                    {
                        "label": "Loss-making periods",
                        "detail": f"{len(losses)} period(s) had negative profit.",
                        "severity": "high" if losses else "low",
                    },
                    {
                        "label": "Revenue declines",
                        "detail": f"{len(declines)} period(s) had negative growth.",
                        "severity": "medium" if declines else "low",
                    },
                ],
            },
            {
                "type": "actions",
                "heading": "Data review plan",
                "items": [
                    {
                        "label": "Review flagged source rows",
                        "detail": "Validate the periods highlighted in the ranking and risk sections.",
                        "priority": "unprioritized",
                    },
                    {
                        "label": "Compare the next upload",
                        "detail": "Use Business Memory to compare observed changes.",
                        "priority": "unprioritized",
                    },
                ],
            },
            {
                "type": "notice",
                "tone": "policy",
                "message": (
                    "Scenarios and forecasts explain uploaded data and stated "
                    "assumptions only; they are not financial recommendations."
                ),
            },
        ],
    }


def _cfo_answer(
    context: dict[str, Any],
    question: str,
    periods: list[dict[str, Any]],
) -> dict[str, Any]:
    response = _comprehensive_answer(context, question, periods)
    metrics = context.get("metrics", {})
    response["sections"].insert(
        1,
        {
            "type": "metrics",
            "heading": "Executive metrics",
            "items": [
                {"label": "Revenue", "value": _money(_number(metrics.get("revenue")))},
                {"label": "Expenses", "value": _money(_number(metrics.get("expenses")))},
                {"label": "Profit", "value": _money(_number(metrics.get("profit")))},
                {
                    "label": "Net margin",
                    "value": _percent(_number(metrics.get("net_margin"))),
                },
                {
                    "label": "Latest ending cash",
                    "value": _money(_number(metrics.get("cash"))),
                    "detail": "Ending balance; not summed across periods.",
                },
            ],
        },
    )
    response["sections"].insert(
        -1,
        {
            "type": "text",
            "heading": "Cash interpretation",
            "markdown": _cash_answer(context),
        },
    )
    action_section = next(
        section
        for section in response["sections"]
        if section["type"] == "actions"
    )
    action_section["heading"] = "30/60/90-day data action plan"
    action_section["items"] = [
        {
            "label": "First 30 days — reconcile",
            "detail": "Validate the lowest-ranked and declining monthly source rows.",
            "priority": "high",
        },
        {
            "label": "By 60 days — compare",
            "detail": "Upload the next period and compare revenue, margin, and ending cash.",
            "priority": "medium",
        },
        {
            "label": "By 90 days — review patterns",
            "detail": "Reassess seasonality, forecast error, and repeated risk flags.",
            "priority": "medium",
        },
    ]
    if PRICING_OR_HIRING.search(question):
        response["sections"].append(
            {
                "type": "notice",
                "tone": "info",
                "heading": "Available-data boundary",
                "message": (
                    "The upload has no unit-price, volume, headcount, payroll, "
                    "or capacity fields. Ledgerly can explain financial patterns "
                    "but cannot quantify pricing or hiring effects without those "
                    "inputs."
                ),
            }
        )
    return response


def deterministic_answer(
    question: str,
    context: dict[str, Any],
) -> str | dict[str, Any] | None:
    metrics = context.get("metrics", {})
    if not metrics:
        return "I could not identify enough structured metrics in the latest upload to answer that confidently."
    periods = _periods(context)
    complex_intents = sum(
        bool(pattern.search(question))
        for pattern in (
            PERIOD_ANALYSIS,
            SCENARIO_ANALYSIS,
            FORECAST_ANALYSIS,
            RISK_ANALYSIS,
        )
    )
    if complex_intents >= 3:
        return _comprehensive_answer(context, question, periods)
    if (
        CFO_ANALYSIS.search(question)
        or ACTION_ANALYSIS.search(question)
        or PRICING_OR_HIRING.search(question)
    ):
        return _cfo_answer(context, question, periods)
    if (
        RECONCILIATION_ANALYSIS.search(question)
        and not PERIOD_ANALYSIS.search(question)
    ):
        return _reconciliation_answer(periods)
    if PERIOD_ANALYSIS.search(question):
        return _best_worst_answer(periods)
    if SEASONALITY_ANALYSIS.search(question):
        return _seasonality_answer(periods)
    if FORECAST_ANALYSIS.search(question):
        return _forecast_answer(periods)
    if SCENARIO_ANALYSIS.search(question):
        return _scenario_answer(context, question)
    if RISK_ANALYSIS.search(question):
        return _risk_answer(periods)
    if CASH_ANALYSIS.search(question):
        return _cash_answer(context)
    if TREND_ANALYSIS.search(question):
        return _trend_answer(periods)
    if MARGIN_ANALYSIS.search(question) and not AGGREGATE_ANALYSIS.search(question):
        return _margin_answer(context, periods)
    if AGGREGATE_ANALYSIS.search(question) or re.search(
        r"\b(revenue|expenses|profit)\b",
        question,
        re.IGNORECASE,
    ):
        return _aggregate_answer(context, periods)
    return None
