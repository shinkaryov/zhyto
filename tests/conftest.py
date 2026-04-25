"""
Pytest configuration and fixtures.
"""

import pytest


@pytest.fixture
def mock_user_id():
    """Provide a mock user ID."""
    return "user_test_123"


@pytest.fixture
def mock_api_key():
    """Provide a mock API key."""
    return "mock_key_abc123xyz"


@pytest.fixture
def mock_settings(monkeypatch):
    """Provide mock settings."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("USE_MOCK_AUTH", "true")
    monkeypatch.setenv("USE_MOCK_COSMOS", "true")
    monkeypatch.setenv("USE_MOCK_OPENAI", "true")

