import importlib
import os
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

import pytest

import harbor.auth.constants as constants


DEFAULT_COMMAND = "gcloud auth print-identity-token"

ENV_KEYS = (
    "HOME",
    "USERPROFILE",
    "HARBOR_CONSTRUCT_ENV",
    "HARBOR_API_KEY",
    "HARBOR_ACCESS_TOKEN_COMMAND",
    "HARBOR_SUPABASE_URL",
    "HARBOR_SUPABASE_PUBLISHABLE_KEY",
)


@contextmanager
def patched_supabase_env(values: dict[str, str]) -> Generator[ModuleType, None, None]:
    original = {key: os.environ.get(key) for key in ENV_KEYS}
    try:
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        # An empty HOME keeps a stored ~/.harbor/credentials.json out of the test.
        with tempfile.TemporaryDirectory() as home:
            os.environ["HOME"] = home
            os.environ["USERPROFILE"] = home  # Windows expanduser reads this
            os.environ.update(values)
            yield importlib.reload(constants)
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        importlib.reload(constants)


def test_auth_constants_default_to_harbor_hub() -> None:
    with patched_supabase_env({}) as reloaded:
        assert reloaded.SUPABASE_URL == reloaded.DEFAULT_SUPABASE_URL
        assert (
            reloaded.SUPABASE_PUBLISHABLE_KEY
            == reloaded.DEFAULT_SUPABASE_PUBLISHABLE_KEY
        )


def test_auth_constants_prefer_harbor_supabase_env() -> None:
    with patched_supabase_env(
        {
            "HARBOR_SUPABASE_URL": "https://branch.supabase.co",
            "HARBOR_SUPABASE_PUBLISHABLE_KEY": "sb_publishable_branch",
        }
    ) as reloaded:
        assert reloaded.SUPABASE_URL == "https://branch.supabase.co"
        assert reloaded.SUPABASE_PUBLISHABLE_KEY == "sb_publishable_branch"


def test_auth_constants_default_to_construct_production() -> None:
    with patched_supabase_env({}) as reloaded:
        assert reloaded.SUPABASE_URL == "https://api.research.inv.tech/hub"
        assert reloaded.SUPABASE_PUBLISHABLE_KEY
        assert reloaded.ACCESS_TOKEN_COMMAND == "gcloud auth print-identity-token"


def test_empty_access_token_command_selects_api_key_login() -> None:
    with patched_supabase_env({"HARBOR_ACCESS_TOKEN_COMMAND": ""}) as reloaded:
        assert reloaded.ACCESS_TOKEN_COMMAND is None


def test_api_key_in_env_disables_default_token_command() -> None:
    with patched_supabase_env({"HARBOR_API_KEY": "hk_test"}) as reloaded:
        assert reloaded.ACCESS_TOKEN_COMMAND is None


def test_explicit_token_command_wins_over_api_key() -> None:
    with patched_supabase_env(
        {"HARBOR_API_KEY": "hk_test", "HARBOR_ACCESS_TOKEN_COMMAND": "print-token"}
    ) as reloaded:
        assert reloaded.ACCESS_TOKEN_COMMAND == "print-token"


def test_default_token_command_skipped_for_custom_hub_url() -> None:
    with patched_supabase_env({"HARBOR_SUPABASE_URL": "https://x.example"}) as reloaded:
        assert reloaded.ACCESS_TOKEN_COMMAND is None


def test_default_token_command_applies_to_staging_hub() -> None:
    with patched_supabase_env({"HARBOR_CONSTRUCT_ENV": "staging"}) as reloaded:
        assert reloaded.ACCESS_TOKEN_COMMAND == "gcloud auth print-identity-token"


def _write_credentials(home: str, content: str) -> None:
    path = Path(home) / ".harbor" / "credentials.json"
    path.parent.mkdir()
    path.write_text(content)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('{"api_key": "sk-harbor-abc"}', None),
        ("", DEFAULT_COMMAND),
        ('{"api_key": "legacy"}', DEFAULT_COMMAND),
    ],
)
def test_only_a_usable_stored_key_disables_default_token_command(
    content: str, expected: str | None
) -> None:
    with tempfile.TemporaryDirectory() as home:
        _write_credentials(home, content)
        with patched_supabase_env({"HOME": home}) as reloaded:
            assert reloaded.ACCESS_TOKEN_COMMAND == expected


@pytest.mark.parametrize(
    "url",
    ["https://api.research.inv.tech/hub/", "https://API.research.inv.tech/hub"],
)
def test_construct_url_spelling_keeps_default_token_command(url: str) -> None:
    with patched_supabase_env({"HARBOR_SUPABASE_URL": url}) as reloaded:
        assert reloaded.ACCESS_TOKEN_COMMAND == DEFAULT_COMMAND
