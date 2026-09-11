"""Tests for PDF ranking report export."""

import base64
import zlib
from datetime import date, datetime, timezone


from app.models.player import Player
from app.models.user import User, UserRole
from app.auth.password import hash_password
from app.reports.pdf import generate_ranking_pdf
from app.schemas.ranking import RankingEntry, RankingResponse, status_suffixes


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
        name=name,
        start_elo=elo,
        current_elo=float(elo),
        active=True,
        disabled=False,
        # Fix #2: entry date (creation date) before the 2025-06 PDF windows.
        created_at=datetime(2025, 5, 1, 12, 0, 0),
    )
    db_session.add(player)
    db_session.commit()
    db_session.refresh(player)
    return player


def _create_match(client, pa_id, pb_id, winner_id, match_date):
    score_a = 3 if winner_id == pa_id else 0
    score_b = 3 if winner_id == pb_id else 0
    return client.post(
        "/matches/",
        json={
            "date": match_date,
            "player_a_id": pa_id,
            "player_b_id": pb_id,
            "player1_score": score_a,
            "player2_score": score_b,
        },
    )


# ── PDF Generation Unit Tests ──────────────────────────────────────────


class TestPdfGeneration:
    """Tests for PDF generation function."""

    def test_generate_pdf_returns_bytes(self):
        """generate_ranking_pdf should return bytes."""
        ranking = RankingResponse(
            from_date=date(2025, 6, 1),
            to_date=date(2025, 6, 30),
            entries=[],
            generated_at=__import__("datetime").datetime(
                2025, 7, 1, tzinfo=__import__("datetime").timezone.utc
            ),
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
                    player_id=1,
                    player_name="Alice",
                    position=1,
                    elo_rating=1216.0,
                    elo_change=16.0,
                    position_change=0,
                ),
                RankingEntry(
                    player_id=2,
                    player_name="Bob",
                    position=2,
                    elo_rating=1184.0,
                    elo_change=-16.0,
                    position_change=0,
                ),
            ],
            generated_at=__import__("datetime").datetime(
                2025, 7, 1, tzinfo=__import__("datetime").timezone.utc
            ),
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
                    player_id=1,
                    player_name="TestPlayer",
                    position=1,
                    elo_rating=1200.0,
                    elo_change=0.0,
                    position_change=0,
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
                    player_id=1,
                    player_name="Winner",
                    position=1,
                    elo_rating=1216.0,
                    elo_change=16.0,
                    position_change=1,
                ),
                RankingEntry(
                    player_id=2,
                    player_name="Loser",
                    position=2,
                    elo_rating=1184.0,
                    elo_change=-16.0,
                    position_change=-1,
                ),
                RankingEntry(
                    player_id=3,
                    player_name="Stable",
                    position=3,
                    elo_rating=1200.0,
                    elo_change=0.0,
                    position_change=0,
                ),
            ],
            generated_at=__import__("datetime").datetime(
                2025, 7, 1, tzinfo=__import__("datetime").timezone.utc
            ),
        )
        pdf = generate_ranking_pdf(ranking)
        assert pdf[:4] == b"%PDF"
        assert len(pdf) > 500

    def test_generate_pdf_missing_position_change(self):
        """PDF should render a missing position change (None) as '-' (Fix #1)."""
        ranking = RankingResponse(
            from_date=date(2025, 6, 1),
            to_date=date(2025, 6, 30),
            entries=[
                RankingEntry(
                    player_id=1,
                    player_name="Newbie",
                    position=1,
                    elo_rating=1500.0,
                    elo_change=0.0,
                    position_change=None,
                )
            ],
            generated_at=__import__("datetime").datetime(
                2025, 7, 1, tzinfo=__import__("datetime").timezone.utc
            ),
        )
        pdf = generate_ranking_pdf(ranking)
        assert pdf[:4] == b"%PDF"
        assert len(pdf) > 500

    def test_generate_pdf_empty_ranking(self):
        """PDF should handle empty ranking gracefully."""
        ranking = RankingResponse(
            from_date=date(2025, 6, 1),
            to_date=date(2025, 6, 30),
            entries=[],
            generated_at=__import__("datetime").datetime(
                2025, 7, 1, tzinfo=__import__("datetime").timezone.utc
            ),
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
            generated_at=__import__("datetime").datetime(
                2025, 7, 1, tzinfo=__import__("datetime").timezone.utc
            ),
        )
        pdf = generate_ranking_pdf(ranking, logo_path="/nonexistent/logo.png")
        assert pdf[:4] == b"%PDF"


