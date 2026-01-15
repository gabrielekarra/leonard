"""Leonard Core - FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from leonard import __version__
from leonard.api.routes import chat, models, tools, memory
from leonard.api.schemas import HealthResponse
from leonard.config import API_PREFIX
from leonard.utils.logging import logger

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info(f"Leonard Core v{__version__} starting...")
    logger.info("Server running at http://localhost:7878")
    yield
    # Cleanup on shutdown
    if chat.orchestrator:
        await chat.orchestrator.shutdown()
    logger.info("Leonard Core stopped")


app = FastAPI(
    title="Leonard Core",
    description="The local-first engine to build and run private AI agents",
    version=__version__,
    lifespan=lifespan,
)

# Configure CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(chat.router, prefix=API_PREFIX)
app.include_router(models.router, prefix=API_PREFIX)
app.include_router(tools.router, prefix=API_PREFIX)
app.include_router(memory.router, prefix=API_PREFIX)


@app.get(f"{API_PREFIX}/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok", version=__version__)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=7878)
