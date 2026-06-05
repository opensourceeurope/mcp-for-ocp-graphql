# RAG Spike Findings

Spike run against branch `worktree-python-core-mcp`.
All experiments run with `uv run python` inside the project venv.

---

## Milvus Lite API

**Exact working code (pymilvus 3.0.0 / milvus-lite 3.0):**

```python
import os
from pymilvus import MilvusClient

# 1. Create client — pass a file path string directly (NOT uri= kwarg)
client = MilvusClient("/tmp/_spike.db")   # creates a directory at that path

# 2. Create collection — quick-setup shorthand (dimension= only, no explicit schema)
client.create_collection(
    collection_name="spike_test",
    dimension=8,
    auto_id=True,
    metric_type="COSINE",   # default is "COSINE"; also "L2", "IP"
)

# 3. Insert — list of dicts; key for vector field is "vector"; auto_id so no id key needed
result = client.insert(
    collection_name="spike_test",
    data=[
        {"vector": [1, 0, 0, 0, 0, 0, 0, 0], "text": "alpha"},
        {"vector": [0, 1, 0, 0, 0, 0, 0, 0], "text": "beta"},
    ],
)
# result == {'insert_count': 2, 'ids': [1, 2]}  (key is 'ids', NOT 'primary_keys')

# 4. Search — data is a list of vectors (batch dimension preserved)
search_results = client.search(
    collection_name="spike_test",
    data=[[1, 0, 0, 0, 0, 0, 0, 0]],   # outer list = batch
    limit=1,
    output_fields=["text"],
)
# Returns: [[ {'id': 1, 'distance': 0.0, 'entity': {'id': 1, 'text': 'alpha'}} ]]
# Access: search_results[0][0]['entity']['text']  -> 'alpha'
# Score:  search_results[0][0]['distance']        -> 0.0  (COSINE; 0.0 = perfect match)

# 5. Cleanup
client.drop_collection("spike_test")
client.close()
import shutil; shutil.rmtree("/tmp/_spike.db")   # it is a DIRECTORY, not a file
```

**Key details:**
- `MilvusClient("/path/to/db")` — positional string arg, no `uri=`. Milvus Lite creates a **directory** at the path (SQLite WAL family). Use `shutil.rmtree` to delete, NOT `os.remove`.
- Quick-setup `create_collection(dimension=N)` adds two fields by default: `id` (int64, primary, auto_id) and `vector` (float_vector dim=N). Any extra keys in the insert dict become dynamic fields (e.g. `"text"`).
- `insert` returns `{'insert_count': N, 'ids': [...]}`.
- `search` result shape: `results[query_index][hit_index]` — each hit is a dict with `'id'`, `'distance'`, and `'entity'` (dict of `output_fields`).
- COSINE distance 0.0 = identical vectors (NOT 1.0 — it is cosine **distance**, lower = more similar).

**OpenCrane's production schema** (from `opencrane/mcp/services/milvus_client.py`) uses an explicit schema instead of quick-setup:

```python
from pymilvus import MilvusClient, DataType

schema = client.create_schema(auto_id=False, enable_dynamic_field=True)
schema.add_field("chunk_id",      DataType.VARCHAR,      max_length=64,    is_primary=True)
schema.add_field("embedding",     DataType.FLOAT_VECTOR, dim=768)
schema.add_field("content",       DataType.VARCHAR,      max_length=65535)
schema.add_field("source_file",   DataType.VARCHAR,      max_length=512)
schema.add_field("source_name",   DataType.VARCHAR,      max_length=256)
schema.add_field("chunk_type",    DataType.VARCHAR,      max_length=32)
schema.add_field("metadata_json", DataType.VARCHAR,      max_length=65535)
schema.add_field("token_count",   DataType.INT64)
schema.add_field("line_start",    DataType.INT64)

index_params = client.prepare_index_params()
index_params.add_index(field_name="embedding", index_type="AUTOINDEX", metric_type="COSINE")

client.create_collection(
    collection_name="ai_docs_chunks_v1",
    schema=schema,
    index_params=index_params
)
```

