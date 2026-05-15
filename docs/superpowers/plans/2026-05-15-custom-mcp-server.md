# Custom MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the reShapr Docker Compose stack with a single lightweight Node.js MCP server that introspects the Open Collective GraphQL API on startup and exposes all query operations as MCP tools.

**Architecture:** On startup the server fetches the OC GraphQL introspection, parses every `Query` operation into an MCP tool definition (name, description, JSON Schema input), then starts either a stdio transport (local Claude Code) or an HTTP transport (hosted). Auth is controlled by `OC_PERSONAL_TOKEN` env var — if set it adds `Personal-Token` header to every OC request; if unset it runs anonymous.

**Tech Stack:** Node.js 18+, `@modelcontextprotocol/sdk` (low-level `Server` API), native `fetch`, native `node:http`, no other runtime deps.

---

## File Map

| Path | Action | Responsibility |
|---|---|---|
| `package.json` | Create | Project metadata, deps, scripts |
| `index.js` | Create | Entry point: fetch schema, build tools, start transport |
| `src/schema.js` | Create | Fetch + parse GraphQL introspection → operation list |
| `src/tools.js` | Create | Map operations → MCP tool definitions + query builders |
| `test/schema.test.js` | Create | Unit tests for schema.js |
| `test/tools.test.js` | Create | Unit tests for tools.js |
| `Dockerfile` | Create | Minimal Node.js image for container hosting |
| `.env.example` | Replace | Only OC_PERSONAL_TOKEN + PORT |
| `README.md` | Replace | New setup instructions |
| `schemas/` | Delete | No longer needed — schema fetched on startup |
| `scripts/refresh-schema.sh` | Delete | Replaced by startup introspection |
| `scripts/print-mcp-config.sh` | Delete | Instructions now in README |

---

## Task 1: Remove reShapr artefacts and bootstrap package

**Files:**
- Delete: `schemas/opencollective.graphql`
- Delete: `scripts/refresh-schema.sh`
- Delete: `scripts/print-mcp-config.sh`
- Create: `package.json`
- Replace: `.env.example`

- [ ] **Step 1: Delete reShapr-only files**

```bash
rm -rf schemas scripts
```

- [ ] **Step 2: Create package.json**

```json
{
  "name": "opencollective-mcp",
  "version": "1.0.0",
  "description": "MCP server for the Open Collective GraphQL API",
  "type": "module",
  "engines": { "node": ">=18" },
  "scripts": {
    "start": "node index.js",
    "start:stdio": "node index.js --stdio",
    "test": "node --test 'test/**/*.test.js'"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.0.0"
  }
}
```

- [ ] **Step 3: Replace .env.example**

Overwrite the file with:

```
# Open Collective GraphQL endpoint (default is fine)
OC_GRAPHQL_ENDPOINT=https://api.opencollective.com/graphql/v2

# Personal Token — if set, adds Personal-Token header (100 req/min, account data)
# Generate at: https://opencollective.com/<your-slug>/admin/for-developers
OC_PERSONAL_TOKEN=

# HTTP port (only used when NOT running with --stdio)
PORT=3000
```

- [ ] **Step 4: Install dependencies**

```bash
npm install
```

Expected: `node_modules/@modelcontextprotocol/sdk` present, no errors.

- [ ] **Step 5: Commit**

```bash
git add package.json package-lock.json .env.example
git commit -m "chore: bootstrap npm package, remove reShapr artefacts"
```

---

## Task 2: Implement schema fetching (`src/schema.js`)

**Files:**
- Create: `src/schema.js`
- Create: `test/schema.test.js`

### What this module does

Sends a GraphQL introspection query to the OC endpoint and returns two things:
- `queryType.fields` — the list of query operations (name, description, args, return type)
- `types` — all named types (used later by tools.js to build field selections)

### Step-by-step

- [ ] **Step 1: Write the failing test**

Create `test/schema.test.js`:

