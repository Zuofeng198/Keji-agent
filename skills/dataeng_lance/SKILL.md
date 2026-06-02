---
name: lance
description: Lance 列式数据格式专家知识，用于 ML/AI 工作负载和向量搜索。涵盖 LanceDB、向量索引（IVF_PQ、HNSW）、嵌入存储、多模态数据集、数据集版本管理和零拷贝读取。
---

# Lance Data Format Expert

Lance is a modern columnar data format optimized for ML and AI applications. This skill helps with Lance for multimodal data storage, vector search, and high-performance data operations.

## Version Information

**Lance SDK:** v3.0.0 (March 2026, SemVer since v1.0.0 graduation in December 2025)
- **pylance** (Python): v3.0.0 (March 2026) - Python wrapper for Lance columnar format
- **LanceDB** (Python): v0.30.0 (March 2026) - Embedded retrieval library
- Lance File Format 2.1 stable; v2.2 in development (faster scans via structural decode batching)
- Lance v2.0.0 manifest is the new default
- DataFusion upgraded to 52.1.0

**Language Support:**
- **Python** (`pylance` package, requires Python >=3.9) - Primary bindings via PyO3
- **Rust** - Core implementation (80.8% of codebase)
- **Java** - JNI bindings with schema metadata API

**Note:** macOS x86 support has been deprecated as of LanceDB v0.26.0.

## Core Concepts

### What is Lance?

Lance is a modern columnar data format that:
- Delivers **100x faster random access** than Parquet without sacrificing scan performance
- Supports **zero-copy automatic versioning** for data evolution
- Provides **native vector search** with sub-millisecond latency (IVF-PQ, IVF-SQ, HNSW algorithms)
- Supports **multivector search** for late interaction models (ColBERT, ColPaLi)
- Handles **multimodal data**: images, videos, 3D point clouds, audio, text, embeddings
- Implements **row-level ACID transactions** with conflict resolution
- Supports **full-text search** with inverted indices, n-gram indexing, fuzzy search, and boosting
- Supports **geospatial data** via GeoArrow types and RTree spatial indices

### Data Format Architecture

**Storage Design:**
- Separates offsets from data for constant-time random access
- Uses late materialization to scan only necessary columns
- Implements statistics-based page pruning (94% IO reduction in optimal cases)
- Default configuration: 1M rows per file, 8 MiB disk page size

**Indices:**
- **Scalar**: BTree, Bitmap, Bloom Filter, Distributed Range BTree
- **Vector**: IVF-PQ, IVF-SQ, HNSW (with GPU-accelerated IVF-PQ indexing, 10x faster builds)
- **Multivector**: Late interaction indices for ColBERT/ColPaLi models (cosine metric)
- **System**: Fragment Reuse, MemWAL
- **Full-text**: Inverted indices, n-gram tokenization, configurable tokenizers and stopword lists
- **Geospatial**: RTree index for spatial queries (GeoArrow types)
- **Binary**: Hamming distance for binary vector similarity search

### Key Performance Characteristics

- **Random Access**: 100x faster than Parquet, 50-100x faster than raw metadata
- **Batched Operations**: 100x better than both Parquet and raw files
- **Vector Search**: Sub-millisecond latency on 1M vectors (128D, SIFT dataset)
- **Scan Performance**: 3x faster than Parquet for vector data with predicates
- **Statistics Optimization**: 30x faster scans with column statistics (v0.8.21+)

## Installation & Setup

### Python Installation

```bash
# Latest stable version
pip install pylance

# LanceDB (includes Lance format support)
pip install lancedb
```

### Quick Start

