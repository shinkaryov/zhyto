"""
Generator module for LLM-based response generation.

Chat generation is unified on Azure OpenAI Responses API.
Embeddings remain separate and are not handled here.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
import json
import random
import time
from typing import Any, Callable, Optional

from openai import AzureOpenAI

from src.rag.market_price_tool import (
    MARKET_PRICE_TOOL_NAME,
    execute_get_current_market_price,
    get_market_price_tool_definitions,
)
from src.rag.portfolio_draft_tool import (
    DRAFT_PORTFOLIO_TRANSACTION_TOOL_NAME,
    execute_draft_portfolio_transaction,
    get_portfolio_draft_tool_definitions,
)
from src.utils.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)
_pending_transaction_draft_ctx: ContextVar[Optional[dict[str, Any]]] = ContextVar(
    "pending_transaction_draft",
    default=None,
)
_llm_call_metadata_ctx: ContextVar[Optional[dict[str, Any]]] = ContextVar(
    "llm_call_metadata",
    default=None,
)

try:
    from openai import (
        APIConnectionError,
        APITimeoutError,
        BadRequestError,
        InternalServerError,
        RateLimitError,
    )

    _RETRYABLE_OPENAI_EXCEPTIONS = (
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
        RateLimitError,
    )
    _BAD_REQUEST_OPENAI_EXCEPTIONS = (BadRequestError,)
except (
    Exception
):  # pragma: no cover - openai package structure may differ across environments.
    _RETRYABLE_OPENAI_EXCEPTIONS = tuple()
    _BAD_REQUEST_OPENAI_EXCEPTIONS = tuple()


class GeneratorError(Exception):
    """Custom exception for generator errors."""

    pass


class LLMServiceUnavailableError(GeneratorError):
    """Raised when transient LLM errors persist after retry attempts."""

    def __init__(
        self, *, attempts: int, deployment: str, operation: str, last_error: Exception
    ):
        self.attempts = attempts
        self.deployment = deployment
        self.operation = operation
        self.last_error = last_error
        super().__init__(
            "LLM service unavailable after "
            f"{attempts} attempt(s) for operation='{operation}' on deployment='{deployment}': {last_error}"
        )


class LLMBadRequestPayloadError(GeneratorError):
    """Raised for model/payload compatibility errors (HTTP 400) on Responses API calls."""

    def __init__(
        self,
        *,
        deployment: str,
        operation: str,
        error_class: str,
        error_message: str,
        error_param: Optional[str] = None,
        status_code: Optional[int] = None,
        cause: Optional[Exception] = None,
    ):
        self.deployment = deployment
        self.operation = operation
        self.error_class = error_class
        self.error_message = error_message
        self.error_param = error_param
        self.status_code = status_code
        self.cause = cause
        super().__init__(
            "LLM bad request on deployment='"
            f"{deployment}' operation='{operation}': "
            f"{error_message}" + (f" (param={error_param})" if error_param else "")
        )


@dataclass(frozen=True)
class ModelCapabilities:
    supports_temperature: bool
    supports_top_p: bool
    supports_penalties: bool
    supports_tools: bool
    supports_reasoning: bool


TOOL_CATEGORY_LIVE_MARKET = "live_market_tools"
TOOL_CATEGORY_PORTFOLIO_ACTION = "portfolio_action_tools"
_SUPPORTED_TOOL_CATEGORIES = {
    TOOL_CATEGORY_LIVE_MARKET,
    TOOL_CATEGORY_PORTFOLIO_ACTION,
}


def _tool_definitions_for_categories(tool_categories: set[str]) -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    if TOOL_CATEGORY_LIVE_MARKET in tool_categories:
        definitions.extend(get_market_price_tool_definitions())
    if TOOL_CATEGORY_PORTFOLIO_ACTION in tool_categories:
        definitions.extend(get_portfolio_draft_tool_definitions())
    return definitions


def _normalize_tool_categories(
    *,
    tool_categories: Optional[set[str] | list[str] | tuple[str, ...]],
    enable_market_price_tool: bool,
) -> set[str]:
    if tool_categories:
        normalized = {
            str(category).strip().lower()
            for category in tool_categories
            if str(category).strip()
        }
        return {
            category
            for category in normalized
            if category in _SUPPORTED_TOOL_CATEGORIES
        }

    # Backward compatibility: legacy boolean enabled all chat tools.
    if enable_market_price_tool:
        return set(_SUPPORTED_TOOL_CATEGORIES)
    return set()


class Generator:
    """Class for generating responses using Azure OpenAI Responses API."""

    def __init__(self, use_mock: Optional[bool] = None):
        """
        Initialize the Generator.

        Args:
            use_mock: Whether to use mock generation. Defaults to settings.use_mock_openai.
        """
        self.use_mock = use_mock if use_mock is not None else settings.use_mock_openai
        self.azure_client: Optional[AzureOpenAI] = None
        self.default_deployment: str = (
            settings.azure_openai_default_deployment
            or settings.azure_openai_deployment_name
            or "gpt-5.4-mini"
        ).strip()
        self.advanced_deployment: str = (
            settings.azure_openai_advanced_deployment or ""
        ).strip()
        self.advanced_api_preference: str = (
            (settings.azure_openai_advanced_api_preference or "responses")
            .strip()
            .lower()
        )

        if self.use_mock:
            logger.info("Using mock generator for development")
        else:
            logger.info("Initializing Azure OpenAI generator")
            self._initialize_azure_openai()
            logger.info(
                "LLM routing config: default_deployment=%s advanced_deployment=%s "
                "advanced_api_preference=%s api_version=%s api_mode=responses",
                self.default_deployment,
                self.advanced_deployment or "<empty>",
                self.advanced_api_preference,
                settings.azure_openai_api_version,
            )

    def _initialize_azure_openai(self) -> None:
        """Initialize Azure OpenAI client for Responses API calls."""
        try:
            if not settings.azure_openai_api_key:
                raise GeneratorError(
                    "Azure OpenAI API key not configured. "
                    "Set AZURE_OPENAI_API_KEY environment variable."
                )

            if not settings.azure_openai_endpoint:
                raise GeneratorError(
                    "Azure OpenAI endpoint not configured. "
                    "Set AZURE_OPENAI_ENDPOINT environment variable."
                )

            if not self.default_deployment:
                raise GeneratorError(
                    "Azure OpenAI deployment name not configured. "
                    "Set AZURE_OPENAI_DEFAULT_DEPLOYMENT or AZURE_OPENAI_DEPLOYMENT_NAME."
                )

            sdk_timeout_seconds = self._resolve_client_timeout_seconds()
            self.azure_client = AzureOpenAI(
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version,
                azure_endpoint=settings.azure_openai_endpoint,
                timeout=sdk_timeout_seconds,
            )
            logger.info(
                "Azure OpenAI generator successfully initialized (api_mode=responses sdk_timeout=%s)",
                f"{sdk_timeout_seconds:.2f}s" if sdk_timeout_seconds else "default",
            )

        except GeneratorError:
            raise
        except Exception as e:
            raise GeneratorError(f"Failed to initialize Azure OpenAI: {e}") from e

    def _resolve_client_timeout_seconds(self) -> Optional[float]:
        if not bool(settings.chat_llm_call_timeout_enabled):
            return None

        default_timeout = max(float(settings.chat_llm_timeout_default_seconds), 0.0)
        advanced_timeout = max(float(settings.chat_llm_timeout_advanced_seconds), 0.0)
        tool_extra = max(float(settings.chat_llm_timeout_tool_extra_seconds), 0.0)
        base_timeout = max(default_timeout, advanced_timeout)
        if base_timeout <= 0:
            return None
        return base_timeout + tool_extra

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[list[dict]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        enable_market_price_tool: bool = False,
        tool_categories: Optional[set[str] | list[str] | tuple[str, ...]] = None,
        deployment: Optional[str] = None,
        chat_intent: Optional[str] = None,
    ) -> str:
        """
        Generate a response using the LLM.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system prompt to set the LLM context.
            history: Optional chat history.
            max_tokens: Maximum tokens in the response.
            temperature: Temperature for response generation (0-1).
            enable_market_price_tool: Legacy compatibility flag (enables all chat tools when no categories are passed).
            deployment: Optional Azure deployment override for this request.

        Returns:
            Generated response text.
        """
        result = self.generate_structured(
            prompt=prompt,
            system_prompt=system_prompt,
            history=history,
            max_tokens=max_tokens,
            temperature=temperature,
            enable_market_price_tool=enable_market_price_tool,
            tool_categories=tool_categories,
            deployment=deployment,
            chat_intent=chat_intent,
        )
        return result["message"]

    def generate_structured(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[list[dict]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        enable_market_price_tool: bool = False,
        tool_categories: Optional[set[str] | list[str] | tuple[str, ...]] = None,
        deployment: Optional[str] = None,
        chat_intent: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Generate response with optional structured side-channel data.

        Returns:
            {
              "message": str,
              "pending_transaction_draft": Optional[dict]
              "model_call_metadata": Optional[dict]
            }
        """
        resolved_requested_deployment = (deployment or self.default_deployment).strip()
        draft_token = _pending_transaction_draft_ctx.set(None)
        metadata_token = _llm_call_metadata_ctx.set(
            {
                "requested_deployment": resolved_requested_deployment or None,
                "final_deployment": None,
                "fallback_used": False,
            }
        )
        try:
            message = self._generate_impl(
                prompt=prompt,
                system_prompt=system_prompt,
                history=history,
                max_tokens=max_tokens,
                temperature=temperature,
                enable_market_price_tool=enable_market_price_tool,
                tool_categories=tool_categories,
                deployment=deployment,
                chat_intent=chat_intent,
            )
            pending_draft = _pending_transaction_draft_ctx.get()
            call_metadata_raw = _llm_call_metadata_ctx.get()
            call_metadata: Optional[dict[str, Any]] = None
            if isinstance(call_metadata_raw, dict):
                requested_deployment = (
                    str(call_metadata_raw.get("requested_deployment") or "").strip()
                    or None
                )
                final_deployment = (
                    str(call_metadata_raw.get("final_deployment") or "").strip() or None
                )
                fallback_used = bool(call_metadata_raw.get("fallback_used"))
                if requested_deployment and final_deployment:
                    fallback_used = fallback_used or (
                        requested_deployment != final_deployment
                    )
                call_metadata = {
                    "requested_deployment": requested_deployment,
                    "final_deployment": final_deployment,
                    "fallback_used": fallback_used,
                }
            return {
                "message": message,
                "pending_transaction_draft": pending_draft,
                "model_call_metadata": call_metadata,
            }
        finally:
            _pending_transaction_draft_ctx.reset(draft_token)
            _llm_call_metadata_ctx.reset(metadata_token)

    def _generate_impl(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[list[dict]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        enable_market_price_tool: bool = False,
        tool_categories: Optional[set[str] | list[str] | tuple[str, ...]] = None,
        deployment: Optional[str] = None,
        chat_intent: Optional[str] = None,
    ) -> str:
        if self.use_mock:
            return self._mock_generate(prompt, system_prompt)

        target_deployment = (deployment or self.default_deployment).strip()
        try:
            resolved_tool_categories = _normalize_tool_categories(
                tool_categories=tool_categories,
                enable_market_price_tool=enable_market_price_tool,
            )
            logger.info(
                "LLM dispatch: deployment=%s api_mode=responses intent=%s legacy_enable_all_tools=%s tool_categories=%s",
                target_deployment,
                chat_intent or "<none>",
                enable_market_price_tool,
                sorted(resolved_tool_categories),
            )
            return self._generate_with_responses_api(
                prompt=prompt,
                system_prompt=system_prompt,
                history=history,
                deployment=target_deployment,
                tools=(
                    _tool_definitions_for_categories(resolved_tool_categories)
                    if resolved_tool_categories
                    else None
                ),
                max_tokens=max_tokens,
                temperature=temperature,
                chat_intent=chat_intent,
            )
        except LLMBadRequestPayloadError as exc:
            if self._should_fallback_to_default_on_bad_request(target_deployment):
                fallback_reason = "advanced_bad_request_payload_fallback"
                logger.warning(
                    "LLM fallback triggered: reason=%s from_deployment=%s to_deployment=%s "
                    "error_class=%s error_param=%s error_message=%s",
                    fallback_reason,
                    target_deployment,
                    self.default_deployment,
                    exc.error_class,
                    exc.error_param or "<none>",
                    exc.error_message,
                )
                return self._generate_impl(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    history=history,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    enable_market_price_tool=enable_market_price_tool,
                    tool_categories=tool_categories,
                    deployment=self.default_deployment,
                    chat_intent=chat_intent,
                )
            raise GeneratorError(
                f"Azure OpenAI call failed: {exc.error_message}"
            ) from exc
        except LLMServiceUnavailableError as exc:
            if self._should_fallback_to_default_on_runtime_error(
                exc, target_deployment
            ):
                logger.warning(
                    "LLM fallback triggered: reason=runtime_unavailable from_deployment=%s to_deployment=%s "
                    "error_class=%s error_message=%s",
                    target_deployment,
                    self.default_deployment,
                    type(exc).__name__,
                    exc,
                )
                return self._generate_impl(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    history=history,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    enable_market_price_tool=enable_market_price_tool,
                    tool_categories=tool_categories,
                    deployment=self.default_deployment,
                    chat_intent=chat_intent,
                )
            raise
        except GeneratorError:
            raise
        except Exception as e:
            wrapped = GeneratorError(str(e))
            if self._should_fallback_to_default_on_runtime_error(
                wrapped, target_deployment
            ):
                logger.warning(
                    "LLM fallback triggered: reason=runtime_unavailable from_deployment=%s to_deployment=%s "
                    "error_class=%s error_message=%s",
                    target_deployment,
                    self.default_deployment,
                    type(wrapped).__name__,
                    wrapped,
                )
                return self._generate_impl(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    history=history,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    enable_market_price_tool=enable_market_price_tool,
                    tool_categories=tool_categories,
                    deployment=self.default_deployment,
                    chat_intent=chat_intent,
                )
            logger.error("Azure generation failed: %s", e)
            raise wrapped from e

    # Backward-compatible wrappers: keep method names stable while using Responses API internally.
    def _generate_azure_responses(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[list[dict]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        deployment: Optional[str] = None,
        chat_intent: Optional[str] = None,
    ) -> str:
        return self._generate_with_responses_api(
            prompt=prompt,
            system_prompt=system_prompt,
            history=history,
            deployment=(deployment or self.default_deployment).strip(),
            tools=None,
            max_tokens=max_tokens,
            temperature=temperature,
            chat_intent=chat_intent,
        )

    def _generate_azure_responses_with_market_tool(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[list[dict]] = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        max_tool_rounds: int = 3,
        deployment: Optional[str] = None,
        chat_intent: Optional[str] = None,
    ) -> str:
        return self._generate_with_responses_api(
            prompt=prompt,
            system_prompt=system_prompt,
            history=history,
            deployment=(deployment or self.default_deployment).strip(),
            tools=_tool_definitions_for_categories(set(_SUPPORTED_TOOL_CATEGORIES)),
            max_tokens=max_tokens,
            temperature=temperature,
            max_tool_rounds=max_tool_rounds,
            chat_intent=chat_intent,
        )

    def _generate_with_responses_api(
        self,
        *,
        prompt: str,
        system_prompt: Optional[str],
        history: Optional[list[dict]],
        deployment: str,
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        timeout_seconds: Optional[float] = None,
        max_tool_rounds: int = 3,
        chat_intent: Optional[str] = None,
        allow_empty_output_fallback: bool = True,
    ) -> str:
        input_items = self._build_responses_input(
            prompt=prompt,
            system_prompt=system_prompt,
            history=history,
        )
        responses_tools = self._to_responses_tools(tools or [])
        operation_prefix = (
            "responses_tool_completion" if responses_tools else "responses_completion"
        )

        response = self._call_responses_api(
            deployment=deployment,
            input_items=input_items,
            operation=f"{operation_prefix}_initial",
            tools=responses_tools if responses_tools else None,
            tool_choice=tool_choice,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            chat_intent=chat_intent,
            is_reasoning_retry=False,
        )

        rounds = 0
        while responses_tools and rounds < max_tool_rounds:
            function_calls = self._extract_responses_function_calls(response)
            if not function_calls:
                break

            tool_outputs: list[dict[str, Any]] = []
            for call in function_calls:
                arguments_raw = call.get("arguments", "{}")
                try:
                    arguments = (
                        json.loads(arguments_raw)
                        if isinstance(arguments_raw, str)
                        else {}
                    )
                except json.JSONDecodeError:
                    arguments = {}

                tool_result = self._execute_tool_call(
                    {
                        "name": call["name"],
                        "args": arguments,
                    }
                )
                self._capture_pending_transaction_draft(tool_result)
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": json.dumps(tool_result, ensure_ascii=False),
                    }
                )

            response = self._call_responses_api(
                deployment=deployment,
                previous_response_id=self._node_get(response, "id"),
                input_items=tool_outputs,
                tools=responses_tools,
                tool_choice=tool_choice,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
                operation=f"{operation_prefix}_round_{rounds + 1}",
                chat_intent=chat_intent,
                is_reasoning_retry=False,
            )
            rounds += 1

        if responses_tools and self._extract_responses_function_calls(response):
            raise GeneratorError(
                "Exceeded maximum responses tool rounds without final answer"
            )

        normalized_content = self._normalize_responses_content(response)
        output_types = self._extract_responses_output_types(response)
        logger.info(
            "LLM normalization: deployment=%s operation=%s output_types=%s normalized_len=%d",
            deployment,
            operation_prefix,
            output_types,
            len(normalized_content),
        )
        if normalized_content:
            return normalized_content

        reasoning_retry_budget = self._max_reasoning_retries_for_response(output_types)
        current_response = response
        current_output_types = output_types
        current_max_tokens = self._bump_retry_tokens(max_tokens)
        for retry_index in range(1, reasoning_retry_budget + 1):
            retry_instruction = self._build_final_answer_retry_instruction()
            retry_input: list[dict[str, Any]]
            retry_previous_response_id: Optional[str]

            if responses_tools and self._node_get(current_response, "id"):
                retry_input = [{"role": "user", "content": retry_instruction}]
                retry_previous_response_id = str(self._node_get(current_response, "id"))
            else:
                retry_input = [
                    *input_items,
                    {"role": "user", "content": retry_instruction},
                ]
                retry_previous_response_id = None

            logger.warning(
                "Reasoning-only response detected. deployment=%s operation=%s retry=%d/%d output_types=%s",
                deployment,
                operation_prefix,
                retry_index,
                reasoning_retry_budget,
                current_output_types,
            )

            current_response = self._call_responses_api(
                deployment=deployment,
                previous_response_id=retry_previous_response_id,
                input_items=retry_input,
                tools=responses_tools if responses_tools else None,
                tool_choice=tool_choice,
                max_tokens=current_max_tokens,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
                operation=f"{operation_prefix}_final_message_retry_{retry_index}",
                chat_intent=chat_intent,
                is_reasoning_retry=True,
            )
            normalized_retry = self._normalize_responses_content(current_response)
            current_output_types = self._extract_responses_output_types(
                current_response
            )
            logger.info(
                "LLM normalization retry: deployment=%s operation=%s output_types=%s normalized_len=%d",
                deployment,
                f"{operation_prefix}_final_message_retry_{retry_index}",
                current_output_types,
                len(normalized_retry),
            )
            if normalized_retry:
                return normalized_retry

        response_shape = self._describe_response_shape(current_response)
        logger.error(
            "Responses API returned empty normalized output after retries. deployment=%s operation=%s output_types=%s response_shape=%s",
            deployment,
            operation_prefix,
            current_output_types,
            response_shape,
        )

        if self._should_fallback_on_empty_output(
            deployment=deployment,
            allow_fallback=allow_empty_output_fallback,
        ):
            fallback_reason = "advanced_empty_output_fallback"
            logger.warning(
                "LLM fallback triggered: reason=%s from_deployment=%s to_deployment=%s error_class=%s error_message=%s",
                fallback_reason,
                deployment,
                self.default_deployment,
                GeneratorError.__name__,
                "Empty normalized output after reasoning-only retries",
            )
            return self._generate_with_responses_api(
                prompt=prompt,
                system_prompt=system_prompt,
                history=history,
                deployment=self.default_deployment,
                tools=tools,
                tool_choice=tool_choice,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
                max_tool_rounds=max_tool_rounds,
                chat_intent=chat_intent,
                allow_empty_output_fallback=False,
            )

        raise GeneratorError(
            "Empty final answer from Azure OpenAI Responses API after reasoning-only retries"
        )

    @staticmethod
    def _bump_retry_tokens(max_tokens: Optional[int]) -> Optional[int]:
        if max_tokens is None:
            return None
        if max_tokens <= 0:
            return max_tokens
        if max_tokens < 800:
            return max_tokens + 300
        return int(max_tokens * 1.25)

    @staticmethod
    def _max_reasoning_retries_for_response(output_types: list[str]) -> int:
        normalized = {str(item or "").lower().strip() for item in output_types}
        if "reasoning" in normalized:
            return 2
        return 0

    def _should_fallback_on_empty_output(
        self, *, deployment: str, allow_fallback: bool
    ) -> bool:
        if not allow_fallback:
            return False
        default = (self.default_deployment or "").strip()
        target = (deployment or "").strip()
        if not default or not target or target == default:
            return False
        return self._is_advanced_deployment(target)

    def _is_advanced_deployment(self, deployment: str) -> bool:
        target = (deployment or "").strip().lower()
        if not target:
            return False
        advanced = (self.advanced_deployment or "").strip().lower()
        if advanced:
            return target == advanced
        return target.endswith("-pro")

    def _resolve_model_tier(self, deployment: str) -> str:
        return "advanced" if self._is_advanced_deployment(deployment) else "default"

    def _resolve_model_capabilities(self, model_tier: str) -> ModelCapabilities:
        tier = (model_tier or "").strip().lower()
        if tier == "advanced":
            return ModelCapabilities(
                supports_temperature=bool(
                    settings.chat_model_advanced_supports_temperature
                ),
                supports_top_p=bool(settings.chat_model_advanced_supports_top_p),
                supports_penalties=bool(
                    settings.chat_model_advanced_supports_penalties
                ),
                supports_tools=bool(settings.chat_model_advanced_supports_tools),
                supports_reasoning=bool(
                    settings.chat_model_advanced_supports_reasoning
                ),
            )

        return ModelCapabilities(
            supports_temperature=bool(settings.chat_model_default_supports_temperature),
            supports_top_p=bool(settings.chat_model_default_supports_top_p),
            supports_penalties=bool(settings.chat_model_default_supports_penalties),
            supports_tools=bool(settings.chat_model_default_supports_tools),
            supports_reasoning=bool(settings.chat_model_default_supports_reasoning),
        )

    def _sanitize_responses_payload(
        self,
        *,
        payload: dict[str, Any],
        deployment: str,
        model_tier: str,
    ) -> tuple[dict[str, Any], list[str]]:
        capabilities = self._resolve_model_capabilities(model_tier)
        unsupported_keys: set[str] = set()
        if not capabilities.supports_temperature:
            unsupported_keys.add("temperature")
        if not capabilities.supports_top_p:
            unsupported_keys.add("top_p")
        if not capabilities.supports_penalties:
            unsupported_keys.update({"frequency_penalty", "presence_penalty"})
        if not capabilities.supports_tools:
            unsupported_keys.update({"tools", "tool_choice"})

        sanitized: dict[str, Any] = {}
        removed_payload_keys: list[str] = []
        for key, value in payload.items():
            if value is None:
                removed_payload_keys.append(key)
                continue
            if key in unsupported_keys:
                removed_payload_keys.append(key)
                continue
            sanitized[key] = value

        logger.debug(
            "Responses payload sanitized: deployment=%s model_tier=%s removed_payload_keys=%s",
            deployment,
            model_tier,
            sorted(set(removed_payload_keys)),
        )
        return sanitized, removed_payload_keys

    def _call_responses_api(
        self,
        *,
        deployment: str,
        input_items: list[dict[str, Any]],
        operation: str,
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        timeout_seconds: Optional[float] = None,
        previous_response_id: Optional[str] = None,
        chat_intent: Optional[str] = None,
        is_reasoning_retry: bool = False,
    ) -> Any:
        effective_timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else self._resolve_call_timeout_seconds(
                deployment=deployment,
                operation=operation,
                chat_intent=chat_intent,
            )
        )
        client = self._get_azure_client()
        runtime_client = (
            client.with_options(timeout=effective_timeout)
            if effective_timeout
            else client
        )
        model_tier = self._resolve_model_tier(deployment)

        payload: dict[str, Any] = {
            "model": deployment,
            "input": input_items,
        }
        if max_tokens is not None:
            payload["max_output_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if frequency_penalty is not None:
            payload["frequency_penalty"] = frequency_penalty
        if presence_penalty is not None:
            payload["presence_penalty"] = presence_penalty
        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id

        payload, _ = self._sanitize_responses_payload(
            payload=payload,
            deployment=deployment,
            model_tier=model_tier,
        )

        logger.info(
            "LLM dispatch: deployment=%s model_tier=%s intent=%s api_mode=responses operation=%s timeout_seconds=%s is_reasoning_retry=%s",
            deployment,
            model_tier,
            chat_intent or "<none>",
            operation,
            f"{effective_timeout:.2f}" if effective_timeout else "default",
            is_reasoning_retry,
        )

        started_at = time.perf_counter()
        response = self._invoke_with_retry(
            lambda: runtime_client.responses.create(**payload),
            deployment=deployment,
            operation=operation,
            timeout_seconds=effective_timeout,
            model_tier=model_tier,
            chat_intent=chat_intent,
            is_reasoning_retry=is_reasoning_retry,
        )
        latency_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "LLM response received: deployment=%s model_tier=%s intent=%s operation=%s output_types=%s latency_ms=%.2f",
            deployment,
            model_tier,
            chat_intent or "<none>",
            operation,
            self._extract_responses_output_types(response),
            latency_ms,
        )
        call_metadata = _llm_call_metadata_ctx.get()
        if isinstance(call_metadata, dict):
            requested_deployment = (
                str(call_metadata.get("requested_deployment") or "").strip()
                or deployment
            )
            call_metadata["requested_deployment"] = requested_deployment
            call_metadata["final_deployment"] = deployment
            if deployment != requested_deployment:
                call_metadata["fallback_used"] = True
        return response

    def _should_fallback_to_default_on_runtime_error(
        self, exc: Exception, target_deployment: str
    ) -> bool:
        default = (self.default_deployment or "").strip()
        target = (target_deployment or "").strip()
        if not default or not target or target == default:
            return False

        advanced = (self.advanced_deployment or "").strip()
        if advanced and target != advanced:
            return False

        if isinstance(exc, LLMServiceUnavailableError):
            return True

        return self._is_retryable_llm_exception(exc)

    def _should_fallback_to_default_on_bad_request(
        self, target_deployment: str
    ) -> bool:
        default = (self.default_deployment or "").strip()
        target = (target_deployment or "").strip()
        if not default or not target or target == default:
            return False
        return self._is_advanced_deployment(target)

    def _get_azure_client(self) -> AzureOpenAI:
        if not self.azure_client:
            raise GeneratorError("Azure OpenAI client not initialized")
        return self.azure_client

    @staticmethod
    def _build_responses_input(
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[list[dict]] = None,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if system_prompt:
            items.append({"role": "system", "content": system_prompt})

        if history:
            for msg in history:
                role = msg.get("role")
                content = msg.get("content")
                if role in {"user", "assistant"} and isinstance(content, str):
                    items.append({"role": role, "content": content})

        items.append({"role": "user", "content": prompt})
        return items

    @staticmethod
    def _build_final_answer_retry_instruction() -> str:
        return (
            "You must produce a final answer message for the user. "
            "Do not return reasoning only."
        )

    @staticmethod
    def _to_responses_tools(chat_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Convert chat/completions tool schema into Responses API function schema.
        """
        converted: list[dict[str, Any]] = []
        for tool in chat_tools:
            if not isinstance(tool, dict):
                continue
            function_block = tool.get("function")
            if isinstance(function_block, dict):
                converted.append(
                    {
                        "type": "function",
                        "name": function_block.get("name"),
                        "description": function_block.get("description"),
                        "parameters": function_block.get(
                            "parameters", {"type": "object", "properties": {}}
                        ),
                    }
                )
                continue
            if tool.get("type") == "function":
                converted.append(tool)
        return converted

    @classmethod
    def _normalize_responses_content(cls, response: Any) -> str:
        text_parts: list[str] = []

        output_text = cls._node_get(response, "output_text")
        text_parts.extend(cls._collect_node_text(output_text, allow_refusal=False))

        if not text_parts:
            text_parts.extend(
                cls._extract_message_text_parts(response, allow_refusal=False)
            )

        if not text_parts:
            choices = cls._node_get(response, "choices")
            if isinstance(choices, (list, tuple)):
                for choice in choices:
                    message = cls._node_get(choice, "message")
                    text_parts.extend(
                        cls._collect_node_text(
                            cls._node_get(message, "content"), allow_refusal=False
                        )
                    )

        if not text_parts:
            text_parts.extend(cls._collect_node_text(output_text, allow_refusal=True))
            if not text_parts:
                text_parts.extend(
                    cls._extract_message_text_parts(response, allow_refusal=True)
                )

        if not text_parts:
            return ""

        deduped: list[str] = []
        seen: set[str] = set()
        for part in text_parts:
            normalized = (part or "").strip()
            if not normalized:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return "\n".join(deduped).strip()

    @classmethod
    def _extract_message_text_parts(
        cls, response: Any, *, allow_refusal: bool
    ) -> list[str]:
        output = cls._node_get(response, "output")
        if not isinstance(output, (list, tuple)):
            return []

        parts: list[str] = []
        for item in output:
            item_type = cls._node_type(item)
            if item_type in {
                "reasoning",
                "function_call",
                "function_call_output",
                "tool_call",
                "tool_result",
            }:
                continue
            if item_type == "refusal" and not allow_refusal:
                continue

            parts.extend(
                cls._collect_node_text(
                    cls._node_get(item, "content"), allow_refusal=allow_refusal
                )
            )
            parts.extend(
                cls._collect_node_text(
                    cls._node_get(item, "text"), allow_refusal=allow_refusal
                )
            )
            parts.extend(
                cls._collect_node_text(
                    cls._node_get(item, "value"), allow_refusal=allow_refusal
                )
            )
            if allow_refusal:
                parts.extend(
                    cls._collect_node_text(
                        cls._node_get(item, "refusal"), allow_refusal=True
                    )
                )
        return parts

    @classmethod
    def _collect_node_text(
        cls, node: Any, *, allow_refusal: bool, _depth: int = 0
    ) -> list[str]:
        if node is None or _depth > 8:
            return []

        if isinstance(node, str):
            stripped = node.strip()
            return [stripped] if stripped else []

        if isinstance(node, (int, float)):
            return [str(node)]

        if isinstance(node, (list, tuple)):
            parts: list[str] = []
            for item in node:
                parts.extend(
                    cls._collect_node_text(
                        item, allow_refusal=allow_refusal, _depth=_depth + 1
                    )
                )
            return parts

        if isinstance(node, dict):
            node_type = str(node.get("type", "")).lower().strip()
            if node_type in {
                "reasoning",
                "function_call",
                "function_call_output",
                "tool_call",
                "tool_result",
            }:
                return []
            if node_type == "refusal" and not allow_refusal:
                return []

            parts: list[str] = []
            for key in ("output_text", "text", "value", "content", "message"):
                if key in node:
                    parts.extend(
                        cls._collect_node_text(
                            node.get(key),
                            allow_refusal=allow_refusal,
                            _depth=_depth + 1,
                        )
                    )
            if allow_refusal and "refusal" in node:
                parts.extend(
                    cls._collect_node_text(
                        node.get("refusal"), allow_refusal=True, _depth=_depth + 1
                    )
                )
            return parts

        node_type = cls._node_type(node)
        if node_type in {
            "reasoning",
            "function_call",
            "function_call_output",
            "tool_call",
            "tool_result",
        }:
            return []
        if node_type == "refusal" and not allow_refusal:
            return []

        parts: list[str] = []
        for attr in ("output_text", "text", "value", "content", "message"):
            if hasattr(node, attr):
                parts.extend(
                    cls._collect_node_text(
                        getattr(node, attr),
                        allow_refusal=allow_refusal,
                        _depth=_depth + 1,
                    )
                )
        if allow_refusal and hasattr(node, "refusal"):
            parts.extend(
                cls._collect_node_text(
                    getattr(node, "refusal"),
                    allow_refusal=True,
                    _depth=_depth + 1,
                )
            )
        return parts

    @classmethod
    def _extract_responses_function_calls(cls, response: Any) -> list[dict[str, Any]]:
        output = cls._node_get(response, "output")
        if not isinstance(output, (list, tuple)):
            return []

        calls: list[dict[str, Any]] = []
        for item in output:
            item_type = cls._node_type(item)
            if item_type != "function_call":
                continue

            name = cls._node_get(item, "name")
            arguments = cls._node_get(item, "arguments")
            call_id = cls._node_get(item, "call_id")

            if not isinstance(name, str) or not name.strip():
                continue
            if not isinstance(call_id, str) or not call_id.strip():
                continue
            if isinstance(arguments, dict):
                arguments = json.dumps(arguments, ensure_ascii=False)
            if not isinstance(arguments, str):
                arguments = "{}"

            calls.append(
                {
                    "name": name.strip(),
                    "arguments": arguments,
                    "call_id": call_id.strip(),
                }
            )
        return calls

    @classmethod
    def _extract_responses_output_types(cls, response: Any) -> list[str]:
        output_types: list[str] = []
        output = cls._node_get(response, "output")
        if not isinstance(output, (list, tuple)):
            return output_types
        for item in output:
            output_types.append(cls._node_type(item) or "unknown")
        return output_types

    @classmethod
    def _describe_response_shape(cls, response: Any) -> str:
        summary = {
            "response_type": type(response).__name__,
            "response_module": type(response).__module__,
            "top_level_keys": cls._list_node_keys(response),
            "has_output_text": cls._node_get(response, "output_text") is not None,
            "output_types": cls._extract_responses_output_types(response),
            "shape_preview": cls._to_sanitized_shape(response),
        }
        serialized = json.dumps(summary, ensure_ascii=False, default=str)
        if len(serialized) > 1800:
            return serialized[:1800] + "...<truncated>"
        return serialized

    @classmethod
    def _to_sanitized_shape(cls, node: Any, *, _depth: int = 0) -> Any:
        if node is None or _depth > 3:
            return None

        if isinstance(node, (bool, int, float)):
            return node

        if isinstance(node, str):
            if len(node) > 200:
                return node[:200] + "...<truncated>"
            return node

        if isinstance(node, (list, tuple)):
            return [
                cls._to_sanitized_shape(item, _depth=_depth + 1)
                for item in list(node)[:8]
            ]

        if isinstance(node, dict):
            sanitized: dict[str, Any] = {}
            for key, value in list(node.items())[:25]:
                key_str = str(key)
                low = key_str.lower()
                if any(
                    blocked in low
                    for blocked in (
                        "prompt",
                        "message",
                        "input",
                        "api_key",
                        "authorization",
                        "token",
                    )
                ):
                    sanitized[key_str] = "<redacted>"
                    continue
                sanitized[key_str] = cls._to_sanitized_shape(value, _depth=_depth + 1)
            return sanitized

        for dump_method_name in ("model_dump", "to_dict", "dict"):
            dump_method = getattr(node, dump_method_name, None)
            if callable(dump_method):
                try:
                    dumped = dump_method()  # type: ignore[misc]
                    return cls._to_sanitized_shape(dumped, _depth=_depth + 1)
                except Exception:
                    pass

        attrs: dict[str, Any] = {}
        for attr in (
            "id",
            "type",
            "role",
            "status",
            "output_text",
            "output",
            "content",
            "text",
            "value",
        ):
            if not hasattr(node, attr):
                continue
            try:
                attrs[attr] = cls._to_sanitized_shape(
                    getattr(node, attr), _depth=_depth + 1
                )
            except Exception:
                continue
        if attrs:
            return attrs

        node_repr = repr(node)
        if len(node_repr) > 200:
            return node_repr[:200] + "...<truncated>"
        return node_repr

    @staticmethod
    def _node_get(node: Any, key: str, default: Any = None) -> Any:
        if node is None:
            return default
        if isinstance(node, dict):
            return node.get(key, default)
        return getattr(node, key, default)

    @staticmethod
    def _node_type(node: Any) -> str:
        if node is None:
            return ""
        if isinstance(node, dict):
            return str(node.get("type", "")).lower().strip()
        return str(getattr(node, "type", "")).lower().strip()

    @staticmethod
    def _list_node_keys(node: Any) -> list[str]:
        if node is None:
            return []
        if isinstance(node, dict):
            return sorted(str(key) for key in node.keys())[:25]
        keys: list[str] = []
        for key in (
            "id",
            "model",
            "output",
            "output_text",
            "choices",
            "status",
            "type",
        ):
            if hasattr(node, key):
                keys.append(key)
        return keys

    def _invoke_with_retry(
        self,
        call: Callable[[], Any],
        *,
        deployment: str,
        operation: str,
        timeout_seconds: Optional[float] = None,
        model_tier: Optional[str] = None,
        chat_intent: Optional[str] = None,
        is_reasoning_retry: bool = False,
    ) -> Any:
        retry_enabled = bool(settings.chat_llm_retry_enabled)
        configured_attempts = max(int(settings.chat_llm_retry_max_attempts), 1)
        attempts = configured_attempts if retry_enabled else 1
        initial_delay = max(float(settings.chat_llm_retry_initial_delay_seconds), 0.0)
        backoff_factor = max(float(settings.chat_llm_retry_backoff_factor), 1.0)
        max_delay = max(float(settings.chat_llm_retry_max_delay_seconds), 0.0)
        jitter = max(float(settings.chat_llm_retry_jitter_seconds), 0.0)
        last_error: Optional[Exception] = None

        for attempt in range(1, attempts + 1):
            try:
                logger.info(
                    "LLM attempt: deployment=%s model_tier=%s intent=%s operation=%s attempt=%d/%d timeout_seconds=%s is_reasoning_retry=%s",
                    deployment,
                    model_tier or self._resolve_model_tier(deployment),
                    chat_intent or "<none>",
                    operation,
                    attempt,
                    attempts,
                    f"{timeout_seconds:.2f}" if timeout_seconds else "default",
                    is_reasoning_retry,
                )
                return call()
            except (
                Exception
            ) as exc:  # pragma: no cover - retry branch is validated in unit tests.
                last_error = exc
                bad_request_details = self._extract_bad_request_details(exc)
                if bad_request_details is not None:
                    logger.error(
                        "LLM bad request detected: deployment=%s model_tier=%s intent=%s operation=%s "
                        "error_class=%s error_param=%s error_message=%s",
                        deployment,
                        model_tier or self._resolve_model_tier(deployment),
                        chat_intent or "<none>",
                        operation,
                        bad_request_details["error_class"],
                        bad_request_details.get("error_param") or "<none>",
                        bad_request_details["error_message"],
                    )
                    raise LLMBadRequestPayloadError(
                        deployment=deployment,
                        operation=operation,
                        error_class=bad_request_details["error_class"],
                        error_message=bad_request_details["error_message"],
                        error_param=bad_request_details.get("error_param"),
                        status_code=bad_request_details.get("status_code"),
                        cause=exc,
                    ) from exc

                retryable = self._is_retryable_llm_exception(exc)
                should_retry = retryable and attempt < attempts

                if not should_retry:
                    if retryable:
                        raise LLMServiceUnavailableError(
                            attempts=attempt,
                            deployment=deployment,
                            operation=operation,
                            last_error=exc,
                        ) from exc
                    raise GeneratorError(f"Azure OpenAI call failed: {exc}") from exc

                delay = initial_delay * (backoff_factor ** (attempt - 1))
                if max_delay > 0:
                    delay = min(delay, max_delay)
                if jitter > 0:
                    delay += random.uniform(0, jitter)

                logger.warning(
                    "Transient LLM call error (%s) on deployment='%s', model_tier='%s', intent='%s', "
                    "operation='%s', is_reasoning_retry=%s, attempt=%d/%d. Retrying in %.2fs",
                    exc,
                    deployment,
                    model_tier or self._resolve_model_tier(deployment),
                    chat_intent or "<none>",
                    operation,
                    is_reasoning_retry,
                    attempt,
                    attempts,
                    delay,
                )
                if delay > 0:
                    time.sleep(delay)

        if last_error is not None:
            raise LLMServiceUnavailableError(
                attempts=attempts,
                deployment=deployment,
                operation=operation,
                last_error=last_error,
            ) from last_error
        raise GeneratorError("Azure OpenAI call failed with unknown error")

    def _resolve_call_timeout_seconds(
        self,
        *,
        deployment: str,
        operation: str,
        chat_intent: Optional[str] = None,
    ) -> Optional[float]:
        if not bool(settings.chat_llm_call_timeout_enabled):
            return None

        target = (deployment or "").strip().lower()
        advanced = (self.advanced_deployment or "").strip().lower()
        default_timeout = max(float(settings.chat_llm_timeout_default_seconds), 0.0)
        advanced_timeout = max(float(settings.chat_llm_timeout_advanced_seconds), 0.0)
        tool_extra = max(float(settings.chat_llm_timeout_tool_extra_seconds), 0.0)

        timeout_seconds = (
            advanced_timeout if (advanced and target == advanced) else default_timeout
        )

        normalized_intent = (chat_intent or "").strip().lower()
        if normalized_intent:
            if normalized_intent == "pure_live_price":
                timeout_seconds = max(
                    float(settings.chat_llm_timeout_live_price_seconds), 0.0
                )
            elif normalized_intent in {
                "factual_rag",
                "portfolio_draft",
                "portfolio_transaction",
            }:
                timeout_seconds = max(
                    float(settings.chat_llm_timeout_factual_seconds), 0.0
                )
            elif normalized_intent in {"analytical_rag", "analytical_with_live_price"}:
                timeout_seconds = max(
                    float(settings.chat_llm_timeout_analytical_seconds), 0.0
                )
            # Unknown intent: keep deployment-based timeout selection.
        # If chat intent is unavailable at call site, deployment-based timeout remains active.

        if timeout_seconds <= 0:
            return None

        if "tool" in (operation or "").lower():
            timeout_seconds += tool_extra
        return timeout_seconds

    @staticmethod
    def _extract_bad_request_details(exc: Exception) -> Optional[dict[str, Any]]:
        status_code = getattr(exc, "status_code", None)
        is_bad_request_status = isinstance(status_code, int) and status_code == 400
        is_bad_request_type = bool(
            _BAD_REQUEST_OPENAI_EXCEPTIONS
            and isinstance(exc, _BAD_REQUEST_OPENAI_EXCEPTIONS)
        )
        if not is_bad_request_status and not is_bad_request_type:
            return None

        error_message = str(exc)
        error_param: Optional[str] = None

        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            error_block = body.get("error")
            if isinstance(error_block, dict):
                candidate_message = error_block.get("message")
                if isinstance(candidate_message, str) and candidate_message.strip():
                    error_message = candidate_message.strip()
                candidate_param = error_block.get("param")
                if isinstance(candidate_param, str) and candidate_param.strip():
                    error_param = candidate_param.strip()

        if not error_message.strip():
            fallback_message = getattr(exc, "message", None)
            if isinstance(fallback_message, str) and fallback_message.strip():
                error_message = fallback_message.strip()

        return {
            "error_class": type(exc).__name__,
            "error_message": error_message.strip() or "Unknown bad request",
            "error_param": error_param,
            "status_code": status_code if isinstance(status_code, int) else None,
        }

    @staticmethod
    def _is_retryable_llm_exception(exc: Exception) -> bool:
        if isinstance(exc, LLMServiceUnavailableError):
            return True

        if _RETRYABLE_OPENAI_EXCEPTIONS and isinstance(
            exc, _RETRYABLE_OPENAI_EXCEPTIONS
        ):
            return True

        status_code = getattr(exc, "status_code", None)
        if isinstance(status_code, int) and status_code in {
            408,
            409,
            425,
            429,
            500,
            502,
            503,
            504,
        }:
            return True

        if isinstance(exc, GeneratorError):
            return False

        message = str(exc).lower()
        non_retryable_markers = (
            "invalid_request_error",
            "content_filter",
            "authentication",
            "unauthorized",
            "forbidden",
            "unsupported",
            "model_not_found",
            "deploymentnotfound",
            "badrequest",
            "invalid api key",
        )
        if any(marker in message for marker in non_retryable_markers):
            return False

        retryable_markers = (
            "timeout",
            "timed out",
            "temporarily unavailable",
            "service unavailable",
            "rate limit",
            "too many requests",
            "connection",
            "connection reset",
            "connection aborted",
            "server error",
            "internal error",
            "gateway",
            "429",
            "500",
            "502",
            "503",
            "504",
        )
        return any(marker in message for marker in retryable_markers)

    @staticmethod
    def _capture_pending_transaction_draft(tool_result: dict[str, Any]) -> None:
        if not isinstance(tool_result, dict):
            return
        if tool_result.get("type") != "pending_transaction_draft":
            return
        draft = tool_result.get("pending_transaction_draft")
        if isinstance(draft, dict):
            _pending_transaction_draft_ctx.set(draft)

    @staticmethod
    def _execute_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
        name = tool_call.get("name")
        arguments = tool_call.get("args") or {}

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}

        if not isinstance(arguments, dict):
            return {
                "ok": False,
                "error_code": "invalid_tool_arguments",
                "message": "Tool arguments must be a JSON object",
            }

        if name == MARKET_PRICE_TOOL_NAME:
            return execute_get_current_market_price(arguments)

        if name == DRAFT_PORTFOLIO_TRANSACTION_TOOL_NAME:
            return execute_draft_portfolio_transaction(arguments)

        return {
            "ok": False,
            "error_code": "unsupported_tool",
            "message": f"Unsupported tool: {name}",
        }

    @staticmethod
    def _mock_generate(prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Generate a mock response for development.

        Args:
            prompt: The user prompt.
            system_prompt: The system prompt (if any).

        Returns:
            A mock response.
        """
        prompt_lower = prompt.lower()

        if "портфель" in prompt_lower or "інвестиції" in prompt_lower:
            return (
                "Відповідно до вашого портфеля та ризик-профілю, я б рекомендував розглянути "
                "збалансоване розподілення активів:\n\n"
                "- 40% в консервативні ОВДП\n"
                "- 30% в диверсифіковані акції\n"
                "- 20% в нерухомість\n"
                "- 10% в готівку для надзвичайних ситуацій\n\n"
                "Це допоможе вам досягти довгострокових фінансових цілей при мінімізації ризику."
            )
        if "податки" in prompt_lower:
            return (
                "Податки на інвестиційні доходи в Україні регулюються наступним чином:\n\n"
                "- ПДФО 18% на доходи від продажу акцій та облігацій\n"
                "- Можливість використання вичетів для компенсації збитків\n\n"
                "Рекомендую звернутись до податкового консультанта для оптимізації."
            )
        return (
            "Спасибі за ваше питання! На основі ваших даних та ринкового контексту, "
            "я можу надати більш детальні рекомендації. "
            "Будь ласка, поточніть ваше запитання або поділіться додатковою інформацією про ваші цілі."
        )


_generator: Optional[Generator] = None


def get_generator() -> Generator:
    """Get or create global generator instance."""
    global _generator
    if _generator is None:
        _generator = Generator()
    return _generator
