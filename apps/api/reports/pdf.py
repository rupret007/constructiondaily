from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

from django.conf import settings
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from reports.models import DailyReport


def build_report_pdf(report: DailyReport) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    content = [
        Paragraph(f"Daily Report: {report.project.code}", styles["Title"]),
        Spacer(1, 12),
        Paragraph(f"Date: {report.report_date}", styles["Normal"]),
        Paragraph(f"Location: {report.location}", styles["Normal"]),
        Paragraph(f"Status: {report.status}", styles["Normal"]),
        Paragraph(f"Prepared by: {report.prepared_by.username}", styles["Normal"]),
        Spacer(1, 8),
        Paragraph("Summary", styles["Heading2"]),
        Paragraph(report.summary or "No summary provided.", styles["Normal"]),
        Spacer(1, 8),
        Paragraph("Weather", styles["Heading2"]),
        Paragraph(report.weather_summary or "No weather details provided.", styles["Normal"]),
    ]
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
