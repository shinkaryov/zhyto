"""Tests for live-market tool orchestration in analytical chat pipeline."""

from src.rag.chat_pipeline import AnalyticalChatPipeline
from src.rag.model_router import ChatModelRouter


class EmptyRetriever:
    def search(self, query: str, top_k: int = 5):
        return []


class SingleResultRetriever:
    def __init__(self):
        self.calls = []

    def search(self, query: str, top_k: int = 5):
        self.calls.append((query, top_k))
        return [
            {
                "content": "AAPL had elevated volatility amid growth-stock repricing.",
                "metadata": {
                    "source_id": "kb-1",
                    "channel": "MarketNews",
                    "url": "https://example.com/aapl",
                    "date": "2026-04-23",
                    "domain": "stocks",
                    "trust_weight": 0.9,
                },
                "distance": 0.12,
            }
        ]


class CapturingGenerator:
    def __init__(self):
        self.calls = []

    def generate(self, prompt: str, system_prompt: str | None = None, **kwargs):
        self.calls.append(
            {"prompt": prompt, "system_prompt": system_prompt, "kwargs": kwargs}
        )
        normalized_system = (system_prompt or "").lower()
        if "internal investment research planner" in normalized_system:
            return (
                '{"hypotheses":['
                '{"hypothesis_id":"H1","short_title":"Company-specific driver",'
                '"description":"Move linked to company catalyst",'
                '"evidence_query":"AAPL company news earnings"},'
                '{"hypothesis_id":"H2","short_title":"Macro risk-off",'
                '"description":"Move linked to broad risk-off",'
                '"evidence_query":"AAPL macro risk sentiment rates"}'
                "]}"
            )
        if "internal evidence compression engine" in normalized_system:
            return (
                '{"hypotheses":['
                '{"hypothesis_id":"H1","title":"Company-specific driver",'
                '"supporting_evidence":[1],"contradicting_evidence":[],'
                '"source_notes":["AAPL volatility on repricing"],"confidence":"medium"},'
                '{"hypothesis_id":"H2","title":"Macro risk-off",'
                '"supporting_evidence":[1],"contradicting_evidence":[],'
                '"source_notes":["Broad risk-off tone"],"confidence":"medium"}'
                "],"
                '"cross_source_consensus":"Short-term volatility regime.",'
                '"major_uncertainties":["No single confirmed catalyst"],'
                '"sources_used":[1]}'
            )
        if "internal senior financial analyst" in normalized_system:
            return "Signals point to short-term de-risking in growth names [1]."
        if "routing mode: analytical_with_live_price" in normalized_system:
            return "AAPL зараз коштує $273.43. Короткостроковий тиск пов'язаний з переоцінкою growth-сегмента [1]."
        return "Tool-backed answer."


def test_live_price_query_runs_advisor_even_without_kb_sources():
    generator = CapturingGenerator()
    pipeline = AnalyticalChatPipeline(retriever=EmptyRetriever(), generator=generator)
    pipeline.model_router = ChatModelRouter(
        enabled=True,
        default_deployment="mini-deploy",
        advanced_deployment="pro-deploy",
    )

    result = pipeline.run(
        question="Яка зараз ціна DUOL?",
        user_portfolio=[{"asset_type": "Акції (ETF)", "ticker": "DUOL"}],
    )

    assert result.message == "Tool-backed answer."
    assert len(generator.calls) == 1
    assert generator.calls[0]["kwargs"].get("enable_market_price_tool") is False
    assert generator.calls[0]["kwargs"].get("tool_categories") == ["live_market_tools"]
    assert generator.calls[0]["kwargs"].get("deployment") == "mini-deploy"


def test_live_price_plus_analysis_uses_tool_and_relevant_rag_context():
    retriever = SingleResultRetriever()
    generator = CapturingGenerator()
    pipeline = AnalyticalChatPipeline(retriever=retriever, generator=generator)
    pipeline.model_router = ChatModelRouter(
        enabled=True,
        default_deployment="mini-deploy",
        advanced_deployment="pro-deploy",
    )

    result = pipeline.run(question="Що сьогодні з AAPL і чому він падає?")

    assert retriever.calls, "RAG retrieval should run for analytical_with_live_price"
    assert (
        len(generator.calls) >= 3
    ), "Expected hypothesis/compression/analyst/advisor generation calls"
    assert generator.calls[-1]["kwargs"].get("enable_market_price_tool") is False
    assert generator.calls[-1]["kwargs"].get("tool_categories") == ["live_market_tools"]
    assert generator.calls[-1]["kwargs"].get("deployment") == "pro-deploy"
    hypothesis_call = next(
        (
            item
            for item in generator.calls
            if "internal investment research planner"
            in (item.get("system_prompt") or "").lower()
        ),
        None,
    )
    compression_call = next(
        (
            item
            for item in generator.calls
            if "internal evidence compression engine"
            in (item.get("system_prompt") or "").lower()
        ),
        None,
    )
    analyst_call = next(
        (
            item
            for item in generator.calls
            if "internal senior financial analyst"
            in (item.get("system_prompt") or "").lower()
        ),
        None,
    )
    assert hypothesis_call is not None
    assert compression_call is not None
    assert analyst_call is not None
    assert hypothesis_call["kwargs"].get("deployment") == "mini-deploy"
    assert compression_call["kwargs"].get("deployment") == "mini-deploy"
    assert analyst_call["kwargs"].get("deployment") == "mini-deploy"
    assert "AAPL зараз коштує" in result.message
    assert len(result.sources) == 1
