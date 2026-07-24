"""PDF report export routes."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
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
from app.services.audit import log_event, get_client_info

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/ranking/pdf")
def export_ranking_pdf(
    request: Request,
    from_date: Optional[date] = Query(default=None),
    to_date: Optional[date] = Query(default=None),
    include_inactive: bool = Query(default=False),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Export ranking report as PDF. Requires ADMIN or SYSTEM role."""
    from datetime import timedelta

    today = date.today()

    if to_date is None:
        first_of_current = today.replace(day=1)
        to_date = first_of_current - timedelta(days=1)
    if from_date is None:
        from_date = date(to_date.year, to_date.month, 1)

    service = RankingService(db)
    ranking = service.generate_ranking(
        from_date=from_date,
        to_date=to_date,
        include_inactive=include_inactive,
    )

    from app.api.routes.ui import _get_club_name
    club_settings = db.query(ClubSettings).first()
    club_name = _get_club_name(db)
    logo_path = club_settings.club_logo_path if club_settings else None

    pdf_bytes = generate_ranking_pdf(
        ranking=ranking,
        club_name=club_name,
        logo_path=logo_path,
        timezone=settings.timezone,
        date_format=settings.date_format,
    )

    ip, ua = get_client_info(request)
    log_event(
        db, action="PDF_EXPORTED", entity_type="report",
        user_id=current_user.id, username=current_user.username,
        new_value={"from_date": str(from_date), "to_date": str(to_date), "include_inactive": include_inactive},
        ip_address=ip, user_agent=ua,
    )

    filename = f"ranking_{from_date}_{to_date}.pdf"

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