```python
import lancedb

# Local database
db = lancedb.connect("~/.lancedb")

# List tables (replaces deprecated table_names())
tables = db.list_tables()  # supports pagination

# Cloud connection (LanceDB Cloud, launched June 2025)
db = lancedb.connect("db://my_database", api_key="ldb_...")

# Async connection
db = await lancedb.connect_async("~/.lancedb")

# Object storage (S3, GCS, Azure, Tencent COS)
db = lancedb.connect(
    "s3://my-bucket/lancedb",
    storage_options={"aws_access_key_id": "***", "aws_secret_access_key": "***"}
)

# Session-based cache control (for large datasets / enterprise deployments)
session = lancedb.Session(cache_size=512 * 1024 * 1024)  # 512 MiB
db = lancedb.connect("~/.lancedb", session=session)
```

## Common Operations

### Creating Tables

```python
import pandas as pd
import pyarrow as pa

# From Pandas DataFrame
df = pd.DataFrame({
    "vector": [[1.1, 2.2], [3.3, 4.4]],
    "text": ["foo", "bar"],
    "price": [10.0, 20.0]
})
table = db.create_table("my_table", data=df, mode="create")

# From PyArrow Table
arrow_table = pa.table({"col1": [1, 2], "col2": ["a", "b"]})
table = db.create_table("arrow_table", data=arrow_table)

# From list of dicts
data = [
    {"vector": [3.1, 4.1], "item": "foo", "price": 10.0},
    {"vector": [5.9, 26.5], "item": "bar", "price": 20.0}
]
table = db.create_table("dict_table", data=data)
```

### Reading Data

```python
# Convert to different formats
df = table.to_pandas()
arrow_table = table.to_arrow()
lance_dataset = table.to_lance()  # For DuckDB integration

# Get row count
count = table.count_rows()

# Retrieve specific rows
rows = table.take_offsets([0, 1, 2])

# Scan entire table
for batch in table.to_arrow():
    process(batch)
```

### Writing & Updating Data

```python
# Add data to existing table
new_data = [{"vector": [7.1, 8.1], "item": "baz", "price": 30.0}]
table.add(new_data)

# Merge/upsert operations (use scalar indexes on key columns for performance)
table.merge_insert("item")  # specify the key column
    .when_matched_update_all()
    .when_not_matched_insert_all()
    .execute(new_data)

# Merge with delete of unmatched source rows
table.merge_insert("item")
    .when_matched_update_all()
    .when_not_matched_by_source_delete()
    .execute(new_data)

# Merge with delete on match (remove matched rows instead of updating)
table.merge_insert("item")
    .when_matched_delete()
    .execute(new_data)

# Update specific rows
table.update(where="price < 15", values={"price": "price * 1.1"})

# Delete rows
table.delete("price > 100")
```

### Querying

```python
# Vector search (ANN - Approximate Nearest Neighbor)
query_vector = [1.0, 2.0]
results = (
    table.search(query_vector)
    .limit(10)
    .to_pandas()
)

# Vector search with filtering
results = (
    table.search(query_vector)
    .where("price > 15")
    .select(["item", "price"])
    .limit(10)
    .to_pandas()
)

# Vector search with distance range filtering
results = (
    table.search(query_vector)
    .distance_range(0.1, 0.5)  # lower_bound (inclusive), upper_bound (exclusive)
    .to_pandas()
)

# Full-text search (requires FTS index)
results = (
    table.search("query text", query_type="fts")
    .limit(10)
    .to_pandas()
)

# Boolean FTS: combine conditions with and/or (Python: also &/|)
from lancedb.query import MatchQuery
combined = MatchQuery("machine learning", "text") & MatchQuery("neural", "text")  # AND
either = MatchQuery("lance", "text") | MatchQuery("arrow", "text")               # OR

# Prefix search (autocomplete-style): matches "mach" → "machine", "machinery"
# Phrase matching with slop: allows terms to be near but not adjacent
results = (
    table.search("mach*", query_type="fts")  # prefix search
    .limit(10)
    .to_pandas()
)

# Hybrid search (vector + full-text with reranking)
results = (
    table.search("flying cars", query_type="hybrid")
    .where("date > '2026-01-01'")
    .reranker("cross_encoder_tuned")
    .select(["id"])
    .limit(10)
    .to_pandas()
)

# Handle bad vectors gracefully
results = (
    table.search(query_vector, on_bad_vectors="fill")  # "error" (default), "fill", or "null"
    .limit(10)
    .to_pandas()
)

# Fast search: skip unindexed data for lower latency (may miss recent inserts)
results = (
    table.search(query_vector, fast_search=True)
    .limit(10)
    .to_pandas()
)

# Query debugging: inspect execution plan
plan = table.search(query_vector).where("price > 15").explain_plan()
metrics = table.search(query_vector).where("price > 15").analyze_plan()

# Prewarm indices for faster cold-start queries
table.prewarm_index()   # load vector/scalar index into cache
table.prewarm_data()    # preload data pages (remote tables)
```

