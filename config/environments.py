"""
Configuration settings for different environments.
"""

# Local environment configuration
LOCAL_CONFIG = {
    "app_env": "development",
    "debug": True,
    "log_level": "DEBUG",
    "use_mock_auth": True,
    "use_mock_cosmos": True,
    "use_mock_openai": True,
}

# Azure environment configuration
AZURE_CONFIG = {
    "app_env": "production",
    "debug": False,
    "log_level": "INFO",
    "use_mock_auth": False,
    "use_mock_cosmos": False,
    "use_mock_openai": False,
}

# Testing environment configuration
TEST_CONFIG = {
    "app_env": "test",
    "debug": True,
    "log_level": "WARNING",
    "use_mock_auth": True,
    "use_mock_cosmos": True,
    "use_mock_openai": True,
}

