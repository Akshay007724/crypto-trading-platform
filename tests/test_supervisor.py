"""Integration test for supervisor routing — mocks the LLM client so no
network/API-key is needed, verifies: (1) NL query routes end-to-end and
produces a schema-valid output, (2) unimplemented agents degrade cleanly
instead of crashing the supervisor, (3) LLM-unavailable degrades cleanly."""

from unittest.mock import MagicMock

from hft.agents.llm_client import LLMResponse
from hft.agents.supervisor import Supervisor
from hft.data_plane.cache import QuoteCache
from hft.data_plane.timeseries import TimeseriesStore
from hft.tools.market_tools import MarketTools, build_default_governor


def _tools(tmp_path) -> MarketTools:
    return MarketTools(
        quote_cache=QuoteCache("redis://localhost:1", ttl_s=5),
        governor=build_default_governor(),
        store=TimeseriesStore(str(tmp_path / "test.db")),
        finnhub_api_key="",
    )


def test_supervisor_reports_llm_unavailable_when_no_api_key(tmp_path):
    llm = MagicMock()
    llm.available = False
    supervisor = Supervisor(_tools(tmp_path), llm=llm)

    result = supervisor.handle_nl_query("What's BTC doing?")

    assert result.ok is False
    assert "unavailable" in result.error


def test_supervisor_routes_nl_query_end_to_end_with_mocked_llm(tmp_path):
    llm = MagicMock()
    llm.available = True
    # First call: model decides to call get_quote. Second call: final answer.
    llm.chat.side_effect = [
        LLMResponse(content="", tool_calls=[{"name": "get_quote", "arguments": {"symbol": "BTC/USD"}}], estimated_cost_usd=0.001, latency_s=0.1),
        LLMResponse(content="BTC/USD data was fetched.", tool_calls=[], estimated_cost_usd=0.001, latency_s=0.1),
    ]
    supervisor = Supervisor(_tools(tmp_path), llm=llm)

    result = supervisor.handle_nl_query("What's BTC/USD doing?")

    assert result.ok is True
    assert result.agent == "nl_query"
    assert result.output["tool_calls_made"] == ["get_quote"]
    assert len(result.output["citations"]) == 1


def test_supervisor_stub_agent_degrades_without_crashing(tmp_path):
    llm = MagicMock()
    llm.available = True
    supervisor = Supervisor(_tools(tmp_path), llm=llm)

    result = supervisor.handle_stub("technical", symbol="BTC/USD")

    assert result.ok is False
    assert "TODO" in result.error


def test_supervisor_rejects_unknown_agent_name(tmp_path):
    llm = MagicMock()
    llm.available = True
    supervisor = Supervisor(_tools(tmp_path), llm=llm)

    result = supervisor.handle_stub("does_not_exist")

    assert result.ok is False
    assert "unknown agent" in result.error
