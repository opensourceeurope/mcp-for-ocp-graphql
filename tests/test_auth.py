import asyncio

import httpx
import pytest

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from mcp_for_ocp_graphql.auth import OCAuthProvider, render_auth_form, verify_oc_token

ENDPOINT = "https://api.opencollective.com/graphql/v2"


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------------------
# verify_oc_token
# ---------------------------------------------------------------------------

def test_verify_oc_token_true_when_me_present():
    captured = {}

    def handler(request):
        captured["headers"] = request.headers
        return httpx.Response(200, json={"data": {"me": {"id": "1"}}})

    with _client(handler) as client:
        assert verify_oc_token("good-token", ENDPOINT, client=client) is True
    assert captured["headers"]["Personal-Token"] == "good-token"


def test_verify_oc_token_false_on_non_200():
    def handler(request):
        return httpx.Response(401, json={"errors": [{"message": "unauthorized"}]})

    with _client(handler) as client:
        assert verify_oc_token("bad-token", ENDPOINT, client=client) is False


def test_verify_oc_token_false_when_me_null():
    def handler(request):
        return httpx.Response(200, json={"data": {"me": None}})

    with _client(handler) as client:
        assert verify_oc_token("tok", ENDPOINT, client=client) is False


def test_verify_oc_token_false_on_network_error():
    def handler(request):
        raise httpx.ConnectError("boom")

    with _client(handler) as client:
        assert verify_oc_token("tok", ENDPOINT, client=client) is False


# ---------------------------------------------------------------------------
# render_auth_form (XSS boundary)
# ---------------------------------------------------------------------------

def test_render_auth_form_escapes_error_and_includes_fields():
    html = render_auth_form("req-123", error="<script>alert(1)</script>")
    assert "&lt;script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    # request_id is present (escaped form is identical for a plain id)
    assert "req-123" in html
    # the oc_token field exists and posts to /oc-login
    assert 'name="oc_token"' in html
    assert 'name="request_id"' in html
    assert "/oc-login" in html


def test_render_auth_form_escapes_request_id():
    html = render_auth_form('"><img src=x onerror=y>', error=None)
    assert "<img src=x" not in html
    assert "&lt;img" in html


def test_render_auth_form_no_error_block_when_none():
    html = render_auth_form("req", error=None)
    assert 'name="oc_token"' in html


# ---------------------------------------------------------------------------
# client store round-trip
# ---------------------------------------------------------------------------

def _make_client(client_id="client-1"):
    return OAuthClientInformationFull(
        client_id=client_id,
        redirect_uris=["https://app.example/callback"],
    )


def test_register_and_get_client_round_trip():
    provider = OCAuthProvider(endpoint=ENDPOINT)
    info = _make_client("abc")

    async def run():
        await provider.register_client(info)
        return await provider.get_client("abc")

    got = asyncio.run(run())
    assert got is not None
    assert got.client_id == "abc"


def test_get_client_unknown_returns_none():
    provider = OCAuthProvider(endpoint=ENDPOINT)
    assert asyncio.run(provider.get_client("nope")) is None


# ---------------------------------------------------------------------------
# load_access_token: presence-only
# ---------------------------------------------------------------------------

def test_load_access_token_returns_access_token_for_nonempty():
    # No httpx client supplied at all -> proves no network call is made.
    provider = OCAuthProvider(endpoint=ENDPOINT)
    token = asyncio.run(provider.load_access_token("some-oc-token"))
    assert token is not None
    assert isinstance(token, AccessToken)
    assert token.token == "some-oc-token"
    assert token.scopes == []
    assert token.expires_at is None


def test_load_access_token_returns_none_for_empty():
    provider = OCAuthProvider(endpoint=ENDPOINT)
    assert asyncio.run(provider.load_access_token("")) is None


# ---------------------------------------------------------------------------
# authorize -> login form redirect
# ---------------------------------------------------------------------------

def _params(redirect="https://app.example/callback", state="xyz", challenge="chal"):
    return AuthorizationParams(
        state=state,
        scopes=["read"],
        code_challenge=challenge,
        redirect_uri=redirect,
        redirect_uri_provided_explicitly=True,
    )


def test_authorize_returns_login_redirect_with_request_id():
    provider = OCAuthProvider(endpoint=ENDPOINT)
    client = _make_client()
    url = asyncio.run(provider.authorize(client, _params()))
    assert url.startswith("/oc-login?request_id=")
    request_id = url.split("request_id=", 1)[1]
    assert request_id  # non-empty


# ---------------------------------------------------------------------------
# code lifecycle
# ---------------------------------------------------------------------------

def _ok_client():
    return _client(lambda r: httpx.Response(200, json={"data": {"me": {"id": "1"}}}))


def _bad_client():
    return _client(lambda r: httpx.Response(200, json={"data": {"me": None}}))


