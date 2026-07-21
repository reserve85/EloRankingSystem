"""Tests for PDF ranking report export."""

from datetime import date

import pytest

from app.models.player import Player
from app.models.user import User, UserRole
from app.auth.password import hash_password
from app.reports.pdf import generate_ranking_pdf
from app.schemas.ranking import RankingEntry, RankingResponse


def _login_as(client, db_session, username, password, role):
    """Create a user and log in."""
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    client.post("/auth/login", data={"username": username, "password": password})
    return user


def _create_player(db_session, name="Player", elo=1200):
    player = Player(
        name=name, start_elo=elo, current_elo=float(elo),
        active=True, disabled=False,
    )
    db_session.add(player)
    db_session.commit()
    db_session.refresh(player)
    return player


def _create_match(client, pa_id, pb_id, winner_id, match_date):
    score_a = 3 if winner_id == pa_id else 0
    score_b = 3 if winner_id == pb_id else 0
    return client.post("/matches/", json={
        "date": match_date, "player_a_id": pa_id,
        "player_b_id": pb_id, "player1_score": score_a, "player2_score": score_b,
    })


# ── PDF Generation Unit Tests ──────────────────────────────────────────


class TestPdfGeneration:
    """Tests for PDF generation function."""

    def test_generate_pdf_returns_bytes(self):
        """generate_ranking_pdf should return bytes."""
        ranking = RankingResponse(
            from_date=date(2025, 6, 1),
            to_date=date(2025, 6, 30),
            entries=[],
            generated_at=__import__("datetime").datetime(2025, 7, 1, tzinfo=__import__("datetime").timezone.utc),
        )
        pdf = generate_ranking_pdf(ranking, club_name="Test Club")
        assert isinstance(pdf, bytes)
        assert len(pdf) > 0
        assert pdf[:4] == b"%PDF"  # PDF magic bytes

    def test_generate_pdf_with_entries(self):
        """PDF should be generated with ranking entries."""
        ranking = RankingResponse(
            from_date=date(2025, 6, 1),
            to_date=date(2025, 6, 30),
            entries=[
                RankingEntry(
                    player_id=1, player_name="Alice", position=1,
                    elo_rating=1216.0, elo_change=16.0, position_change=0,
                ),
                RankingEntry(
                    player_id=2, player_name="Bob", position=2,
                    elo_rating=1184.0, elo_change=-16.0, position_change=0,
                ),
            ],
            generated_at=__import__("datetime").datetime(2025, 7, 1, tzinfo=__import__("datetime").timezone.utc),
        )
        pdf = generate_ranking_pdf(ranking, club_name="Dart Club")
        assert pdf[:4] == b"%PDF"
        assert len(pdf) > 500  # Non-trivial PDF

    def test_generate_pdf_contains_entries(self):
        """PDF should be larger when it has entries than when empty."""
        from datetime import datetime as dt, timezone
        empty_ranking = RankingResponse(
            from_date=date(2025, 6, 1),
            to_date=date(2025, 6, 30),
            entries=[],
            generated_at=dt(2025, 7, 1, tzinfo=timezone.utc),
        )
        empty_pdf = generate_ranking_pdf(empty_ranking, club_name="MyClub")

        ranking = RankingResponse(
            from_date=date(2025, 6, 1),
            to_date=date(2025, 6, 30),
            entries=[
                RankingEntry(
                    player_id=1, player_name="TestPlayer", position=1,
                    elo_rating=1200.0, elo_change=0.0, position_change=0,
                ),
            ],
            generated_at=dt(2025, 7, 1, tzinfo=timezone.utc),
        )
        pdf = generate_ranking_pdf(ranking, club_name="MyClub")
        assert len(pdf) > len(empty_pdf)  # More data = larger PDF

    def test_generate_pdf_color_rules(self):
        """PDF should handle positive, negative, and zero changes."""
        ranking = RankingResponse(
            from_date=date(2025, 6, 1),
            to_date=date(2025, 6, 30),
            entries=[
                RankingEntry(
                    player_id=1, player_name="Winner", position=1,
                    elo_rating=1216.0, elo_change=16.0, position_change=1,
                ),
                RankingEntry(
                    player_id=2, player_name="Loser", position=2,
                    elo_rating=1184.0, elo_change=-16.0, position_change=-1,
                ),
                RankingEntry(
                    player_id=3, player_name="Stable", position=3,
                    elo_rating=1200.0, elo_change=0.0, position_change=0,
                ),
            ],
            generated_at=__import__("datetime").datetime(2025, 7, 1, tzinfo=__import__("datetime").timezone.utc),
        )
        pdf = generate_ranking_pdf(ranking)
        assert pdf[:4] == b"%PDF"

    def test_generate_pdf_empty_ranking(self):
        """PDF should handle empty ranking gracefully."""
        ranking = RankingResponse(
            from_date=date(2025, 6, 1),
            to_date=date(2025, 6, 30),
            entries=[],
            generated_at=__import__("datetime").datetime(2025, 7, 1, tzinfo=__import__("datetime").timezone.utc),
        )
        pdf = generate_ranking_pdf(ranking, club_name="Empty Club")
        assert pdf[:4] == b"%PDF"

    def test_generate_pdf_date_range_in_header(self):
        """PDF should be generated successfully with date range."""
        from datetime import datetime as dt, timezone
        ranking = RankingResponse(
            from_date=date(2025, 3, 1),
            to_date=date(2025, 3, 31),
            entries=[],
            generated_at=dt(2025, 4, 1, tzinfo=timezone.utc),
        )
        pdf = generate_ranking_pdf(ranking, club_name="DateRangeClub")
        assert pdf[:4] == b"%PDF"
        assert len(pdf) > 200  # Non-trivial PDF with date info

    def test_generate_pdf_with_logo_path_missing(self):
        """PDF should generate even if logo path doesn't exist."""
        ranking = RankingResponse(
            from_date=date(2025, 6, 1),
            to_date=date(2025, 6, 30),
            entries=[],
            generated_at=__import__("datetime").datetime(2025, 7, 1, tzinfo=__import__("datetime").timezone.utc),
        )
        pdf = generate_ranking_pdf(ranking, logo_path="/nonexistent/logo.png")
        assert pdf[:4] == b"%PDF"


