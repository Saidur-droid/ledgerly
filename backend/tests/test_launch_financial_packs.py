from io import BytesIO

from openpyxl import Workbook
from reportlab.pdfgen.canvas import Canvas

from app.business_engine.parser import parse_business_file


def test_retail_and_service_expected_totals_are_independently_asserted():
    retail=b"date,revenue,expenses,cash\n2026-01-31,12000,9000,4000\n2026-02-28,15000,11000,6500\n"
    service=b"date,revenue,expenses,cash\n2026-01-31,8000,2500,9000\n2026-02-28,10000,3000,14000\n"
    parsed_retail=parse_business_file("retail.csv",retail)
    parsed_service=parse_business_file("service.csv",service)
    assert parsed_retail.metrics=={"revenue":27000.0,"expenses":20000.0,"profit":7000.0,"cash":6500.0}
    assert parsed_service.metrics=={"revenue":18000.0,"expenses":5500.0,"profit":12500.0,"cash":14000.0}
    assert parsed_retail.records[1]["revenue_growth"]==25.0


def test_messy_csv_preserves_original_values_and_flags_missing_cogs():
    data=b'date,gross sales,expenses,cash balance,currency\n2026-01-31,"10,000","3,250","6,750",USD\nwrong-date,-500,100,6150,EUR\n'
    parsed=parse_business_file("messy.csv",data)
    assert parsed.metrics["revenue"]==9500.0
    assert parsed.metrics["expenses"]==3350.0
    assert parsed.metrics["profit"]==6150.0
    assert parsed.records[0]["gross sales"]=="10,000"
    assert "cogs" not in parsed.columns


def test_multi_sheet_xlsx_uses_first_sheet_explicitly_without_double_counting():
    workbook=Workbook(); first=workbook.active; first.title="P&L"; first.append(["date","revenue","expenses","cash"]); first.append(["2026-01-31",1000,400,600])
    second=workbook.create_sheet("Bank"); second.append(["date","revenue","expenses","cash"]); second.append(["2026-01-31",999999,0,999999])
    output=BytesIO(); workbook.save(output)
    parsed=parse_business_file("multi.xlsx",output.getvalue())
    assert parsed.metrics=={"revenue":1000.0,"expenses":400.0,"profit":600.0,"cash":600.0}
    assert parsed.metadata["source_location"]=="P&L"


def test_text_pdf_bank_statement_extracts_declared_balances():
    output=BytesIO(); canvas=Canvas(output); canvas.drawString(72,750,"Bank statement"); canvas.drawString(72,730,"Revenue: 12,500.00"); canvas.drawString(72,710,"Expenses: 7,250.00"); canvas.drawString(72,690,"Cash balance: 5,250.00"); canvas.save()
    parsed=parse_business_file("statement.pdf",output.getvalue())
    assert parsed.metrics=={"revenue":12500.0,"expenses":7250.0,"profit":5250.0,"cash":5250.0}
    assert parsed.metadata["source_location"]=="PDF document"
