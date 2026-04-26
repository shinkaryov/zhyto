"""FastAPI backend for ЖИТО."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.core import VERSION
from src.utils import setup_logging, get_logger
from src.api.routes import auth, chat, portfolio, notes, health, config

# Setup logging
setup_logging()
logger = get_logger(__name__)


def _warm_up_services() -> None:
    """Initialize heavy shared services at startup to reduce first-request latency."""
    from src.db.cosmos_client import get_cosmos_client
    from src.rag.retriever import get_retriever
    from src.rag.generator import get_generator

    get_cosmos_client()
    get_retriever()
    get_generator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    logger.info(f"Starting ЖИТО v{VERSION}")
    try:
        await run_in_threadpool(_warm_up_services)
        logger.info("Warm-up completed")
    except Exception as exc:
        logger.warning(f"Warm-up skipped due to error: {exc}")
    yield
    logger.info("Shutting down ЖИТО")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="ЖИТО API",
        description="AI-powered financial assistant for investors",
        version=VERSION,
        lifespan=lifespan,
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Update in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(health.router)
    app.include_router(config.router)
    app.include_router(auth.router)
    app.include_router(chat.router)
    app.include_router(portfolio.router)
    app.include_router(notes.router)

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": str(exc)},
        )

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.app.fastapi_main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
