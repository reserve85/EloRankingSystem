"""Version and build information."""

import os
from datetime import datetime

GITHUB_REPO_URL = "https://github.com/reserve85/EloRankingSystem"


def get_version_info(timezone: str = "UTC") -> dict:
    """Get version, git commit, and build date info.

    Values are injected during Docker build via ARG/ENV,
    or fall back to defaults for local development.

    Args:
        timezone: IANA timezone name for build date formatting.

    Returns:
        Dict with version, git_commit, build_date, github_url, release_url.
    """
    raw_version = os.getenv("APP_VERSION", "0.1.0")
    # Strip leading "v" or "vv" to avoid double-v in output
    version = raw_version.lstrip("v")

    git_commit = os.getenv("GIT_COMMIT", "dev")[:7]

    raw_build_date = os.getenv("BUILD_DATE", "development")
    build_date = _format_build_date(raw_build_date, timezone)

    return {
        "version": version,
        "git_commit": git_commit,
        "build_date": build_date,
        "github_url": GITHUB_REPO_URL,
        "release_url": f"{GITHUB_REPO_URL}/releases/tag/v{version}",
    }


def _format_build_date(raw: str, timezone: str) -> str:
    """Format build date string using the configured timezone.

    Args:
        raw: Raw build date string (ISO 8601 or 'development').
        timezone: IANA timezone name.

    Returns:
        Formatted date string in the given timezone.
    """
    if raw == "development":
        return "development"

    try:
        from zoneinfo import ZoneInfo

        # Parse ISO 8601 datetime string
        dt = datetime.fromisoformat(raw)
        tz = ZoneInfo(timezone)
        dt_local = dt.astimezone(tz)
        return dt_local.strftime("%Y-%m-%d %H:%M:%S %Z")
    except (ValueError, ImportError, KeyError, OSError):
        return raw
