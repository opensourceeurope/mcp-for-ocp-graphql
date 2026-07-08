"""MCP server for the Open Collective GraphQL API."""

# torch (via sentence-transformers) and faiss (via milvus-lite) each link their
# own OpenMP runtime. When both run multi-threaded in one process they collide
# and segfault — notably on macOS — the moment milvus builds its HNSW index at
# search time. Pinning OpenMP to a single thread before either native library
# loads avoids the clash; query-time embedding + search is single-vector work,
# so the throughput cost is negligible. setdefault lets the environment override.
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
