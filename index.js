import { AsyncLocalStorage } from 'node:async_hooks';
import express from 'express';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { CallToolRequestSchema, ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import { mcpAuthRouter } from '@modelcontextprotocol/sdk/server/auth/router.js';
import { requireBearerAuth } from '@modelcontextprotocol/sdk/server/auth/middleware/bearerAuth.js';
import { fetchSchema } from './src/schema.js';
import { buildTools } from './src/tools.js';
import { createOAuthProvider } from './src/auth.js';

const ENDPOINT = process.env.OC_GRAPHQL_ENDPOINT ?? 'https://api.opencollective.com/graphql/v2';
const PORT = parseInt(process.env.PORT ?? '3000', 10);
const PUBLIC_URL = process.env.PUBLIC_URL ?? `http://localhost:${PORT}`;

if (Number.isNaN(PORT)) {
  process.stderr.write('Invalid PORT env var\n');
  process.exit(1);
}

process.stderr.write('Fetching Open Collective schema…\n');
let schema;
try {
  schema = await fetchSchema(ENDPOINT);
} catch (err) {
  process.stderr.write(`Failed to fetch schema: ${err.message}\n`);
  process.exit(1);
}
process.stderr.write(`Ready — ${schema.queryType.fields.length} operations available\n`);

const tokenStorage = new AsyncLocalStorage();
const tools = buildTools(schema, ENDPOINT, () => tokenStorage.getStore()?.token ?? null);

const provider = createOAuthProvider(ENDPOINT);
const issuerUrl = new URL(PUBLIC_URL);

const app = express();

app.use(mcpAuthRouter({
  provider,
  issuerUrl,
  serviceDocumentationUrl: new URL('https://documentation.opencollective.com'),
  scopesSupported: [],
  resourceName: 'Open Collective MCP',
}));

const bearerAuth = requireBearerAuth({ verifier: provider });

app.post('/mcp', bearerAuth, async (req, res) => {
  const token = req.auth.token;

  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const raw = Buffer.concat(chunks).toString();

  if (!raw) {
    res.status(400).end('Empty body');
    return;
  }

  let body;
  try {
    body = JSON.parse(raw);
  } catch {
    res.status(400).end('Invalid JSON');
    return;
  }

  const server = new Server(
    { name: 'opencollective', version: '1.0.0' },
    { capabilities: { tools: {} } }
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: tools.map(({ name, description, inputSchema }) => ({ name, description, inputSchema })),
  }));

  server.setRequestHandler(CallToolRequestSchema, async (req) => {
    const tool = tools.find(t => t.name === req.params.name);
    if (!tool) return { content: [{ type: 'text', text: `Unknown tool: ${req.params.name}` }], isError: true };
    try {
      const result = await tool.handler(req.params.arguments ?? {});
      return { content: [{ type: 'text', text: JSON.stringify(result, null, 2) }] };
    } catch (err) {
      return { content: [{ type: 'text', text: err.message }], isError: true };
    }
  });

  try {
    await tokenStorage.run({ token }, async () => {
      const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });
      await server.connect(transport);
      await transport.handleRequest(req, res, body);
    });
  } catch (err) {
    process.stderr.write(`MCP request error: ${err.message}\n`);
    if (!res.headersSent) {
      res.status(500).end(err.message);
    }
  }
});

app.listen(PORT, () => {
  process.stderr.write(`MCP server listening on :${PORT} (issuer: ${PUBLIC_URL})\n`);
});
