export function unwrapType(type) {
  if (type.kind === 'NON_NULL' || type.kind === 'LIST') return unwrapType(type.ofType);
  return type;
}

export function graphqlTypeToJsonSchema(type, typeMap = {}) {
  if (type.kind === 'NON_NULL') return graphqlTypeToJsonSchema(type.ofType, typeMap);
  if (type.kind === 'LIST') return { type: 'array', items: graphqlTypeToJsonSchema(type.ofType, typeMap) };
  if (type.kind === 'ENUM') {
    const info = typeMap[type.name];
    if (info?.enumValues?.length) return { type: 'string', enum: info.enumValues.map(v => v.name) };
    return { type: 'string' };
  }
  if (type.kind === 'INPUT_OBJECT') {
    const info = typeMap[type.name];
    if (!info?.inputFields) return { type: 'string' };
    return {
      type: 'object',
      properties: Object.fromEntries(
        info.inputFields.map(f => [
          f.name,
          {
            ...graphqlTypeToJsonSchema(f.type, typeMap),
            ...(f.description ? { description: f.description } : {}),
          },
        ])
      ),
    };
  }
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
  if (depth > 1 || visited.has(typeName)) return null;
  const info = typeMap[typeName];
  if (!info || !info.fields) return null;

  const next = new Set(visited);
  next.add(typeName);

  const parts = info.fields
    .map(f => {
      if (f.args?.some(a => a.type?.kind === 'NON_NULL')) return null;
      const core = unwrapType(f.type);
      const coreInfo = typeMap[core.name];
      if (!coreInfo || coreInfo.kind === 'UNION') return null;
      const isLeaf = !coreInfo.fields;
      if (isLeaf) return f.name;
      // Only recurse into `nodes` at depth 0 — the standard OC collection pattern.
      // Recursing into arbitrary object fields causes query-validation failures
      // (wrong field names) or null-propagation errors from scope-restricted resolvers.
      if (f.name !== 'nodes' || depth !== 0) return null;
      const sub = buildSelection(core.name, typeMap, depth + 1, next);
      return sub ? `${f.name} { ${sub} }` : null;
    })
    .filter(Boolean);

  return parts.length ? parts.join(' ') : null;
}

function isLeafType(typeName, typeMap) {
  const info = typeMap[typeName];
  if (!info) return true;
  return info.kind === 'SCALAR' || info.kind === 'ENUM';
}

function camelToWords(str) {
  return str.replace(/([A-Z])/g, ' $1').toLowerCase().replace(/^./, c => c.toUpperCase());
}

const DESCRIPTIONS = {
  account: 'Fetch a single account (Collective, Fund, Event, Project, Organization, or Individual) by id, slug, or GitHub handle.',
  accounts: 'List and filter accounts across the platform. Supports filtering by type (COLLECTIVE, FUND, EVENT, PROJECT, ORGANIZATION, INDIVIDUAL), Fiscal Host, country, tags, and activity.',
  activities: 'List activity log entries for an account, individual, or host. Activities record all platform actions such as contributions made, expenses approved, and member changes.',
  application: 'Fetch an OAuth application by id or client id.',
  collective: 'Fetch a Collective by id, slug, or GitHub handle. Collectives are groups organized around a shared mission that raise and spend money transparently without incorporating.',
  conversation: 'Fetch a single conversation by id. Conversations are public discussion threads on a Collective page where community members ask questions and organize.',
  community: 'List accounts that have interacted with a given Collective or Fiscal Host — contributors, expense submitters, and other participants.',
  currencyExchangeRate: 'Get live currency exchange rates used by Open Collective for multi-currency transactions and balance reporting.',
  event: 'Fetch an Event by id, slug, or GitHub handle. Events are gatherings that Collectives organize, promote, and sell tickets for.',
  expense: 'Fetch a single expense by reference. Expenses are payment requests submitted to a Collective that go through admin and Fiscal Host approval before payment is processed.',
  expenses: 'List and filter expenses across accounts or Fiscal Hosts. Supports filtering by status (PENDING, APPROVED, PAID, REJECTED), type (INVOICE, RECEIPT), payee, date range, amount, and more.',
  expenseTagStats: 'Get tag usage statistics for expenses within an account or Fiscal Host. Useful for analyzing and categorizing spending patterns.',
  exportRequest: 'Fetch a single data export request by reference.',
  exportRequests: 'List data export requests for an account, filterable by type and status.',
  fund: 'Fetch a Fund by id, slug, or GitHub handle. Funds let supporters pool money and direct it toward multiple Collectives simultaneously.',
  host: 'Fetch a Fiscal Host by id, slug, or GitHub handle. Fiscal Hosts hold funds in their bank account and handle taxes and legal compliance on behalf of hosted Collectives.',
  hosts: 'List and filter Fiscal Hosts. Supports filtering by country, currency, tags, and activity status.',
  individual: 'Fetch an Individual account by id, slug, or GitHub handle. Individuals are personal user accounts representing people who contribute to Collectives and submit expenses.',
  memberInvitations: 'List pending team member invitations for an account or a specific member. Returns null if the caller lacks permission to view invitations.',
  order: 'Fetch a single order (contribution) by reference. Orders represent financial contributions to a Collective, which may be one-time or recurring subscriptions.',
  orders: 'List and filter orders (contributions) for an account. Supports filtering by status, frequency (one-time/recurring), payment method, tier, date range, and amount.',
  organization: 'Fetch an Organization by id, slug, or GitHub handle. Organizations are company or entity accounts that contribute to Collectives and manage team donations.',
  project: 'Fetch a Project by id, slug, or GitHub handle. Projects are fundraising initiatives within a Collective with their own transparent budget, tiers, and goals.',
  search: 'Search across accounts and other entities on Open Collective. Currently in beta — API may change.',
  tagStats: 'Get tag usage statistics across accounts. Useful for discovering popular categories and themes on the platform.',
  tier: 'Fetch a single Tier by reference. Tiers are contribution levels that Collectives create to recognize and incentivize supporters at different amounts.',
  transaction: 'Fetch a single transaction by reference. Transactions are ledger records of financial activity, created in complementary credit/debit pairs to reflect balance changes.',
  transactions: 'List and filter transactions for an account. Supports filtering by type (CREDIT/DEBIT), payment method, date range, linked expenses or orders, and more.',
  transactionGroup: 'Fetch a group of related transactions by group id. Transaction groups link the complementary credit/debit pairs of a single financial event. Currently in beta.',
  transactionGroups: 'List transaction groups for an account, filterable by type, kind, and date range. Currently in beta.',
  transactionsImport: 'Fetch a transactions import by id. Fiscal Hosts use transaction imports to bulk-load bank statement data into the platform ledger.',
  update: 'Fetch a single Update by id or slug. Updates are posts published to a Collective page to share progress, news, and impact with supporters.',
  updates: 'List published Updates for an account. Updates are communications shared with supporters about progress, changes, and impact. Only published updates are returned.',
  paypalPlan: 'Fetch a PayPal subscription plan for a given account, amount, and frequency. Used during checkout to set up recurring PayPal contributions.',
  personalToken: 'Fetch a personal API token by id. Personal tokens authenticate API requests on behalf of an individual account.',
  virtualCard: 'Fetch a single Virtual Card by reference. Virtual Cards are payment cards issued to Collective team members for pre-approved spending.',
  virtualCardRequest: 'Fetch a single Virtual Card request by reference. Virtual Card requests are submitted by Collective admins to obtain new cards for approved spending.',
  virtualCardRequests: 'List Virtual Card requests for a Fiscal Host or Collective, filterable by status.',
  hostApplication: 'Fetch a single Fiscal Host application by reference. Host applications are submitted by Collectives seeking to be fiscally hosted.',
  offPlatformTransactionsInstitutions: 'List financial institutions available for off-platform (manual bank transfer) transaction imports, filterable by country and provider.',
  loggedInAccount: 'Fetch the account of the currently authenticated user. Requires a personal token.',
  me: 'Fetch the currently authenticated individual user. Requires a personal token. Returns the logged-in user\'s personal account details.',
  platformSubscriptionTiers: 'List the available Open Collective platform subscription tiers for organizations and Fiscal Hosts.',
};