---

## Embedding

**Exact load + encode calls that worked:**

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("nomic-ai/nomic-embed-text-v1.5", trust_remote_code=True)

# Query-side prefix (for retrieval)
query_vec = model.encode("search_query: how to list expenses by host")
# len(query_vec) == 768, dtype == float32

# Document-side prefix (for indexing)
doc_vec = model.encode("search_document: list expenses by host collective slug")
# len(doc_vec) == 768
```

**trust_remote_code required:** YES — the model uses a custom modeling file. Without it, transformers refuses to load it.

**Extra deps required:** YES — `einops>=0.7` must be installed. Without it, transformers raises:
```
ImportError: This modeling file requires the following packages that were not found
in your environment: einops. Run `pip install einops`
```
`einops` has been added to `pyproject.toml` dependencies (`"einops>=0.7"`).

**Embedding dimension:** 768 (float32)

**nomic task prefixes** (required for correct embedding — the model is trained with them):
- Queries: prefix with `"search_query: "`
- Documents: prefix with `"search_document: "`

**HF_TOKEN note:** Model loads fine without a token (it's public), but unauthenticated requests are rate-limited. Set `HF_TOKEN` in production to avoid throttling.

---

## OpenCrane CLI

**Version:** 0.18.5

**Top-level commands:**
```
add       Interactively add documentation sources
build     Full pipeline: fetch -> llms -> chunk -> embed -> index
chunk     Generate rag-chunks.json from documentation
embed     Generate embeddings from rag-chunks.json
fetch     Fetch documentation from GitHub
index     Initialize Milvus vector database
init      Scaffold new project (.opencrane/ directory)
inspect   Launch MCP Inspector (stdio)
llms      Generate llms-full.txt files
pack      Package MCP server for distribution via uvx
serve     Start MCP server (stdio or HTTP transport)
tokens    Generate token count report for llms-full.txt files
visualize Render interactive HTML for chunk visualization
```

**`opencrane chunk` flags:**
```
--config TEXT        Python config class (module:Class) or YAML file path
--llmstxt-dir PATH   Directory containing llms-full.txt  (env: AI_DOCS_LLMSTXT_DIR)
--chunks-file PATH   Output path for rag-chunks.json      (env: AI_DOCS_CHUNKS_FILE)
--force              Always regenerate (chunking normally always regenerates anyway)
```
Default chunks file: `.opencrane/chunks.json`

**`opencrane embed` flags:**
```
--config TEXT            Python config class or YAML file
--chunks-file PATH       Input chunks JSON     (env: AI_DOCS_CHUNKS_FILE;   default: .opencrane/chunks.json)
--embeddings-file PATH   Output embeddings JSON (env: AI_DOCS_EMBEDDINGS_FILE; default: .opencrane/embeddings.json)
--force                  Regenerate even if chunks SHA unchanged
```

**`opencrane index` flags:**
```
--config TEXT   Python config class or YAML file
```
Reads `AI_DOCS_CHUNKS_FILE` (default `.opencrane/chunks.json`) and `AI_DOCS_EMBEDDINGS_FILE` (default `.opencrane/embeddings.json`).

**`opencrane llms` flags:**
```
--config TEXT        Python config class or YAML file
--sources-dir PATH   Source dir (repeatable)  (env: AI_DOCS_SOURCES_DIRS)
--llmstxt-dir PATH   Output dir for llms-full.txt (env: AI_DOCS_LLMSTXT_DIR)
--force              Regenerate even without git changes
```

**Key environment variables (from `opencrane/shared/config.py` and service files):**

| Variable | Default | Description |
|---|---|---|
| `MILVUS_DB_PATH` | `.opencrane/milvus.db` | Milvus Lite file path (takes precedence over host/port) |
| `MILVUS_HOST` | `localhost` | Milvus server host (ignored when MILVUS_DB_PATH set) |
| `MILVUS_PORT` | `19530` | Milvus server port |
| `MILVUS_COLLECTION` | `ai_docs_chunks_v1` | Collection name |
| `EMBEDDING_MODEL` | `nomic-ai/nomic-embed-text-v1.5` | HuggingFace model ID |
| `AI_DOCS_CHUNKS_FILE` | `.opencrane/chunks.json` | Chunks JSON path |
| `AI_DOCS_EMBEDDINGS_FILE` | `.opencrane/embeddings.json` | Embeddings JSON path |
| `AI_DOCS_LLMSTXT_DIR` | `.opencrane/llmstxt` | llms-full.txt directory |
| `AI_DOCS_SOURCES_DIRS` | `` | Comma-separated source dirs |
| `AI_DOCS_EMBEDDINGS_BACKEND` | `` | Embedding backend override |
| `DROP_EXISTING` | `false` | Drop+recreate collection on index |
| `GITHUB_TOKEN` | `` | Required for `opencrane fetch` |
| `HF_TOKEN` | `` | HuggingFace token (rate-limit avoidance) |
| `HYBRID_ALPHA` | `0.6` | Vector vs keyword blend weight (0=keyword only, 1=vector only) |

**Important:** OpenCrane's `MilvusService` uses `MILVUS_DB_PATH` (not `MILVUS_URI`) because pymilvus reads `MILVUS_URI` at import time and fails if it's a file path. Any custom search code must follow the same pattern.

**OpenCrane's MilvusService.search() signature** (for reference when implementing our own search):
```python
milvus.search(
    query_vector: List[float],
    limit: int = 5,
    chunk_types: Optional[List[str]] = None,
    source_files: Optional[List[str]] = None,
    source_names: Optional[List[str]] = None,
    metadata_contains: Optional[List[str]] = None,
) -> List[Dict]
```
Returns a flat list of dicts (not raw pymilvus hit objects). Each dict has keys: `chunk_id`, `content`, `source_file`, `source_name`, `chunk_type`, `metadata_json`, `token_count`, `line_start`, `distance`.

---

## Environment Notes

### Installed versions (post-spike)
| Package | Version |
|---|---|
| pymilvus | 3.0.0 |
| milvus-lite | 3.0 |
| sentence-transformers | 5.5.1 |
| torch | 2.10.0 |
| einops | 0.8.2 |
| transformers | 5.10.2 |
| tokenizers | 0.22.2 |

### pyproject.toml changes
Added to `[project].dependencies`:
```toml
"pymilvus>=2.4",
"milvus-lite>=2.4",
"sentence-transformers>=3",
"einops>=0.7",
```
Note: `uv` resolved `pymilvus` to 3.0.0 and `milvus-lite` to 3.0 (both far above the `>=2.4` floor). The API in 3.x differs from 2.x; the findings above document the 3.x API.

### Version mismatch warning
During `uvx opencrane` install, this warning appeared:
```
warning: The package `pymilvus==2.5.18` does not have an extra named `milvus-lite`
```
This affects only the `uvx opencrane` ephemeral environment (OpenCrane pins pymilvus==2.5.18 for its own use). Our project venv uses pymilvus 3.0.0. These are separate venvs and do not conflict.

### Milvus Lite is a DIRECTORY
`MilvusClient("/tmp/_spike.db")` creates a directory (SQLite WAL), not a single file. Use `shutil.rmtree` or `rm -rf` for cleanup; `os.remove` raises `PermissionError`.

### nomic-embed-text-v1.5 model download
Model is ~550 MB and caches to `~/.cache/huggingface/hub/`. First run downloads automatically. Subsequent runs are instant (cache hit).

### Existing tests
All 27 existing tests pass after adding the new deps (`uv run pytest -q` → `27 passed in 0.30s`).