### Indexing

```python
# Create vector index (IVF_PQ for large datasets)
# num_partitions defaults are now auto-determined by Lance if omitted
table.create_index(
    metric="cosine",  # or "L2", "dot", "hamming" (binary vectors)
    num_partitions=256,
    num_sub_vectors=16
)

# Create scalar index (BTree)
table.create_scalar_index("price", index_type="BTREE")

# Create full-text search index with configurable options
table.create_fts_index("text_column", tokenizer="en")

# Create multivector index (for ColBERT/ColPaLi models, cosine only)
table.create_index(
    vector_column_name="multivector_col",
    metric="cosine"
)
```

### Versioning

```python
# Lance provides automatic versioning (zero-copy)

# View versions
versions = table.list_versions()

# Checkout specific version
table.checkout(version=5)

# Restore to latest
table.checkout_latest()

# Time travel queries
results = table.checkout(version=3).search(vector).to_pandas()
```

## Integration Patterns

### Apache Arrow Integration

```python
import pyarrow as pa
import lancedb

# Lance natively supports Arrow tables
arrow_table = pa.table({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})
table = db.create_table("arrow_native", data=arrow_table)

# Convert Lance to Arrow (zero-copy)
arrow_data = table.to_arrow()

# Stream large datasets
for batch in table.to_arrow():
    # Process in batches without loading entire dataset
    process_batch(batch)
```

### DuckDB Integration

DuckDB integration enables zero-copy SQL analytics on Lance tables via Apache Arrow.

```python
import lancedb
import duckdb

db = lancedb.connect("data/sample-lancedb")
table = db.create_table("analytics", data=[
    {"vector": [3.1, 4.1], "item": "foo", "price": 10.0, "quantity": 5},
    {"vector": [5.9, 26.5], "item": "bar", "price": 20.0, "quantity": 3},
    {"vector": [1.2, 3.4], "item": "baz", "price": 15.0, "quantity": 8}
])

# Convert to Lance dataset for DuckDB
lance_dataset = table.to_lance()

# Simple queries
duckdb.query("SELECT * FROM lance_dataset WHERE price > 12")

# Aggregations
duckdb.query("SELECT item, mean(price) as avg_price FROM lance_dataset GROUP BY item")

# Complex analytics
duckdb.query("""
    SELECT
        item,
        price,
        quantity,
        price * quantity as total_value,
        RANK() OVER (ORDER BY price DESC) as price_rank
    FROM lance_dataset
    WHERE quantity > 2
""")

# Join with other data sources
duckdb.query("""
    SELECT l.item, l.price, p.category
    FROM lance_dataset l
    JOIN parquet_table p ON l.item = p.item
""")
```

**DuckDB Performance Features:**
- Column selection pushdown (only scans required columns)
- Filter pushdown (reduces data scanned)
- Streaming support (aggregate tables exceeding memory)
- Zero-copy data sharing via Arrow

### Polars Integration

```python
import polars as pl
import lancedb

db = lancedb.connect("data/polars-db")
table = db.create_table("polars_data", data=df)

# Convert Lance to Polars DataFrame
polars_df = pl.from_arrow(table.to_arrow())

# Query with Polars expressions
result = (
    polars_df
    .filter(pl.col("price") > 15)
    .groupby("category")
    .agg(pl.col("price").mean())
)
```

