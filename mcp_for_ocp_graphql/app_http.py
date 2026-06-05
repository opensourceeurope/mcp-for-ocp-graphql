"""Hosted Streamable-HTTP entrypoint with OAuth for mcp-for-ocp-graphql.

This serves the same three tools as the stdio entrypoint, but over Streamable-HTTP
with an OAuth 2.1 authorization-server flow (see :mod:`mcp_for_ocp_graphql.auth`).
The OAuth access token *is* the user's Open Collective personal token; on each
``graphql_query`` call we read that bearer from the request's auth context and forward
it to the OC GraphQL API as the ``Personal-Token`` header (per-request token).

Wiring (confirmed against mcp==1.27.2):
* ``FastMCP(..., auth_server_provider=provider, auth=AuthSettings(...), stateless_http=True)``.
  Passing ``auth_server_provider`` makes FastMCP auto-build a ``ProviderTokenVerifier``,
  which in turn wires the bearer-auth + auth-context middleware AND mounts the OAuth
  endpoints (``/.well-known/oauth-authorization-server``, ``/authorize``, ``/token``,
  ``/register``) plus the ``/mcp`` route.
* The custom login routes are registered with ``@mcp.custom_route(path, methods=[...])``
  (exists in 1.27.2; such routes are intentionally unauthenticated, suitable for the
  OAuth login form). They are appended to the Starlette app by ``streamable_http_app()``.
"""

from __future__ import annotations

import os

import httpx
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.fastmcp import FastMCP

from .auth import OCAuthProvider, render_auth_form
from .app_stdio import DEFAULT_ENDPOINT, load_doc_search, load_schema
from .schema_index import SchemaIndex
from .server import register_tools


def _request_token() -> str:
    """Resolve the per-request OC personal token from the auth context.

    Called at ``graphql_query`` time. Raises if there is no authenticated bearer,
    which should not happen behind the OAuth middleware but is defensive.
    """
    access = get_access_token()
    if access is None or not access.token:
        raise RuntimeError("No authenticated access token on this request.")
    return access.token


def build_http_app(*, provider: object | None = None):
    """Build and return the Starlette app for the hosted HTTP server.

    Factored out so the boot smoke test can drive it via Starlette's ``TestClient``
    without binding a port. ``provider`` may be injected (tests) — otherwise a real
    :class:`OCAuthProvider` is created against ``OC_GRAPHQL_ENDPOINT``.
    """
    endpoint = os.environ.get("OC_GRAPHQL_ENDPOINT", DEFAULT_ENDPOINT)
    port = int(os.environ.get("PORT", "3000"))
    public_url = os.environ.get("PUBLIC_URL", f"http://localhost:{port}")

    auth_provider = provider if provider is not None else OCAuthProvider(endpoint=endpoint)

    mcp = FastMCP(
        "mcp-for-ocp-graphql",
        auth_server_provider=auth_provider,
        auth=AuthSettings(
            issuer_url=public_url,
            resource_server_url=public_url,
            client_registration_options=ClientRegistrationOptions(enabled=True),
        ),
        host="0.0.0.0",
        port=port,
        stateless_http=True,
    )

    index = SchemaIndex(load_schema())
    doc_search = load_doc_search()
    register_tools(
        mcp,
        index=index,
        endpoint=endpoint,
        token=_request_token,  # per-request: resolved from auth context at call time
        doc_search=doc_search,
    )

    @mcp.custom_route("/oc-login", methods=["GET"])
    async def oc_login_get(request: Request) -> Response:
        request_id = request.query_params.get("request_id", "")
        return HTMLResponse(render_auth_form(request_id))

    @mcp.custom_route("/oc-login", methods=["POST"])
    async def oc_login_post(request: Request) -> Response:
        form = await request.form()
        request_id = str(form.get("request_id", ""))
        oc_token = str(form.get("oc_token", ""))
        try:
            with httpx.Client(timeout=30) as client:
                redirect_url = auth_provider.complete_login(
                    request_id, oc_token, client=client
                )
        except ValueError as exc:
            return HTMLResponse(
                render_auth_form(request_id, error=str(exc)), status_code=400
            )
        return RedirectResponse(url=redirect_url, status_code=302)

    return mcp.streamable_http_app()


def main():
    """Run the hosted Streamable-HTTP server.

    ``mcp.run(transport="streamable-http")`` would rebuild its own app; to guarantee the
    custom login routes are mounted we build the app explicitly and serve it with uvicorn.
    """
    import uvicorn

    port = int(os.environ.get("PORT", "3000"))
    app = build_http_app()
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