def test_code_lifecycle_happy_path():
    clock = {"now": 1000.0}
    provider = OCAuthProvider(endpoint=ENDPOINT, now=lambda: clock["now"])
    client = _make_client()

    async def run():
        url = await provider.authorize(client, _params(state="st"))
        request_id = url.split("request_id=", 1)[1]
        with _ok_client() as http:
            redirect = provider.complete_login(request_id, "PASTED-OC-TOKEN", client=http)
        # redirect carries code + state back to the client's redirect_uri
        assert "code=" in redirect
        assert "state=st" in redirect
        code = redirect.split("code=", 1)[1].split("&", 1)[0]

        loaded = await provider.load_authorization_code(client, code)
        assert loaded is not None
        assert isinstance(loaded, AuthorizationCode)
        assert loaded.code == code
        assert loaded.code_challenge == "chal"

        token = await provider.exchange_authorization_code(client, loaded)
        assert isinstance(token, OAuthToken)
        assert token.access_token == "PASTED-OC-TOKEN"
        assert token.token_type == "Bearer"
        return code, loaded

    code, loaded = asyncio.run(run())

    # SINGLE-USE: a second exchange of the same code must fail
    with pytest.raises(TokenError):
        asyncio.run(provider.exchange_authorization_code(client, loaded))


def test_load_authorization_code_rejects_wrong_client():
    provider = OCAuthProvider(endpoint=ENDPOINT)
    client = _make_client("owner")
    other = _make_client("intruder")

    async def run():
        url = await provider.authorize(client, _params())
        request_id = url.split("request_id=", 1)[1]
        with _ok_client() as http:
            redirect = provider.complete_login(request_id, "TOK", client=http)
        code = redirect.split("code=", 1)[1].split("&", 1)[0]
        return await provider.load_authorization_code(other, code)

    assert asyncio.run(run()) is None


def test_expired_code_is_rejected():
    clock = {"now": 1000.0}
    provider = OCAuthProvider(endpoint=ENDPOINT, now=lambda: clock["now"])
    client = _make_client()

    async def setup():
        url = await provider.authorize(client, _params())
        request_id = url.split("request_id=", 1)[1]
        with _ok_client() as http:
            redirect = provider.complete_login(request_id, "TOK", client=http)
        return redirect.split("code=", 1)[1].split("&", 1)[0]

    code = asyncio.run(setup())
    # advance the clock past the 30s TTL
    clock["now"] += 31

    assert asyncio.run(provider.load_authorization_code(client, code)) is None

    # exchanging an expired code raises invalid_grant
    expired = AuthorizationCode(
        code=code,
        scopes=["read"],
        expires_at=1000.0 + 30,
        client_id=client.client_id,
        code_challenge="chal",
        redirect_uri="https://app.example/callback",
        redirect_uri_provided_explicitly=True,
    )
    with pytest.raises(TokenError):
        asyncio.run(provider.exchange_authorization_code(client, expired))


def test_complete_login_invalid_token_raises_value_error():
    provider = OCAuthProvider(endpoint=ENDPOINT)
    client = _make_client()

    async def run():
        url = await provider.authorize(client, _params())
        return url.split("request_id=", 1)[1]

    request_id = asyncio.run(run())
    with _bad_client() as http:
        with pytest.raises(ValueError):
            provider.complete_login(request_id, "BAD-TOKEN", client=http)


def test_exchange_authorization_code_unknown_raises():
    provider = OCAuthProvider(endpoint=ENDPOINT)
    client = _make_client()
    bogus = AuthorizationCode(
        code="does-not-exist",
        scopes=[],
        expires_at=9_999_999_999.0,
        client_id=client.client_id,
        code_challenge="c",
        redirect_uri="https://app.example/callback",
        redirect_uri_provided_explicitly=True,
    )
    with pytest.raises(TokenError):
        asyncio.run(provider.exchange_authorization_code(client, bogus))


# ---------------------------------------------------------------------------
# refresh tokens are not supported
# ---------------------------------------------------------------------------

def test_load_refresh_token_returns_none():
    provider = OCAuthProvider(endpoint=ENDPOINT)
    client = _make_client()
    assert asyncio.run(provider.load_refresh_token(client, "anything")) is None


def test_exchange_refresh_token_raises_token_error():
    provider = OCAuthProvider(endpoint=ENDPOINT)
    client = _make_client()
    from mcp.server.auth.provider import RefreshToken

    rt = RefreshToken(token="r", client_id=client.client_id, scopes=[])
    with pytest.raises(TokenError):
        asyncio.run(provider.exchange_refresh_token(client, rt, []))


def test_revoke_token_is_noop():
    provider = OCAuthProvider(endpoint=ENDPOINT)
    # revoking a never-issued token should not raise
    asyncio.run(provider.revoke_token(AccessToken(token="x", client_id="c", scopes=[])))
