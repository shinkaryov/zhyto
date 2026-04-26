"""Unit tests for unified Responses API generation and retry/fallback behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.rag.generator import Generator, GeneratorError, LLMServiceUnavailableError
from src.utils.config import settings


@dataclass
class _ResponseLikeObject:
    """Simple object-like response node used by parser tests."""

    # Keep fields dynamic through kwargs-like initialization.
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class _StubResponsesAPI:
    def __init__(self, queued: list[Any]):
        self._queued = list(queued)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._queued:
            raise AssertionError("Stub responses queue exhausted")
        item = self._queued.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _StubAzureClient:
    def __init__(self, queued_responses: list[Any]):
        self.responses = _StubResponsesAPI(queued_responses)
        self.timeout_options: list[Any] = []

    def with_options(self, **kwargs):
        self.timeout_options.append(kwargs.get("timeout"))
        return self


class _BadRequestLikeError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        param: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.body = {
            "error": {
                "message": message,
                "param": param,
            }
        }


def _make_generator_with_stub(
    queued_responses: list[Any],
) -> tuple[Generator, _StubAzureClient]:
    generator = Generator(use_mock=True)
    generator.use_mock = False
    generator.default_deployment = "gpt-5.4-mini"
    generator.advanced_deployment = "gpt-5.4-pro"
    client = _StubAzureClient(queued_responses)
    generator.azure_client = client
    return generator, client


def _message_response(text: str) -> _ResponseLikeObject:
    return _ResponseLikeObject(
        id="resp_message",
        output_text=None,
        output=[
            _ResponseLikeObject(
                type="message",
                content=[
                    {"type": "output_text", "text": {"value": text}},
                ],
            )
        ],
    )


def _reasoning_only_response() -> _ResponseLikeObject:
    return _ResponseLikeObject(
        id="resp_reasoning",
        output_text=None,
        output=[_ResponseLikeObject(type="reasoning", summary=[])],
    )


def _empty_non_reasoning_response() -> _ResponseLikeObject:
    return _ResponseLikeObject(
        id="resp_empty_message",
        output_text=None,
        output=[_ResponseLikeObject(type="message", content=[])],
    )


def test_normalize_responses_content_reads_output_text():
    response = _ResponseLikeObject(output_text="Final answer", output=[])
    assert Generator._normalize_responses_content(response) == "Final answer"


def test_normalize_responses_content_reads_message_string_blocks():
    response = _ResponseLikeObject(
        output_text=None,
        output=[
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "Block one"},
                    {"type": "output_text", "text": "Block two"},
                ],
            }
        ],
    )

    normalized = Generator._normalize_responses_content(response)
    assert normalized == "Block one\nBlock two"


def test_normalize_responses_content_reads_nested_text_value():
    response = _ResponseLikeObject(
        output_text=None,
        output=[
            _ResponseLikeObject(
                type="message",
                content=[
                    {"type": "output_text", "text": {"value": "Аналітичний висновок."}}
                ],
            )
        ],
    )
    assert Generator._normalize_responses_content(response) == "Аналітичний висновок."


def test_normalize_responses_content_ignores_reasoning_when_message_exists():
    response = _ResponseLikeObject(
        output_text=None,
        output=[
            _ResponseLikeObject(type="reasoning", summary=[{"text": "internal"}]),
            _ResponseLikeObject(
                type="message",
                content=[
                    {"type": "output_text", "text": {"value": "User-facing answer"}}
                ],
            ),
        ],
    )

    assert Generator._normalize_responses_content(response) == "User-facing answer"


def test_normalize_responses_content_returns_empty_for_reasoning_only():
    response = _reasoning_only_response()
    assert Generator._normalize_responses_content(response) == ""


def test_normalize_responses_content_ignores_tool_call_output():
    response = _ResponseLikeObject(
        output_text=None,
        output=[
            _ResponseLikeObject(
                type="function_call",
                name="get_current_market_price",
                arguments='{"ticker":"AAPL"}',
                call_id="call_1",
            ),
        ],
    )

    assert Generator._normalize_responses_content(response) == ""


def test_generate_with_responses_retries_on_reasoning_only_and_returns_message(
    monkeypatch,
):
    monkeypatch.setattr(settings, "chat_llm_retry_enabled", False)

    generator, client = _make_generator_with_stub(
        [
            _reasoning_only_response(),
            _message_response("Final answer after retry"),
        ]
    )

    result = generator._generate_with_responses_api(
        prompt="Проаналізуй портфель",
        system_prompt="system",
        history=[],
        deployment="gpt-5.4-mini",
        tools=None,
        max_tokens=500,
        temperature=0.2,
    )

    assert result == "Final answer after retry"
    assert len(client.responses.calls) == 2
    retry_input = client.responses.calls[1]["input"]
    assert isinstance(retry_input, list)
    assert (
        "You must produce a final answer message for the user."
        in retry_input[-1]["content"]
    )


def test_reasoning_only_response_can_succeed_on_third_attempt(monkeypatch):
    monkeypatch.setattr(settings, "chat_llm_retry_enabled", False)

    generator, client = _make_generator_with_stub(
        [
            _reasoning_only_response(),
            _reasoning_only_response(),
            _message_response("Resolved on third call"),
        ]
    )

    result = generator._generate_with_responses_api(
        prompt="Проаналізуй портфель",
        system_prompt="system",
        history=[],
        deployment="gpt-5.4-pro",
        tools=None,
        max_tokens=450,
        temperature=0.2,
        chat_intent="analytical_rag",
    )

    assert result == "Resolved on third call"
    assert len(client.responses.calls) == 3


def test_reasoning_only_pro_falls_back_to_mini_after_targeted_retries(monkeypatch):
    monkeypatch.setattr(settings, "chat_llm_retry_enabled", False)

    generator, client = _make_generator_with_stub(
        [
            _reasoning_only_response(),  # pro initial
            _reasoning_only_response(),  # pro targeted retry 1
            _reasoning_only_response(),  # pro targeted retry 2
            _message_response("fallback-mini-answer"),  # mini fallback
        ]
    )

    result = generator.generate(
        prompt="Проаналізуй мій портфель",
        system_prompt="system",
        history=[],
        deployment="gpt-5.4-pro",
        chat_intent="analytical_rag",
    )

    assert result == "fallback-mini-answer"
    assert len(client.responses.calls) == 4
    assert [call["model"] for call in client.responses.calls[:3]] == ["gpt-5.4-pro"] * 3
    assert client.responses.calls[3]["model"] == "gpt-5.4-mini"


def test_generate_structured_reports_final_model_without_fallback(monkeypatch):
    monkeypatch.setattr(settings, "chat_llm_retry_enabled", False)
    generator, _ = _make_generator_with_stub([_message_response("mini-ok")])

    result = generator.generate_structured(
        prompt="Що таке ETF?",
        system_prompt="system",
        history=[],
        deployment="gpt-5.4-mini",
    )

    metadata = result.get("model_call_metadata")
    assert isinstance(metadata, dict)
    assert metadata["requested_deployment"] == "gpt-5.4-mini"
    assert metadata["final_deployment"] == "gpt-5.4-mini"
    assert metadata["fallback_used"] is False


def test_generate_structured_reports_fallback_to_mini_metadata(monkeypatch):
    monkeypatch.setattr(settings, "chat_llm_retry_enabled", False)
    generator, _ = _make_generator_with_stub(
        [
            _reasoning_only_response(),
            _reasoning_only_response(),
            _reasoning_only_response(),
            _message_response("fallback-mini-answer"),
        ]
    )

    result = generator.generate_structured(
        prompt="Проаналізуй мій портфель",
        system_prompt="system",
        history=[],
        deployment="gpt-5.4-pro",
        chat_intent="analytical_rag",
    )

    metadata = result.get("model_call_metadata")
    assert isinstance(metadata, dict)
    assert metadata["requested_deployment"] == "gpt-5.4-pro"
    assert metadata["final_deployment"] == "gpt-5.4-mini"
    assert metadata["fallback_used"] is True


def test_mini_empty_output_does_not_fallback_further(monkeypatch):
    monkeypatch.setattr(settings, "chat_llm_retry_enabled", False)

    generator, client = _make_generator_with_stub(
        [
            _reasoning_only_response(),
            _reasoning_only_response(),
            _reasoning_only_response(),
        ]
    )

    try:
        generator.generate(
            prompt="Що таке ETF?",
            system_prompt="system",
            history=[],
            deployment="gpt-5.4-mini",
            chat_intent="factual_rag",
        )
        assert False, "Expected GeneratorError"
    except GeneratorError as exc:
        assert "Empty final answer" in str(exc)

    assert len(client.responses.calls) == 3
    assert all(call["model"] == "gpt-5.4-mini" for call in client.responses.calls)


def test_empty_output_fallback_happens_only_advanced_to_default(monkeypatch):
    monkeypatch.setattr(settings, "chat_llm_retry_enabled", False)

    generator, client = _make_generator_with_stub(
        [
            _empty_non_reasoning_response(),  # pro initial -> no reasoning retries
            _message_response("mini-after-empty-fallback"),  # mini fallback
        ]
    )

    result = generator.generate(
        prompt="Analyze",
        system_prompt="system",
        history=[],
        deployment="gpt-5.4-pro",
        chat_intent="analytical_rag",
    )
    assert result == "mini-after-empty-fallback"
    assert [call["model"] for call in client.responses.calls] == [
        "gpt-5.4-pro",
        "gpt-5.4-mini",
    ]

    generator2, client2 = _make_generator_with_stub([_empty_non_reasoning_response()])
    try:
        generator2.generate(
            prompt="Analyze",
            system_prompt="system",
            history=[],
            deployment="gpt-5.4-mini",
            chat_intent="factual_rag",
        )
        assert False, "Expected GeneratorError for mini empty output"
    except GeneratorError:
        pass
    assert [call["model"] for call in client2.responses.calls] == ["gpt-5.4-mini"]


def test_generate_with_responses_logs_shape_on_empty_normalization(monkeypatch, caplog):
    monkeypatch.setattr(settings, "chat_llm_retry_enabled", False)

    generator, _ = _make_generator_with_stub(
        [
            _reasoning_only_response(),
            _reasoning_only_response(),
            _reasoning_only_response(),
        ]
    )

    try:
        generator._generate_with_responses_api(
            prompt="Analyze",
            system_prompt="system",
            history=[],
            deployment="gpt-5.4-mini",
            tools=None,
            max_tokens=400,
            temperature=0.1,
        )
        assert False, "Expected GeneratorError"
    except GeneratorError as exc:
        assert "Empty final answer" in str(exc)

    combined_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert (
        "Responses API returned empty normalized output after retries" in combined_logs
    )
    assert "response_shape=" in combined_logs


def test_mini_generation_uses_responses_create(monkeypatch):
    monkeypatch.setattr(settings, "chat_llm_retry_enabled", False)

    generator, client = _make_generator_with_stub([_message_response("mini-ok")])

    result = generator.generate(
        prompt="Що таке ETF?",
        system_prompt="system",
        history=[],
        deployment="gpt-5.4-mini",
    )

    assert result == "mini-ok"
    assert len(client.responses.calls) == 1
    assert client.responses.calls[0]["model"] == "gpt-5.4-mini"


def test_advanced_payload_sanitization_removes_temperature(monkeypatch):
    generator = Generator(use_mock=True)
    monkeypatch.setattr(settings, "chat_model_advanced_supports_temperature", False)

    sanitized, removed = generator._sanitize_responses_payload(
        payload={
            "model": "gpt-5.4-pro",
            "input": [{"role": "user", "content": "test"}],
            "temperature": 0.2,
        },
        deployment="gpt-5.4-pro",
        model_tier="advanced",
    )

    assert "temperature" not in sanitized
    assert "temperature" in removed


def test_advanced_payload_sanitization_removes_top_p_and_penalties(monkeypatch):
    generator = Generator(use_mock=True)
    monkeypatch.setattr(settings, "chat_model_advanced_supports_top_p", False)
    monkeypatch.setattr(settings, "chat_model_advanced_supports_penalties", False)

    sanitized, removed = generator._sanitize_responses_payload(
        payload={
            "model": "gpt-5.4-pro",
            "input": [{"role": "user", "content": "test"}],
            "top_p": 0.9,
            "frequency_penalty": 0.1,
            "presence_penalty": 0.2,
        },
        deployment="gpt-5.4-pro",
        model_tier="advanced",
    )

    assert "top_p" not in sanitized
    assert "frequency_penalty" not in sanitized
    assert "presence_penalty" not in sanitized
    assert {"top_p", "frequency_penalty", "presence_penalty"}.issubset(set(removed))


def test_default_payload_sanitization_keeps_temperature_when_supported(monkeypatch):
    generator = Generator(use_mock=True)
    monkeypatch.setattr(settings, "chat_model_default_supports_temperature", True)

    sanitized, removed = generator._sanitize_responses_payload(
        payload={
            "model": "gpt-5.4-mini",
            "input": [{"role": "user", "content": "test"}],
            "temperature": 0.2,
        },
        deployment="gpt-5.4-mini",
        model_tier="default",
    )

    assert sanitized["temperature"] == 0.2
    assert "temperature" not in removed


def test_pro_generation_uses_responses_create(monkeypatch):
    monkeypatch.setattr(settings, "chat_llm_retry_enabled", False)

    generator, client = _make_generator_with_stub([_message_response("pro-ok")])

    result = generator.generate(
        prompt="Проаналізуй мій портфель",
        system_prompt="system",
        history=[],
        deployment="gpt-5.4-pro",
    )

    assert result == "pro-ok"
    assert len(client.responses.calls) == 1
    assert client.responses.calls[0]["model"] == "gpt-5.4-pro"


def test_bad_request_on_advanced_triggers_one_fallback_to_mini(monkeypatch, caplog):
    monkeypatch.setattr(settings, "chat_llm_retry_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_retry_max_attempts", 3)
    caplog.set_level("DEBUG", logger="src.rag.generator")

    generator, client = _make_generator_with_stub(
        [
            _BadRequestLikeError(
                "Unsupported parameter: 'temperature' is not supported with this model.",
                param="temperature",
            ),
            _message_response("fallback-mini-after-bad-request"),
        ]
    )

    result = generator.generate(
        prompt="Проаналізуй мій портфель",
        system_prompt="system",
        history=[],
        deployment="gpt-5.4-pro",
        chat_intent="analytical_rag",
    )

    assert result == "fallback-mini-after-bad-request"
    assert [call["model"] for call in client.responses.calls] == [
        "gpt-5.4-pro",
        "gpt-5.4-mini",
    ]
    combined_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "advanced_bad_request_payload_fallback" in combined_logs
    assert "removed_payload_keys" in combined_logs


def test_bad_request_on_mini_raises_generator_error_without_fallback(monkeypatch):
    monkeypatch.setattr(settings, "chat_llm_retry_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_retry_max_attempts", 3)

    generator, client = _make_generator_with_stub(
        [
            _BadRequestLikeError(
                "Unsupported parameter: 'temperature' is not supported with this model.",
                param="temperature",
            ),
        ]
    )

    try:
        generator.generate(
            prompt="Що таке ETF?",
            system_prompt="system",
            history=[],
            deployment="gpt-5.4-mini",
            chat_intent="factual_rag",
        )
        assert False, "Expected GeneratorError"
    except GeneratorError as exc:
        assert "Unsupported parameter" in str(exc)

    assert [call["model"] for call in client.responses.calls] == ["gpt-5.4-mini"]


def test_bad_request_fallback_payload_is_sanitized_again(monkeypatch):
    monkeypatch.setattr(settings, "chat_llm_retry_enabled", False)
    monkeypatch.setattr(settings, "chat_model_default_supports_temperature", False)

    generator, client = _make_generator_with_stub(
        [
            _BadRequestLikeError(
                "Unsupported parameter: 'temperature' is not supported with this model.",
                param="temperature",
            ),
            _message_response("fallback-sanitized"),
        ]
    )

    sanitize_calls: list[tuple[str, str]] = []
    original_sanitize = generator._sanitize_responses_payload

    def tracking_sanitize(*, payload, deployment, model_tier):
        sanitize_calls.append((deployment, model_tier))
        return original_sanitize(
            payload=payload, deployment=deployment, model_tier=model_tier
        )

    monkeypatch.setattr(generator, "_sanitize_responses_payload", tracking_sanitize)

    result = generator.generate(
        prompt="Проаналізуй мій портфель",
        system_prompt="system",
        history=[],
        deployment="gpt-5.4-pro",
        chat_intent="analytical_rag",
    )

    assert result == "fallback-sanitized"
    assert sanitize_calls[0][0] == "gpt-5.4-pro"
    assert sanitize_calls[-1][0] == "gpt-5.4-mini"
    assert "temperature" not in client.responses.calls[-1]


def test_fallback_from_pro_to_mini_uses_responses_create(monkeypatch):
    monkeypatch.setattr(settings, "chat_llm_retry_enabled", False)

    generator, client = _make_generator_with_stub(
        [_message_response("fallback-mini-ok")]
    )
    attempted_deployments: list[str] = []

    def fake_invoke_with_retry(
        call, *, deployment, operation, timeout_seconds=None, **kwargs
    ):  # noqa: ARG001
        attempted_deployments.append(deployment)
        if deployment == "gpt-5.4-pro":
            raise LLMServiceUnavailableError(
                attempts=1,
                deployment="gpt-5.4-pro",
                operation=operation,
                last_error=Exception("timeout"),
            )
        return call()

    monkeypatch.setattr(generator, "_invoke_with_retry", fake_invoke_with_retry)

    result = generator.generate(
        prompt="Проаналізуй мій портфель",
        system_prompt="system",
        history=[],
        deployment="gpt-5.4-pro",
    )

    assert result == "fallback-mini-ok"
    assert attempted_deployments[0] == "gpt-5.4-pro"
    assert attempted_deployments[-1] == "gpt-5.4-mini"
    assert len(client.responses.calls) == 1
    assert client.responses.calls[0]["model"] == "gpt-5.4-mini"


def test_adaptive_timeout_prefers_live_price_when_intent_provided(monkeypatch):
    generator = Generator(use_mock=True)
    monkeypatch.setattr(settings, "chat_llm_call_timeout_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_timeout_default_seconds", 30.0)
    monkeypatch.setattr(settings, "chat_llm_timeout_advanced_seconds", 60.0)
    monkeypatch.setattr(settings, "chat_llm_timeout_live_price_seconds", 15.0)
    monkeypatch.setattr(settings, "chat_llm_timeout_factual_seconds", 30.0)
    monkeypatch.setattr(settings, "chat_llm_timeout_analytical_seconds", 60.0)
    monkeypatch.setattr(settings, "chat_llm_timeout_tool_extra_seconds", 4.0)

    timeout_seconds = generator._resolve_call_timeout_seconds(
        deployment="gpt-5.4-pro",
        operation="responses_completion",
        chat_intent="pure_live_price",
    )
    assert timeout_seconds == 15.0


def test_adaptive_timeout_falls_back_to_deployment_based_when_intent_missing(
    monkeypatch,
):
    generator = Generator(use_mock=True)
    generator.advanced_deployment = "gpt-5.4-pro"
    monkeypatch.setattr(settings, "chat_llm_call_timeout_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_timeout_default_seconds", 30.0)
    monkeypatch.setattr(settings, "chat_llm_timeout_advanced_seconds", 60.0)
    monkeypatch.setattr(settings, "chat_llm_timeout_tool_extra_seconds", 4.0)

    advanced_timeout = generator._resolve_call_timeout_seconds(
        deployment="gpt-5.4-pro",
        operation="responses_completion",
        chat_intent=None,
    )
    default_timeout = generator._resolve_call_timeout_seconds(
        deployment="gpt-5.4-mini",
        operation="responses_completion",
        chat_intent=None,
    )
    assert advanced_timeout == 60.0
    assert default_timeout == 30.0


def test_invoke_with_retry_succeeds_after_transient_failures(monkeypatch):
    monkeypatch.setattr(settings, "chat_llm_retry_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_retry_max_attempts", 3)
    monkeypatch.setattr(settings, "chat_llm_retry_initial_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "chat_llm_retry_backoff_factor", 2.0)
    monkeypatch.setattr(settings, "chat_llm_retry_max_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "chat_llm_retry_jitter_seconds", 0.0)

    generator = Generator(use_mock=True)
    attempts = {"count": 0}

    def flaky_call():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise Exception("timeout while calling azure")
        return "ok"

    result = generator._invoke_with_retry(
        flaky_call,
        deployment="gpt-5.4-mini",
        operation="responses_completion",
    )

    assert result == "ok"
    assert attempts["count"] == 3


def test_invoke_with_retry_raises_service_unavailable_after_exhaustion(monkeypatch):
    monkeypatch.setattr(settings, "chat_llm_retry_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_retry_max_attempts", 3)
    monkeypatch.setattr(settings, "chat_llm_retry_initial_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "chat_llm_retry_backoff_factor", 2.0)
    monkeypatch.setattr(settings, "chat_llm_retry_max_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "chat_llm_retry_jitter_seconds", 0.0)

    generator = Generator(use_mock=True)
    attempts = {"count": 0}

    def always_fails():
        attempts["count"] += 1
        raise Exception("503 service unavailable")

    try:
        generator._invoke_with_retry(
            always_fails,
            deployment="gpt-5.4-mini",
            operation="responses_completion",
        )
        assert False, "Expected LLMServiceUnavailableError"
    except LLMServiceUnavailableError as exc:
        assert exc.attempts == 3
        assert attempts["count"] == 3
