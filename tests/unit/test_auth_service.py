"""Unit tests for local auth service."""

from __future__ import annotations

import os

import pytest
from fastapi import HTTPException

from src.auth.auth_service import (
    authenticate_credentials,
    decode_access_token,
    issue_access_token,
    list_secret_questions,
    register_whitelisted_user_with_secret,
    register_whitelisted_user,
    reset_password_with_secret_question,
)
from src.db import cosmos_client as cosmos_client_module
from src.utils.config import settings


def test_register_authenticate_and_issue_token(tmp_path):
    whitelist_file = tmp_path / "whitelist.txt"
    whitelist_file.write_text("shinkaryovae@com\n", encoding="utf-8")
    mock_db_file = tmp_path / "mock_cosmos_db.json"

    old_whitelist = settings.auth_email_whitelist_file
    old_secret = settings.auth_token_secret
    old_ttl = settings.auth_token_ttl_minutes
    old_min = settings.auth_password_min_length
    old_iters = settings.auth_password_pbkdf2_iterations
    old_use_mock = settings.use_mock_cosmos
    old_local_mock_file = os.environ.get("LOCAL_COSMOS_MOCK_FILE")
    old_client = cosmos_client_module._cosmos_client

    try:
        settings.auth_email_whitelist_file = str(whitelist_file)
        settings.auth_token_secret = "token-secret-123"
        settings.auth_token_ttl_minutes = 60
        settings.auth_password_min_length = 8
        settings.auth_password_pbkdf2_iterations = 120000
        settings.use_mock_cosmos = True
        os.environ["LOCAL_COSMOS_MOCK_FILE"] = str(mock_db_file)
        cosmos_client_module._cosmos_client = None

        identity = register_whitelisted_user("Shinkaryovae@com", "secret123")
        assert identity.email == "shinkaryovae@com"
        assert identity.user_id.startswith("user_")

        auth_identity = authenticate_credentials("shinkaryovae@com", "secret123")
        assert auth_identity == identity

        token = issue_access_token(identity)
        restored = decode_access_token(token)
        assert restored.email == identity.email
        assert restored.user_id == identity.user_id
    finally:
        settings.auth_email_whitelist_file = old_whitelist
        settings.auth_token_secret = old_secret
        settings.auth_token_ttl_minutes = old_ttl
        settings.auth_password_min_length = old_min
        settings.auth_password_pbkdf2_iterations = old_iters
        settings.use_mock_cosmos = old_use_mock
        cosmos_client_module._cosmos_client = old_client
        if old_local_mock_file is None:
            os.environ.pop("LOCAL_COSMOS_MOCK_FILE", None)
        else:
            os.environ["LOCAL_COSMOS_MOCK_FILE"] = old_local_mock_file


def test_cannot_register_twice(tmp_path):
    whitelist_file = tmp_path / "whitelist.txt"
    whitelist_file.write_text("shinkaryovae@com\n", encoding="utf-8")
    mock_db_file = tmp_path / "mock_cosmos_db.json"

    old_whitelist = settings.auth_email_whitelist_file
    old_use_mock = settings.use_mock_cosmos
    old_local_mock_file = os.environ.get("LOCAL_COSMOS_MOCK_FILE")
    old_client = cosmos_client_module._cosmos_client

    try:
        settings.auth_email_whitelist_file = str(whitelist_file)
        settings.use_mock_cosmos = True
        os.environ["LOCAL_COSMOS_MOCK_FILE"] = str(mock_db_file)
        cosmos_client_module._cosmos_client = None

        register_whitelisted_user("shinkaryovae@com", "secret123")
        with pytest.raises(HTTPException) as exc:
            register_whitelisted_user("shinkaryovae@com", "secret123")
        assert exc.value.status_code == 409
    finally:
        settings.auth_email_whitelist_file = old_whitelist
        settings.use_mock_cosmos = old_use_mock
        cosmos_client_module._cosmos_client = old_client
        if old_local_mock_file is None:
            os.environ.pop("LOCAL_COSMOS_MOCK_FILE", None)
        else:
            os.environ["LOCAL_COSMOS_MOCK_FILE"] = old_local_mock_file


