"""PDF report export routes."""

from datetime import date, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from io import BytesIO

from app.core.database import get_db
from app.core.config import settings
from app.auth.dependencies import require_admin
from app.models.user import User
from app.models.club_settings import ClubSettings
from app.services.ranking import RankingService
from app.reports.pdf import generate_ranking_pdf

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/ranking/pdf")
def export_ranking_pdf(
    from_date: Optional[date] = Query(default=None, description="Start of period (default: first day of previous month)"),
    to_date: Optional[date] = Query(default=None, description="End of period (default: last day of previous month)"),
    include_inactive: bool = Query(default=False, description="Include inactive players"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Export ranking report as PDF. Requires ADMIN or SYSTEM role.

    Default period is the previous month.
    """
    from datetime import timedelta

    today = date.today()

    # Default to previous month
    if to_date is None:
        first_of_current = today.replace(day=1)
        to_date = first_of_current - timedelta(days=1)
    if from_date is None:
        from_date = date(to_date.year, to_date.month, 1)

    # Generate ranking
    service = RankingService(db)
    ranking = service.generate_ranking(
        from_date=from_date,
        to_date=to_date,
        include_inactive=include_inactive,
    )

    # Get club name from settings
    club_settings = db.query(ClubSettings).first()
    club_name = club_settings.club_name if club_settings else settings.app_name
    logo_path = club_settings.club_logo_path if club_settings else None

    # Generate PDF
    pdf_bytes = generate_ranking_pdf(
        ranking=ranking,
        club_name=club_name,
        logo_path=logo_path,
    )

    filename = f"ranking_{from_date}_{to_date}.pdf"

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )