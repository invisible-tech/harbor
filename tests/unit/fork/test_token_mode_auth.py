"""Regression tests for token-command authentication mode."""

from __future__ import annotations

import shlex
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from typer.testing import CliRunner

import harbor.auth.constants as C
import harbor.auth.tokens as tokens
from harbor.auth.errors import AuthenticationError, NotAuthenticatedError
from harbor.cli.auth import auth_app

pytestmark = pytest.mark.unit
runner = CliRunner()


def _py(code: str) -> str:
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"


@pytest.fixture(autouse=True)
def _isolate_token_cache():
    tokens.invalidate_token()
    yield
    tokens.invalidate_token()


async def test_token_command_timeout_is_an_authentication_error(monkeypatch):
    monkeypatch.setattr(C, "ACCESS_TOKEN_COMMAND", _py("import time; time.sleep(5)"))
    monkeypatch.setattr(tokens, "_TOKEN_COMMAND_TIMEOUT_SEC", 0.5)

    with pytest.raises(AuthenticationError, match="timed out"):
        await tokens.get_access_token()


async def test_token_command_shlex_preserves_quoted_argument_with_spaces(
    monkeypatch, tmp_path: Path
):
    script = tmp_path / "token command.py"
    script.write_text("print('quoted-argument-token')\n")
    monkeypatch.setattr(
        C,
        "ACCESS_TOKEN_COMMAND",
        f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}",
    )

    assert await tokens.get_access_token() == "quoted-argument-token"


async def test_nonzero_command_reports_only_last_stderr_line(monkeypatch):
    code = "import sys; print('first diagnostic', file=sys.stderr); "
    code += "print('final diagnostic', file=sys.stderr); sys.exit(7)"
    monkeypatch.setattr(C, "ACCESS_TOKEN_COMMAND", _py(code))

    with pytest.raises(AuthenticationError) as exc_info:
        await tokens.get_access_token()

    assert "exited 7: final diagnostic" in str(exc_info.value)
    assert "first diagnostic" not in str(exc_info.value)


async def test_resolve_bearer_uses_command_token_and_is_anonymous_without_credentials(
    monkeypatch,
):
    from harbor.auth.client import _resolve_bearer

    monkeypatch.delenv("HARBOR_API_KEY", raising=False)
    monkeypatch.setattr(C, "ACCESS_TOKEN_COMMAND", _py("print('command-token')"))
    assert await _resolve_bearer() == "command-token"

    tokens.invalidate_token()
    monkeypatch.setattr(C, "ACCESS_TOKEN_COMMAND", None)
    assert await _resolve_bearer() is None


async def test_require_user_id_decodes_token_subject(monkeypatch):
    from harbor.auth.client import require_user_id

    token = jwt.encode({"sub": "user-123"}, "test-secret", algorithm="HS256")
    monkeypatch.setattr(C, "ACCESS_TOKEN_COMMAND", _py(f"print({token!r})"))

    assert await require_user_id() == "user-123"


async def test_require_user_id_rejects_anonymous_caller(monkeypatch):
    from harbor.auth.client import require_user_id

    monkeypatch.delenv("HARBOR_API_KEY", raising=False)
    monkeypatch.setattr(C, "ACCESS_TOKEN_COMMAND", None)
    token_lookup = AsyncMock(return_value=jwt.encode({"sub": "user-123"}, "k"))
    monkeypatch.setattr("harbor.auth.client.get_access_token", token_lookup)
    with pytest.raises(NotAuthenticatedError):
        await require_user_id()
    token_lookup.assert_not_awaited()


async def test_leaderboard_function_sends_token_mode_authorization(monkeypatch):
    from harbor.hub import leaderboards

    monkeypatch.setattr(C, "ACCESS_TOKEN_COMMAND", "token-command")
    monkeypatch.setattr(
        leaderboards, "get_access_token", AsyncMock(return_value="hub-jwt")
    )
    response = MagicMock(status_code=200, text="{}")
    response.json.return_value = {"ok": True}
    request_client = MagicMock()
    request_client.__aenter__ = AsyncMock(return_value=request_client)
    request_client.__aexit__ = AsyncMock(return_value=None)
    request_client.post = AsyncMock(return_value=response)
    monkeypatch.setattr(
        leaderboards.httpx, "AsyncClient", MagicMock(return_value=request_client)
    )

    result = await leaderboards._call_function(
        "leaderboard-read", {"leaderboard_id": "board-1"}, require_auth=False
    )

    assert result == {"ok": True}
    headers = request_client.post.await_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer hub-jwt"
    leaderboards.get_access_token.assert_awaited_once_with()


async def test_insecure_supabase_url_is_rejected_before_running_token_command(
    monkeypatch, tmp_path: Path
):
    marker = tmp_path / "command-ran"
    code = f"from pathlib import Path; Path({str(marker)!r}).write_text('ran'); print('jwt')"
    monkeypatch.setattr(C, "ACCESS_TOKEN_COMMAND", _py(code))
    monkeypatch.setattr(tokens, "SUPABASE_URL", "http://public.example/supabase")

    with pytest.raises(AuthenticationError, match="insecure URL"):
        await tokens.get_access_token()
    assert not marker.exists()


def test_login_and_logout_point_to_token_command_without_running_flows(monkeypatch):
    from harbor.auth import flows

    monkeypatch.setattr(C, "ACCESS_TOKEN_COMMAND", "credential-helper token")
    login_flow = AsyncMock()
    logout_flow = AsyncMock()
    monkeypatch.setattr(flows, "login", login_flow)
    monkeypatch.setattr(flows, "logout", logout_flow)

    login_result = runner.invoke(auth_app, ["login"])
    logout_result = runner.invoke(auth_app, ["logout"])

    assert login_result.exit_code == 0
    assert logout_result.exit_code == 0
    assert "HARBOR_ACCESS_TOKEN_COMMAND" in login_result.output
    assert "HARBOR_ACCESS_TOKEN_COMMAND" in logout_result.output
    login_flow.assert_not_awaited()
    logout_flow.assert_not_awaited()


@pytest.mark.parametrize(
    ("verification", "raises", "exit_code", "message"),
    [
        (True, False, 0, "Token authentication"),
        (False, False, 1, "Not authenticated"),
        (None, True, 1, "Not authenticated"),
    ],
)
def test_status_verifies_token_command(
    monkeypatch, verification, raises, exit_code, message
):
    from harbor.auth import flows

    from harbor.auth.flows import AuthStatus

    monkeypatch.setattr(C, "ACCESS_TOKEN_COMMAND", "credential-helper token")
    monkeypatch.setattr(
        flows, "auth_status", MagicMock(return_value=AuthStatus(mode="none"))
    )
    verify = AsyncMock(
        side_effect=AuthenticationError("token unavailable") if raises else None,
        return_value=verification,
    )
    monkeypatch.setattr(flows, "verify_credential", verify)

    result = runner.invoke(auth_app, ["status"])

    assert result.exit_code == exit_code
    assert message in result.output
    verify.assert_awaited_once_with()
