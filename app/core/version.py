"""Version and build information."""

import os


def get_version_info() -> dict:
    """Get version, git commit, and build date info.

    Values are injected during Docker build via ARG/ENV,
    or fall back to defaults for local development.
    """
    return {
        "version": os.getenv("APP_VERSION", "0.1.0"),
        "git_commit": os.getenv("GIT_COMMIT", "dev")[:7],
        "build_date": os.getenv("BUILD_DATE", "development"),
    }