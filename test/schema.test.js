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

    const schema = await fetchSchema('https://example.com/graphql');
    assert.equal(schema.queryType.fields.length, 1);
    assert.equal(schema.queryType.fields[0].name, 'currencyExchangeRate');
    assert.equal(schema.types.length, 2);
  });

  test('does not send a Personal-Token header', async () => {
    let capturedHeaders;
    globalThis.fetch = async (_url, opts) => {
      capturedHeaders = opts.headers;
      return { ok: true, json: async () => ({ data: { __schema: MOCK_SCHEMA } }) };
    };

    await fetchSchema('https://example.com/graphql');
    assert.equal(capturedHeaders['Personal-Token'], undefined);
  });

  test('throws on HTTP error', async () => {
    globalThis.fetch = async () => ({ ok: false, status: 401, statusText: 'Unauthorized' });
    await assert.rejects(() => fetchSchema('https://example.com/graphql'), /401/);
  });

  test('throws on GraphQL errors', async () => {
    globalThis.fetch = async () => ({
      ok: true,
      json: async () => ({ errors: [{ message: 'Schema not found' }] }),
    });
    await assert.rejects(() => fetchSchema('https://example.com/graphql'), /Schema not found/);
  });

  test('throws when response has no schema data', async () => {
    globalThis.fetch = async () => ({
      ok: true,
      json: async () => ({ data: {} }),
    });
    await assert.rejects(() => fetchSchema('https://example.com/graphql'), /no schema data/);
  });

  test('introspection query requests description on type fields', async () => {
    let capturedQuery;
    globalThis.fetch = async (_url, opts) => {
      capturedQuery = JSON.parse(opts.body).query;
      return { ok: true, json: async () => ({ data: { __schema: MOCK_SCHEMA } }) };
    };
    await fetchSchema('https://example.com/graphql');
    assert.match(capturedQuery, /fields\(includeDeprecated: false\) \{[^}]*description/s);
  });
});