export function buildTools(schema, endpoint, tokenOrGetter) {
  const getToken = typeof tokenOrGetter === 'function' ? tokenOrGetter : () => tokenOrGetter;
  const typeMap = Object.fromEntries(schema.types.map(t => [t.name, t]));

  return schema.queryType.fields.map(op => {
    const inputSchema = {
      type: 'object',
      properties: Object.fromEntries(
        op.args.map(a => [
          a.name,
          {
            ...graphqlTypeToJsonSchema(a.type, typeMap),
            ...(a.description ? { description: a.description } : {}),
          },
        ])
      ),
      required: op.args.filter(a => a.type.kind === 'NON_NULL').map(a => a.name),
    };

    const returnTypeName = unwrapType(op.type).name;
    const isLeaf = isLeafType(returnTypeName, typeMap);
    const selection = isLeaf ? null : (buildSelection(returnTypeName, typeMap) ?? '__typename');
    const subSel = selection ? ` { ${selection} }` : '';

    const argsDef = op.args.map(a => `$${a.name}: ${argTypeStr(a.type)}`).join(', ');
    const argsUse = op.args.map(a => `${a.name}: $${a.name}`).join(', ');
    // `let` so scope-error retries can permanently strip bad fields for this op
    let query = op.args.length
      ? `query ${op.name}(${argsDef}) { ${op.name}(${argsUse})${subSel} }`
      : `{ ${op.name}${subSel} }`;

    async function handler(args = {}) {
      const token = getToken();
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Personal-Token'] = token;

      for (let attempt = 0; attempt < 2; attempt++) {
        const res = await fetch(endpoint, {
          method: 'POST',
          headers,
          body: JSON.stringify({ query, variables: args }),
        });
        if (!res.ok) throw new Error(`GraphQL request failed: ${res.status} ${res.statusText}`);
        const { data, errors } = await res.json();
        const result = data?.[op.name];
        if (result != null) return result;
        if (!errors?.length) return result;

        // If the result is null due to NON_NULL field scope errors, strip the
        // offending fields and retry once. Persisting the stripped query means
        // subsequent calls pay only one API round-trip instead of two.
        if (attempt === 0) {
          const badFields = errors
            .filter(e => Array.isArray(e.path) && e.path.length >= 2)
            .map(e => String(e.path[1]));
          if (badFields.length > 0) {
            for (const f of badFields) {
              query = query.replace(new RegExp(`\\b${f}\\b`, 'g'), '');
            }
            continue;
          }
        }

        throw new Error(errors.map(e => e.message).join(', '));
      }
    }

    return {
      name: op.name,
      description: op.description || DESCRIPTIONS[op.name] || camelToWords(op.name),
      inputSchema,
      handler,
    };
  });
}
