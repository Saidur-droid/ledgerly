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
