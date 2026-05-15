import crypto from 'node:crypto';

// code -> { ocToken, codeChallenge, expiresAt }
const pendingCodes = new Map();

// Purge expired codes every minute so memory doesn't grow unbounded
setInterval(() => {
  const now = Date.now();
  for (const [code, entry] of pendingCodes) {
    if (entry.expiresAt < now) pendingCodes.delete(code);
  }
}, 60_000).unref();

// clientId -> client info
const registeredClients = new Map();

export async function verifyOCToken(token, endpoint) {
  let res;
  try {
    res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Personal-Token': token },
      body: JSON.stringify({ query: '{ me { id slug } }' }),
    });
  } catch {
    return null;
  }
  if (!res.ok) return null;
  const { data, errors } = await res.json();
  if (errors?.length || !data?.me?.id) return null;
  return data.me;
}

export function escape(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;');
}

export function renderAuthForm(params, client, errorMessage) {
  const err = errorMessage
    ? `<p class="error" role="alert">${escape(errorMessage)}</p>`
    : '';
  const scopeField = params.scopes?.length
    ? `<input type="hidden" name="scope" value="${escape(params.scopes.join(' '))}">`
    : '';
  const stateField = params.state
    ? `<input type="hidden" name="state" value="${escape(params.state)}">`
    : '';

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Authenticate — MCP for Open Collective</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #f5f5f5; display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 1rem; }
    .card { background: #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,.12); padding: 2rem; width: 100%; max-width: 480px; }
    h1 { font-size: 1.25rem; margin-bottom: .5rem; }
    p.subtitle { color: #555; font-size: .9rem; margin-bottom: 1.5rem; }
    label { display: block; font-size: .875rem; font-weight: 500; margin-bottom: .4rem; }
    input[type="password"] { width: 100%; padding: .6rem .75rem; border: 1px solid #ccc; border-radius: 4px; font-size: 1rem; margin-bottom: 1rem; }
    input[type="password"]:focus { outline: 2px solid #1869f5; border-color: transparent; }
    button { width: 100%; padding: .7rem; background: #1869f5; color: #fff; border: none; border-radius: 4px; font-size: 1rem; cursor: pointer; }
    button:hover { background: #0f52c7; }
    .error { color: #c0392b; font-size: .875rem; margin-bottom: 1rem; padding: .5rem .75rem; background: #fdf2f2; border-radius: 4px; border: 1px solid #f5c6cb; }
    .hint { margin-top: 1rem; font-size: .8rem; color: #666; text-align: center; }
    .hint a { color: #1869f5; }
    .security { margin-top: 1.5rem; padding: 1rem; background: #f8f9fa; border-radius: 6px; border: 1px solid #e9ecef; }
    .security h2 { font-size: .875rem; font-weight: 600; color: #333; margin-bottom: .6rem; }
    .security ul { padding-left: 1.2rem; }
    .security li { font-size: .8rem; color: #555; margin-bottom: .35rem; line-height: 1.4; }
    .security a { color: #1869f5; }
    .footer { margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid #eee; font-size: .75rem; color: #888; text-align: center; line-height: 1.5; }
    .footer a { color: #1869f5; }
  </style>
</head>
<body>
  <div class="card">
    <h1>MCP for the Open Collective Platform</h1>
    <p class="subtitle">Enter your Open Collective personal token to connect your AI agent to the platform's GraphQL API.</p>
    <form method="POST" action="/authorize" autocomplete="off">
      <input type="hidden" name="client_id" value="${escape(client.client_id)}">
      <input type="hidden" name="redirect_uri" value="${escape(params.redirectUri)}">
      <input type="hidden" name="response_type" value="code">
      <input type="hidden" name="code_challenge" value="${escape(params.codeChallenge)}">
      <input type="hidden" name="code_challenge_method" value="S256">
      ${stateField}
      ${scopeField}
      ${err}
      <label for="oc_token">Personal Token</label>
      <input type="password" id="oc_token" name="oc_token" required autofocus
             placeholder="Paste your token here" spellcheck="false" autocomplete="off">
      <button type="submit">Authenticate</button>
    </form>
    <p class="hint">
      Get your token at
      <a href="https://opencollective.com/dashboard/lukasz-gornicki3/for-developers" target="_blank" rel="noopener">
        opencollective.com → Dashboard → For Developers
      </a>
    </p>

    <div class="security">
      <h2>How your token is handled</h2>
      <ul>
        <li><strong>Not stored server-side.</strong> Your token is never written to disk or a database. It lives only in memory for the duration of the OAuth handshake (max 30 seconds), then is handed directly to your MCP client (e.g. Claude Code).</li>
        <li><strong>Stored by your MCP client.</strong> After the handshake, your MCP client holds the token in its own secure credential store and sends it with every API request. The server never caches it between requests.</li>
        <li><strong>Used only against Open Collective.</strong> The token is forwarded as a <code>Personal-Token</code> header on GraphQL queries to <code>api.opencollective.com</code>. No other service receives it.</li>
        <li><strong>Verified once.</strong> The server calls <code>{ me { id } }</code> on Open Collective once at login to confirm the token is valid. After that, Open Collective rejects invalid tokens naturally on each query.</li>
        <li><strong>Read-only.</strong> This MCP server exposes only query operations — no mutations. Your token cannot be used to modify any data through this server.</li>
      </ul>
    </div>

    <div class="footer">
      Built with ❤️ by <a href="https://github.com/opensourceeurope" target="_blank" rel="noopener">Open Source Europe</a> —
      a European nonprofit giving open source projects a shared fiscal and legal home.<br>
      <a href="https://github.com/opensourceeurope/community/issues" target="_blank" rel="noopener">Community</a> ·
      <a href="https://discord.gg/c9fYn44jev" target="_blank" rel="noopener">Discord</a>
    </div>
  </div>
</body>
</html>`;
}

export function createOAuthProvider(endpoint) {
  return {
    get clientsStore() {
      return {
        getClient: async (clientId) => registeredClients.get(clientId),
        registerClient: async (client) => {
          const registered = { ...client, client_id: client.client_id ?? crypto.randomUUID() };
          registeredClients.set(registered.client_id, registered);
          return registered;
        },
      };
    },

    async authorize(client, params, res) {
      const req = res.req;

      if (req.method !== 'POST') {
        res.send(renderAuthForm(params, client, null));
        return;
      }

      const ocToken = (req.body?.oc_token ?? '').trim();

      if (!ocToken) {
        res.send(renderAuthForm(params, client, 'Token is required.'));
        return;
      }

      const me = await verifyOCToken(ocToken, endpoint);
      if (!me) {
        res.send(renderAuthForm(params, client, 'Invalid or unauthorized token. Check your token and try again.'));
        return;
      }

      const code = crypto.randomUUID();
      pendingCodes.set(code, {
        ocToken,
        codeChallenge: params.codeChallenge,
        expiresAt: Date.now() + 30_000, // 30 seconds — enough for code exchange, not for replay
      });

      const redirect = new URL(params.redirectUri);
      redirect.searchParams.set('code', code);
      if (params.state) redirect.searchParams.set('state', params.state);
      res.redirect(302, redirect.toString());
    },

    async challengeForAuthorizationCode(_client, authorizationCode) {
      const entry = pendingCodes.get(authorizationCode);
      if (!entry || entry.expiresAt < Date.now()) throw new Error('Invalid or expired authorization code');
      return entry.codeChallenge;
    },

    async exchangeAuthorizationCode(_client, authorizationCode) {
      const entry = pendingCodes.get(authorizationCode);
      if (!entry || entry.expiresAt < Date.now()) throw new Error('Invalid or expired authorization code');
      pendingCodes.delete(authorizationCode); // one-time use
      return { access_token: entry.ocToken, token_type: 'bearer' };
    },

    async exchangeRefreshToken(_client, refreshToken) {
      // OC personal tokens don't expire — validate and echo back
      const me = await verifyOCToken(refreshToken, endpoint);
      if (!me) throw new Error('Invalid token');
      return { access_token: refreshToken, token_type: 'bearer' };
    },

    async verifyAccessToken(token) {
      if (!token?.trim()) throw new Error('Missing token');
      // OC personal tokens don't expire; expiresAt required by requireBearerAuth (Unix seconds)
      const expiresAt = Math.floor(Date.now() / 1000) + 10 * 365 * 24 * 3600;
      return { token, clientId: 'oc-user', scopes: [], expiresAt };
    },
  };
}