# ── PDF Export Route Tests ─────────────────────────────────────────────


class TestPdfExportRoute:
    """Tests for PDF export API endpoint."""

    def test_admin_can_export_pdf(self, client, db_session):
        """ADMIN should be able to export PDF."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        _create_player(db_session, "Alice", elo=1200)

        resp = client.get("/reports/ranking/pdf?from_date=2025-06-01&to_date=2025-06-30")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content[:4] == b"%PDF"

    def test_system_can_export_pdf(self, client, db_session):
        """SYSTEM should be able to export PDF."""
        _login_as(client, db_session, "sys", "pass", UserRole.SYSTEM)

        resp = client.get("/reports/ranking/pdf?from_date=2025-06-01&to_date=2025-06-30")
        assert resp.status_code == 200
        assert resp.content[:4] == b"%PDF"

    def test_user_cannot_export_pdf(self, client, db_session):
        """USER should NOT be able to export PDF (403)."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)

        resp = client.get("/reports/ranking/pdf?from_date=2025-06-01&to_date=2025-06-30")
        assert resp.status_code == 403

    def test_unauthenticated_cannot_export_pdf(self, client, db_session):
        """Unauthenticated request should return 401."""
        resp = client.get("/reports/ranking/pdf?from_date=2025-06-01&to_date=2025-06-30")
        assert resp.status_code == 401

    def test_pdf_with_matches(self, client, db_session):
        """PDF should be generated with match data."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)
        _create_match(client, pa.id, pb.id, pa.id, "2025-06-15")

        resp = client.get("/reports/ranking/pdf?from_date=2025-06-01&to_date=2025-06-30")
        assert resp.status_code == 200
        assert resp.content[:4] == b"%PDF"
        assert len(resp.content) > 500

    def test_pdf_content_disposition(self, client, db_session):
        """PDF response should have correct content disposition."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp = client.get("/reports/ranking/pdf?from_date=2025-06-01&to_date=2025-06-30")
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert "ranking_2025-06-01_2025-06-30.pdf" in resp.headers.get("content-disposition", "")

    def test_pdf_default_period(self, client, db_session):
        """PDF should use previous month as default period."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp = client.get("/reports/ranking/pdf")
        assert resp.status_code == 200
        assert resp.content[:4] == b"%PDF"

    def test_pdf_with_include_inactive(self, client, db_session):
        """PDF should work with include_inactive flag."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        _create_player(db_session, "Inactive", elo=1200)

        resp = client.get("/reports/ranking/pdf?from_date=2025-06-01&to_date=2025-06-30&include_inactive=true")
        assert resp.status_code == 200
        assert resp.content[:4] == b"%PDF"

    def test_pdf_is_valid(self, client, db_session):
        """PDF response should be a valid PDF file."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp = client.get("/reports/ranking/pdf?from_date=2025-06-01&to_date=2025-06-30")
        assert resp.content[:4] == b"%PDF"
        assert b"%%EOF" in resp.content  # Valid PDF structure