### Pandas Integration

```python
import pandas as pd

# Direct conversion
df = table.to_pandas()

# Filtered conversion
df = table.search(vector).where("price > 10").to_pandas()

# Write Pandas back to Lance
table.add(df)
```

## Performance Optimization Tips

### 1. Data Clustering Strategy

```python
# Natural clustering (insertion order)
# Tables with timestamps or incrementing IDs are already well-clustered
data_with_timestamp = [
    {"id": 1, "timestamp": "2026-01-01", "value": 10},
    {"id": 2, "timestamp": "2026-01-02", "value": 20},
    # ... continues chronologically
]

# Custom clustering via compaction
table.compact_files()  # Reorganize fragments for better clustering
```

**Best Practice**: Natural clustering occurs with:
- Insertion timestamps
- Incrementing IDs
- Sequential data insertion

### 2. Fragment Management

```python
# AVOID: Single-row inserts (creates too many small fragments)
for row in large_dataset:
    table.add([row])  # ❌ Creates many small fragments

# PREFER: Batch inserts (LanceDB v0.30.0+ uses parallel inserts for local tables)
batch_size = 1000
for i in range(0, len(large_dataset), batch_size):
    batch = large_dataset[i:i+batch_size]
    table.add(batch)  # ✅ Creates optimally-sized fragments, now parallelized

# Regular compaction for streaming workloads
table.compact_files(target_rows_per_fragment=1_000_000)
```

### 3. Column Statistics & Page Pruning

Lance v0.8.21+ uses column statistics for 30x faster scans (94% IO reduction in optimal cases).

```python
# Optimize queries with predicates
# Statistics enable page pruning when filtering

# Efficient query (uses statistics)
results = table.search(vector).where("timestamp >= '2026-01-01'").to_pandas()

# Stats work best on clustered columns
# - Timestamps (naturally ordered)
# - Sequential IDs
# - Sorted categorical data
```

### 4. Index Selection

```python
# Vector indices - choose based on dataset size

# Small datasets (< 100K vectors): No index needed
# Medium (100K - 10M): IVF_PQ
table.create_index(metric="cosine", num_partitions=256, num_sub_vectors=16)

# Large (10M+): IVF_PQ with more partitions
table.create_index(metric="cosine", num_partitions=1024, num_sub_vectors=32)

# Scalar indices - use for frequent filters
table.create_scalar_index("category", index_type="BTREE")  # For equality/range
table.create_scalar_index("tags", index_type="BITMAP")     # For categorical
```

### 5. Query Optimization

```python
# Late materialization - Lance only scans necessary columns
# Avoid SELECT * when possible

# Inefficient
all_data = table.search(vector).to_pandas()  # Loads all columns

# Efficient
needed_data = table.search(vector).select(["id", "price"]).to_pandas()

# Pre-filtering with vector search
results = (
    table.search(vector)
    .where("price > 100 AND category = 'premium'")  # Applied during search
    .limit(10)
    .to_pandas()
)
```

### 6. Cloud Storage Optimization

#### The Serial Dependency Chain (Critical for Latency)

Point lookups on remote storage are bounded by **sequential round-trips**, not parallelism.
Each Lance query must complete these steps in order — each depends on the previous result:

```
Step 1: Read manifest        →  find which fragments/indexes exist
Step 2: Read index (BTREE)   →  locate the target data page
Step 3: Read data page       →  return matching rows
```

On S3 Standard (50-150 ms/GET), a single point lookup takes **150-450 ms**.
On S3 Express One Zone (5-10 ms/GET), the same lookup takes **15-30 ms**.
Lance uses 64 concurrent I/O threads for cloud (`LANCE_IO_THREADS` env var), which helps
**scan throughput** across many fragments but cannot parallelize this serial chain.

**Key takeaway:** For point-lookup workloads, minimize per-GET latency (use Express One
Zone) and minimize fragment count (aggressive compaction) to reduce the number of
sequential steps.

