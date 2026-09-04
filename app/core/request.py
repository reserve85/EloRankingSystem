"""Request helpers - client IP resolution honoring trusted proxies (Fix M6)."""

from app.core.config import settings


def get_client_ip(request) -> str:
    """Resolve the real client IP for rate-limiting keys and audit logs.

    The socket peer (``request.client.host``) is used by default. When
    ``TRUSTED_PROXIES`` is configured and the direct peer is one of the trusted
    proxies, the right-most ``X-Forwarded-For`` entry that is not itself a
    trusted proxy is used instead. This stops the rate limiter and audit logs
    from collapsing every user behind a reverse proxy into a single address,
    while still ignoring client-supplied headers when no proxy is trusted.

    Args:
        request: FastAPI Request object.

    Returns:
        The resolved client IP string.
    """
    peer = request.client.host if request.client and request.client.host else "127.0.0.1"
    trusted = _parse_trusted_proxies(settings.trusted_proxies)
    if not trusted or peer not in trusted:
        return peer

    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return peer
    # Scan right-to-left; the left-most entry that is not a trusted proxy is
    # the real client (starlette ProxyHeadersMiddleware semantics).
    for part in reversed([p.strip() for p in forwarded.split(",") if p.strip()]):
        if part not in trusted:
            return part
    return peer


def _parse_trusted_proxies(value) -> set[str]:
    """Normalize the ``TRUSTED_PROXIES`` config value into a set of IPs.

    Accepts a comma-separated string (set via env/YAML) or an iterable (used
    by tests). Returns an empty set when nothing is configured.
    """
    if not value:
        return set()
    if isinstance(value, str):
        return {item.strip() for item in value.split(",") if item.strip()}
    return set(value)
