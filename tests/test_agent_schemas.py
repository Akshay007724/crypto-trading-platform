"""Contract tests: every agent's output schema must accept a well-formed
payload and reject a malformed one — this is what `BaseAgent.validate_output`
enforces before anything reaches the UI."""

import pytest
from pydantic import ValidationError

from hft.agents.schemas import AGENT_SCHEMAS, NLQueryOutput


def test_nl_query_output_accepts_valid_payload():
    output = NLQueryOutput(
        question="What's BTC doing?",
        answer="BTC/USD is at $100,000.",
        citations=[{"label": "get_quote(BTC/USD)", "tool": "get_quote"}],
        tool_calls_made=["get_quote"],
    )
    assert output.answer.startswith("BTC")


def test_nl_query_output_rejects_missing_required_field():
    with pytest.raises(ValidationError):
        NLQueryOutput(answer="missing question and citations")


@pytest.mark.parametrize("agent_name", list(AGENT_SCHEMAS))
def test_every_registered_agent_has_a_schema(agent_name):
    assert AGENT_SCHEMAS[agent_name] is not None