#### S3 Configuration

```python
# Standard S3
db = lancedb.connect(
    "s3://my-bucket/lancedb",
    storage_options={
        "aws_access_key_id": "***",
        "aws_secret_access_key": "***",
        "region": "us-west-2",
        "aws_endpoint_url": "https://s3.us-west-2.amazonaws.com"
    }
)

# S3 Express One Zone (native support, auto-detects --x-s3 suffix)
# Best latency option for remote storage: 5-10 ms per GET
db = lancedb.connect("s3://my-bucket--usw2-az1--x-s3/lancedb")

# Concurrent writes from multiple replicas (requires DynamoDB table
# with hash key "base_uri" and range key "version")
db = lancedb.connect("s3+ddb://my-bucket--usw2-az1--x-s3/lancedb?ddbTableName=lance-locks")

# Batch operations for cloud storage
table.add(large_batch)  # Better than many small adds
```

#### I/O Thread Tuning

```bash
# Default: 64 threads for cloud, 8 for local
# Increase if network bandwidth is not saturated (e.g., large scans)
export LANCE_IO_THREADS=128

# Note: more threads help scan throughput, NOT point-lookup latency
# Point lookups are bounded by the serial manifest→index→data chain
```

#### Compaction Is Critical on Remote Storage

Each fragment adds a potential sequential GET to every query. On local disk the overhead
is microseconds; on S3 it's 5-150 ms per extra fragment read.

```python
# Compact aggressively for remote storage
table.compact_files(target_rows_per_fragment=1_000_000)

# For small tables with frequent single-row writes, compact on every write
# or lower the threshold well below the local-disk default
```

#### Object Store Compatibility

Lance works with any S3-compatible store via the `object_store` crate, but performance
varies dramatically based on each store's small-random-read characteristics:

| Store | Small GET p90 | Suitability for Lance |
|-------|--------------|----------------------|
| S3 Express One Zone | ~10 ms | Best remote option |
| S3 Standard | ~42 ms | Acceptable for scans, slow for point lookups |
| Cloudflare R2 | ~199 ms | Poor — 5x slower than S3 Standard for small reads |
| MinIO (local) | <5 ms | Good for self-hosted / dev |

R2 is optimized for large-file CDN egress, not the many small byte-range reads Lance
generates. It also does not support multipart HTTP range requests.

#### Known Cloud Storage Issues

