# MCP Python SDK Auth + Streamable-HTTP — Spike Findings

**SDK version confirmed:** `mcp` 1.27.2 (Python 3.11)
**All findings confirmed by reading installed source under `.venv/lib/python3.11/site-packages/mcp/`**

---

## 1. Auth Provider Protocol

### File
`mcp/server/auth/provider.py`

### Class to implement
```python
from mcp.server.auth.provider import OAuthAuthorizationServerProvider
```

`OAuthAuthorizationServerProvider` is a `Protocol` (structural subtyping). You do not need to inherit from it — just implement the required methods with matching signatures. It is generic over three TypeVars:

```python
class OAuthAuthorizationServerProvider(Protocol, Generic[AuthorizationCodeT, RefreshTokenT, AccessTokenT]):
    ...
```

For a concrete class the simplest form is:

```python
class MyProvider:
    async def get_client(...) -> ...: ...
    async def register_client(...) -> None: ...
    async def authorize(...) -> str: ...
    async def load_authorization_code(...) -> AuthorizationCode | None: ...
    async def exchange_authorization_code(...) -> OAuthToken: ...
    async def load_refresh_token(...) -> RefreshToken | None: ...
    async def exchange_refresh_token(...) -> OAuthToken: ...
    async def load_access_token(...) -> AccessToken | None: ...
    async def revoke_token(...) -> None: ...
```

### Data models (all in `mcp/server/auth/provider.py`)

```python
from mcp.server.auth.provider import (
    AccessToken,         # token, client_id, scopes, expires_at, resource, subject, claims
    AuthorizationCode,   # code, scopes, expires_at, client_id, code_challenge, redirect_uri,
                         #   redirect_uri_provided_explicitly, resource, subject
    RefreshToken,        # token, client_id, scopes, expires_at, subject
    AuthorizationParams, # state, scopes, code_challenge, redirect_uri,
                         #   redirect_uri_provided_explicitly, resource
    AuthorizeError,      # dataclass(frozen=True): error, error_description
    TokenError,          # dataclass(frozen=True): error, error_description
    RegistrationError,   # dataclass(frozen=True): error, error_description
    construct_redirect_uri,  # construct_redirect_uri(base: str, **params: str | None) -> str
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
```

### Every method signature — exact

```python
async def get_client(self, client_id: str) -> OAuthClientInformationFull | None: ...

async def register_client(self, client_info: OAuthClientInformationFull) -> None: ...

async def authorize(
    self,
    client: OAuthClientInformationFull,
    params: AuthorizationParams,
) -> str:
    # Return a URL string to redirect to.
    # For the passthrough flow: store params, render the HTML form at a custom
    # route, and construct the redirect-back URL yourself.
    # This method should return the URL of your custom HTML token-entry form.
    ...

async def load_authorization_code(
    self,
    client: OAuthClientInformationFull,
    authorization_code: str,
) -> AuthorizationCode | None: ...

async def exchange_authorization_code(
    self,
    client: OAuthClientInformationFull,
    authorization_code: AuthorizationCode,
) -> OAuthToken: ...
    # OAuthToken fields: access_token, token_type="Bearer", expires_in, scope, refresh_token

async def load_refresh_token(
    self,
    client: OAuthClientInformationFull,
    refresh_token: str,
) -> RefreshToken | None: ...

async def exchange_refresh_token(
    self,
    client: OAuthClientInformationFull,
    refresh_token: RefreshToken,
    scopes: list[str],
) -> OAuthToken: ...

async def load_access_token(self, token: str) -> AccessToken | None: ...
    # For presence-only verification: return an AccessToken if the string
    # exists in your in-memory store. The SDK bearer middleware calls this
    # via ProviderTokenVerifier.verify_token -> provider.load_access_token.

async def revoke_token(
    self,
    token: AccessToken | RefreshToken,
) -> None: ...
```

### Helper error types

```python
from mcp.server.auth.provider import AuthorizeError, TokenError, RegistrationError
# All are @dataclass(frozen=True) with fields: error (Literal), error_description: str | None
# Raise them from the appropriate methods; handlers catch them automatically.
```

---

## 2. AuthSettings and Wiring

### File
`mcp/server/auth/settings.py`

