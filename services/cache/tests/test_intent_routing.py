"""Unit tests for intent-aware model selection in autoroute.py."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.autoroute import _COMPLEX_INTENTS, select_model_for_intent


@pytest.mark.asyncio
async def test_complex_intent_restricted_to_complex_models():
    """Debugging requests only consider complex-only models."""
    candidates = ["claude-haiku-4-5", "gpt-4o-mini", "claude-sonnet-4-6"]
    complex_only = ["claude-sonnet-4-6"]

    with patch("app.autoroute.get_model_scores", new_callable=AsyncMock) as mock_scores:
        mock_scores.return_value = {
            "claude-haiku-4-5": 0.9,
            "gpt-4o-mini": 0.8,
            "claude-sonnet-4-6": 0.7,
        }
        result = await select_model_for_intent(None, "debugging", candidates, complex_only)

    assert result == "claude-sonnet-4-6", "Debugging must route to complex model only"


@pytest.mark.asyncio
async def test_simple_intent_uses_all_candidates():
    """Question requests may use any candidate, picking the best scorer."""
    candidates = ["claude-haiku-4-5", "gpt-4o-mini", "claude-sonnet-4-6"]
    complex_only = ["claude-sonnet-4-6"]

    with patch("app.autoroute.get_model_scores", new_callable=AsyncMock) as mock_scores:
        mock_scores.return_value = {
            "claude-haiku-4-5": 0.95,
            "gpt-4o-mini": 0.80,
            "claude-sonnet-4-6": 0.70,
        }
        result = await select_model_for_intent(None, "question", candidates, complex_only)

    assert result == "claude-haiku-4-5", "Question should route to best (cheapest) model"


@pytest.mark.asyncio
@pytest.mark.parametrize("intent", sorted(_COMPLEX_INTENTS))
async def test_all_complex_intents_are_restricted(intent):
    """Every intent in _COMPLEX_INTENTS must stay on complex models."""
    candidates = ["claude-haiku-4-5", "claude-sonnet-4-6"]
    complex_only = ["claude-sonnet-4-6"]

    with patch("app.autoroute.get_model_scores", new_callable=AsyncMock) as mock_scores:
        mock_scores.return_value = {"claude-haiku-4-5": 0.99, "claude-sonnet-4-6": 0.50}
        result = await select_model_for_intent(None, intent, candidates, complex_only)

    assert result == "claude-sonnet-4-6", f"Complex intent '{intent}' routed to cheap model"


@pytest.mark.asyncio
async def test_fallback_to_all_candidates_when_no_complex_overlap():
    """If no complex_models appear in candidates, use all candidates."""
    candidates = ["claude-haiku-4-5", "gpt-4o-mini"]
    complex_only = ["claude-sonnet-4-6"]  # not in candidates

    with patch("app.autoroute.get_model_scores", new_callable=AsyncMock) as mock_scores:
        mock_scores.return_value = {"claude-haiku-4-5": 0.9, "gpt-4o-mini": 0.8}
        result = await select_model_for_intent(None, "code_generation", candidates, complex_only)

    assert result in candidates, "Must fall back to all candidates when complex list has no overlap"


@pytest.mark.asyncio
async def test_empty_complex_models_uses_all_candidates():
    """Empty complex_models list means all candidates are eligible for any intent."""
    candidates = ["claude-haiku-4-5", "gpt-4o-mini"]

    with patch("app.autoroute.get_model_scores", new_callable=AsyncMock) as mock_scores:
        mock_scores.return_value = {"claude-haiku-4-5": 0.9, "gpt-4o-mini": 0.7}
        result = await select_model_for_intent(None, "debugging", candidates, [])

    assert result == "claude-haiku-4-5"
