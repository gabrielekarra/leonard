"""Shared orchestrator instance for API routes."""

from typing import Optional

from leonard.engine.orchestrator import LeonardOrchestrator

orchestrator: Optional[LeonardOrchestrator] = None


async def get_orchestrator() -> LeonardOrchestrator:
    """Get or create the orchestrator instance."""
    global orchestrator
    if orchestrator is None:
        orchestrator = LeonardOrchestrator()
        await orchestrator.initialize()
    return orchestrator
