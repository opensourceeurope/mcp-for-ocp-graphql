"""OAuth 2.1 authorization-server provider for the Open Collective MCP server.

Passthrough design: the user pastes their Open Collective *personal token* into an
HTML form during the OAuth authorize step. That token becomes the OAuth access
token. On each MCP request the bearer token is forwarded to the OC API as the
``Personal-Token`` header. Consequences:

* Access-token verification is **presence-only** — we never call OC to validate a
  bearer on each request. OC rejects bad tokens naturally when a tool runs.
* Authorization codes live in memory with a ~30s TTL and are single-use.
* The OC token is validated exactly **once**, at form-submit time, by calling the
  OC GraphQL ``{ me { id } }`` query with the token.

The HTTP app / route wiring (Starlette) lives in a separate module; this module is
just the provider plus the two helpers the route needs (``verify_oc_token`` and
``render_auth_form``) and the ``complete_login`` callback.
"""

from __future__ import annotations

import html
import secrets
import time
from dataclasses import dataclass
from typing import Callable

import httpx
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

# How long a freshly-minted authorization code is valid for. Long enough for the
# client to immediately exchange it, short enough that a leaked code is useless.
CODE_TTL_SECONDS = 30

# A non-expiring stand-in client id reported for every access token. OC personal
# tokens are not tied to a registered OAuth client, so there is nothing better.
ACCESS_TOKEN_CLIENT_ID = "oc-user"

# The query used to prove a personal token is valid.
_VERIFY_QUERY = "{ me { id } }"


def verify_oc_token(token: str, endpoint: str, *, client: httpx.Client) -> bool:
    """Return True iff ``token`` is a valid Open Collective personal token.

    POSTs ``{ me { id } }`` to the OC GraphQL endpoint with the token in the
    ``Personal-Token`` header. True only when the response is HTTP 200, carries
    no GraphQL errors, and ``data.me`` is truthy. Any network error yields False.

    The httpx client is injected so tests can supply a ``MockTransport``.
    """
    if not token:
        return False
    headers = {"Content-Type": "application/json", "Personal-Token": token}
    try:
        response = client.post(endpoint, json={"query": _VERIFY_QUERY}, headers=headers)
    except httpx.HTTPError:
        return False
    if response.status_code != 200:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    if payload.get("errors"):
        return False
    data = payload.get("data") or {}
    return bool(data.get("me"))


