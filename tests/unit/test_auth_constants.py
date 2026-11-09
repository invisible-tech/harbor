import importlib
import os
from collections.abc import Generator
from contextlib import contextmanager
from types import ModuleType

import harbor.auth.constants as constants


ENV_KEYS = (
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
