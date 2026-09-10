"""PDF report generation for ranking exports using ReportLab."""

from datetime import datetime
from io import BytesIO
from typing import Optional
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from app.schemas.ranking import RankingEntry, RankingResponse, status_suffixes


DATE_FORMAT_MAP = {
    "dd/MM/yyyy": "%d/%m/%Y",
    "MM/dd/yyyy": "%m/%d/%Y",
    "yyyy-MM-dd": "%Y-%m-%d",
    "dd.MM.yyyy": "%d.%m.%Y",
}

# Column layout. The widths add up to the A4 usable width (210mm minus the
# two 15mm margins); the old 201mm layout silently clipped the last column.
COLUMN_HEADERS = ["#", "Player", "Elo Rating", "Elo Change", "Pos. Change", "180", "HF", "LD"]
COLUMN_WIDTHS = [16 * mm, 56 * mm, 26 * mm, 23 * mm, 23 * mm, 12 * mm, 12 * mm, 12 * mm]

# The player-name cell contains markup, so it needs a real paragraph style -
# TableStyle FONTNAME/FONTSIZE commands only apply to plain string cells.
_PLAYER_CELL_STYLE = ParagraphStyle(
    "PlayerCell",
    fontName="Helvetica",
    fontSize=9,
    leading=11,
)


def _format_elo_change(change: float) -> str:
    """Format an Elo change with an explicit ``+`` for positive values."""
    sign = "+" if change > 0 else ""
    return f"{sign}{change:.1f}"


def _format_position_change(position_change: Optional[int]) -> str:
    """Format a position change like the dashboard: ``+1``, ``-1`` or ``-``.

    ``None`` (no previous ranking position) and 0 both render as ``-`` so the
    PDF stays consistent with the ranking table.
    """
    if position_change is None or position_change == 0:
        return "-"
    return f"{position_change:+d}"


def _format_count(value: int) -> str:
    """Counts render as ``-`` when zero, matching the dashboard table."""
    return str(value) if value else "-"


def _player_markup(entry: RankingEntry) -> str:
    """ReportLab markup for a player's name cell.

    Mirrors the dashboard ranking table: a disabled name gets a real
    strikethrough, and the ``(inactive)``/``(disabled)`` markers are appended
    in muted grey *outside* the strikethrough.
    """
    name = _xml_escape(entry.player_name)
    if entry.disabled:
        name = f"<strike>{name}</strike>"
    suffixes = status_suffixes(inactive=entry.inactive, disabled=entry.disabled)
    if suffixes:
        name += f' <font color="#6c757d">{_xml_escape(" ".join(suffixes))}</font>'
    return name


def _player_cell(entry: RankingEntry) -> Paragraph:
    """Player-name table cell."""
    return Paragraph(_player_markup(entry), _PLAYER_CELL_STYLE)


def _build_table_data(ranking: RankingResponse) -> list[list]:
    """Table rows (header included); the name column holds a Paragraph."""
    data = [list(COLUMN_HEADERS)]
    for entry in ranking.entries:
        data.append(
            [
                str(entry.position),
                _player_cell(entry),
                f"{entry.elo_rating:.1f}",
                _format_elo_change(entry.elo_change),
                _format_position_change(entry.position_change),
                _format_count(entry.total_180s),
                _format_count(len(entry.high_finishes or [])),
                _format_count(len(entry.low_darts or [])),
            ]
        )
    return data


def _change_color_commands(entries: list[RankingEntry]) -> list:
    """Colour the Elo-change and position-change columns green/red per row."""
    green = colors.HexColor("#2fb344")
    red = colors.HexColor("#d63939")
    commands = []
    for i, entry in enumerate(entries):
        row = i + 1  # +1 for the header row

        if entry.elo_change > 0:
            commands.append(("TEXTCOLOR", (3, row), (3, row), green))
        elif entry.elo_change < 0:
            commands.append(("TEXTCOLOR", (3, row), (3, row), red))

        # None = no previous position; nothing to colour.
        if entry.position_change is not None and entry.position_change > 0:
            commands.append(("TEXTCOLOR", (4, row), (4, row), green))
        elif entry.position_change is not None and entry.position_change < 0:
            commands.append(("TEXTCOLOR", (4, row), (4, row), red))
    return commands


def _base_table_style() -> list:
    """Base TableStyle commands shared by header, body and grid."""
    return [
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#206bc4")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        # Body (applies to plain string cells; the player column styles itself)
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


def _format_date(d, date_format: str = "dd/MM/yyyy") -> str:
    """Format a date object using the configured display format."""
    fmt = DATE_FORMAT_MAP.get(date_format, "%d/%m/%Y")
    return d.strftime(fmt)


def _format_datetime(dt, date_format: str = "dd/MM/yyyy", tz_name: str = "") -> str:
    """Format a datetime object using the configured display format."""
    fmt = DATE_FORMAT_MAP.get(date_format, "%d/%m/%Y")
    tz_str = f" {tz_name}" if tz_name else ""
    return dt.strftime(f"{fmt} %H:%M:%S") + tz_str


def generate_ranking_pdf(
    ranking: RankingResponse,
    club_name: str = "Dart Club",
    logo_path: str | None = None,
    timezone: str = "UTC",
    date_format: str = "dd/MM/yyyy",
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

    # Logo (if provided) - always use light mode logo, max 500x500 preserving aspect ratio
    if logo_path:
        import os

        if os.path.exists(logo_path):
            try:
                from reportlab.platypus import Image as RLImage
                from PIL import Image as PILImage

                with PILImage.open(logo_path) as pil_img:
                    orig_w, orig_h = pil_img.size

                max_size = 50 * mm
                if orig_w > 0 and orig_h > 0:
                    ratio = min(max_size / orig_w, max_size / orig_h)
                    img_w = orig_w * ratio
                    img_h = orig_h * ratio
                else:
                    img_w = img_h = 30 * mm

                img = RLImage(logo_path, width=img_w, height=img_h)
                elements.append(img)
                elements.append(Spacer(1, 4 * mm))
            except Exception:
                pass  # Skip logo if file is invalid

    # Title
    elements.append(Paragraph(club_name, title_style))
    elements.append(Paragraph("Elo Ranking Report", subtitle_style))

    # Date range info
    range_text = (
        f"Period: {_format_date(ranking.from_date, date_format)} - "
        f"{_format_date(ranking.to_date, date_format)}"
    )
    elements.append(Paragraph(range_text, info_style))

    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(timezone)
        now = datetime.now(tz)
    except (ImportError, KeyError, OSError):
        now = datetime.utcnow()
        timezone = "UTC"
    export_text = f"Export Date: {_format_datetime(now, date_format, timezone)}"
    elements.append(Paragraph(export_text, info_style))
    elements.append(Spacer(1, 6 * mm))

    # Ranking table
    table = Table(_build_table_data(ranking), colWidths=COLUMN_WIDTHS, repeatRows=1)
    style_commands = _base_table_style()
    style_commands += _change_color_commands(ranking.entries)
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
    elements.append(
        Paragraph(
            "Generated by Elo Ranking System",
            footer_style,
        )
    )

    # Build PDF
    doc.build(elements)
    return buffer.getvalue()
