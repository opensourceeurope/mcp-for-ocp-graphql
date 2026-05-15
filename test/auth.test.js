import { test, describe, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { verifyOCToken, createOAuthProvider, renderAuthForm } from '../src/auth.js';

describe('verifyOCToken', () => {
  let originalFetch;
  before(() => { originalFetch = globalThis.fetch; });
  after(() => { globalThis.fetch = originalFetch; });

  test('returns account info when token is valid', async () => {
    globalThis.fetch = async (_url, opts) => {
      assert.equal(opts.headers['Personal-Token'], 'valid-token');
      return { ok: true, json: async () => ({ data: { me: { id: 'abc123', slug: 'testuser' } } }) };
    };
    const result = await verifyOCToken('valid-token', 'https://api.example.com/graphql');
    assert.deepEqual(result, { id: 'abc123', slug: 'testuser' });
  });

  test('returns null when OC returns errors', async () => {
    globalThis.fetch = async () => ({
      ok: true,
      json: async () => ({ errors: [{ message: 'Unauthorized' }] }),
    });
    const result = await verifyOCToken('bad-token', 'https://api.example.com/graphql');
    assert.equal(result, null);
  });

  test('returns null when me is missing from response', async () => {
    globalThis.fetch = async () => ({
      ok: true,
      json: async () => ({ data: { me: null } }),
    });
    const result = await verifyOCToken('bad-token', 'https://api.example.com/graphql');
    assert.equal(result, null);
  });

  test('returns null on HTTP error', async () => {
    globalThis.fetch = async () => ({ ok: false, status: 401 });
    const result = await verifyOCToken('bad-token', 'https://api.example.com/graphql');
    assert.equal(result, null);
  });
});

describe('createOAuthProvider', () => {
  let originalFetch;
  before(() => { originalFetch = globalThis.fetch; });
  after(() => { globalThis.fetch = originalFetch; });

  const ENDPOINT = 'https://api.example.com/graphql';

  describe('clientsStore', () => {
    test('registers a client and retrieves it by id', async () => {
      const provider = createOAuthProvider(ENDPOINT);
      const client = await provider.clientsStore.registerClient({
        client_name: 'Claude Code',
        redirect_uris: ['http://localhost:3000/callback'],
      });
      assert.ok(client.client_id, 'should assign a client_id');
      const retrieved = await provider.clientsStore.getClient(client.client_id);
      assert.deepEqual(retrieved, client);
    });

    test('returns undefined for unknown client', async () => {
      const provider = createOAuthProvider(ENDPOINT);
      const result = await provider.clientsStore.getClient('nonexistent');
      assert.equal(result, undefined);
    });
  });

  describe('verifyAccessToken', () => {
    test('returns auth info for any non-empty token', async () => {
      const provider = createOAuthProvider(ENDPOINT);
      const before = Math.floor(Date.now() / 1000);
      const info = await provider.verifyAccessToken('any-token');
      assert.equal(info.token, 'any-token');
      assert.equal(info.clientId, 'oc-user');
      assert.ok(Array.isArray(info.scopes));
      assert.ok(typeof info.expiresAt === 'number' && info.expiresAt > before, 'expiresAt must be a future Unix timestamp');
    });

    test('throws for missing token', async () => {
      const provider = createOAuthProvider(ENDPOINT);
      await assert.rejects(() => provider.verifyAccessToken(''), /missing/i);
      await assert.rejects(() => provider.verifyAccessToken(null), /missing/i);
    });
  });

  describe('exchangeAuthorizationCode', () => {
    test('returns OC token and deletes code after use', async () => {
      globalThis.fetch = async () => ({
        ok: true,
        json: async () => ({ data: { me: { id: 'abc', slug: 'alice' } } }),
      });
      const provider = createOAuthProvider(ENDPOINT);

      // Simulate authorize flow: store a code manually via authorize()
      const fakeParams = { codeChallenge: 'challenge123', redirectUri: 'http://localhost:1234/cb', state: 'st', scopes: [] };
      const fakeClient = { client_id: 'c1', redirect_uris: ['http://localhost:1234/cb'] };
      let redirected;
      const fakeRes = {
        req: { method: 'POST', body: { oc_token: 'my-oc-token' } },
        redirect: (_code, url) => { redirected = url; },
        send: () => {},
      };

      await provider.authorize(fakeClient, fakeParams, fakeRes);
      assert.ok(redirected, 'should have redirected');

      const code = new URL(redirected).searchParams.get('code');
      assert.ok(code, 'redirect should include code');

      const tokens = await provider.exchangeAuthorizationCode(fakeClient, code);
      assert.equal(tokens.access_token, 'my-oc-token');
      assert.equal(tokens.token_type, 'bearer');

      // Code must be deleted — second exchange should fail
      await assert.rejects(() => provider.exchangeAuthorizationCode(fakeClient, code), /invalid|expired/i);
    });

    test('rejects expired codes', async () => {
      const provider = createOAuthProvider(ENDPOINT);
      await assert.rejects(
        () => provider.exchangeAuthorizationCode({}, 'nonexistent-code'),
        /invalid|expired/i
      );
    });
  });

  describe('authorize', () => {
    test('renders form on GET', async () => {
      const provider = createOAuthProvider(ENDPOINT);
      const params = { codeChallenge: 'ch', redirectUri: 'http://localhost/cb', state: 'st', scopes: [] };
      const client = { client_id: 'c1', redirect_uris: ['http://localhost/cb'] };
      let sent;
      const res = { req: { method: 'GET', body: {} }, send: (html) => { sent = html; }, redirect: () => {} };

      await provider.authorize(client, params, res);
      assert.ok(sent.includes('<form'), 'should render a form');
      assert.ok(sent.includes('oc_token'), 'form should have oc_token field');
    });

    test('renders form with error when token field empty on POST', async () => {
      const provider = createOAuthProvider(ENDPOINT);
      const params = { codeChallenge: 'ch', redirectUri: 'http://localhost/cb', state: 'st', scopes: [] };
      const client = { client_id: 'c1', redirect_uris: ['http://localhost/cb'] };
      let sent;
      const res = { req: { method: 'POST', body: { oc_token: '' } }, send: (html) => { sent = html; }, redirect: () => {} };

      await provider.authorize(client, params, res);
      assert.ok(sent.includes('<form'), 'should re-render form');
      assert.ok(sent.includes('required'), 'should show error');
    });

    test('renders form with error when OC rejects token on POST', async () => {
      globalThis.fetch = async () => ({ ok: true, json: async () => ({ data: { me: null } }) });
      const provider = createOAuthProvider(ENDPOINT);
      const params = { codeChallenge: 'ch', redirectUri: 'http://localhost/cb', state: 'st', scopes: [] };
      const client = { client_id: 'c1', redirect_uris: ['http://localhost/cb'] };
      let sent;
      const res = { req: { method: 'POST', body: { oc_token: 'bad' } }, send: (html) => { sent = html; }, redirect: () => {} };

      await provider.authorize(client, params, res);
      assert.ok(sent.includes('<form'), 'should re-render form on invalid token');
    });

    test('escapes XSS in error messages', () => {
      const html = renderAuthForm({ codeChallenge: '<script>', redirectUri: 'http://x/cb', state: '', scopes: [] }, { client_id: '<evil>' }, 'bad <token>');
      assert.ok(!html.includes('<script>'), 'should escape script tags');
      assert.ok(!html.includes('<evil>'), 'should escape client_id');
      assert.ok(html.includes('&lt;script&gt;'), 'should have escaped version');
    });
  });

  describe('challengeForAuthorizationCode', () => {
    test('returns stored challenge for valid code', async () => {
      globalThis.fetch = async () => ({
        ok: true,
        json: async () => ({ data: { me: { id: 'abc', slug: 'alice' } } }),
      });
      const provider = createOAuthProvider(ENDPOINT);
      const params = { codeChallenge: 'mychallenge', redirectUri: 'http://localhost/cb', state: '', scopes: [] };
      const client = { client_id: 'c1', redirect_uris: ['http://localhost/cb'] };
      let redirected;
      const res = {
        req: { method: 'POST', body: { oc_token: 'tok' } },
        redirect: (_c, url) => { redirected = url; },
        send: () => {},
      };
      await provider.authorize(client, params, res);
      const code = new URL(redirected).searchParams.get('code');
      const challenge = await provider.challengeForAuthorizationCode(client, code);
      assert.equal(challenge, 'mychallenge');
    });

    test('throws for unknown code', async () => {
      const provider = createOAuthProvider(ENDPOINT);
      await assert.rejects(() => provider.challengeForAuthorizationCode({}, 'unknown'), /invalid|expired/i);
    });
  });
});

describe('renderAuthForm', () => {
  test('escapes all user-controlled values', () => {
    const html = renderAuthForm(
      { codeChallenge: '"><img>', redirectUri: 'http://x/cb', state: '"><svg>', scopes: [] },
      { client_id: '"><script>alert(1)</script>' },
      null
    );
    assert.ok(!html.includes('"><img>'));
    assert.ok(!html.includes('"><svg>'));
    assert.ok(!html.includes('<script>alert'));
  });

  test('includes all required hidden fields', () => {
    const html = renderAuthForm(
      { codeChallenge: 'ch', redirectUri: 'http://x/cb', state: 'st', scopes: ['account'] },
      { client_id: 'c1' },
      null
    );
    assert.ok(html.includes('name="code_challenge"'));
    assert.ok(html.includes('name="redirect_uri"'));
    assert.ok(html.includes('name="state"'));
    assert.ok(html.includes('name="response_type"'));
    assert.ok(html.includes('name="code_challenge_method"'));
    assert.ok(html.includes('name="scope"'));
    assert.ok(html.includes('name="client_id"'));
  });
});