- **S3 memory leak (GitHub #2468):** Buffering behavior can exceed 16 GB RAM on
  2 GB datasets. Workaround: FUSE mount (rclone/s3fs) or batch processing.
- **No native disk cache yet (GitHub #2626):** Feature request for transparent
  local SSD caching of remote data. Not shipped as of February 2026. Would
  eliminate the latency penalty for warm reads.
- **Manifest lookup is O(1) (GitHub #2790):** Fixed — `lance.dataset()` takes
  ~125 ms on S3 regardless of version count (previously grew linearly).

### 7. Memory Management

```python
# Stream large results instead of loading to memory
for batch in table.to_arrow():
    process_batch(batch)
    # Each batch processed independently

# Use DuckDB for aggregations exceeding memory
lance_dataset = table.to_lance()
duckdb.query("SELECT category, SUM(value) FROM lance_dataset GROUP BY category")
```

## Configuration Best Practices

### Default Settings (Recommended)

```python
# Lance defaults (optimized for most workloads)
# - 1M rows per file
# - 8 MiB disk page size
# - Adaptive structural encodings

# Override if needed
table = db.create_table(
    "custom_config",
    data=data,
    mode="create",
    # Custom configuration via LanceDB settings
)
```

### Expression Simplification

Lance uses Apache DataFusion to optimize filter predicates:

```python
# Complex predicate
table.search(vector).where("value IN (1, 2, 3, 4, 5)")

# Lance simplifies based on statistics
# If stats show value_max = 3, expression becomes: value IN (1, 2, 3)
# Reduces computational overhead
```

## Version-Specific Features

### Lance SDK v3.0.0 (March 2026)
- IVF-based index prewarm support for faster cold starts
- FTS usable as a filter in vector search queries
- `when_matched_delete` in merge_insert operations
- Stable row IDs enabled in commit operations
- Aggregate operations in scanner
- Tencent COS object storage support
- Custom headers for object store requests
- Schema evolution: alter column nullable to non-nullable
- File Format v2.2 development: faster scans via structural decode batching
- DataFusion upgraded to 52.1.0
- **Breaking**: Shuffle buffer removed, index progress callback changes

### Lance SDK v1.0.0 (December 2025)
- Graduated to stable SemVer releases
- Breaking changes only on major version bumps (2.0, 3.0, etc.)
- Breaking changes never invalidate existing Lance data, only SDK-level APIs

### Lance File Format 2.1 (Stable, October 2025)
- Cascading encoding and compression without sacrificing random access
- Documented spec with backwards compatibility commitment
- v2 manifest is now the default

### Lance v0.8.21+ (Statistics & Page Pruning)
- Column statistics for min/max values
- Statistics-based page pruning
- 30x faster scans with predicates
- 94% IO reduction in optimal scenarios

### LanceDB v0.30.0 (March 2026)
- Lance dependency upgraded to v3.0.0
- Parallel inserts for local tables (significant write throughput improvement)
- `fast_search` parameter: skip unindexed data for lower latency
- `explain_plan()` and `analyze_plan()` for query debugging and optimization
- `prewarm_index()` and `prewarm_data()` for remote tables
- `list_tables()` replaces deprecated `table_names()` (adds pagination)
- `num_deleted_rows` returned from delete operations
- Background dataset update checking
- Remote table schema caching for performance
- Boolean FTS queries: combine with `and`/`or` (`&`/`|`), phrase `slop`, prefix search
- Dict-to-SQL struct conversion in `table.update()`
- `when_matched_delete` in merge_insert

### LanceDB v0.26+ (December 2025)
- Lance dependency upgraded to v2.0.0
- `num_partitions` defaults auto-determined by Lance
- Namespace credentials vending and async namespace connection
- `to_pydantic` support in async API
- IVF-SQ index support and HNSW aliases
- `index_cache_size` on `open_table` deprecated in favor of session-level cache via `lancedb.Session`
- macOS x86 support deprecated

### LanceDB Cloud (June 2025 launch, ongoing updates)
- Managed cloud service with $30M Series A funding
- Multimodal Lakehouse Suite: Search, EDA, Feature Engineering, Training
- Self-serve onboarding with workflow-based UI
- Visual index creation (vector, scalar, FTS) in the UI
- Apache Arrow Flight-SQL protocol for SQL queries on billions of rows
- GCP autoscaling support
- Improved load balancing with tenant isolation
- Session-based cache control for Python and TypeScript
- Streaming ingestion with automatic index optimization

### Recent Search Enhancements
- **Multivector search**: Late interaction models (ColBERT, ColPaLi) with per-document vector lists
- **Distance range filtering**: `distance_range()` for bounded similarity search
- **FTS as vector search filter**: Use full-text search conditions as pre/post-filters in vector queries
- **Boolean FTS**: SHOULD/MUST/MUST_NOT operators, phrase matching with `slop`, prefix search
- **Fuzzy search & boosting**: Typo-tolerant FTS with relevance tuning
- **Hybrid search with reranking**: Combined vector + FTS with cross-encoder rerankers; reranker info in explain plans
- **Hamming distance**: Binary vector similarity search
- **GPU-accelerated IVF-PQ**: 10x faster index builds
- **HNSW-accelerated partition computation**: Up to 50% less indexing time
- **500x faster range queries**: 100us on 1M int32 values (from 50ms)
- **`fast_search` mode**: Skip unindexed data for lower latency when freshness is not critical

### Ecosystem Additions
- **lance-graph**: Graph module contributed by Uber (Cypher queries, COLLECT aggregation, WITH clause)
- **GeoArrow GEO types**: Native geospatial data type support
- **RTree geospatial index**: Spatial index specification
- **VoyageAI v4**: First-class embedding support including multimodal models
- **lance-data-viewer**: Local web UI for browsing Lance tables
- **lance-namespace**: Open spec for standardized access to Lance table collections
- **Spark integration**: Via lance-spark for distributed workloads
- **Lance-Trino integration**: SQL analytics via Trino connector
- **OpenTelemetry instrumentation**: `opentelemetry-instrumentation-lancedb` for observability

## Common Patterns

### RAG (Retrieval-Augmented Generation)

```python
import lancedb
from sentence_transformers import SentenceTransformer

# Setup
db = lancedb.connect("rag_db")
model = SentenceTransformer('all-MiniLM-L6-v2')

# Index documents
documents = [
    {"text": "Lance is a columnar format", "source": "doc1"},
    {"text": "Vector search enables semantic retrieval", "source": "doc2"}
]

# Generate embeddings
for doc in documents:
    doc["vector"] = model.encode(doc["text"]).tolist()

table = db.create_table("documents", data=documents)
table.create_index(metric="cosine")

# Query
query = "What is Lance?"
query_vector = model.encode(query).tolist()
results = table.search(query_vector).limit(5).to_pandas()
```

### Multimodal Search

```python
# Combine text and image embeddings
data = [
    {
        "text": "A red car",
        "text_vector": text_encoder.encode("A red car"),
        "image_vector": image_encoder.encode(image_bytes),
        "metadata": {"category": "vehicle"}
    }
]

table = db.create_table("multimodal", data=data)

# Search by text
text_results = table.search(query_text_vector, vector_column="text_vector").limit(10)

# Search by image
image_results = table.search(query_image_vector, vector_column="image_vector").limit(10)

# Hybrid search with metadata filtering
results = (
    table.search(query_vector, vector_column="text_vector")
    .where("metadata.category = 'vehicle'")
    .limit(10)
    .to_pandas()
)
```

### Multivector Search (ColBERT / Late Interaction)

```python
import pyarrow as pa

# Define schema with nested vector list for late interaction models
schema = pa.schema([
    pa.field("id", pa.int64()),
    pa.field("text", pa.utf8()),
    pa.field("multivector", pa.list_(pa.list_(pa.float32(), 256)))  # variable-length list of 256-dim vectors
])

# Create table and index (cosine metric only for multivector)
table = db.create_table("colbert_docs", schema=schema)
table.add(documents_with_multivectors)
table.create_index(vector_column_name="multivector", metric="cosine")

# Query with a single vector
results = table.search([query_vector], vector_column_name="multivector").limit(10).to_arrow()

# Query with multiple vectors (late interaction scoring)
query_vectors = [[0.1] * 256, [0.2] * 256, [0.3] * 256]
results = table.search(query_vectors, vector_column_name="multivector").limit(10).to_arrow()
```

**Note:** Multivector search uses late interaction scoring - it finds the best matching pairs between query and document vectors for more nuanced relevance. Only cosine metric is supported; vector types can be float16, float32, or float64.

### Time-Series Data with Versioning

```python
# Append time-series data
import datetime

metrics = [
    {"timestamp": datetime.datetime.now(), "cpu": 45.2, "memory": 60.1}
]
table.add(metrics)

# Query historical versions
v1_data = table.checkout(version=1).to_pandas()  # Yesterday's data
v2_data = table.checkout(version=2).to_pandas()  # Today's data

# Compare versions
diff = set(v2_data["timestamp"]) - set(v1_data["timestamp"])
```

## Troubleshooting

### Common Issues

**Slow Queries:**
- Use `explain_plan()` and `analyze_plan()` to identify bottlenecks
- Check if data is clustered on filter columns
- Create appropriate indices (scalar/vector)
- Use column selection (`.select()`) to reduce data scanned
- Run `table.compact_files()` if many small fragments exist
- Try `fast_search=True` if freshness is not required

**Slow Queries on S3 / Remote Storage:**
- Point lookups are bounded by serial round-trips (manifest→index→data), not parallelism
- Use S3 Express One Zone (5-10 ms/GET) instead of Standard (50-150 ms/GET)
- Compact aggressively — each extra fragment adds a sequential remote GET
- Increasing `LANCE_IO_THREADS` helps scan throughput but not point-lookup latency
- Consider `s3+ddb://` URI scheme if running multiple writer replicas

**High Memory Usage:**
- Stream results: `for batch in table.to_arrow(): ...`
- Use DuckDB for aggregations
- Limit result sets: `.limit(N)`
- Select only needed columns

**Version Compatibility:**
- Check Lance format version: `table.version()`
- Preview versions available for 6+ months
- Upgrade path available in docs

## Resources

- **Lance Format Documentation**: https://lancedb.github.io/lance/
- **Lance Format GitHub**: https://github.com/lance-format/lance
- **Lance Website**: https://lance.org/
- **LanceDB Docs**: https://docs.lancedb.com/
- **LanceDB GitHub**: https://github.com/lancedb/lancedb
- **Python API Reference**: https://lancedb.github.io/lancedb/python/python/
- **LanceDB Changelog**: https://docs.lancedb.com/changelog/changelog
- **Blog**: https://lancedb.com/blog/
- **lance-data-viewer**: https://github.com/lance-format/lance-data-viewer
- **lance-namespace**: https://github.com/lance-format/lance-namespace
- **VLDB 2025 Paper**: Research paper on Lance internals published at VLDB 2025

## Quick Reference

### Install
```bash
pip install pylance lancedb  # pylance >=3.0.0, lancedb >=0.30.0
```

### Basic Operations
```python
import lancedb

# Connect
db = lancedb.connect("path/to/db")

# Create table
table = db.create_table("name", data=data)

# Vector search
results = table.search(vector).limit(10).to_pandas()

# Add data
table.add(new_data)

# Update
table.update(where="condition", values={"col": "value"})

# Delete
table.delete("condition")

# DuckDB SQL
lance_dataset = table.to_lance()
duckdb.query("SELECT * FROM lance_dataset WHERE col > 10")
```

### Performance Checklist
- ✅ Use batch inserts (not single rows) — parallel inserts in v0.30.0+
- ✅ Run compaction regularly (background compaction now available)
- ✅ Create indices for frequent queries (scalar indexes speed up merge_insert)
- ✅ Use column selection in queries
- ✅ Leverage data clustering
- ✅ Apply filters early in query chain
- ✅ Stream large result sets
- ✅ Use session-level cache control for large datasets
- ✅ Consider GPU-accelerated index builds for large vector datasets
- ✅ Prewarm indices for faster cold-start queries
- ✅ Use `fast_search=True` when freshness is not critical
- ✅ Use `explain_plan()` / `analyze_plan()` to diagnose slow queries

---

When helping users with Lance:
1. Always check version compatibility (Lance SDK 3.0.0, pylance 3.0.0, LanceDB 0.30.0)
2. Recommend batch operations over single-row operations (parallel inserts in v0.30.0+)
3. Suggest appropriate indices based on query patterns (vector, scalar, FTS, multivector, geospatial)
4. Optimize for data clustering when possible
5. Use DuckDB integration for complex SQL analytics (now with Arrow Flight-SQL)
6. Leverage Arrow for zero-copy interoperability
7. Apply performance best practices from v0.8.21+ (statistics, page pruning)
8. Use session-level cache configuration instead of deprecated `index_cache_size`
9. Consider multivector search for ColBERT/ColPaLi late interaction models
10. Use `distance_range()` when bounded similarity is needed instead of top-k
11. Use `explain_plan()` / `analyze_plan()` to diagnose query performance issues
12. Use `list_tables()` instead of deprecated `table_names()`
13. Prewarm indices on startup for latency-sensitive applications
