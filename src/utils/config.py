"""
Utility module for configuration management.
"""

import os
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ============================================================
    # Application Configuration
    # ============================================================
    app_env: str = Field(default="development", env="APP_ENV")
    app_debug: bool = Field(default=True, env="APP_DEBUG")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    # ============================================================
    # Feature Flags
    # ============================================================
    feature_auth_enabled: bool = Field(default=False, env="FEATURE_AUTH_ENABLED")
    feature_cosmos_db_enabled: bool = Field(
        default=False, env="FEATURE_COSMOS_DB_ENABLED"
    )
    feature_azure_openai_enabled: bool = Field(
        default=False, env="FEATURE_AZURE_OPENAI_ENABLED"
    )
    chat_analytical_pipeline_enabled: bool = Field(
        default=True, env="CHAT_ANALYTICAL_PIPELINE_ENABLED"
    )

    # ============================================================
    # Mock Configuration (for local development)
    # ============================================================
    use_mock_auth: bool = Field(default=True, env="USE_MOCK_AUTH")
    use_mock_cosmos: bool = Field(default=True, env="USE_MOCK_COSMOS")
    use_mock_openai: bool = Field(default=True, env="USE_MOCK_OPENAI")
    fail_open_to_mock_in_production: bool = Field(
        default=False, env="FAIL_OPEN_TO_MOCK_IN_PRODUCTION"
    )

    # ============================================================
    # ChromaDB Configuration
    # ============================================================
    chroma_db_path: str = Field(default="./chroma_data", env="CHROMA_DB_PATH")
    chroma_collection_name: str = Field(
        default="ukraine_invest_market_context", env="CHROMA_COLLECTION_NAME"
    )
    chat_retrieval_initial_top_k: int = Field(
        default=30, env="CHAT_RETRIEVAL_INITIAL_TOP_K"
    )
    chat_rerank_top_k: int = Field(default=12, env="CHAT_RERANK_TOP_K")
    chat_synthesis_max_clusters: int = Field(
        default=6, env="CHAT_SYNTHESIS_MAX_CLUSTERS"
    )
    chat_context_max_sources: int = Field(default=10, env="CHAT_CONTEXT_MAX_SOURCES")
    chat_rerank_similarity_weight: float = Field(
        default=0.55, env="CHAT_RERANK_SIMILARITY_WEIGHT"
    )
    chat_rerank_trust_weight: float = Field(default=0.2, env="CHAT_RERANK_TRUST_WEIGHT")
    chat_rerank_freshness_weight: float = Field(
        default=0.15, env="CHAT_RERANK_FRESHNESS_WEIGHT"
    )
    chat_rerank_domain_weight: float = Field(
        default=0.1, env="CHAT_RERANK_DOMAIN_WEIGHT"
    )
    chat_freshness_half_life_days: int = Field(
        default=14, env="CHAT_FRESHNESS_HALF_LIFE_DAYS"
    )
    chat_llm_retry_enabled: bool = Field(default=True, env="CHAT_LLM_RETRY_ENABLED")
    chat_llm_retry_max_attempts: int = Field(
        default=2, env="CHAT_LLM_RETRY_MAX_ATTEMPTS"
    )
    chat_llm_retry_initial_delay_seconds: float = Field(
        default=0.35,
        env="CHAT_LLM_RETRY_INITIAL_DELAY_SECONDS",
    )
    chat_llm_retry_backoff_factor: float = Field(
        default=1.8,
        env="CHAT_LLM_RETRY_BACKOFF_FACTOR",
    )
    chat_llm_retry_max_delay_seconds: float = Field(
        default=2.0,
        env="CHAT_LLM_RETRY_MAX_DELAY_SECONDS",
    )
    chat_llm_retry_jitter_seconds: float = Field(
        default=0.1,
        env="CHAT_LLM_RETRY_JITTER_SECONDS",
    )
    chat_llm_call_timeout_enabled: bool = Field(
        default=True,
        env="CHAT_LLM_CALL_TIMEOUT_ENABLED",
    )
    chat_llm_timeout_default_seconds: float = Field(
        default=30.0,
        env="CHAT_LLM_TIMEOUT_DEFAULT_SECONDS",
    )
    chat_llm_timeout_advanced_seconds: float = Field(
        default=60.0,
        env="CHAT_LLM_TIMEOUT_ADVANCED_SECONDS",
    )
    chat_llm_timeout_tool_extra_seconds: float = Field(
        default=4.0,
        env="CHAT_LLM_TIMEOUT_TOOL_EXTRA_SECONDS",
    )
    chat_llm_timeout_live_price_seconds: float = Field(
        default=15.0,
        env="CHAT_LLM_TIMEOUT_LIVE_PRICE_SECONDS",
    )
    chat_llm_timeout_factual_seconds: float = Field(
        default=30.0,
        env="CHAT_LLM_TIMEOUT_FACTUAL_SECONDS",
    )
    chat_llm_timeout_analytical_seconds: float = Field(
        default=60.0,
        env="CHAT_LLM_TIMEOUT_ANALYTICAL_SECONDS",
    )
    chat_parallel_hypothesis_workers: int = Field(
        default=4,
        env="CHAT_PARALLEL_HYPOTHESIS_WORKERS",
    )
    chat_embedding_cache_ttl_seconds: int = Field(
        default=600,
        env="CHAT_EMBEDDING_CACHE_TTL_SECONDS",
    )
    chat_embedding_cache_max_entries: int = Field(
        default=512,
        env="CHAT_EMBEDDING_CACHE_MAX_ENTRIES",
    )
    chat_hypothesis_cache_ttl_seconds: int = Field(
        default=300,
        env="CHAT_HYPOTHESIS_CACHE_TTL_SECONDS",
    )
    chat_hypothesis_cache_max_entries: int = Field(
        default=128,
        env="CHAT_HYPOTHESIS_CACHE_MAX_ENTRIES",
    )
    chat_compression_cache_ttl_seconds: int = Field(
        default=300,
        env="CHAT_COMPRESSION_CACHE_TTL_SECONDS",
    )
    chat_compression_cache_max_entries: int = Field(
        default=128,
        env="CHAT_COMPRESSION_CACHE_MAX_ENTRIES",
    )

    # ============================================================
    # Azure Configuration
    # ============================================================
    azure_tenant_id: Optional[str] = Field(default=None, env="AZURE_TENANT_ID")
    azure_client_id: Optional[str] = Field(default=None, env="AZURE_CLIENT_ID")
    azure_client_secret: Optional[str] = Field(default=None, env="AZURE_CLIENT_SECRET")
    azure_subscription_id: Optional[str] = Field(
        default=None, env="AZURE_SUBSCRIPTION_ID"
    )

    # ============================================================
    # Azure OpenAI Configuration
    # ============================================================
    azure_openai_api_key: Optional[str] = Field(
        default=None, env="AZURE_OPENAI_API_KEY"
    )
    azure_openai_endpoint: Optional[str] = Field(
        default=None, env="AZURE_OPENAI_ENDPOINT"
    )
    azure_openai_deployment_name: str = Field(
        default="gpt-5.4-mini", env="AZURE_OPENAI_DEPLOYMENT_NAME"
    )
    azure_openai_default_deployment: Optional[str] = Field(
        default=None, env="AZURE_OPENAI_DEFAULT_DEPLOYMENT"
    )
    azure_openai_advanced_deployment: str = Field(
        default="gpt-5-4-advanced", env="AZURE_OPENAI_ADVANCED_DEPLOYMENT"
    )
    azure_openai_advanced_api_preference: str = Field(
        default="responses", env="AZURE_OPENAI_ADVANCED_API_PREFERENCE"
    )
    enable_adaptive_model_routing: bool = Field(
        default=True, env="ENABLE_ADAPTIVE_MODEL_ROUTING"
    )
    chat_model_default_supports_temperature: bool = Field(
        default=True, env="CHAT_MODEL_DEFAULT_SUPPORTS_TEMPERATURE"
    )
    chat_model_default_supports_top_p: bool = Field(
        default=True, env="CHAT_MODEL_DEFAULT_SUPPORTS_TOP_P"
    )
    chat_model_default_supports_penalties: bool = Field(
        default=True, env="CHAT_MODEL_DEFAULT_SUPPORTS_PENALTIES"
    )
    chat_model_default_supports_tools: bool = Field(
        default=True, env="CHAT_MODEL_DEFAULT_SUPPORTS_TOOLS"
    )
    chat_model_default_supports_reasoning: bool = Field(
        default=True, env="CHAT_MODEL_DEFAULT_SUPPORTS_REASONING"
    )
    chat_model_advanced_supports_temperature: bool = Field(
        default=False, env="CHAT_MODEL_ADVANCED_SUPPORTS_TEMPERATURE"
    )
    chat_model_advanced_supports_top_p: bool = Field(
        default=False, env="CHAT_MODEL_ADVANCED_SUPPORTS_TOP_P"
    )
    chat_model_advanced_supports_penalties: bool = Field(
        default=False, env="CHAT_MODEL_ADVANCED_SUPPORTS_PENALTIES"
    )
    chat_model_advanced_supports_tools: bool = Field(
        default=True, env="CHAT_MODEL_ADVANCED_SUPPORTS_TOOLS"
    )
    chat_model_advanced_supports_reasoning: bool = Field(
        default=True, env="CHAT_MODEL_ADVANCED_SUPPORTS_REASONING"
    )

    azure_openai_embedding_deployment_name: str = Field(
        default="text-embedding-3-small", env="AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"
    )

    azure_openai_api_version: str = Field(
        default="2025-03-01-preview", env="AZURE_OPENAI_API_VERSION"
    )

    # ============================================================
    # Azure Cosmos DB Configuration
    # ============================================================
    cosmos_db_connection_string: Optional[str] = Field(
        default=None, env="COSMOS_DB_CONNECTION_STRING"
    )

    # ============================================================
    # Entra ID (Azure AD) Configuration
    # ============================================================
    entra_client_id: Optional[str] = Field(default=None, env="ENTRA_CLIENT_ID")
    entra_authority_url: str = Field(
        default="https://login.microsoftonline.com/", env="ENTRA_AUTHORITY_URL"
    )
    entra_redirect_uri: str = Field(
        default="http://localhost:3000", env="ENTRA_REDIRECT_URI"
    )

    # ============================================================
    # Local Auth (Email + Password + Whitelist)
    # ============================================================
    auth_email_whitelist_file: str = Field(
        default="src/auth/email_whitelist.txt",
        env="AUTH_EMAIL_WHITELIST_FILE",
    )
    auth_token_secret: str = Field(
        default="change_me_please_too",
        env="AUTH_TOKEN_SECRET",
    )
    auth_token_ttl_minutes: int = Field(
        default=24 * 60,
        env="AUTH_TOKEN_TTL_MINUTES",
    )
    auth_password_min_length: int = Field(
        default=8,
        env="AUTH_PASSWORD_MIN_LENGTH",
    )
    auth_password_pbkdf2_iterations: int = Field(
        default=200000,
        env="AUTH_PASSWORD_PBKDF2_ITERATIONS",
    )

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
    }

    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.app_env.lower() == "production"

    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.app_env.lower() == "development"

    def allow_mock_fallback(self) -> bool:
        """Whether runtime is allowed to silently fall back to mock services."""
        if not self.is_production():
            return True
        return bool(self.fail_open_to_mock_in_production)


def load_settings() -> Settings:
    """Load and return application settings."""
    # Load .env file if it exists
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)

    # Backward-compatible alias for cloud deployments that prefer CHROMA_PERSIST_DIR.
    if not os.getenv("CHROMA_DB_PATH") and os.getenv("CHROMA_PERSIST_DIR"):
        os.environ["CHROMA_DB_PATH"] = os.environ["CHROMA_PERSIST_DIR"]

    return Settings()


# Create global settings instance
settings = load_settings()
