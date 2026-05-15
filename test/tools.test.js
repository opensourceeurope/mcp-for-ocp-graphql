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

  test('ENUM maps to string with valid enum values', () => {
    const typeMap = {
      Currency: { kind: 'ENUM', name: 'Currency', enumValues: [{ name: 'USD' }, { name: 'EUR' }, { name: 'GBP' }] },
    };
    assert.deepEqual(
      graphqlTypeToJsonSchema({ kind: 'ENUM', name: 'Currency', ofType: null }, typeMap),
      { type: 'string', enum: ['USD', 'EUR', 'GBP'] }
    );
  });

  test('INPUT_OBJECT expands to object with typed properties', () => {
    const typeMap = {
      AccountReferenceInput: {
        kind: 'INPUT_OBJECT',
        name: 'AccountReferenceInput',
        inputFields: [
          { name: 'id', description: 'The account ID', type: { kind: 'SCALAR', name: 'String', ofType: null } },
          { name: 'slug', description: 'The account slug', type: { kind: 'SCALAR', name: 'String', ofType: null } },
        ],
      },
    };
    assert.deepEqual(
      graphqlTypeToJsonSchema({ kind: 'INPUT_OBJECT', name: 'AccountReferenceInput', ofType: null }, typeMap),
      {
        type: 'object',
        properties: {
          id: { type: 'string', description: 'The account ID' },
          slug: { type: 'string', description: 'The account slug' },
        },
      }
    );
  });

  test('INPUT_OBJECT omits description key when field has no description', () => {
    const typeMap = {
      SimpleInput: {
        kind: 'INPUT_OBJECT',
        name: 'SimpleInput',
        inputFields: [
          { name: 'value', description: null, type: { kind: 'SCALAR', name: 'Int', ofType: null } },
        ],
      },
    };
    assert.deepEqual(
      graphqlTypeToJsonSchema({ kind: 'INPUT_OBJECT', name: 'SimpleInput', ofType: null }, typeMap),
      { type: 'object', properties: { value: { type: 'integer' } } }
    );
  });

  test('INPUT_OBJECT unknown in typeMap falls back to string', () => {
    assert.deepEqual(
      graphqlTypeToJsonSchema({ kind: 'INPUT_OBJECT', name: 'UnknownInput', ofType: null }, {}),
      { type: 'string' }
    );
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

  test('omits UNION-typed fields', () => {
    const map = {
      Parent: { kind: 'OBJECT', fields: [{ name: 'u', type: { kind: 'UNION', name: 'U', ofType: null } }, { name: 'name', type: { kind: 'SCALAR', name: 'String', ofType: null } }] },
      U: { kind: 'UNION', fields: null },
      String: { kind: 'SCALAR', fields: null },
    };
    const sel = buildSelection('Parent', map);
    assert.ok(!sel.includes('u'), 'should not include union field');
    assert.ok(sel.includes('name'), 'should include scalar field');
  });

  test('skips fields with required arguments (avoids 400 on fields like members, transactions)', () => {
    const map = {
      Account: {
        kind: 'OBJECT',
        fields: [
          { name: 'slug', args: [], type: { kind: 'SCALAR', name: 'String', ofType: null } },
          { name: 'members', args: [{ type: { kind: 'NON_NULL' } }], type: { kind: 'OBJECT', name: 'MemberCollection', ofType: null } },
          { name: 'imageUrl', args: [{ type: { kind: 'SCALAR' } }], type: { kind: 'SCALAR', name: 'String', ofType: null } },
        ],
      },
      MemberCollection: {
        kind: 'OBJECT',
        fields: [{ name: 'totalCount', args: [], type: { kind: 'SCALAR', name: 'Int', ofType: null } }],
      },
      String: { kind: 'SCALAR', fields: null },
      Int: { kind: 'SCALAR', fields: null },
    };
    const sel = buildSelection('Account', map);
    assert.ok(sel.includes('slug'), 'should include arg-free scalar');
    assert.ok(sel.includes('imageUrl'), 'should include field with optional args');
    assert.ok(!sel.includes('members'), 'should skip field with required arg');
  });

  test('only recurses into `nodes` fields — other object fields are dropped', () => {
    const map = {
      Collection: {
        kind: 'OBJECT',
        fields: [
          { name: 'totalCount', args: [], type: { kind: 'SCALAR', name: 'Int', ofType: null } },
          { name: 'nodes', args: [], type: { kind: 'LIST', name: null, ofType: { kind: 'OBJECT', name: 'Item', ofType: null } } },
          { name: 'meta', args: [], type: { kind: 'OBJECT', name: 'Meta', ofType: null } },
        ],
      },
      Item: {
        kind: 'OBJECT',
        fields: [
          { name: 'slug', args: [], type: { kind: 'SCALAR', name: 'String', ofType: null } },
          { name: 'nested', args: [], type: { kind: 'OBJECT', name: 'Meta', ofType: null } },
        ],
      },
      Meta: {
        kind: 'OBJECT',
        fields: [{ name: 'version', args: [], type: { kind: 'SCALAR', name: 'String', ofType: null } }],
      },
      Int: { kind: 'SCALAR', fields: null },
      String: { kind: 'SCALAR', fields: null },
    };
    const sel = buildSelection('Collection', map);
    assert.ok(sel.includes('totalCount'), 'should include scalar');
    assert.ok(sel.includes('nodes'), 'should include nodes');
    assert.ok(sel.includes('slug'), 'should include scalars inside nodes');
    assert.ok(!sel.includes('meta'), 'should NOT include non-nodes object field at depth 0');
    assert.ok(!sel.includes('nested'), 'should NOT recurse into object inside nodes');
  });

  test('includes INTERFACE-typed fields using the interface own fields', () => {
    const map = {
      AccountCollection: {
        kind: 'OBJECT',
        fields: [
          { name: 'totalCount', type: { kind: 'SCALAR', name: 'Int', ofType: null } },
          { name: 'nodes', type: { kind: 'LIST', name: null, ofType: { kind: 'INTERFACE', name: 'Account', ofType: null } } },
        ],
      },
      Account: {
        kind: 'INTERFACE',
        fields: [
          { name: 'id', type: { kind: 'SCALAR', name: 'String', ofType: null } },
          { name: 'slug', type: { kind: 'SCALAR', name: 'String', ofType: null } },
          { name: 'name', type: { kind: 'SCALAR', name: 'String', ofType: null } },
        ],
      },
      Int: { kind: 'SCALAR', fields: null },
      String: { kind: 'SCALAR', fields: null },
    };
    const sel = buildSelection('AccountCollection', map);
    assert.ok(sel.includes('nodes'), 'should include nodes field');
    assert.ok(sel.includes('id'), 'should include id from interface fields');
    assert.ok(sel.includes('slug'), 'should include slug from interface fields');
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

  test('handler throws on GraphQL errors when result is null after retry', async () => {
    // No path → no field to strip → exhausts retries and throws
    globalThis.fetch = async () => ({
      ok: true,
      json: async () => ({ data: { currencyExchangeRate: null }, errors: [{ message: 'Unauthorized' }] }),
    });

    const tools = buildTools(FIXTURE_SCHEMA, 'https://api.example.com/graphql', null);
    await assert.rejects(() => tools[0].handler({}), /Unauthorized/);
  });

  test('handler retries with bad fields stripped and memoises result for future calls', async () => {
    let callCount = 0;
    globalThis.fetch = async (_url, opts) => {
      callCount++;
      const body = JSON.parse(opts.body);
      if (callCount === 1) {
        return {
          ok: true,
          json: async () => ({
            data: { currencyExchangeRate: null },
            errors: [{ path: ['currencyExchangeRate', 'fromCurrency'], message: 'Not allowed for scope "account"' }],
          }),
        };
      }
      assert.ok(!body.query.includes('fromCurrency'), 'retry query should not include stripped field');
      return {
        ok: true,
        json: async () => ({ data: { currencyExchangeRate: [{ toCurrency: 'EUR', value: 0.92 }] } }),
      };
    };

    const tools = buildTools(FIXTURE_SCHEMA, 'https://api.example.com/graphql', null);
    const result = await tools[0].handler({});
    assert.equal(callCount, 2, 'should have retried once');
    assert.equal(result[0].toCurrency, 'EUR');

    // Second call should use the already-stripped query — only one fetch
    const result2 = await tools[0].handler({});
    assert.equal(callCount, 3, 'second call should need only one fetch');
    assert.equal(result2[0].toCurrency, 'EUR');
  });

  test('handler returns partial data when some fields error but result exists', async () => {
    globalThis.fetch = async () => ({
      ok: true,
      json: async () => ({
        data: { currencyExchangeRate: [{ fromCurrency: 'USD', toCurrency: 'EUR', value: 0.92 }] },
        errors: [{ message: 'Not allowed for scope "account"' }],
      }),
    });

    const tools = buildTools(FIXTURE_SCHEMA, 'https://api.example.com/graphql', null);
    const result = await tools[0].handler({});
    assert.equal(result[0].fromCurrency, 'USD');
  });

  test('handler throws on HTTP error', async () => {
    globalThis.fetch = async () => ({ ok: false, status: 500, statusText: 'Internal Server Error' });
    const tools = buildTools(FIXTURE_SCHEMA, 'https://api.example.com/graphql', null);
    await assert.rejects(() => tools[0].handler({}), /500/);
  });

  test('INPUT_OBJECT arg is expanded to object schema with properties', () => {
    const schema = {
      queryType: {
        fields: [{
          name: 'getAccount',
          description: 'Get an account',
          args: [{
            name: 'account',
            description: 'The account to look up',
            defaultValue: null,
            type: { kind: 'INPUT_OBJECT', name: 'AccountReferenceInput', ofType: null },
          }],
          type: { kind: 'OBJECT', name: 'Account', ofType: null },
        }],
      },
      types: [
        { kind: 'OBJECT', name: 'Account', fields: [{ name: 'id', type: { kind: 'SCALAR', name: 'String', ofType: null } }], enumValues: null },
        {
          kind: 'INPUT_OBJECT',
          name: 'AccountReferenceInput',
          fields: null,
          inputFields: [
            { name: 'id', description: 'The account ID', type: { kind: 'SCALAR', name: 'String', ofType: null } },
            { name: 'slug', description: 'The account slug', type: { kind: 'SCALAR', name: 'String', ofType: null } },
          ],
          enumValues: null,
        },
      ],
    };

    const tools = buildTools(schema, 'https://example.com', null);
    const accountArg = tools[0].inputSchema.properties.account;
    assert.equal(accountArg.type, 'object');
    assert.deepEqual(accountArg.properties, {
      id: { type: 'string', description: 'The account ID' },
      slug: { type: 'string', description: 'The account slug' },
    });
  });

  test('uses hardcoded description map over camelToWords fallback', () => {
    const schema = {
      queryType: {
        fields: [
          { name: 'collective', description: null, args: [], type: { kind: 'SCALAR', name: 'String', ofType: null } },
          { name: 'expenses', description: null, args: [], type: { kind: 'SCALAR', name: 'String', ofType: null } },
          { name: 'me', description: null, args: [], type: { kind: 'SCALAR', name: 'String', ofType: null } },
        ],
      },
      types: [{ kind: 'SCALAR', name: 'String', fields: null, enumValues: null }],
    };
    const tools = buildTools(schema, 'https://example.com', null);
    assert.ok(tools[0].description.length > 'Collective'.length, 'collective should have a meaningful description, not just the name');
    assert.ok(tools[1].description.length > 'Expenses'.length, 'expenses should have a meaningful description, not just the name');
    assert.ok(tools[2].description.length > 'Me'.length, 'me should have a meaningful description, not just the name');
  });

  test('falls back to human-readable words for unknown operation names', () => {
    const schema = {
      queryType: {
        fields: [
          { name: 'unknownFooBar', description: null, args: [], type: { kind: 'SCALAR', name: 'String', ofType: null } },
          { name: 'listSomething', description: null, args: [], type: { kind: 'SCALAR', name: 'String', ofType: null } },
        ],
      },
      types: [{ kind: 'SCALAR', name: 'String', fields: null, enumValues: null }],
    };
    const tools = buildTools(schema, 'https://example.com', null);
    assert.equal(tools[0].description, 'Unknown foo bar');
    assert.equal(tools[1].description, 'List something');
  });

  test('ENUM arg includes valid values in inputSchema', () => {
    const schema = {
      queryType: {
        fields: [{
          name: 'listAccounts',
          description: 'List accounts',
          args: [{
            name: 'currency',
            description: 'Currency filter',
            defaultValue: null,
            type: { kind: 'ENUM', name: 'Currency', ofType: null },
          }],
          type: { kind: 'OBJECT', name: 'Account', ofType: null },
        }],
      },
      types: [
        { kind: 'OBJECT', name: 'Account', fields: [{ name: 'id', type: { kind: 'SCALAR', name: 'String', ofType: null } }], enumValues: null },
        { kind: 'ENUM', name: 'Currency', fields: null, inputFields: null, enumValues: [{ name: 'USD' }, { name: 'EUR' }, { name: 'GBP' }] },
      ],
    };

    const tools = buildTools(schema, 'https://example.com', null);
    const currencyArg = tools[0].inputSchema.properties.currency;
    assert.equal(currencyArg.type, 'string');
    assert.deepEqual(currencyArg.enum, ['USD', 'EUR', 'GBP']);
  });
});
