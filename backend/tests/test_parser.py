from app.business_engine.parser import parse_business_file


def test_csv_parser_detects_core_metrics():
    content = b"month,revenue,expenses\nJan,1000,700\nFeb,1200,800\n"
    result = parse_business_file("business.csv", content)
    assert result.metrics["revenue"] == 2200
    assert result.metrics["expenses"] == 1500
    assert result.metrics["profit"] == 700
    assert result.confidence > 0.7


def test_rejects_unsupported_format():
    try:
        parse_business_file("notes.txt", b"hello")
    except ValueError as error:
        assert "Unsupported" in str(error)
    else:
        raise AssertionError("Expected unsupported format to fail")


def test_invalid_numeric_and_date_values_do_not_invent_metrics():
    content = (
        b"date,revenue,expenses\n"
        b"not-a-date,not-a-number,300\n"
        b"2026-02-28,1200,invalid\n"
    )
    result = parse_business_file("business.csv", content)

    assert result.metrics["revenue"] == 1200
    assert result.metrics["expenses"] == 300
    assert result.metrics["profit"] == 900
    assert result.records[0]["date"] == "not-a-date"
