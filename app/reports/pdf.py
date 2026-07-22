"""PDF report generation for ranking exports using ReportLab."""

from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from app.schemas.ranking import RankingResponse


def generate_ranking_pdf(
    ranking: RankingResponse,
    club_name: str = "Dart Club",
    logo_path: str | None = None,
) -> bytes:
    """Generate a PDF ranking report.

    Args:
        ranking: The ranking data to render.
        club_name: Name of the club for the header.
        logo_path: Optional path to club logo image file.

    Returns:
        PDF file content as bytes.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Title"],
        fontSize=20,
        spaceAfter=6 * mm,
        alignment=TA_CENTER,
    )
    subtitle_style = ParagraphStyle(
        "CustomSubtitle",
        parent=styles["Normal"],
        fontSize=12,
        spaceAfter=4 * mm,
        alignment=TA_CENTER,
        textColor=colors.grey,
    )
    info_style = ParagraphStyle(
        "InfoStyle",
        parent=styles["Normal"],
        fontSize=10,
        spaceAfter=2 * mm,
        alignment=TA_LEFT,
        textColor=colors.grey,
    )

    elements = []

    # Logo (if provided)
    if logo_path:
        import os
        if os.path.exists(logo_path):
            try:
                from reportlab.platypus import Image

                img = Image(logo_path, width=30 * mm, height=30 * mm)
                elements.append(img)
                elements.append(Spacer(1, 4 * mm))
            except Exception:
                pass  # Skip logo if file is invalid

    # Title
    elements.append(Paragraph(club_name, title_style))
    elements.append(Paragraph("Elo Ranking Report", subtitle_style))

    # Date range info
    range_text = (
        f"Period: {ranking.from_date.strftime('%d.%m.%Y')} - "
        f"{ranking.to_date.strftime('%d.%m.%Y')}"
    )
    elements.append(Paragraph(range_text, info_style))

    export_text = f"Export Date: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')}"
    elements.append(Paragraph(export_text, info_style))
    elements.append(Spacer(1, 6 * mm))

    # Table header
    header = ["#", "Player", "Elo Rating", "Elo Change", "Pos. Change", "180", "HF", "LD"]

    # Table data
    data = [header]
    for entry in ranking.entries:
        elo_sign = "+" if entry.elo_change >= 0 else ""
        pos_sign = "+" if entry.position_change >= 0 else ""
        hf_count = len(entry.high_finishes) if entry.high_finishes else 0
        ld_count = len(entry.low_darts) if entry.low_darts else 0
        data.append([
            str(entry.position),
            entry.player_name,
            f"{entry.elo_rating:.1f}",
            f"{elo_sign}{entry.elo_change:.1f}",
            f"{pos_sign}{entry.position_change}",
            str(entry.total_180s) if entry.total_180s else "-",
            str(hf_count) if hf_count else "-",
            str(ld_count) if ld_count else "-",
        ])

    # Create table
    col_widths = [18 * mm, 45 * mm, 28 * mm, 28 * mm, 28 * mm, 18 * mm, 18 * mm, 18 * mm]
    table = Table(data, colWidths=col_widths, repeatRows=1)

    # Base style
    style_commands = [
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#206bc4")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        # Body
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("ALIGN", (2, 1), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        # Grid
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#1a5fb4")),
        # Alternating row colors
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
    ]

    # Color rules for Elo Change and Position Change columns
    for i, entry in enumerate(ranking.entries):
        row = i + 1  # +1 for header row

        # Elo Change coloring
        if entry.elo_change > 0:
            style_commands.append(("TEXTCOLOR", (3, row), (3, row), colors.HexColor("#2fb344")))
        elif entry.elo_change < 0:
            style_commands.append(("TEXTCOLOR", (3, row), (3, row), colors.HexColor("#d63939")))

        # Position Change coloring
        if entry.position_change > 0:
            style_commands.append(("TEXTCOLOR", (4, row), (4, row), colors.HexColor("#2fb344")))
        elif entry.position_change < 0:
            style_commands.append(("TEXTCOLOR", (4, row), (4, row), colors.HexColor("#d63939")))

    table.setStyle(TableStyle(style_commands))
    elements.append(table)

    # Footer note
    elements.append(Spacer(1, 8 * mm))
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.grey,
        alignment=TA_CENTER,
    )
    elements.append(Paragraph(
        "Generated by Elo Ranking System",
        footer_style,
    ))

    # Build PDF
    doc.build(elements)
    return buffer.getvalue()