```python
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions

auth = AuthSettings(
    issuer_url="http://localhost:8000",         # AnyHttpUrl; HTTPS required except localhost
    service_documentation_url=None,
    client_registration_options=ClientRegistrationOptions(
        enabled=True,           # enables /register endpoint (dynamic client registration)
        client_secret_expiry_seconds=None,
        valid_scopes=None,      # None = no scope validation
        default_scopes=None,
    ),
    revocation_options=RevocationOptions(enabled=False),
    required_scopes=None,       # None = no scope requirements on MCP endpoints
    resource_server_url=None,   # None = AS+RS are the same server
)
```

**`AuthSettings` field notes:**
- `issuer_url`: The base URL used to construct auth endpoint URLs and for `/.well-known/oauth-authorization-server`. Must not have a trailing slash, fragment, or query string.
- `resource_server_url`: When set to the MCP server URL, the SDK also serves `/.well-known/oauth-protected-resource`. For a single combined AS+RS server, set this to the same base URL or leave `None`.

---

## 3. FastMCP Constructor and Auth Attachment

### File
`mcp/server/fastmcp/server.py`

```python
from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions

mcp = FastMCP(
    name="oc-mcp",
    auth_server_provider=my_provider,   # OAuthAuthorizationServerProvider impl
    token_verifier=None,                # if auth_server_provider is given, token_verifier
                                        # is auto-created as ProviderTokenVerifier(provider)
    auth=AuthSettings(...),
    host="0.0.0.0",
    port=8000,
    stateless_http=True,               # create fresh transport per request (recommended for OAuth)
)
```

**Validation rules enforced in `__init__`:**
- You must provide exactly ONE of `auth_server_provider` or `token_verifier` when `auth` is set.
- Providing neither, or both, raises `ValueError`.
- If `auth_server_provider` is given without `token_verifier`, a `ProviderTokenVerifier` wrapping the provider is created automatically.

---

## 4. Running Streamable-HTTP

### Option A — `mcp.run()` (synchronous entry point)

```python
mcp.run(transport="streamable-http")
# Internally calls anyio.run(mcp.run_streamable_http_async)
# which calls uvicorn with host/port from settings.
```

### Option B — `streamable_http_app()` + uvicorn (more control)

```python
import uvicorn

app = mcp.streamable_http_app()
uvicorn.run(app, host="0.0.0.0", port=8000)
```

`streamable_http_app()` returns a fully configured `starlette.applications.Starlette` instance that includes:

- Auth routes mounted at `/authorize`, `/token`, `/register` (if enabled), `/revoke` (if enabled)
- `/.well-known/oauth-authorization-server` metadata endpoint
- `GET+POST /mcp` endpoint (default; configurable via `streamable_http_path`) protected by `RequireAuthMiddleware`
- `AuthenticationMiddleware` with `BearerAuthBackend` and `AuthContextMiddleware` in the middleware stack
- Any custom routes registered via `@mcp.custom_route`

**MCP endpoint path** defaults to `/mcp`. Override at construction:
```python
mcp = FastMCP(..., streamable_http_path="/mcp")
```

---

## 5. How the `/authorize` SDK Route Works (Critical for Passthrough)

### File
`mcp/server/auth/handlers/authorize.py`

The SDK's `AuthorizationHandler.handle()`:

1. Parses `GET /authorize?client_id=...&code_challenge=...&redirect_uri=...` query params.
2. Validates `response_type=code`, `code_challenge_method=S256` (PKCE required).
3. Loads the client via `provider.get_client(client_id)`.
4. Validates `redirect_uri` against the client's registered URIs.
5. Builds an `AuthorizationParams` object.
6. Calls `await provider.authorize(client, params)` and redirects to the URL it returns.

**Passthrough strategy:** Your `authorize()` implementation stores the `AuthorizationParams` in memory (keyed by a random state token) and returns the URL of your custom HTML form (e.g., `http://localhost:8000/oc-authorize?state=<token>`). The SDK's `/authorize` handler will redirect the browser there.

```python
import secrets

class OCProvider:
    def __init__(self):
        self._pending: dict[str, tuple[OAuthClientInformationFull, AuthorizationParams]] = {}
        self._codes: dict[str, AuthorizationCode] = {}
        self._tokens: dict[str, AccessToken] = {}
        self._clients: dict[str, OAuthClientInformationFull] = {}

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        state_key = secrets.token_urlsafe(32)
        self._pending[state_key] = (client, params)
        return f"http://localhost:8000/oc-authorize?pending_state={state_key}"
```