def _entry(name="Alice", *, disabled=False, inactive=False):
    """RankingEntry stub for rendering tests."""
    return RankingEntry(
        player_id=1,
        player_name=name,
        position=1,
        elo_rating=1200.0,
        elo_change=0.0,
        position_change=0,
        disabled=disabled,
        inactive=inactive,
    )


def _extract_pdf_text(pdf_bytes: bytes) -> bytes:
    """Return the decompressed page content of a generated PDF.

    ReportLab writes page content ASCII85 + Flate compressed (and without a
    newline before ``endstream``), so names and status markers cannot be
    looked up in the raw PDF bytes.
    """
    parts = []
    idx = 0
    while True:
        start = pdf_bytes.find(b"stream", idx)
        if start < 0:
            break
        end = pdf_bytes.find(b"endstream", start)
        if end < 0:
            break
        blob = pdf_bytes[start + len(b"stream") : end].strip(b"\r\n")
        for decode in (
            lambda b: zlib.decompress(base64.a85decode(b, adobe=False)),
            lambda b: zlib.decompress(base64.a85decode(b, adobe=True)),
            lambda b: zlib.decompress(b),
            lambda b: b,
        ):
            try:
                parts.append(decode(blob))
                break
            except Exception:
                continue
        idx = end + len(b"endstream")
    return b"\n".join(parts)


class TestRankingEntryDisplayName:
    """Ranking entries expose the table's display name (single source)."""

    def test_display_name_plain(self):
        assert _entry().display_name == "Alice"

    def test_display_name_inactive(self):
        assert _entry(inactive=True).display_name == "Alice (inactive)"

    def test_display_name_disabled(self):
        assert _entry(disabled=True).display_name == "Alice (disabled)"

    def test_display_name_both_in_table_order(self):
        assert _entry(inactive=True, disabled=True).display_name == "Alice (inactive) (disabled)"

    def test_status_suffixes_order(self):
        assert status_suffixes(inactive=True, disabled=True) == ("(inactive)", "(disabled)")
        assert status_suffixes(inactive=False, disabled=False) == ()
        assert status_suffixes(inactive=True, disabled=False) == ("(inactive)",)
        assert status_suffixes(inactive=False, disabled=True) == ("(disabled)",)


