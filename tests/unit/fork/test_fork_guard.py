import pytest

import harbor.auth.constants as auth_constants
import harbor.cli.auth as cli_auth
import harbor.cli.hub as cli_hub
import harbor.constants as constants
import harbor.publisher.packager as packager
import harbor.storage.resumable as resumable
import rewardkit.judges as judges
from harbor.agents.installed.claude_code import ClaudeCodeOptions

pytestmark = pytest.mark.unit


def test_construct_auth_defaults_are_present() -> None:
    assert hasattr(auth_constants, "ACCESS_TOKEN_COMMAND")
    assert (
        auth_constants.DEFAULT_ACCESS_TOKEN_COMMAND
        == "gcloud auth print-identity-token"
    )
    assert constants.CONSTRUCT_API_URLS["production"] == "https://api.research.inv.tech"
    assert (
        constants.CONSTRUCT_API_URLS["staging"] == "https://api.research.invsta.systems"
    )


def test_packager_deny_list_contains_fork_exclusions() -> None:
    assert {
        ".git/",
        ".venv/",
        "node_modules/",
        ".env*",
        "*.local.json",
        ".gitignore",
    } <= set(packager.DENY_LIST)


def test_resumable_storage_fork_helpers_are_present() -> None:
    assert callable(resumable.retry_transient_or_expired_token_once)
    assert callable(resumable._keep_path_prefix)


def test_fork_cli_helpers_are_present() -> None:
    assert callable(cli_hub._parse_trial_download_id)
    assert callable(cli_auth._token_mode_pointer)


def test_rewardkit_retry_helper_is_present() -> None:
    assert callable(judges._acompletion_with_retry)


def test_claude_code_bare_option_is_present() -> None:
    assert "bare" in ClaudeCodeOptions.model_fields
