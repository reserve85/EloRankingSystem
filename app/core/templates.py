"""Jinja2 template rendering configuration."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.core.config import settings

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Fix #9: hide the "API Docs" footer link when the OpenAPI surface is
# disabled in production.
templates.env.globals["api_docs_enabled"] = (
    str(settings.app_env).strip().lower() != "production"
)