---

## 6. Custom HTML Authorize Route

### Decorator
`@mcp.custom_route(path, methods)` — defined in `FastMCP.custom_route()`

```python
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

@mcp.custom_route("/oc-authorize", methods=["GET", "POST"])
async def oc_authorize_form(request: Request) -> Response:
    if request.method == "GET":
        pending_state = request.query_params.get("pending_state", "")
        html = f"""
        <form method="POST" action="/oc-authorize">
          <input type="hidden" name="pending_state" value="{pending_state}">
          <label>Paste your Open Collective Personal Token:</label>
          <input type="password" name="oc_token" required>
          <button type="submit">Authorize</button>
        </form>
        """
        return HTMLResponse(html)

    form = await request.form()
    pending_state = form.get("pending_state", "")
    oc_token = form.get("oc_token", "")

    client, params = provider._pending.pop(pending_state, (None, None))
    if not client or not params:
        return HTMLResponse("Invalid or expired state.", status_code=400)

    # Validate OC token by calling the OC API
    # (skipped here — call OC's /api/v1/me or similar)

    # Issue auth code
    code = secrets.token_urlsafe(32)
    import time
    provider._codes[code] = AuthorizationCode(
        code=code,
        scopes=params.scopes or [],
        expires_at=time.time() + 30,           # 30-second TTL
        client_id=client.client_id,
        code_challenge=params.code_challenge,
        redirect_uri=params.redirect_uri,
        redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
        resource=params.resource,
    )

    # Redirect back to the client's redirect_uri with code + state
    redirect_url = construct_redirect_uri(
        str(params.redirect_uri),
        code=code,
        state=params.state,
    )
    return RedirectResponse(redirect_url, status_code=302)
```

**Important note:** The docstring for `@custom_route` explicitly states that routes registered this way do NOT require authorization — correct for an auth flow page.

---

## 7. Bearer Token Extraction Inside a Tool

### File
`mcp/server/auth/middleware/auth_context.py`

```python
from mcp.server.auth.middleware.auth_context import get_access_token
# Returns: AccessToken | None
```

`get_access_token()` reads from a `ContextVar` (`auth_context_var`) that is populated by `AuthContextMiddleware` for every authenticated request.

**Usage in a tool:**

```python
from mcp.server.fastmcp import FastMCP, Context
from mcp.server.auth.middleware.auth_context import get_access_token

mcp = FastMCP(...)

@mcp.tool()
async def some_tool(query: str, ctx: Context) -> str:
    token_info = get_access_token()
    if token_info is None:
        raise ValueError("Not authenticated")
    oc_token = token_info.token        # the raw access_token string == OC personal token
    # Use it as: headers={"Personal-Token": oc_token}
    ...
```

`token_info.token` is the raw string value stored in your `AccessToken` when you called `exchange_authorization_code`. For the passthrough design, this is the OC token the user pasted.

**How it flows:**
1. Client sends `Authorization: Bearer <access_token>` on MCP requests.
2. `BearerAuthBackend.authenticate()` extracts the `Bearer ` prefix, calls `token_verifier.verify_token(token)`.
3. `ProviderTokenVerifier.verify_token` calls `provider.load_access_token(token)` — your in-memory lookup.
4. `AuthContextMiddleware` stores the result `AccessToken` in `auth_context_var`.
5. Any sync or async call to `get_access_token()` during that request returns it.

---

## 8. Token Exchange Implementation Detail

The SDK's `TokenHandler` (`mcp/server/auth/handlers/token.py`) handles PKCE verification before calling your provider:

1. Calls `provider.load_authorization_code(client, code)` — your lookup.
2. Checks `expires_at < time.time()` — expires authorization codes for you.
3. Verifies PKCE: `base64url(sha256(code_verifier)) == auth_code.code_challenge`.
4. Only then calls `provider.exchange_authorization_code(client, auth_code)`.

**Your `exchange_authorization_code` should:**
- Delete the authorization code from storage (single-use).
- Store the new `AccessToken` in memory.
- Return an `OAuthToken(access_token=oc_token, token_type="Bearer")`.