```js
import { test, describe, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { fetchSchema } from '../src/schema.js';

// Minimal introspection response fixture
const MOCK_SCHEMA = {
  queryType: {
    fields: [
      {
        name: 'currencyExchangeRate',
        description: 'Live exchange rates',
        args: [
          {
            name: 'requests',
            description: 'List of currency pairs',
            defaultValue: null,
            type: { kind: 'NON_NULL', name: null, ofType: { kind: 'LIST', name: null, ofType: { kind: 'NON_NULL', name: null, ofType: { kind: 'INPUT_OBJECT', name: 'CurrencyExchangeRateRequest' } } } },
          },
        ],
        type: { kind: 'LIST', name: null, ofType: { kind: 'OBJECT', name: 'CurrencyExchangeRateResult', ofType: null } },
      },
    ],
  },
  types: [
    { kind: 'SCALAR', name: 'String', fields: null, enumValues: null },
    {
      kind: 'OBJECT',
      name: 'CurrencyExchangeRateResult',
      fields: [
        { name: 'fromCurrency', type: { kind: 'SCALAR', name: 'String', ofType: null } },
        { name: 'toCurrency', type: { kind: 'SCALAR', name: 'String', ofType: null } },
        { name: 'value', type: { kind: 'SCALAR', name: 'Float', ofType: null } },
      ],
      enumValues: null,
    },
  ],
};

describe('fetchSchema', () => {
  let originalFetch;

  before(() => { originalFetch = globalThis.fetch; });
  after(() => { globalThis.fetch = originalFetch; });

  test('returns parsed schema on success', async () => {
    globalThis.fetch = async () => ({
      ok: true,
      json: async () => ({ data: { __schema: MOCK_SCHEMA } }),
    });

    const schema = await fetchSchema('https://example.com/graphql', null);
    assert.equal(schema.queryType.fields.length, 1);
    assert.equal(schema.queryType.fields[0].name, 'currencyExchangeRate');
    assert.equal(schema.types.length, 2);
  });

  test('sends Personal-Token header when token provided', async () => {
    let capturedHeaders;
    globalThis.fetch = async (_url, opts) => {
      capturedHeaders = opts.headers;
      return { ok: true, json: async () => ({ data: { __schema: MOCK_SCHEMA } }) };
    };

    await fetchSchema('https://example.com/graphql', 'my-token');
    assert.equal(capturedHeaders['Personal-Token'], 'my-token');
  });

  test('omits Personal-Token header when no token', async () => {
    let capturedHeaders;
    globalThis.fetch = async (_url, opts) => {
      capturedHeaders = opts.headers;
      return { ok: true, json: async () => ({ data: { __schema: MOCK_SCHEMA } }) };
    };

    await fetchSchema('https://example.com/graphql', null);
    assert.equal(capturedHeaders['Personal-Token'], undefined);
  });

  test('throws on HTTP error', async () => {
    globalThis.fetch = async () => ({ ok: false, status: 401, statusText: 'Unauthorized' });
    await assert.rejects(() => fetchSchema('https://example.com/graphql', null), /401/);
  });

  test('throws on GraphQL errors', async () => {
    globalThis.fetch = async () => ({
      ok: true,
      json: async () => ({ errors: [{ message: 'Schema not found' }] }),
    });
    await assert.rejects(() => fetchSchema('https://example.com/graphql', null), /Schema not found/);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm test
```

Expected: fails with `Cannot find module '../src/schema.js'`

- [ ] **Step 3: Create `src/schema.js`**

