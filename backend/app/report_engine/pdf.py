from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def build_pulse_report(company_name: str, pulse: dict) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, rightMargin=20 * mm, leftMargin=20 * mm, topMargin=18 * mm)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("LEDGERLY", styles["Heading3"]),
        Paragraph("Your business speaks.", styles["Title"]),
        Spacer(1, 8 * mm),
        Paragraph(company_name, styles["Heading2"]),
        Paragraph(f"Business Pulse™: {pulse['score']}/100", styles["Heading1"]),
        Paragraph(pulse["summary"], styles["BodyText"]),
        Spacer(1, 7 * mm),
    ]
    rows = [["Metric", "Value"]] + [[key.replace("_", " ").title(), f"{value:,.2f}"] for key, value in pulse["metrics"].items()]
    table = Table(rows, colWidths=[90 * mm, 60 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7357FF")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#E8E4F0")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    story.extend([table, Spacer(1, 8 * mm), Paragraph("This report explains uploaded business data only. It is not financial advice.", styles["Italic"])])
    document.build(story)
    return output.getvalue()
