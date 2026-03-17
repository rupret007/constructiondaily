"""Generate takeoff summary PDF for preconstruction plan sets."""

from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import PlanSet


def _escape(s: str) -> str:
    return xml_escape(s) if s else ""


def build_takeoff_pdf(plan_set: PlanSet, snapshot_payload: dict) -> bytes:
    """
    Build a PDF containing plan set name, capture time, and a table of all takeoff rows
    (sheet, category, unit, quantity). Uses letter size and reportlab.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=0.75 * inch, leftMargin=0.75 * inch)
    styles = getSampleStyleSheet()

    plan_set_name = _escape(snapshot_payload.get("plan_set_name") or plan_set.name or "Plan set")
    captured_at = snapshot_payload.get("captured_at") or ""
    content = [
        Paragraph(f"Takeoff summary: {plan_set_name}", styles["Title"]),
        Spacer(1, 12),
        Paragraph(f"Captured: {_escape(captured_at[:19]) if captured_at else '—'}", styles["Normal"]),
        Spacer(1, 16),
    ]

    rows = [["Sheet", "Category", "Unit", "Quantity"]]
    for sheet_data in snapshot_payload.get("sheets", []):
        sheet_title = sheet_data.get("title") or sheet_data.get("sheet_number") or sheet_data.get("id", "")[:8]
        for t in sheet_data.get("takeoff_items", []):
            rows.append([
                _escape(str(sheet_title)),
                _escape(t.get("category", "")),
                _escape(t.get("unit", "")),
                _escape(str(t.get("quantity", ""))),
            ])
    for t in snapshot_payload.get("plan_set_level_takeoff", []):
        rows.append([
            "(plan set)",
            _escape(t.get("category", "")),
            _escape(t.get("unit", "")),
            _escape(str(t.get("quantity", ""))),
        ])

    if len(rows) > 1:
        table = Table(rows, colWidths=[1.5 * inch, 1.5 * inch, 1.2 * inch, 1.2 * inch])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), (0.85, 0.85, 0.85)),
            ("TEXTCOLOR", (0, 0), (-1, 0), (0, 0, 0)),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("ALIGN", (3, 0), (3, -1), "RIGHT"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, (0.7, 0.7, 0.7)),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
        ]))
        content.append(table)
    else:
        content.append(Paragraph("No takeoff items in this snapshot.", styles["Normal"]))

    doc.build(content)
    return buffer.getvalue()