```js
const INTROSPECTION_QUERY = `{
  __schema {
    queryType {
      fields {
        name
        description
        args {
          name
          description
          defaultValue
          type { kind name ofType { kind name ofType { kind name ofType { kind name } } } }
        }
        type { kind name ofType { kind name ofType { kind name } } }
      }
    }
    types {
      kind
      name
      fields(includeDeprecated: false) {
        name
        type { kind name ofType { kind name ofType { kind name ofType { kind name } } } }
      }
      enumValues { name }
    }
  }
}`;

export async function fetchSchema(endpoint, token) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Personal-Token'] = token;

  const res = await fetch(endpoint, {
    method: 'POST',
    headers,
    body: JSON.stringify({ query: INTROSPECTION_QUERY }),
  });

  if (!res.ok) throw new Error(`Introspection failed: ${res.status} ${res.statusText}`);
  const { data, errors } = await res.json();
  if (errors?.length) throw new Error(`Introspection errors: ${errors.map(e => e.message).join(', ')}`);

  return data.__schema;
}
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
npm test
```

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/schema.js test/schema.test.js
git commit -m "feat: add GraphQL introspection fetcher"
```

---

## Task 3: Implement tool generation (`src/tools.js`)

**Files:**
- Create: `src/tools.js`
- Create: `test/tools.test.js`

### What this module does

Takes the `schema` object from `fetchSchema` and returns an array of tool objects:
```js
[{ name, description, inputSchema, handler }]
```

Each `handler(args)` builds and executes a typed GraphQL query against the OC API.

Helper functions:
- `unwrapType(type)` — strips `NON_NULL`/`LIST` wrappers to reach the named type
- `argTypeStr(type)` — converts a GraphQL type object back to its SDL string (`String!`, `[Int]`, etc.)
- `graphqlTypeToJsonSchema(type)` — maps a GraphQL arg type to a JSON Schema snippet
- `buildSelection(typeName, typeMap, depth, visited)` — recursively builds a field selection string for a return type (max depth 3, guards against circular refs)
- `buildTools(schema, endpoint, token)` — orchestrates the above into MCP tool definitions

- [ ] **Step 1: Write the failing tests**

Create `test/tools.test.js`:

```js
import { test, describe, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { buildTools, unwrapType, graphqlTypeToJsonSchema, buildSelection } from '../src/tools.js';

// Shared fixture — a minimal schema with one operation and one return type
const FIXTURE_SCHEMA = {
  queryType: {
    fields: [
      {
        name: 'currencyExchangeRate',
        description: 'Live exchange rates',
        args: [
          {
            name: 'requests',
            description: 'Currency pairs',
            defaultValue: null,
            type: {
              kind: 'NON_NULL', name: null,
              ofType: { kind: 'LIST', name: null, ofType: { kind: 'NON_NULL', name: null, ofType: { kind: 'INPUT_OBJECT', name: 'CurrencyExchangeRateRequest', ofType: null } } },
            },
          },
        ],
        type: { kind: 'NON_NULL', name: null, ofType: { kind: 'LIST', name: null, ofType: { kind: 'OBJECT', name: 'CurrencyExchangeRateResult', ofType: null } } },
      },
    ],
  },
  types: [
    { kind: 'SCALAR', name: 'String', fields: null, enumValues: null },
    { kind: 'SCALAR', name: 'Float', fields: null, enumValues: null },
    {
      kind: 'OBJECT',
      name: 'CurrencyExchangeRateResult',
      fields: [
        { name: 'fromCurrency', type: { kind: 'SCALAR', name: 'String', ofType: null } },
        { name: 'toCurrency', type: { kind: 'SCALAR', name: 'String', ofType: null } },
        { name: 'value', type: { kind: 'SCALAR', name: 'Float', ofType: null } },
      ],
      enumValues: null,
    },
  ],
};

describe('unwrapType', () => {
  test('unwraps NON_NULL', () => {
    const t = { kind: 'NON_NULL', name: null, ofType: { kind: 'SCALAR', name: 'String', ofType: null } };
    assert.deepEqual(unwrapType(t), { kind: 'SCALAR', name: 'String', ofType: null });
  });

  test('unwraps nested NON_NULL + LIST', () => {
    const t = { kind: 'NON_NULL', name: null, ofType: { kind: 'LIST', name: null, ofType: { kind: 'SCALAR', name: 'Int', ofType: null } } };
    assert.deepEqual(unwrapType(t), { kind: 'SCALAR', name: 'Int', ofType: null });
  });

  test('returns named type unchanged', () => {
    const t = { kind: 'SCALAR', name: 'Boolean', ofType: null };
    assert.deepEqual(unwrapType(t), t);
  });
});

describe('graphqlTypeToJsonSchema', () => {
  test('maps String to string', () => {
    assert.deepEqual(graphqlTypeToJsonSchema({ kind: 'SCALAR', name: 'String', ofType: null }), { type: 'string' });
  });

  test('maps Int to integer', () => {
    assert.deepEqual(graphqlTypeToJsonSchema({ kind: 'SCALAR', name: 'Int', ofType: null }), { type: 'integer' });
  });

  test('maps Float to number', () => {
    assert.deepEqual(graphqlTypeToJsonSchema({ kind: 'SCALAR', name: 'Float', ofType: null }), { type: 'number' });
  });

  test('maps Boolean to boolean', () => {
    assert.deepEqual(graphqlTypeToJsonSchema({ kind: 'SCALAR', name: 'Boolean', ofType: null }), { type: 'boolean' });
  });

  test('maps ID to string', () => {
    assert.deepEqual(graphqlTypeToJsonSchema({ kind: 'SCALAR', name: 'ID', ofType: null }), { type: 'string' });
  });

  test('maps unknown scalar to string', () => {
    assert.deepEqual(graphqlTypeToJsonSchema({ kind: 'SCALAR', name: 'DateTime', ofType: null }), { type: 'string' });
  });

  test('maps LIST to array', () => {
    const t = { kind: 'LIST', name: null, ofType: { kind: 'SCALAR', name: 'String', ofType: null } };
    assert.deepEqual(graphqlTypeToJsonSchema(t), { type: 'array', items: { type: 'string' } });
  });

  test('unwraps NON_NULL before mapping', () => {
    const t = { kind: 'NON_NULL', name: null, ofType: { kind: 'SCALAR', name: 'Int', ofType: null } };
    assert.deepEqual(graphqlTypeToJsonSchema(t), { type: 'integer' });
  });
});

describe('buildSelection', () => {
  const typeMap = Object.fromEntries(FIXTURE_SCHEMA.types.map(t => [t.name, t]));

  test('returns scalar field names for a simple object type', () => {
    const sel = buildSelection('CurrencyExchangeRateResult', typeMap);
    assert.ok(sel.includes('fromCurrency'));
    assert.ok(sel.includes('toCurrency'));
    assert.ok(sel.includes('value'));
  });

  test('returns null for unknown type', () => {
    assert.equal(buildSelection('NonExistent', typeMap), null);
  });

  test('returns null for scalar type', () => {
    assert.equal(buildSelection('String', typeMap), null);
  });
});

describe('buildTools', () => {
  let originalFetch;
  before(() => { originalFetch = globalThis.fetch; });
  after(() => { globalThis.fetch = originalFetch; });

  test('returns one tool per query operation', () => {
    const tools = buildTools(FIXTURE_SCHEMA, 'https://api.example.com/graphql', null);
    assert.equal(tools.length, 1);
    assert.equal(tools[0].name, 'currencyExchangeRate');
    assert.equal(tools[0].description, 'Live exchange rates');
  });

  test('marks NON_NULL args as required', () => {
    const tools = buildTools(FIXTURE_SCHEMA, 'https://api.example.com/graphql', null);
    assert.deepEqual(tools[0].inputSchema.required, ['requests']);
  });

  test('handler sends query to endpoint', async () => {
    let capturedBody;
    globalThis.fetch = async (_url, opts) => {
      capturedBody = JSON.parse(opts.body);
      return { ok: true, json: async () => ({ data: { currencyExchangeRate: [] } }) };
    };

    const tools = buildTools(FIXTURE_SCHEMA, 'https://api.example.com/graphql', null);
    await tools[0].handler({ requests: [{ fromCurrency: 'USD', toCurrency: 'EUR' }] });

    assert.ok(capturedBody.query.includes('currencyExchangeRate'));
    assert.ok(capturedBody.query.includes('$requests'));
  });

  test('handler adds Personal-Token header when token set', async () => {
    let capturedHeaders;
    globalThis.fetch = async (_url, opts) => {
      capturedHeaders = opts.headers;
      return { ok: true, json: async () => ({ data: { currencyExchangeRate: [] } }) };
    };

    const tools = buildTools(FIXTURE_SCHEMA, 'https://api.example.com/graphql', 'tok-123');
    await tools[0].handler({ requests: [] });
    assert.equal(capturedHeaders['Personal-Token'], 'tok-123');
  });

  test('handler throws on GraphQL errors', async () => {
    globalThis.fetch = async () => ({
      ok: true,
      json: async () => ({ errors: [{ message: 'Unauthorized' }] }),
    });

    const tools = buildTools(FIXTURE_SCHEMA, 'https://api.example.com/graphql', null);
    await assert.rejects(() => tools[0].handler({}), /Unauthorized/);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm test
```

Expected: fails with `Cannot find module '../src/tools.js'`

- [ ] **Step 3: Create `src/tools.js`**

```js
export function unwrapType(type) {
  if (type.kind === 'NON_NULL' || type.kind === 'LIST') return unwrapType(type.ofType);
  return type;
}

export function graphqlTypeToJsonSchema(type) {
  if (type.kind === 'NON_NULL') return graphqlTypeToJsonSchema(type.ofType);
  if (type.kind === 'LIST') return { type: 'array', items: graphqlTypeToJsonSchema(type.ofType) };
  switch (type.name) {
    case 'Int': return { type: 'integer' };
    case 'Float': return { type: 'number' };
    case 'Boolean': return { type: 'boolean' };
    case 'String': case 'ID': default: return { type: 'string' };
  }
}

function argTypeStr(type) {
  if (type.kind === 'NON_NULL') return `${argTypeStr(type.ofType)}!`;
  if (type.kind === 'LIST') return `[${argTypeStr(type.ofType)}]`;
  return type.name;
}

export function buildSelection(typeName, typeMap, depth = 0, visited = new Set()) {
  if (depth > 3 || visited.has(typeName)) return null;
  const info = typeMap[typeName];
  if (!info || !info.fields) return null;

  const next = new Set(visited);
  next.add(typeName);

  const parts = info.fields
    .map(f => {
      const core = unwrapType(f.type);
      const isLeaf = !typeMap[core.name]?.fields;
      if (isLeaf) return f.name;
      const sub = buildSelection(core.name, typeMap, depth + 1, next);
      return sub ? `${f.name} { ${sub} }` : null;
    })
    .filter(Boolean);

  return parts.length ? parts.join(' ') : null;
}

export function buildTools(schema, endpoint, token) {
  const typeMap = Object.fromEntries(schema.types.map(t => [t.name, t]));

  return schema.queryType.fields.map(op => {
    const inputSchema = {
      type: 'object',
      properties: Object.fromEntries(
        op.args.map(a => [
          a.name,
          {
            ...graphqlTypeToJsonSchema(a.type),
            ...(a.description ? { description: a.description } : {}),
          },
        ])
      ),
      required: op.args.filter(a => a.type.kind === 'NON_NULL').map(a => a.name),
    };

    const returnTypeName = unwrapType(op.type).name;
    const selection = buildSelection(returnTypeName, typeMap) ?? '__typename';

    const argsDef = op.args.map(a => `$${a.name}: ${argTypeStr(a.type)}`).join(', ');
    const argsUse = op.args.map(a => `${a.name}: $${a.name}`).join(', ');
    const query = op.args.length
      ? `query ${op.name}(${argsDef}) { ${op.name}(${argsUse}) { ${selection} } }`
      : `{ ${op.name} { ${selection} } }`;

    async function handler(args = {}) {
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Personal-Token'] = token;
      const res = await fetch(endpoint, {
        method: 'POST',
        headers,
        body: JSON.stringify({ query, variables: args }),
      });
      const { data, errors } = await res.json();
      if (errors?.length) throw new Error(errors.map(e => e.message).join(', '));
      return data[op.name];
    }

    return {
      name: op.name,
      description: op.description ?? op.name,
      inputSchema,
      handler,
    };
  });
}
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
npm test
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/tools.js test/tools.test.js
git commit -m "feat: add GraphQL-to-MCP tool builder"
```

---

## Task 4: Wire the server entry point (`index.js`)

**Files:**
- Create: `index.js`

### What this does

1. Reads env vars (`OC_GRAPHQL_ENDPOINT`, `OC_PERSONAL_TOKEN`, `PORT`)
2. Calls `fetchSchema` — exits with error if introspection fails
3. Calls `buildTools` to get tool definitions
4. Registers tools on a `Server` instance using the MCP SDK's low-level request handler API (works with raw JSON Schema, no Zod needed)
5. Starts stdio transport if `--stdio` arg is present, otherwise starts HTTP on `PORT`

The HTTP path uses a per-request `StreamableHTTPServerTransport` with `sessionIdGenerator: undefined` (stateless — appropriate for a simple GraphQL proxy).

- [ ] **Step 1: Create `index.js`**

```js
import http from 'node:http';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { CallToolRequestSchema, ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import { fetchSchema } from './src/schema.js';
import { buildTools } from './src/tools.js';

const ENDPOINT = process.env.OC_GRAPHQL_ENDPOINT ?? 'https://api.opencollective.com/graphql/v2';
const TOKEN = process.env.OC_PERSONAL_TOKEN ?? null;
const PORT = parseInt(process.env.PORT ?? '3000', 10);
const USE_STDIO = process.argv.includes('--stdio');

process.stderr.write('Fetching Open Collective schema…\n');
let schema;
try {
  schema = await fetchSchema(ENDPOINT, TOKEN);
} catch (err) {
  process.stderr.write(`Failed to fetch schema: ${err.message}\n`);
  process.exit(1);
}
const tools = buildTools(schema, ENDPOINT, TOKEN);
process.stderr.write(`Ready — ${tools.length} tools available\n`);

function makeServer() {
  const server = new Server(
    { name: 'opencollective', version: '1.0.0' },
    { capabilities: { tools: {} } }
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: tools.map(({ name, description, inputSchema }) => ({ name, description, inputSchema })),
  }));

  server.setRequestHandler(CallToolRequestSchema, async (req) => {
    const tool = tools.find(t => t.name === req.params.name);
    if (!tool) {
      return {
        content: [{ type: 'text', text: `Unknown tool: ${req.params.name}` }],
        isError: true,
      };
    }
    try {
      const result = await tool.handler(req.params.arguments ?? {});
      return { content: [{ type: 'text', text: JSON.stringify(result, null, 2) }] };
    } catch (err) {
      return { content: [{ type: 'text', text: err.message }], isError: true };
    }
  });

  return server;
}

if (USE_STDIO) {
  const server = makeServer();
  const transport = new StdioServerTransport();
  await server.connect(transport);
} else {
  async function readBody(req) {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const raw = Buffer.concat(chunks).toString();
    return raw ? JSON.parse(raw) : undefined;
  }

  const httpServer = http.createServer(async (req, res) => {
    try {
      const body = await readBody(req);
      const server = makeServer();
      const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });
      await server.connect(transport);
      await transport.handleRequest(req, res, body);
    } catch (err) {
      if (!res.headersSent) {
        res.writeHead(500);
        res.end(err.message);
      }
    }
  });

  httpServer.listen(PORT, () => {
    process.stderr.write(`MCP server listening on :${PORT}\n`);
  });
}
```

- [ ] **Step 2: Smoke-test stdio mode**

In one terminal:

```bash
node index.js --stdio
```

Expected output on stderr: `Fetching Open Collective schema…` then `Ready — N tools available` (N will be a large number — all OC query operations).

Send it a `list_tools` request by piping JSON (Ctrl-C to stop after checking):

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | node index.js --stdio 2>/dev/null | head -c 500
```

Expected: JSON response containing `"tools":[{"name":...`

- [ ] **Step 3: Smoke-test HTTP mode**

```bash
node index.js &
sleep 3
curl -s -X POST http://localhost:3000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | head -c 300
kill %1
```

Expected: JSON response with tools list.

- [ ] **Step 4: Commit**

```bash
git add index.js
git commit -m "feat: add MCP server entry point with stdio and HTTP transports"
```

---

## Task 5: Add Dockerfile

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Create `.dockerignore`**

```
node_modules
.env
.git
docs
test
```

- [ ] **Step 2: Create `Dockerfile`**

```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY index.js ./
COPY src/ ./src/
ENV PORT=3000
EXPOSE 3000
CMD ["node", "index.js"]
```

- [ ] **Step 3: Build and run the image**

```bash
docker build -t opencollective-mcp .
docker run --rm -p 3000:3000 opencollective-mcp
```

Expected: same startup logs as Node run. Ctrl-C to stop.

- [ ] **Step 4: Test with token env var**

```bash
docker run --rm -p 3000:3000 -e OC_PERSONAL_TOKEN=test-token opencollective-mcp
```

Expected: server starts, no errors about token.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "feat: add Dockerfile for container hosting"
```

---

## Task 6: Rewrite README

**Files:**
- Replace: `README.md`

- [ ] **Step 1: Rewrite README.md**

Replace the full content with:

````markdown
# opencollective-mcp

MCP server for the [Open Collective GraphQL API](https://api.opencollective.com/graphql/v2).

Introspects the full OC schema on startup and exposes every query operation as an MCP tool. Mutations are excluded. Auth is controlled by `OC_PERSONAL_TOKEN` — if set, adds a `Personal-Token` header to every request (100 req/min, account-scoped data); if unset, runs anonymous (10 req/min, public data only).

## Requirements

- Node.js 18+
- Docker (only for container hosting)

## Local usage (stdio)

```bash
npm install

# anonymous
node index.js --stdio

# with personal token
OC_PERSONAL_TOKEN=<your-token> node index.js --stdio
```

Register with Claude Code:

```bash
# anonymous
claude mcp add --transport stdio opencollective -- node /abs/path/to/index.js --stdio

# with personal token
claude mcp add --transport stdio opencollective-pt -- \
  env OC_PERSONAL_TOKEN=<your-token> node /abs/path/to/index.js --stdio
```

Generate a Personal Token at `https://opencollective.com/<your-slug>/admin/for-developers`.

## Hosted usage (HTTP / Docker)

```bash
docker build -t opencollective-mcp .
docker run -d -p 3000:3000 -e OC_PERSONAL_TOKEN=<token> opencollective-mcp
```

Register with Claude Code:

```bash
claude mcp add --transport http opencollective http://your-host:3000/mcp
```

Works on any EU container platform: Scaleway Serverless Containers (free tier), OVH, Hetzner.

## Configuration

| Env var | Default | Description |
|---|---|---|
| `OC_GRAPHQL_ENDPOINT` | `https://api.opencollective.com/graphql/v2` | OC API endpoint |
| `OC_PERSONAL_TOKEN` | _(unset)_ | Personal token for authenticated requests |
| `PORT` | `3000` | HTTP port (ignored in stdio mode) |

## Development

```bash
npm test      # run unit tests
node index.js --stdio   # run locally
```

## Stack

- [Model Context Protocol SDK](https://github.com/modelcontextprotocol/typescript-sdk)
- [Open Collective GraphQL API v2](https://developers.opencollective.com/access)
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README for custom MCP server"
```

---

## Task 7: Final verification

- [ ] **Step 1: Run full test suite**

```bash
npm test
```

Expected: all tests pass, zero failures.

- [ ] **Step 2: Verify no reShapr references remain**

```bash
grep -r "reshapr\|RESHAPR" . --exclude-dir={node_modules,.git}
```

Expected: no output.

- [ ] **Step 3: Test end-to-end with Claude Code (stdio)**

```bash
# Register the server
claude mcp add --transport stdio opencollective -- node $(pwd)/index.js --stdio

# Open a new Claude Code session and verify the tools appear
claude mcp list
```

Expected: `opencollective` listed with status connected.

- [ ] **Step 4: Final commit**

```bash
git add -A
git status  # verify only expected files remain
git commit -m "chore: final cleanup and verification"
```