def render_auth_form(request_id: str, error: str | None = None) -> str:
    """Render the login form HTML.

    The form POSTs ``oc_token`` plus a hidden ``request_id`` to ``/oc-login``.
    Every interpolated value is escaped with :func:`html.escape` — this is an XSS
    boundary: ``request_id`` comes from us but is round-tripped through the URL,
    and ``error`` may echo user-influenced content.
    """
    safe_request_id = html.escape(request_id, quote=True)
    if error:
        error_block = (
            f'<p class="error" role="alert">{html.escape(error, quote=True)}</p>'
        )
    else:
        error_block = ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Authenticate — MCP for Open Collective</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: system-ui, sans-serif; background: #f5f5f5; display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 1rem; }}
    .card {{ background: #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,.12); padding: 2rem; width: 100%; max-width: 480px; }}
    h1 {{ font-size: 1.25rem; margin-bottom: .5rem; }}
    p.subtitle {{ color: #555; font-size: .9rem; margin-bottom: 1.5rem; }}
    label {{ display: block; font-size: .875rem; font-weight: 500; margin-bottom: .4rem; }}
    input[type="password"] {{ width: 100%; padding: .6rem .75rem; border: 1px solid #ccc; border-radius: 4px; font-size: 1rem; margin-bottom: 1rem; }}
    input[type="password"]:focus {{ outline: 2px solid #1869f5; border-color: transparent; }}
    button {{ width: 100%; padding: .7rem; background: #1869f5; color: #fff; border: none; border-radius: 4px; font-size: 1rem; cursor: pointer; }}
    button:hover {{ background: #0f52c7; }}
    .error {{ color: #c0392b; font-size: .875rem; margin-bottom: 1rem; padding: .5rem .75rem; background: #fdf2f2; border-radius: 4px; border: 1px solid #f5c6cb; }}
    .hint {{ margin-top: 1rem; font-size: .8rem; color: #666; text-align: center; }}
    .hint a {{ color: #1869f5; }}
    .security {{ margin-top: 1.5rem; padding: 1rem; background: #f8f9fa; border-radius: 6px; border: 1px solid #e9ecef; }}
    .security h2 {{ font-size: .875rem; font-weight: 600; color: #333; margin-bottom: .6rem; }}
    .security ul {{ padding-left: 1.2rem; }}
    .security li {{ font-size: .8rem; color: #555; margin-bottom: .35rem; line-height: 1.4; }}
    .footer {{ margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid #eee; font-size: .75rem; color: #888; text-align: center; line-height: 1.5; }}
    .footer a {{ color: #1869f5; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>MCP for the Open Collective Platform</h1>
    <p class="subtitle">Enter your Open Collective personal token to connect your AI agent to the platform's GraphQL API.</p>
    <form method="POST" action="/oc-login" autocomplete="off">
      <input type="hidden" name="request_id" value="{safe_request_id}">
      {error_block}
      <label for="oc_token">Personal Token</label>
      <input type="password" id="oc_token" name="oc_token" required autofocus
             placeholder="Paste your token here" spellcheck="false" autocomplete="off">
      <button type="submit">Authenticate</button>
    </form>
    <p class="hint">
      Get your token at
      <a href="https://opencollective.com/dashboard" target="_blank" rel="noopener">
        opencollective.com → Dashboard → For Developers
      </a>
    </p>

    <div class="security">
      <h2>How your token is handled</h2>
      <ul>
        <li><strong>Not stored server-side.</strong> Your token is never written to disk or a database. It lives only in memory for the duration of the OAuth handshake (max 30 seconds), then is handed directly to your MCP client.</li>
        <li><strong>Stored by your MCP client.</strong> After the handshake, your MCP client holds the token in its own secure credential store and sends it with every API request.</li>
        <li><strong>Used only against Open Collective.</strong> The token is forwarded as a <code>Personal-Token</code> header on GraphQL queries to Open Collective. No other service receives it.</li>
        <li><strong>Verified once.</strong> The server calls <code>{{ me {{ id }} }}</code> on Open Collective once at login to confirm the token is valid.</li>
        <li><strong>Read-only.</strong> This MCP server exposes only query operations — no mutations.</li>
      </ul>
    </div>

    <div class="footer">
      Built with care by <a href="https://github.com/opensourceeurope" target="_blank" rel="noopener">Open Source Europe</a>.
    </div>
  </div>
</body>
</html>"""


@dataclass
class _PendingAuth:
    """An authorize request awaiting the user pasting their OC token."""

    client_id: str
    redirect_uri: str
    redirect_uri_provided_explicitly: bool
    code_challenge: str
    state: str | None
    scopes: list[str]
    resource: str | None = None


@dataclass
class _CodeEntry:
    """A minted, single-use authorization code bound to its PKCE/redirect context."""

    oc_token: str
    client_id: str
    redirect_uri: str
    redirect_uri_provided_explicitly: bool
    code_challenge: str
    scopes: list[str]
    expires_at: float
    resource: str | None = None


class OCAuthProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    """Passthrough OAuth provider backed by Open Collective personal tokens."""

    def __init__(self, *, endpoint: str, now: Callable[[], float] = time.time) -> None:
        self._endpoint = endpoint
        self._now = now
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._pending: dict[str, _PendingAuth] = {}
        self._codes: dict[str, _CodeEntry] = {}

    # -- client registration -------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            client_info.client_id = secrets.token_urlsafe(16)
        self._clients[client_info.client_id] = client_info

    # -- authorize -> login form --------------------------------------------

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        request_id = secrets.token_urlsafe(16)
        self._pending[request_id] = _PendingAuth(
            client_id=client.client_id or "",
            redirect_uri=str(params.redirect_uri),
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            code_challenge=params.code_challenge,
            state=params.state,
            scopes=list(params.scopes or []),
            resource=params.resource,
        )
        return f"/oc-login?request_id={request_id}"

    # -- form callback -------------------------------------------------------

    def complete_login(
        self, request_id: str, oc_token: str, *, client: httpx.Client
    ) -> str:
        """Complete login from the form route.

        Validates the pasted OC token, mints a single-use authorization code bound
        to the pending request's PKCE/redirect/client/scopes, and returns the
        client redirect URI with ``?code=...&state=...`` appended.

        Raises ``ValueError`` with a user-facing message if the request is unknown
        or the token is invalid (so the route can re-render the form with an error).
        """
        oc_token = (oc_token or "").strip()
        pending = self._pending.get(request_id)
        if pending is None:
            raise ValueError("Your login session expired. Please start again.")
        if not oc_token:
            raise ValueError("Token is required.")
        if not verify_oc_token(oc_token, self._endpoint, client=client):
            raise ValueError(
                "Invalid or unauthorized token. Check your token and try again."
            )

        code = secrets.token_urlsafe(32)
        self._codes[code] = _CodeEntry(
            oc_token=oc_token,
            client_id=pending.client_id,
            redirect_uri=pending.redirect_uri,
            redirect_uri_provided_explicitly=pending.redirect_uri_provided_explicitly,
            code_challenge=pending.code_challenge,
            scopes=pending.scopes,
            expires_at=self._now() + CODE_TTL_SECONDS,
            resource=pending.resource,
        )
        # Pending request is consumed exactly once.
        del self._pending[request_id]

        return construct_redirect_uri(
            pending.redirect_uri, code=code, state=pending.state
        )

    # -- authorization code --------------------------------------------------

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        entry = self._codes.get(authorization_code)
        if entry is None:
            return None
        if entry.expires_at < self._now():
            return None
        if entry.client_id != (client.client_id or ""):
            return None
        return self._to_auth_code(authorization_code, entry)

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        # Pop for single use: even an expired or wrong-client code is removed.
        entry = self._codes.pop(authorization_code.code, None)
        if entry is None or entry.expires_at < self._now():
            raise TokenError("invalid_grant", "Invalid or expired authorization code")
        return OAuthToken(
            access_token=entry.oc_token,
            token_type="Bearer",
            scope=" ".join(entry.scopes) or None,
        )

    @staticmethod
    def _to_auth_code(code: str, entry: _CodeEntry) -> AuthorizationCode:
        return AuthorizationCode(
            code=code,
            scopes=entry.scopes,
            expires_at=entry.expires_at,
            client_id=entry.client_id,
            code_challenge=entry.code_challenge,
            redirect_uri=entry.redirect_uri,
            redirect_uri_provided_explicitly=entry.redirect_uri_provided_explicitly,
            resource=entry.resource,
        )

    # -- refresh tokens: unsupported ----------------------------------------

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        return None

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        raise TokenError("invalid_grant", "Refresh tokens are not supported")

    # -- access token: presence-only ----------------------------------------

    async def load_access_token(self, token: str) -> AccessToken | None:
        if not token:
            return None
        # PRESENCE ONLY: never call Open Collective here. OC rejects bad tokens
        # naturally when a tool actually runs a query.
        return AccessToken(
            token=token,
            client_id=ACCESS_TOKEN_CLIENT_ID,
            scopes=[],
            expires_at=None,
        )

    # -- revocation ----------------------------------------------------------

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        # Access tokens are the user's OC personal token and are never stored, so
        # there is nothing to revoke. Drop any matching authorization code defensively.
        value = getattr(token, "token", None)
        if value:
            self._codes.pop(value, None)
