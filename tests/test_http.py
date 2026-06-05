import html

from starlette.testclient import TestClient

from mcp_for_ocp_graphql.app_http import build_http_app


def test_oauth_metadata_endpoint():
    client = TestClient(build_http_app())
    resp = client.get("/.well-known/oauth-authorization-server")
    assert resp.status_code == 200
    data = resp.json()
    for key in ("issuer", "authorization_endpoint", "token_endpoint", "registration_endpoint"):
        assert key in data, f"missing {key} in metadata: {data}"


def test_oc_login_get_renders_form():
    client = TestClient(build_http_app())
    resp = client.get("/oc-login?request_id=abc")
    assert resp.status_code == 200
    body = resp.text
    assert 'name="oc_token"' in body
    assert "abc" in body


def test_oc_login_post_invalid_token_rerenders_with_error():
    class FailingProvider:
        def complete_login(self, request_id, oc_token, *, client):
            raise ValueError("Invalid token")

    client = TestClient(build_http_app(provider=FailingProvider()))
    resp = client.post(
        "/oc-login",
        data={"request_id": "abc", "oc_token": "bad"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert html.escape("Invalid token", quote=True) in resp.text