class TestPdfPlayerNaming:
    """PDF player names match the ranking table: suffix + strikethrough."""

    def _ranking(self, *entries):
        return RankingResponse(
            from_date=date(2025, 6, 1),
            to_date=date(2025, 6, 30),
            entries=list(entries),
            generated_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
        )

    def test_pdf_plain_name_has_no_suffix(self):
        pdf = generate_ranking_pdf(self._ranking(_entry()), club_name="Club")
        text = _extract_pdf_text(pdf)
        assert b"Alice" in text
        assert b"inactive" not in text
        assert b"disabled" not in text

    def test_pdf_shows_inactive_suffix(self):
        pdf = generate_ranking_pdf(self._ranking(_entry("Ina", inactive=True)), club_name="Club")
        text = _extract_pdf_text(pdf)
        assert b"Ina" in text
        assert b"inactive" in text

    def test_pdf_shows_disabled_suffix(self):
        pdf = generate_ranking_pdf(self._ranking(_entry("Dis", disabled=True)), club_name="Club")
        text = _extract_pdf_text(pdf)
        assert b"Dis" in text
        assert b"disabled" in text

    def test_pdf_shows_both_suffixes(self):
        pdf = generate_ranking_pdf(
            self._ranking(_entry("Al", inactive=True, disabled=True)),
            club_name="Club",
        )
        text = _extract_pdf_text(pdf)
        assert b"Al" in text
        assert b"inactive" in text
        assert b"disabled" in text

    def test_player_markup_strikes_name_only(self):
        from app.reports.pdf import _player_markup

        markup = _player_markup(_entry("Alice", disabled=True, inactive=True))
        # The name is struck through; the markers stay outside the strike.
        assert "<strike>Alice</strike>" in markup
        assert "(inactive) (disabled)" in markup
        assert markup.index("</strike>") < markup.index("(inactive)")

    def test_player_markup_plain_name_not_struck(self):
        from app.reports.pdf import _player_markup

        assert _player_markup(_entry("Alice")) == "Alice"

    def test_player_markup_escapes_name(self):
        from app.reports.pdf import _player_markup

        markup = _player_markup(_entry("Tim & Co <3>", disabled=True))
        assert "<strike>Tim &amp; Co &lt;3&gt;</strike>" in markup


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

    def test_inverted_date_range_rejected(self, client, db_session):
        """PDF export returns 422 for an inverted date range (review #3)."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        resp = client.get("/reports/ranking/pdf?from_date=2025-06-30&to_date=2025-06-01")
        assert resp.status_code == 422

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

        resp = client.get(
            "/reports/ranking/pdf?from_date=2025-06-01&to_date=2025-06-30&include_inactive=true"
        )
        assert resp.status_code == 200
        assert resp.content[:4] == b"%PDF"

    def test_pdf_shows_status_markers_like_ranking_table(self, client, db_session):
        """Disabled players in the PDF carry (inactive)/(disabled) markers."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        player = _create_player(db_session, "Rita", elo=1200)
        player.disabled = True
        db_session.commit()

        resp = client.get(
            "/reports/ranking/pdf?from_date=2025-06-01&to_date=2025-06-30&include_inactive=true"
        )
        assert resp.status_code == 200
        text = _extract_pdf_text(resp.content)
        assert b"Rita" in text
        assert b"disabled" in text
        assert b"inactive" in text

    def test_pdf_is_valid(self, client, db_session):
        """PDF response should be a valid PDF file."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp = client.get("/reports/ranking/pdf?from_date=2025-06-01&to_date=2025-06-30")
        assert resp.content[:4] == b"%PDF"
        assert b"%%EOF" in resp.content  # Valid PDF structure


class TestPdfDateFormat:
    """Tests for Task 5: PDF date format and timezone."""

    def test_pdf_uses_configured_date_format(self):
        """PDF should use the configured date format in period text."""
        from app.reports.pdf import _format_date

        d = date(2025, 7, 15)
        assert _format_date(d, "dd/MM/yyyy") == "15/07/2025"
        assert _format_date(d, "MM/dd/yyyy") == "07/15/2025"
        assert _format_date(d, "yyyy-MM-dd") == "2025-07-15"
        assert _format_date(d, "dd.MM.yyyy") == "15.07.2025"

    def test_pdf_format_date_default_format(self):
        """_format_date should default to dd/MM/yyyy."""
        from app.reports.pdf import _format_date

        d = date(2025, 1, 5)
        assert _format_date(d) == "05/01/2025"

    def test_pdf_uses_custom_club_name(self):
        """PDF should be generated with custom club name."""
        ranking = RankingResponse(
            from_date=date(2025, 6, 1),
            to_date=date(2025, 6, 30),
            entries=[],
            generated_at=__import__("datetime").datetime(
                2025, 7, 1, tzinfo=__import__("datetime").timezone.utc
            ),
        )
        pdf = generate_ranking_pdf(ranking, club_name="My Custom Club")
        assert pdf[:4] == b"%PDF"
        assert len(pdf) > 200  # Valid PDF was generated

    def test_pdf_different_club_names_produce_different_pdfs(self):
        """PDFs with different club names should differ in size/content."""
        ranking = RankingResponse(
            from_date=date(2025, 6, 1),
            to_date=date(2025, 6, 30),
            entries=[],
            generated_at=__import__("datetime").datetime(
                2025, 7, 1, tzinfo=__import__("datetime").timezone.utc
            ),
        )
        pdf1 = generate_ranking_pdf(ranking, club_name="Short")
        pdf2 = generate_ranking_pdf(ranking, club_name="A Much Longer Club Name Here")
        # Different names produce different PDFs
        assert pdf1 != pdf2

    def test_pdf_default_club_name_is_dart_club(self):
        """Default club_name parameter should be 'Dart Club' for backward compatibility."""
        ranking = RankingResponse(
            from_date=date(2025, 6, 1),
            to_date=date(2025, 6, 30),
            entries=[],
            generated_at=__import__("datetime").datetime(
                2025, 7, 1, tzinfo=__import__("datetime").timezone.utc
            ),
        )
        # Default parameter is "Dart Club" but the caller (route) should pass the actual club name
        pdf = generate_ranking_pdf(ranking)
        assert pdf[:4] == b"%PDF"
