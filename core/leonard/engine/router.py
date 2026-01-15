"""
The Router is a small, fast LLM that decides which model to use for each task.
It analyzes the user's message and routes to the best available model.
"""

import json
from typing import Optional

from pydantic import BaseModel

from leonard.models.registry import ModelCapability, ModelRegistry, RegisteredModel
from leonard.runtime.process_manager import ProcessManager
from leonard.utils.logging import logger


class RoutingDecision(BaseModel):
    """Result of routing analysis."""

    model_id: str
    model_name: str
    reason: str
    capability: ModelCapability
    confidence: float  # 0.0 - 1.0


class Router:
    """
    Uses a small LLM to intelligently route requests to the best model.
    The router model is always kept in memory for fast decisions.
    """

    ROUTING_PROMPT = """You are a routing assistant. Your job is to analyze the user's message and decide which AI model should handle it.

Available models:
{models_description}

User message: {user_message}

Analyze the message and respond with a JSON object:
{{
    "model_id": "id of the best model to use",
    "capability": "the main capability needed (general/coding/reasoning/creative/math/analysis)",
    "reason": "brief explanation of why this model",
    "confidence": 0.0 to 1.0
}}

If no specialized model fits well, use the model with highest "general" capability.
Respond ONLY with the JSON object, no other text."""

    def __init__(self, process_manager: ProcessManager, registry: ModelRegistry):
        self.process_manager = process_manager
        self.registry = registry
        self._router_ready = False

    async def ensure_router_ready(self):
        """Make sure router model is loaded and running."""
        if self._router_ready and self.process_manager.is_running("leonard-router"):
            return

        router = self.registry.get_router()

        if not router.local_path:
            raise RuntimeError(
                "Router model not downloaded. Please download the router model first."
            )

        from pathlib import Path

        await self.process_manager.start(
            model_id="leonard-router",
            model_path=Path(router.local_path),
            n_ctx=4096,  # Smaller context for router
            n_gpu_layers=-1,
        )

        self._router_ready = True
        logger.info("Router model ready")

    async def route(self, user_message: str) -> RoutingDecision:
        """
        Analyze user message and decide which model to use.

        Args:
            user_message: The message from the user

        Returns:
            RoutingDecision with model_id, reason, capability, confidence
        """
        await self.ensure_router_ready()

        available = self.registry.get_available_workers()

        # If no worker models available, we can only use router as fallback
        if not available:
            logger.warning("No worker models available, using router as fallback")
            router = self.registry.get_router()
            return RoutingDecision(
                model_id="leonard-router",
                model_name=router.name,
                reason="No other models available",
                capability=ModelCapability.GENERAL,
                confidence=0.5,
            )

        # Build models description for prompt
        models_desc = self._build_models_description(available)

        prompt = self.ROUTING_PROMPT.format(
            models_description=models_desc,
            user_message=user_message,
        )

        # Ask router to decide
        try:
            response = await self.process_manager.chat(
                model_id="leonard-router",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.1,  # Low temp for consistent routing
            )

            decision = self._parse_routing_response(response, available)
            logger.info(f"Routing decision: {decision.model_id} ({decision.reason})")
            return decision

        except Exception as e:
            logger.error(f"Routing failed: {e}, falling back to best general model")
            return self._fallback_routing(available)

    def _build_models_description(self, models: list[RegisteredModel]) -> str:
        """Build description of available models for the prompt."""
        lines = []
        for m in models:
            caps = ", ".join(
                [f"{cap.value}: {score:.1f}" for cap, score in m.capabilities.items()]
            )
            lines.append(f"- {m.id}: {m.name} (capabilities: {caps})")
        return "\n".join(lines)

    def _parse_routing_response(
        self,
        response: str,
        available: list[RegisteredModel],
    ) -> RoutingDecision:
        """Parse the router's JSON response."""
        try:
            # Clean response (remove markdown if present)
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            response = response.strip()

            data = json.loads(response)

            # Validate model_id exists
            model_id = data.get("model_id", "")
            valid_ids = {m.id for m in available}
            model_name = ""

            if model_id not in valid_ids:
                # Try to match by name
                for m in available:
                    if (
                        m.name.lower() in model_id.lower()
                        or model_id.lower() in m.name.lower()
                    ):
                        model_id = m.id
                        model_name = m.name
                        break
                else:
                    # Use first available
                    model_id = available[0].id
                    model_name = available[0].name
            else:
                # Find name for the model
                for m in available:
                    if m.id == model_id:
                        model_name = m.name
                        break

            # Parse capability
            capability_str = data.get("capability", "general")
            try:
                capability = ModelCapability(capability_str)
            except ValueError:
                capability = ModelCapability.GENERAL

            return RoutingDecision(
                model_id=model_id,
                model_name=model_name,
                reason=data.get("reason", "Selected by router"),
                capability=capability,
                confidence=float(data.get("confidence", 0.7)),
            )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to parse routing response: {e}")
            return self._fallback_routing(available)

    def _fallback_routing(self, available: list[RegisteredModel]) -> RoutingDecision:
        """Fallback: pick model with highest general capability."""
        best = max(
            available,
            key=lambda m: m.capabilities.get(ModelCapability.GENERAL, 0),
        )
        return RoutingDecision(
            model_id=best.id,
            model_name=best.name,
            reason="Fallback to best general model",
            capability=ModelCapability.GENERAL,
            confidence=0.5,
        )

    async def direct_route(self, model_id: str) -> Optional[RoutingDecision]:
        """
        Skip routing and use a specific model directly.
        Useful when user explicitly selects a model.

        Args:
            model_id: The model ID to use

        Returns:
            RoutingDecision for the specified model, or None if not found/available
        """
        model = self.registry.get(model_id)
        if not model or not model.is_downloaded:
            return None

        return RoutingDecision(
            model_id=model.id,
            model_name=model.name,
            reason="User selected this model",
            capability=ModelCapability.GENERAL,
            confidence=1.0,
        )