```python
async def exchange_authorization_code(
    self,
    client: OAuthClientInformationFull,
    authorization_code: AuthorizationCode,
) -> OAuthToken:
    # single-use: remove code
    del self._codes[authorization_code.code]

    # store access token (presence-only — no expiry needed for passthrough)
    self._tokens[authorization_code.code] = AccessToken(
        token=authorization_code.code,   # reuse code value or generate new
        client_id=client.client_id,
        scopes=authorization_code.scopes,
    )
    # Actually: the OC token is the value we want to store.
    # We need it to have been threaded through from the authorize step.
    # One pattern: store it in the AuthorizationCode.subject field or
    # subclass AuthorizationCode with an extra field (the SDK allows this —
    # see NOTE in provider.py: "FastMCP doesn't render any of these types
    # in the user response, so it's OK to add fields to subclasses").
    ...
    return OAuthToken(access_token=oc_token_string, token_type="Bearer")
```

**Trick for storing the OC token through the flow:** Subclass `AuthorizationCode` with an extra field:

```python
from mcp.server.auth.provider import AuthorizationCode

class OCAuthorizationCode(AuthorizationCode):
    oc_token: str  # the pasted OC personal token
```

This works because `OAuthAuthorizationServerProvider` is generic over `AuthorizationCodeT = TypeVar("AuthorizationCodeT", bound=AuthorizationCode)` and `load_authorization_code` can return your subtype.

---

## 9. Complete Wiring Skeleton

