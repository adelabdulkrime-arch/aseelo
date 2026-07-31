"""Rate limiting (slowapi + Redis when available, in-memory otherwise)."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)


def _client_key(request: Request) -> str:
    """Prefer the authenticated user, fall back to client IP."""
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"user:{user_id}"
    return f"ip:{get_remote_address(request)}"


def _build_limiter() -> Limiter:
    """Build the limiter.

    ``headers_enabled`` stays off: slowapi can only inject X-RateLimit-* headers
    when the endpoint returns a raw ``Response``, and ours return Pydantic models.
    """
    storage_uri = settings.redis_url if settings.rate_limit_enabled else None
    try:
        return Limiter(
            key_func=_client_key,
            storage_uri=storage_uri,
            enabled=settings.rate_limit_enabled,
        )
    except Exception:  # noqa: BLE001 - fall back to memory storage
        logger.warning("rate_limit_storage_unavailable_falling_back_to_memory")
        return Limiter(key_func=_client_key, enabled=settings.rate_limit_enabled)


limiter = _build_limiter()
