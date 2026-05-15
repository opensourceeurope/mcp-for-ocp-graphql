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
        type { kind name ofType { kind name ofType { kind name ofType { kind name } } } }
      }
    }
    types {
      kind
      name
      fields(includeDeprecated: false) {
        name
        description
        args { type { kind } }
        type { kind name ofType { kind name ofType { kind name ofType { kind name } } } }
      }
      inputFields {
        name
        description
        defaultValue
        type { kind name ofType { kind name ofType { kind name ofType { kind name } } } }
      }
      enumValues { name }
    }
  }
}`;

export async function fetchSchema(endpoint) {
  const res = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: INTROSPECTION_QUERY }),
  });

  if (!res.ok) throw new Error(`Introspection failed: ${res.status} ${res.statusText}`);
  const { data, errors } = await res.json();
  if (errors?.length) throw new Error(`Introspection errors: ${errors.map(e => e.message).join(', ')}`);

  if (!data?.__schema) throw new Error('Introspection succeeded but response contained no schema data');
  return data.__schema;
}