```python
import secrets
import time
from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.auth.provider import (
    AuthorizationCode, AuthorizationParams, AccessToken, RefreshToken,
    AuthorizeError, TokenError, construct_redirect_uri,
)
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

ISSUER = "http://localhost:8000"   # change for production

class OCProvider:
    def __init__(self):
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._pending: dict[str, tuple[OAuthClientInformationFull, AuthorizationParams]] = {}
        self._codes: dict[str, "OCAuthorizationCode"] = {}
        self._tokens: dict[str, AccessToken] = {}

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self._clients[client_info.client_id] = client_info

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        key = secrets.token_urlsafe(32)
        self._pending[key] = (client, params)
        return f"{ISSUER}/oc-authorize?pending_state={key}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> "OCAuthorizationCode | None":
        return self._codes.get(authorization_code)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: "OCAuthorizationCode"
    ) -> OAuthToken:
        del self._codes[authorization_code.code]
        access_token = AccessToken(
            token=authorization_code.oc_token,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
        )
        self._tokens[authorization_code.oc_token] = access_token
        return OAuthToken(access_token=authorization_code.oc_token, token_type="Bearer")

    async def load_access_token(self, token: str) -> AccessToken | None:
        return self._tokens.get(token)   # presence-only check

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        return None  # no refresh tokens in passthrough

    async def exchange_refresh_token(self, client, refresh_token, scopes) -> OAuthToken:
        raise TokenError(error="invalid_grant", error_description="refresh not supported")

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        if isinstance(token, AccessToken):
            self._tokens.pop(token.token, None)


class OCAuthorizationCode(AuthorizationCode):
    oc_token: str  # the pasted OC personal token


provider = OCProvider()

mcp = FastMCP(
    name="oc-mcp",
    auth_server_provider=provider,
    auth=AuthSettings(
        issuer_url=ISSUER,
        client_registration_options=ClientRegistrationOptions(enabled=True),
        resource_server_url=ISSUER,   # combined AS+RS
    ),
    host="0.0.0.0",
    port=8000,
    stateless_http=True,
)

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

@mcp.custom_route("/oc-authorize", methods=["GET", "POST"])
async def oc_authorize_form(request: Request):
    if request.method == "GET":
        ps = request.query_params.get("pending_state", "")
        return HTMLResponse(f"""<form method="POST">
          <input type="hidden" name="pending_state" value="{ps}">
          <input type="password" name="oc_token" placeholder="Your OC personal token">
          <button>Authorize</button></form>""")
    form = await request.form()
    ps = str(form.get("pending_state", ""))
    oc_token = str(form.get("oc_token", "")).strip()
    pair = provider._pending.pop(ps, None)
    if not pair or not oc_token:
        return HTMLResponse("Invalid state or missing token.", status_code=400)
    client, params = pair
    # TODO: validate oc_token against OC API here
    code_str = secrets.token_urlsafe(32)
    provider._codes[code_str] = OCAuthorizationCode(
        code=code_str, scopes=params.scopes or [],
        expires_at=time.time() + 30, client_id=client.client_id,
        code_challenge=params.code_challenge, redirect_uri=params.redirect_uri,
        redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
        resource=params.resource, oc_token=oc_token,
    )
    return RedirectResponse(construct_redirect_uri(str(params.redirect_uri), code=code_str, state=params.state), 302)


@mcp.tool()
async def example_tool(query: str) -> str:
    token = get_access_token()
    oc_token_str = token.token if token else ""
    # headers={"Personal-Token": oc_token_str}
    return f"would call OC API with token length {len(oc_token_str)}"


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

---

## 10. SDK-Imposed Constraints and Gotchas

### A. `authorize()` returns a URL — it does NOT render HTML
The SDK's `/authorize` handler calls `provider.authorize()` and immediately issues a `302 RedirectResponse`. You cannot return an HTML page from `authorize()`. You must redirect to a custom route that renders the form.

### B. Registration requires `authorization_code` + `refresh_token` in `grant_types`
`RegistrationHandler` (`mcp/server/auth/handlers/register.py` line 76) rejects clients that don't include both `"authorization_code"` and `"refresh_token"` in `grant_types`. Your `exchange_refresh_token` must therefore be implemented (even if it just raises `TokenError`).

### C. PKCE is mandatory; `code_challenge_method` must be `S256`
`AuthorizationRequest` model (`mcp/server/auth/handlers/authorize.py`) enforces `Literal["S256"]` for `code_challenge_method`. The `TokenHandler` performs SHA-256 PKCE verification before calling your provider — you cannot skip this.

### D. `issuer_url` must be HTTPS in production
`validate_issuer_url()` in `mcp/server/auth/routes.py` allows HTTP only for `localhost` / `127.0.0.1`. Any non-localhost deployment requires HTTPS.

### E. `AuthorizationCode.expires_at` is a `float` (Unix timestamp)
The `TokenHandler` checks `auth_code.expires_at < time.time()`. Set it to `time.time() + 30` for 30-second TTL.

### F. `AccessToken.expires_at` is an `int | None`
The `BearerAuthBackend` checks `auth_info.expires_at < int(time.time())` only when `expires_at` is not `None`. For presence-only verification, set `expires_at=None`.

### G. `custom_route` routes are NOT auth-protected
The decorator's docstring confirms: "Routes using this decorator will not require authorization." Safe to use for the HTML form.

### H. `stateless_http=True` is needed for OAuth
When `stateless_http=True`, `StreamableHTTPSessionManager` creates a fresh transport per request. This is correct for OAuth passthrough — the bearer token is re-verified on every request via `BearerAuthBackend`.

### I. `token_verifier` is auto-created from `auth_server_provider`
If only `auth_server_provider` is given, `FastMCP.__init__` creates `ProviderTokenVerifier(auth_server_provider)`. This means `load_access_token` is the hook for token verification — presence in the dict is enough.

### J. Dynamic client registration stores clients via `register_client`
Your `register_client` must persist `OAuthClientInformationFull` objects (at minimum in-memory dict). The `client_id` is set by the `RegistrationHandler` (a UUID4) before calling `register_client`.

---

## 11. Key Import Map

| What you need | Import |
|---|---|
| Provider protocol | `from mcp.server.auth.provider import OAuthAuthorizationServerProvider` |
| Data models | `from mcp.server.auth.provider import AccessToken, AuthorizationCode, RefreshToken, AuthorizationParams` |
| Error types | `from mcp.server.auth.provider import AuthorizeError, TokenError, RegistrationError` |
| Redirect URL builder | `from mcp.server.auth.provider import construct_redirect_uri` |
| Client + token models | `from mcp.shared.auth import OAuthClientInformationFull, OAuthToken` |
| AuthSettings | `from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions` |
| FastMCP | `from mcp.server.fastmcp import FastMCP` |
| Token in tool | `from mcp.server.auth.middleware.auth_context import get_access_token` |
| Route function | `from mcp.server.auth.routes import create_auth_routes` (used internally; not needed directly) |