def test_secret_question_password_reset(tmp_path):
    whitelist_file = tmp_path / "whitelist.txt"
    whitelist_file.write_text("shinkaryovae@com\n", encoding="utf-8")
    mock_db_file = tmp_path / "mock_cosmos_db.json"

    old_whitelist = settings.auth_email_whitelist_file
    old_use_mock = settings.use_mock_cosmos
    old_local_mock_file = os.environ.get("LOCAL_COSMOS_MOCK_FILE")
    old_client = cosmos_client_module._cosmos_client

    try:
        settings.auth_email_whitelist_file = str(whitelist_file)
        settings.use_mock_cosmos = True
        os.environ["LOCAL_COSMOS_MOCK_FILE"] = str(mock_db_file)
        cosmos_client_module._cosmos_client = None

        register_whitelisted_user_with_secret(
            "shinkaryovae@com",
            "secret123",
            secret_question_id="favorite_asset",
            secret_answer="OVDP",
        )

        reset_password_with_secret_question(
            email="shinkaryovae@com",
            secret_question_id="favorite_asset",
            secret_answer="ovdp",
            new_password="new-secret-456",
        )

        authenticated = authenticate_credentials("shinkaryovae@com", "new-secret-456")
        assert authenticated.email == "shinkaryovae@com"
    finally:
        settings.auth_email_whitelist_file = old_whitelist
        settings.use_mock_cosmos = old_use_mock
        cosmos_client_module._cosmos_client = old_client
        if old_local_mock_file is None:
            os.environ.pop("LOCAL_COSMOS_MOCK_FILE", None)
        else:
            os.environ["LOCAL_COSMOS_MOCK_FILE"] = old_local_mock_file


def test_secret_question_invalid_answer_fails(tmp_path):
    whitelist_file = tmp_path / "whitelist.txt"
    whitelist_file.write_text("shinkaryovae@com\n", encoding="utf-8")
    mock_db_file = tmp_path / "mock_cosmos_db.json"

    old_whitelist = settings.auth_email_whitelist_file
    old_use_mock = settings.use_mock_cosmos
    old_local_mock_file = os.environ.get("LOCAL_COSMOS_MOCK_FILE")
    old_client = cosmos_client_module._cosmos_client

    try:
        settings.auth_email_whitelist_file = str(whitelist_file)
        settings.use_mock_cosmos = True
        os.environ["LOCAL_COSMOS_MOCK_FILE"] = str(mock_db_file)
        cosmos_client_module._cosmos_client = None

        register_whitelisted_user_with_secret(
            "shinkaryovae@com",
            "secret123",
            secret_question_id="favorite_asset",
            secret_answer="OVDP",
        )
        with pytest.raises(HTTPException) as exc:
            reset_password_with_secret_question(
                email="shinkaryovae@com",
                secret_question_id="favorite_asset",
                secret_answer="wrong",
                new_password="new-secret-456",
            )
        assert exc.value.status_code == 401
    finally:
        settings.auth_email_whitelist_file = old_whitelist
        settings.use_mock_cosmos = old_use_mock
        cosmos_client_module._cosmos_client = old_client
        if old_local_mock_file is None:
            os.environ.pop("LOCAL_COSMOS_MOCK_FILE", None)
        else:
            os.environ["LOCAL_COSMOS_MOCK_FILE"] = old_local_mock_file


def test_secret_question_catalog_size():
    questions = list_secret_questions()
    assert len(questions) == 7


def test_legacy_user_can_bootstrap_secret_question_via_reset(tmp_path):
    whitelist_file = tmp_path / "whitelist.txt"
    whitelist_file.write_text("shinkaryovae@gmail.com\n", encoding="utf-8")
    mock_db_file = tmp_path / "mock_cosmos_db.json"

    old_whitelist = settings.auth_email_whitelist_file
    old_use_mock = settings.use_mock_cosmos
    old_local_mock_file = os.environ.get("LOCAL_COSMOS_MOCK_FILE")
    old_client = cosmos_client_module._cosmos_client

    try:
        settings.auth_email_whitelist_file = str(whitelist_file)
        settings.use_mock_cosmos = True
        os.environ["LOCAL_COSMOS_MOCK_FILE"] = str(mock_db_file)
        cosmos_client_module._cosmos_client = None

        # Legacy user created before secret-question flow.
        register_whitelisted_user("shinkaryovae@gmail.com", "legacy-pass-123")

        reset_password_with_secret_question(
            email="shinkaryovae@gmail.com",
            secret_question_id="favorite_asset",
            secret_answer="AAPL",
            new_password="fresh-pass-456",
        )

        identity = authenticate_credentials("shinkaryovae@gmail.com", "fresh-pass-456")
        assert identity.email == "shinkaryovae@gmail.com"
    finally:
        settings.auth_email_whitelist_file = old_whitelist
        settings.use_mock_cosmos = old_use_mock
        cosmos_client_module._cosmos_client = old_client
        if old_local_mock_file is None:
            os.environ.pop("LOCAL_COSMOS_MOCK_FILE", None)
        else:
            os.environ["LOCAL_COSMOS_MOCK_FILE"] = old_local_mock_file
