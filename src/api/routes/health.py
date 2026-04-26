"""
Health check endpoints.
"""

from fastapi import APIRouter, Response

from src.utils.logger import get_logger

router = APIRouter(prefix="/health", tags=["health"])
logger = get_logger(__name__)


@router.get("")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check(response: Response):
    """Readiness endpoint with dependency diagnostics for production operations."""
    checks: dict[str, dict[str, object]] = {}
    critical_failures: list[str] = []
    warnings: list[str] = []

    # Cosmos DB is critical for persistent user data.
    try:
        from src.db.cosmos_client import get_cosmos_client

        cosmos = get_cosmos_client()
        cosmos_ready = bool(cosmos.is_ready() and not cosmos.use_mock)
        checks["cosmos"] = {
            "ready": cosmos_ready,
            "mode": "mock" if cosmos.use_mock else "cloud",
        }
        if not cosmos_ready:
            critical_failures.append("cosmos")
    except Exception as exc:
        checks["cosmos"] = {"ready": False, "error": str(exc)}
        critical_failures.append("cosmos")

    # Chroma must be mounted and collection should be available.
    try:
        from src.db.chroma_client import get_chroma_client

        chroma = get_chroma_client()
        chroma_ready = bool(chroma.is_ready())
        checks["chroma"] = {"ready": chroma_ready}
        if not chroma_ready:
            critical_failures.append("chroma")
    except Exception as exc:
        checks["chroma"] = {"ready": False, "error": str(exc)}
        critical_failures.append("chroma")

    # OpenAI connectivity is important; do not hard-fail readiness on temporary outages.
    try:
        from src.rag.generator import get_generator

        generator = get_generator()
        llm_ready = bool(
            (not generator.use_mock) and (generator.azure_client is not None)
        )
        checks["openai"] = {
            "ready": llm_ready,
            "mode": "mock" if generator.use_mock else "cloud",
        }
        if not llm_ready:
            warnings.append("openai")
    except Exception as exc:
        checks["openai"] = {"ready": False, "error": str(exc)}
        warnings.append("openai")

    is_ready = len(critical_failures) == 0
    response.status_code = 200 if is_ready else 503
    payload = {
        "status": "ready" if is_ready else "not_ready",
        "checks": checks,
    }
    if critical_failures:
        payload["critical_failures"] = critical_failures
    if warnings:
        payload["warnings"] = warnings

    if is_ready:
        logger.info(
            "Readiness check passed: cosmos=%s chroma=%s openai=%s",
            checks.get("cosmos", {}).get("ready"),
            checks.get("chroma", {}).get("ready"),
            checks.get("openai", {}).get("ready"),
        )
    else:
        logger.warning(
            "Readiness check failed: critical=%s checks=%s",
            critical_failures,
            checks,
        )
    return payload
