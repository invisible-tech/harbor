import os
from pathlib import Path
from urllib.parse import urlparse

from harbor.constants import (
    CONSTRUCT_API_URLS,
    CONSTRUCT_HUB_URL,
    HARBOR_REGISTRY_WEBSITE_URL,
)

DEFAULT_SUPABASE_URL = CONSTRUCT_HUB_URL
# The Construct hub authenticates by bearer token and ignores the apikey, but
# the client requires a non-empty one.
DEFAULT_SUPABASE_PUBLISHABLE_KEY = "construct-hub-no-apikey"
DEFAULT_ACCESS_TOKEN_COMMAND = "gcloud auth print-identity-token"

SUPABASE_URL = os.environ.get("HARBOR_SUPABASE_URL", DEFAULT_SUPABASE_URL)
SUPABASE_PUBLISHABLE_KEY = os.environ.get(
    "HARBOR_SUPABASE_PUBLISHABLE_KEY", DEFAULT_SUPABASE_PUBLISHABLE_KEY
)

CREDENTIALS_DIR = Path("~/.harbor").expanduser()
CREDENTIALS_PATH = CREDENTIALS_DIR / "credentials.json"


def _default_access_token_command() -> str | None:
    """The built-in command applies to a Construct hub URL only, and never
    overrides an API-key login (env key or stored credentials), so a gcloud
    identity token is not sent to a custom host."""
    if SUPABASE_URL not in {f"{url}/hub" for url in CONSTRUCT_API_URLS.values()}:
        return None
    if os.environ.get("HARBOR_API_KEY", "").strip() or CREDENTIALS_PATH.exists():
        return None
    return DEFAULT_ACCESS_TOKEN_COMMAND


# Shell command printing a bearer token; replaces the API-key login entirely.
# HARBOR_ACCESS_TOKEN_COMMAND="" selects API-key login explicitly.
ACCESS_TOKEN_COMMAND = (
    os.environ.get("HARBOR_ACCESS_TOKEN_COMMAND", _default_access_token_command())
    or None
)

SUPABASE_REQUEST_TIMEOUT_SECONDS = 30.0

# Auth requests carry long-lived secrets (the API key) or short-lived bearers,
# so they must only go over TLS. http:// is allowed solely for loopback
# (local `supabase start` dev), which never leaves the machine.
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def assert_secure_supabase_url(url: str) -> None:
    """Refuse to send credentials over a non-TLS URL (loopback dev excepted)."""
    from harbor.auth.errors import AuthenticationError

    parsed = urlparse(url)
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and (parsed.hostname or "").lower() in _LOCAL_HOSTS:
        return
    raise AuthenticationError(
        f"Refusing to send credentials over an insecure URL ({url!r}). "
        "Use an https:// hub URL (http:// is allowed only for localhost)."
    )


# Pending PKCE verifier for OAuth flows that span two invocations
# (`harbor auth login --no-browser` + `--callback-url`, or the viewer's
# login-url/callback request pair).
OAUTH_PENDING_PATH = CREDENTIALS_DIR / "oauth-pending.json"
CALLBACK_PORT = 19284
# Path served by the ephemeral local callback server AND baked into the
# authorize URL's redirect — both sides derive from this one constant.
LOCAL_CALLBACK_PATH = "/auth/callback"
LOCAL_CALLBACK_URL = f"http://localhost:{CALLBACK_PORT}{LOCAL_CALLBACK_PATH}"
HOSTED_CALLBACK_URL = f"{HARBOR_REGISTRY_WEBSITE_URL}/auth/cli-callback"
