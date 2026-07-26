from app.business_pulse.engine import calculate_pulse, compare_metrics


def test_pulse_is_explainable_and_bounded():
    result = calculate_pulse({"revenue": 100_000, "expenses": 60_000, "profit": 40_000}, 0.94)
    assert 0 <= result.score <= 100
    assert len(result.factors) == 4
    assert result.metrics["net_margin"] == 40


def test_comparison_calculates_change():
    comparison = compare_metrics({"revenue": 109_300}, {"revenue": 100_000})
    assert comparison is not None
    assert comparison["changes"]["revenue"]["percent_change"] == 9.3
