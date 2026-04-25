"""Unit tests for chat fallback behavior after LLM failures."""

from src.api.routes import chat
from src.auth.auth_service import AuthIdentity
from src.rag.generator import GeneratorError, LLMServiceUnavailableError
from src.utils.config import settings


class StubCosmosClient:
    def __init__(self):
        self.added_assets = []

    @staticmethod
    def get_user_notes(user_id: str):
        return []

    @staticmethod
    def get_user_portfolio(user_id: str):
        return []

    def add_portfolio_asset(self, asset_data: dict):
        payload = dict(asset_data)
        payload["id"] = "asset_1"
        self.added_assets.append(payload)
        return payload


class StubRetriever:
    @staticmethod
    def search(query: str, top_k: int = 5):
        return []


class UnavailableGenerator:
    @staticmethod
    def generate(*args, **kwargs):
        raise LLMServiceUnavailableError(
            attempts=3,
            deployment="gpt-5.4-mini",
            operation="chat_completion",
            last_error=Exception("503 service unavailable"),
        )


class BrokenGenerator:
    @staticmethod
    def generate(*args, **kwargs):
        raise GeneratorError("invalid response format from provider")


class ShouldNotBeCalledGenerator:
    @staticmethod
    def generate(*args, **kwargs):
        raise AssertionError("Generator should not be called for direct draft confirmation flow")


def test_chat_returns_user_friendly_message_for_llm_unavailability(monkeypatch):
    monkeypatch.setattr(settings, "chat_analytical_pipeline_enabled", False)
    monkeypatch.setattr(chat, "get_cosmos_client", lambda: StubCosmosClient())
    monkeypatch.setattr(chat, "get_retriever", lambda: StubRetriever())
    monkeypatch.setattr(chat, "get_generator", lambda: UnavailableGenerator())

    request = chat.ChatRequest(message="Яка зараз ціна DUOL?")
    identity = AuthIdentity(email="test@example.com", user_id="user_1")

    response = chat._send_message_sync(request, identity)

    assert response.message == "Зараз не можемо обробити ваш запит. Спробуйте пізніше."
    assert response.sources == []


def test_chat_returns_generation_error_message_for_non_retryable_failures(monkeypatch):
    monkeypatch.setattr(settings, "chat_analytical_pipeline_enabled", False)
    monkeypatch.setattr(chat, "get_cosmos_client", lambda: StubCosmosClient())
    monkeypatch.setattr(chat, "get_retriever", lambda: StubRetriever())
    monkeypatch.setattr(chat, "get_generator", lambda: BrokenGenerator())

    request = chat.ChatRequest(message="What is ETF?")
    identity = AuthIdentity(email="test@example.com", user_id="user_1")

    response = chat._send_message_sync(request, identity)

    assert "technical error" in response.message
    assert response.sources == []


def test_chat_confirm_message_persists_pending_transaction_draft(monkeypatch):
    monkeypatch.setattr(settings, "chat_analytical_pipeline_enabled", False)
    cosmos = StubCosmosClient()
    monkeypatch.setattr(chat, "get_cosmos_client", lambda: cosmos)
    monkeypatch.setattr(chat, "get_retriever", lambda: StubRetriever())
    monkeypatch.setattr(chat, "get_generator", lambda: ShouldNotBeCalledGenerator())

    request = chat.ChatRequest(
        message="Так, додай",
        history=[
            chat.ChatMessage(role="user", content="Вчора купив 20 акцій TSLA за 4000 доларів"),
            chat.ChatMessage(
                role="assistant",
                content="Готово. Я підготував запис: 20 TSLA по $200 за акцію. Додати в портфель?",
                pending_transaction_draft={
                    "asset_type": "Акції (ETF)",
                    "ticker": "TSLA",
                    "amount": 20,
                    "currency": "USD",
                    "purchase_price": 200,
                    "purchase_date": "2026-04-23",
                    "total_value": 4000,
                },
                draft_status="pending",
            ),
        ],
    )
    identity = AuthIdentity(email="test@example.com", user_id="user_1")

    response = chat._send_message_sync(request, identity)

    assert "додано в портфель" in response.message.lower()
    assert response.sources == []
    assert len(cosmos.added_assets) == 1
    assert cosmos.added_assets[0]["ticker"] == "TSLA"
    assert cosmos.added_assets[0]["purchase_price"] == 200
