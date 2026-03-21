from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from reports.models import DailyReport


def _escape_paragraph(s: str) -> str:
    """Escape XML special chars so ReportLab Paragraph does not interpret tags."""
    if s is None:
        return ""
    return xml_escape(str(s))


def build_report_pdf(report: DailyReport) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=20,
        textColor=colors.HexColor("#1e3a8a"),  # Deep blue
        spaceAfter=12,
        fontName="Helvetica-Bold",
    )
    section_style = ParagraphStyle(
        "SectionHeader",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=colors.HexColor("#1e3a8a"),
        borderPadding=2,
        spaceBefore=15,
        spaceAfter=10,
        fontName="Helvetica-Bold",
    )
    label_style = ParagraphStyle(
        "Label",
        parent=styles["Normal"],
        fontSize=10,
        fontName="Helvetica-Bold",
        textColor=colors.gray,
    )
    value_style = ParagraphStyle(
        "Value",
        parent=styles["Normal"],
        fontSize=10,
        fontName="Helvetica",
    )

    content = []

    # Header / Branding
    header_data = [
        [
            Paragraph(f"DAILY REPORT: {_escape_paragraph(report.project.name)}", title_style),
            Paragraph(f"<b>PROJECT:</b> {_escape_paragraph(report.project.code)}", value_style),
        ]
    ]
    header_table = Table(header_data, colWidths=[4.5 * inch, 2.5 * inch])
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ]
        )
    )
    content.append(header_table)
    content.append(Spacer(1, 0.2 * inch))

    # Info Grid
    info_data = [
        [Paragraph("DATE", label_style), Paragraph("LOCATION", label_style), Paragraph("PREPARED BY", label_style)],
        [
            Paragraph(str(report.report_date), value_style),
            Paragraph(_escape_paragraph(report.location), value_style),
            Paragraph(_escape_paragraph(report.prepared_by.get_full_name() or report.prepared_by.username), value_style),
        ],
        [Paragraph("STATUS", label_style), Paragraph("REVISION", label_style), ""],
        [Paragraph(report.status.upper(), value_style), Paragraph(str(report.revision), value_style), ""],
    ]
    info_table = Table(info_data, colWidths=[2.3 * inch] * 3)
    info_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
                ("TOPPADDING", (0, 1), (-1, 1), 0),
                ("BOTTOMPADDING", (0, 2), (-1, 2), 0),
                ("TOPPADDING", (0, 3), (-1, 3), 0),
            ]
        )
    )
    content.append(info_table)
    content.append(Spacer(1, 0.2 * inch))

    # Summary Section
    content.append(Paragraph("EXECUTIVE SUMMARY", section_style))
    content.append(Paragraph(_escape_paragraph(report.summary or "No summary provided."), value_style))

    # Weather Table
    content.append(Paragraph("WEATHER CONDITIONS", section_style))
    weather_data = [
        [Paragraph("CONDITION", label_style), Paragraph("HIGH", label_style), Paragraph("LOW", label_style), Paragraph("WIND", label_style)],
        [
            Paragraph(_escape_paragraph(report.weather_summary or "N/A"), value_style),
            Paragraph(f"{report.temperature_high_c}°C" if report.temperature_high_c is not None else "N/A", value_style),
            Paragraph(f"{report.temperature_low_c}°C" if report.temperature_low_c is not None else "N/A", value_style),
            Paragraph(f"{report.wind_max_kph} kph" if report.wind_max_kph is not None else "N/A", value_style),
        ],
    ]
    weather_table = Table(weather_data, colWidths=[3 * inch, 1.3 * inch, 1.3 * inch, 1.4 * inch])
    weather_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    content.append(weather_table)

    # Labor Entries
    labor_entries = report.laborentry_set.all()
    if labor_entries.exists():
        content.append(Paragraph("LABOR FORCE", section_style))
        labor_data = [
            [
                Paragraph("TRADE", label_style),
                Paragraph("COMPANY", label_style),
                Paragraph("WORKERS", label_style),
                Paragraph("HOURS", label_style),
            ]
        ]
        for entry in labor_entries:
            labor_data.append(
                [
                    Paragraph(_escape_paragraph(entry.trade), value_style),
                    Paragraph(_escape_paragraph(entry.company), value_style),
                    Paragraph(str(entry.workers), value_style),
                    Paragraph(str(entry.regular_hours + entry.overtime_hours), value_style),
                ]
            )
        labor_table = Table(labor_data, colWidths=[2 * inch, 2.5 * inch, 1.25 * inch, 1.25 * inch])
        labor_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        content.append(labor_table)

    # Equipment Entries
    equipment_entries = report.equipmententry_set.all()
    if equipment_entries.exists():
        content.append(Paragraph("EQUIPMENT ON SITE", section_style))
        equip_data = [
            [
                Paragraph("EQUIPMENT", label_style),
                Paragraph("QUANTITY", label_style),
                Paragraph("HOURS USED", label_style),
                Paragraph("DOWNTIME", label_style),
            ]
        ]
        for entry in equipment_entries:
            equip_data.append(
                [
                    Paragraph(_escape_paragraph(entry.equipment_name), value_style),
                    Paragraph(str(entry.quantity), value_style),
                    Paragraph(str(entry.hours_used), value_style),
                    Paragraph(str(entry.downtime_hours), value_style),
                ]
            )
        equip_table = Table(equip_data, colWidths=[3 * inch, 1.25 * inch, 1.25 * inch, 1.5 * inch])
        equip_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        content.append(equip_table)

    doc.build(content)
    return buffer.getvalue()


def save_report_snapshot(report: DailyReport) -> tuple[str, str]:
    pdf_bytes = build_report_pdf(report)
    base_dir = Path(settings.MEDIA_ROOT) / "snapshots"
    base_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"report-{report.id}-rev-{report.revision}.pdf"
    file_path = base_dir / file_name
    file_path.write_bytes(pdf_bytes)
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    relative_path = str(file_path.relative_to(settings.MEDIA_ROOT))
    return relative_path, digest
