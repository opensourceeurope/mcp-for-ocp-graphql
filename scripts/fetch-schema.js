import { writeFileSync } from 'node:fs';
import { fetchSchema } from '../src/schema.js';

const ENDPOINT = process.env.OC_GRAPHQL_ENDPOINT ?? 'https://api.opencollective.com/graphql/v2';
const OUTPUT = process.argv[2] ?? 'schema.json';

process.stderr.write(`Fetching schema from ${ENDPOINT}\n`);
const schema = await fetchSchema(ENDPOINT);
writeFileSync(OUTPUT, JSON.stringify(schema));
process.stderr.write(`Wrote ${OUTPUT} — ${schema.queryType.fields.length} queries, ${schema.types.length} types\n`);
