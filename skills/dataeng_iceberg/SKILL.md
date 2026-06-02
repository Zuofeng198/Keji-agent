---
name: iceberg
description: Apache Iceberg 表格式专家知识，用于构建数据湖仓一体架构。涵盖表结构演进、ACID事务、快照隔离、分区演化、时间回溯、压缩合并以及与 Spark/Flink/Trino/Athena 等引擎的集成。
---

# Apache Iceberg Expert

Apache Iceberg is a high-performance open table format for huge analytic datasets. This skill helps architect, build, and optimize data lakehouses with Iceberg, focusing on fundamentals and practical patterns.

## Version Information

**Current Stable Format:** Version 2 (v2) - Production standard
**Latest Format:** Version 3 (v3) - Spec finalized 2025, ecosystem adoption ongoing (Spark/Flink supported; Trino/Athena pending)
**Upcoming:** Version 4 (v4) - Parquet metadata, single-file commits (in development)

**Key Version Features:**
- **v1**: Original format, wide compatibility
- **v2**: Delete files, row-level deletes, partition spec IDs
- **v3**: Deletion vectors (Roaring bitmaps), default column values, row lineage tracking, table encryption keys, multi-argument transforms
- **v4** (planned): Parquet-based metadata (replacing Avro), single-file commits

## Core Concepts

### What is Apache Iceberg?

Apache Iceberg is a high-performance table format that brings ACID transactions, schema evolution, time travel, and partition evolution to data lakes. Unlike traditional formats (Parquet, ORC), Iceberg provides a complete table abstraction with:

- **ACID Transactions**: Serializable isolation, atomic commits
- **Snapshot Isolation**: Consistent reads while writes occur
- **Schema Evolution**: Add/drop/rename columns without rewrites
- **Partition Evolution**: Change partitioning without rewriting data
- **Time Travel**: Query historical table states
- **Hidden Partitioning**: Physical layout transparent to users
- **Metadata-Only Operations**: Many operations don't touch data files

### Table Format Architecture

Iceberg's architecture consists of three layers:

#### 1. Catalog Layer
Where services find the current metadata pointer. Implementations include:
- **Hive Metastore** - Traditional, existing Hive infrastructure
- **AWS Glue** - Managed AWS catalog
- **Nessie** - Git-like catalog with branches/tags/multi-table transactions
- **REST** - Standard API for catalog operations
- **JDBC** - Database-backed catalog
- **Polaris** - Multi-engine interoperable catalog (Apache Top-Level Project, graduated Feb 2026)

#### 2. Metadata Layer

**Metadata Files:**
- Contain table schema, partitioning config, properties, snapshots
- Every write creates new metadata file (atomic swap)
- JSON format (currently Avro, moving to Parquet in v4)
- Immutable - old versions remain for time travel

**Manifest Lists:**
- Track manifests that comprise a snapshot
- Store partition stats, data file counts per manifest
- Enable metadata-only query planning

**Manifest Files:**
- Contain rows for each data file in the table
- Include file path, partition data, metrics (row count, column bounds, null counts)
- Enable predicate pushdown and file pruning

#### 3. Data Layer

**Data Files:**
- Actual table data in Parquet, ORC, or Avro format
- Parquet is most common and recommended
- Immutable - writes create new files
- Deleted via snapshot expiration (garbage collection)

**Delete Files (v2+):**
- Position deletes: Track deleted rows by file + position
- Equality deletes: Track deleted rows by column values
- Enable row-level modifications without rewriting entire files

### Snapshot Isolation & Time Travel

**Snapshots:**
- Every write operation creates a new snapshot (version)
- Snapshots are immutable and include complete table state
- Allow concurrent reads during writes (MVCC)
- Enable time travel queries

**Time Travel:**
- Query table as it existed at specific timestamp or snapshot
- Useful for reproducibility, auditing, debugging
- Powered by metadata retention

**Immutability Benefits:**
- Snapshot isolation keeps readers/writers from interfering
- No locks needed between readers and writers
- Consistent reads at all times

### Hidden Partitioning

Traditional systems (Hive) expose partitions to users, requiring explicit partition filters:
```sql
-- Hive - users must know partitioning
SELECT * FROM events
WHERE year = 2025 AND month = 10 AND day = 19
```

Iceberg uses **hidden partitioning** with transform functions:
```sql
-- Iceberg - partition transparently from timestamp
SELECT * FROM events
WHERE event_time >= '2025-10-19'
```

**Benefits:**
- Users query logical columns, not physical partitions
- Iceberg automatically applies partition pruning
- Partition strategy can evolve without breaking queries
- Reduces user error and query complexity

**Partition Transforms:**
- `year(timestamp)` - Partition by year
- `month(timestamp)` - Partition by month
- `day(timestamp)` - Partition by day
- `hour(timestamp)` - Partition by hour
- `bucket(N, column)` - Hash into N buckets
- `truncate(width, column)` - Truncate strings/ints to width

### Schema Evolution

Iceberg supports safe schema changes without rewriting data:

**Supported Operations:**
- Add columns (nullable or with defaults)
- Drop columns
- Rename columns
- Update column types (widening: int → long, float → double, decimal scale up)
- Reorder columns

**How It Works:**
- Schema stored in metadata, not data files
- New writes use new schema
- Old files read with old schema
- Column IDs track fields across schema versions

### Partition Evolution

Change partitioning strategy over time without rewriting historical data:

**Example:**
```sql
-- Start with daily partitions
CREATE TABLE events (
  id bigint,
  event_time timestamp,
  data string
) PARTITIONED BY (day(event_time));

-- Data grows, switch to hourly partitions (metadata operation)
ALTER TABLE events
ADD PARTITION FIELD hour(event_time);

ALTER TABLE events
DROP PARTITION FIELD day(event_time);
```

**Key Points:**
- Metadata-only operation (no data rewrite)
- Old data keeps old partitioning
- New data uses new partitioning
- Queries work across both partition schemes
- Compaction may rewrite with new scheme over time

## Key Operations

### Creating Iceberg Tables

#### SQL (Spark)

```sql
-- Basic table creation
CREATE TABLE catalog_name.db.table_name (
  id bigint,
  data string,
  category string,
  event_time timestamp
) USING iceberg;

-- With partitioning
CREATE TABLE catalog_name.db.events (
  id bigint,
  user_id string,
  event_type string,
  event_time timestamp,
  data string
) USING iceberg
PARTITIONED BY (days(event_time));

-- With table properties
CREATE TABLE catalog_name.db.events (
  id bigint,
  data string,
  event_time timestamp
) USING iceberg
PARTITIONED BY (bucket(16, id), days(event_time))
TBLPROPERTIES (
  'write.format.default' = 'parquet',
  'write.parquet.compression-codec' = 'zstd',
  'write.metadata.compression-codec' = 'gzip',
  'write.target-file-size-bytes' = '536870912'  -- 512MB
);

-- CTAS (Create Table As Select)
CREATE TABLE catalog_name.db.events_copy
USING iceberg
AS SELECT * FROM catalog_name.db.events;

-- From existing Parquet data
CREATE TABLE catalog_name.db.imported_data
USING iceberg
PARTITIONED BY (year, month)
AS SELECT * FROM parquet.`s3://bucket/path/`;
```

#### API (PySpark)

```python
from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName("Iceberg Example") \
    .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
    .config("spark.sql.catalog.my_catalog", "org.apache.iceberg.spark.SparkCatalog") \
    .config("spark.sql.catalog.my_catalog.type", "hadoop") \
    .config("spark.sql.catalog.my_catalog.warehouse", "s3://bucket/warehouse") \
    .getOrCreate()

# Create table with DataFrame schema
df = spark.createDataFrame([
    (1, "2025-10-19", "data1"),
    (2, "2025-10-20", "data2")
], ["id", "date", "data"])

df.writeTo("my_catalog.db.table_name") \
    .using("iceberg") \
    .partitionedBy("date") \
    .tableProperty("write.format.default", "parquet") \
    .create()
```

### Writing Data

#### Append (Most Common)

```sql
-- Append new data
INSERT INTO catalog.db.events
VALUES (1, 'user1', 'click', current_timestamp(), 'data');

-- Append from query
INSERT INTO catalog.db.events
SELECT * FROM staging_table
WHERE event_date = '2025-10-19';
```

```python
# PySpark append
df.writeTo("catalog.db.events").append()

# Or
df.write.format("iceberg") \
    .mode("append") \
    .save("catalog.db.events")
```

#### Overwrite

```sql
-- Overwrite entire table
INSERT OVERWRITE catalog.db.events
SELECT * FROM new_data;

-- Overwrite specific partition (dynamic)
INSERT OVERWRITE catalog.db.events
SELECT * FROM new_data
WHERE event_date = '2025-10-19';  -- Only this partition overwritten
```

```python
# PySpark overwrite
df.writeTo("catalog.db.events").overwrite()

# Overwrite specific partition
df.writeTo("catalog.db.events") \
    .overwritePartitions()
```

#### Upsert (MERGE)

```sql
-- Merge (upsert) pattern
MERGE INTO catalog.db.events t
USING updates u
ON t.id = u.id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;

-- Delete-then-insert pattern
MERGE INTO catalog.db.events t
USING updates u
ON t.id = u.id
WHEN MATCHED THEN DELETE
WHEN NOT MATCHED THEN INSERT *;

-- Conditional merge
MERGE INTO catalog.db.events t
USING updates u
ON t.id = u.id
WHEN MATCHED AND u.is_deleted = true THEN DELETE
WHEN MATCHED THEN UPDATE SET
  t.data = u.data,
  t.updated_at = u.updated_at
WHEN NOT MATCHED AND u.is_deleted = false THEN INSERT *;
```

#### Delete

```sql
-- Delete with filter
DELETE FROM catalog.db.events
WHERE event_time < '2025-01-01';

-- Delete entire partition (metadata-only if partition matches exactly)
DELETE FROM catalog.db.events
WHERE event_date = '2025-10-19';
```

### Reading Data

#### Standard Queries

```sql
-- Simple select
SELECT * FROM catalog.db.events
WHERE event_time >= '2025-10-01';

-- Iceberg applies partition pruning automatically
SELECT user_id, COUNT(*) as event_count
FROM catalog.db.events
WHERE event_time BETWEEN '2025-10-01' AND '2025-10-31'
GROUP BY user_id;
```

```python
# PySpark read
df = spark.table("catalog.db.events")

# Or
df = spark.read.format("iceberg").load("catalog.db.events")

# With filter pushdown
df = spark.read.format("iceberg") \
    .load("catalog.db.events") \
    .filter("event_time >= '2025-10-01'")
```

#### Time Travel Queries

```sql
-- Query by timestamp (Spark 3.3+)
SELECT * FROM catalog.db.events
FOR TIMESTAMP AS OF '2025-10-01 00:00:00';

-- Query by snapshot ID
SELECT * FROM catalog.db.events
FOR VERSION AS OF 3827452938479827;

-- Older Spark versions
SELECT * FROM catalog.db.events.snapshots;  -- List snapshots

SELECT * FROM catalog.db.events
WHERE snapshot_id = 3827452938479827;
```

```python
# PySpark time travel
# By timestamp
df = spark.read.format("iceberg") \
    .option("as-of-timestamp", "1698019200000") \
    .load("catalog.db.events")

# By snapshot ID
df = spark.read.format("iceberg") \
    .option("snapshot-id", "3827452938479827") \
    .load("catalog.db.events")
```

#### Incremental Reads

```sql
-- Read changes between snapshots
SELECT * FROM catalog.db.events
FOR VERSION AS OF 100
MINUS
SELECT * FROM catalog.db.events
FOR VERSION AS OF 90;
```

```python
# PySpark incremental read
df = spark.read.format("iceberg") \
    .option("start-snapshot-id", "90") \
    .option("end-snapshot-id", "100") \
    .load("catalog.db.events")
```

### Table Maintenance

#### Expire Snapshots

```sql
-- Expire snapshots older than 7 days
CALL catalog.system.expire_snapshots(
  table => 'db.events',
  older_than => TIMESTAMP '2025-10-12 00:00:00',
  retain_last => 10  -- Keep at least 10 snapshots
);

-- Expire by snapshot count
CALL catalog.system.expire_snapshots(
  table => 'db.events',
  max_snapshot_age_ms => 604800000,  -- 7 days in ms
  retain_last => 5
);
```

**Best Practice:** Run regularly (daily/weekly) to prevent metadata bloat and reclaim storage.

#### Compact Data Files

```sql
-- Compact small files (bin-packing)
CALL catalog.system.rewrite_data_files(
  table => 'db.events',
  strategy => 'binpack',
  options => map(
    'target-file-size-bytes', '536870912',  -- 512MB
    'min-file-size-bytes', '134217728'      -- 128MB
  )
);

-- Compact with filter (specific partition)
CALL catalog.system.rewrite_data_files(
  table => 'db.events',
  where => 'event_date = "2025-10-19"',
  strategy => 'binpack'
);

-- Sort data within files
CALL catalog.system.rewrite_data_files(
  table => 'db.events',
  strategy => 'sort',
  sort_order => 'user_id ASC, event_time DESC',
  options => map('target-file-size-bytes', '536870912')
);
```

**When to Compact:**
- After streaming ingestion (many small files)
- When query performance degrades
- After significant deletes/updates
- Typically weekly or after major writes

#### Remove Orphan Files

```sql
-- Find and delete orphaned data files
CALL catalog.system.remove_orphan_files(
  table => 'db.events',
  older_than => TIMESTAMP '2025-10-12 00:00:00',
  location => 's3://bucket/warehouse/db/events'
);
```

**What are orphan files?**
- Files written but never committed
- Files from failed writes
- Not referenced by any snapshot

#### Rewrite Manifests

```sql
-- Consolidate manifest files
CALL catalog.system.rewrite_manifests(
  table => 'db.events'
);
```

**When needed:**
- Many small manifest files after numerous writes
- Slow query planning
- Typically monthly or when planning time increases

### Metadata Operations

```sql
-- View snapshots
SELECT * FROM catalog.db.events.snapshots
ORDER BY committed_at DESC;

-- View files
SELECT * FROM catalog.db.events.files;

-- View manifests
SELECT * FROM catalog.db.events.manifests;

-- View partitions
SELECT * FROM catalog.db.events.partitions;

-- View history
SELECT * FROM catalog.db.events.history;

-- View refs (branches/tags)
SELECT * FROM catalog.db.events.refs;
```

## Integration Patterns

### Apache Spark

**Configuration:**

```python
from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName("Iceberg Spark") \
    .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
    .config("spark.sql.catalog.spark_catalog", "org.apache.iceberg.spark.SparkSessionCatalog") \
    .config("spark.sql.catalog.spark_catalog.type", "hive") \
    .config("spark.sql.catalog.local", "org.apache.iceberg.spark.SparkCatalog") \
    .config("spark.sql.catalog.local.type", "hadoop") \
    .config("spark.sql.catalog.local.warehouse", "/path/to/warehouse") \
    .getOrCreate()
```

**Common Operations:**

```python
# Read
df = spark.table("catalog.db.events")

# Write
df.writeTo("catalog.db.events").append()

# Time travel
df = spark.read.format("iceberg") \
    .option("snapshot-id", snapshot_id) \
    .load("catalog.db.events")

# Incremental read
df = spark.read.format("iceberg") \
    .option("start-snapshot-id", start_id) \
    .option("end-snapshot-id", end_id) \
    .load("catalog.db.events")
```

### Apache Flink (Streaming)

**Configuration:**

```java
StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
StreamTableEnvironment tEnv = StreamTableEnvironment.create(env);

// Configure catalog
tEnv.executeSql(
    "CREATE CATALOG iceberg_catalog WITH (" +
    "'type'='iceberg'," +
    "'catalog-type'='hive'," +
    "'uri'='thrift://localhost:9083'," +
    "'warehouse'='s3://bucket/warehouse'" +
    ")"
);
```

**Streaming Writes:**

```sql
-- Create Iceberg table
CREATE TABLE iceberg_catalog.db.events (
  id BIGINT,
  user_id STRING,
  event_time TIMESTAMP(3),
  data STRING
) WITH (
  'write.format.default' = 'parquet',
  'write.target-file-size-bytes' = '134217728'  -- 128MB
);

-- Stream from Kafka to Iceberg
INSERT INTO iceberg_catalog.db.events
SELECT id, user_id, event_time, data
FROM kafka_source;
```

**Real-Time Architecture Pattern:**
```
Kafka → Flink (streaming writes) → Iceberg ← Trino (queries)
                                          ← Spark (batch processing)
```

### Trino/Presto

**Configuration (Trino):**

```properties
# catalog/iceberg.properties
connector.name=iceberg
iceberg.catalog.type=hive_metastore
hive.metastore.uri=thrift://localhost:9083
```

**Queries:**

```sql
-- Standard queries work seamlessly
SELECT user_id, COUNT(*) as events
FROM iceberg.db.events
WHERE event_date >= DATE '2025-10-01'
GROUP BY user_id;

-- Time travel
SELECT * FROM iceberg.db.events
FOR VERSION AS OF 12345678901234;

-- System tables
SELECT * FROM iceberg.db."events$snapshots";
SELECT * FROM iceberg.db."events$files";
SELECT * FROM iceberg.db."events$manifests";
```

### Catalog Implementations

#### Hive Metastore

```python
# Spark config
spark = SparkSession.builder \
    .config("spark.sql.catalog.hive_catalog", "org.apache.iceberg.spark.SparkCatalog") \
    .config("spark.sql.catalog.hive_catalog.type", "hive") \
    .config("spark.sql.catalog.hive_catalog.uri", "thrift://metastore:9083") \
    .getOrCreate()
```

**Pros:**
- Existing Hive infrastructure
- Wide compatibility

**Cons:**
- No multi-table transactions
- Single point of failure
- Scaling limitations

#### AWS Glue

```python
# Spark config
spark = SparkSession.builder \
    .config("spark.sql.catalog.glue_catalog", "org.apache.iceberg.spark.SparkCatalog") \
    .config("spark.sql.catalog.glue_catalog.catalog-impl", "org.apache.iceberg.aws.glue.GlueCatalog") \
    .config("spark.sql.catalog.glue_catalog.warehouse", "s3://bucket/warehouse") \
    .config("spark.sql.catalog.glue_catalog.io-impl", "org.apache.iceberg.aws.s3.S3FileIO") \
    .getOrCreate()
```

**Pros:**
- Managed AWS service
- AWS ecosystem integration
- No infrastructure management

**Cons:**
- AWS-specific (vendor lock-in)
- Rate limits on API calls

#### Nessie (Git-like Catalog)

```python
# Spark config
spark = SparkSession.builder \
    .config("spark.sql.catalog.nessie", "org.apache.iceberg.spark.SparkCatalog") \
    .config("spark.sql.catalog.nessie.catalog-impl", "org.apache.iceberg.nessie.NessieCatalog") \
    .config("spark.sql.catalog.nessie.uri", "http://nessie:19120/api/v1") \
    .config("spark.sql.catalog.nessie.ref", "main") \
    .config("spark.sql.catalog.nessie.warehouse", "s3://bucket/warehouse") \
    .getOrCreate()
```

**Unique Features:**
- Git-like branches and tags
- Multi-table transactions
- Isolated development environments
- Rollback across multiple tables

**Example:**

```sql
-- Create branch for testing
CREATE BRANCH test_branch IN nessie;

-- Switch to branch
USE REFERENCE test_branch IN nessie;

-- Make changes on branch
INSERT INTO nessie.db.events VALUES (...);

-- Merge branch to main
MERGE BRANCH test_branch INTO main IN nessie;
```

#### REST Catalog

```python
# Spark config
spark = SparkSession.builder \
    .config("spark.sql.catalog.rest", "org.apache.iceberg.spark.SparkCatalog") \
    .config("spark.sql.catalog.rest.catalog-impl", "org.apache.iceberg.rest.RESTCatalog") \
    .config("spark.sql.catalog.rest.uri", "https://catalog-api.example.com") \
    .config("spark.sql.catalog.rest.warehouse", "s3://bucket/warehouse") \
    .getOrCreate()
```

**Pros:**
- Standard API
- Engine-agnostic
- Modern architecture
- Easy to implement custom catalogs

## Partitioning & Performance

### Partitioning Strategies

#### 1. Temporal Partitioning (Most Common)

```sql
-- Daily partitions (recommended for most workloads)
CREATE TABLE events (
  id bigint,
  event_time timestamp,
  data string
) PARTITIONED BY (days(event_time));

-- Hourly (high-volume streaming)
PARTITIONED BY (hours(event_time));

-- Monthly (low-volume, long retention)
PARTITIONED BY (months(event_time));

-- Year/Month/Day split (AWS best practice)
PARTITIONED BY (years(event_time), months(event_time), days(event_time));
```

**Guideline:** Aim for partitions with 100MB - 1GB of data each.

#### 2. Bucketing (High Cardinality)

```sql
-- Hash-based bucketing
CREATE TABLE events (
  user_id string,
  event_time timestamp,
  data string
) PARTITIONED BY (bucket(16, user_id));

-- Combined temporal + bucketing
PARTITIONED BY (days(event_time), bucket(16, user_id));
```

**When to use:**
- High-cardinality columns (user_id, device_id)
- Even distribution needed
- Join optimization

#### 3. Truncate (Categorical)

```sql
-- Truncate strings to prefix
CREATE TABLE logs (
  log_id string,
  country string,
  data string
) PARTITIONED BY (truncate(2, country));  -- First 2 chars

-- Truncate numbers
PARTITIONED BY (truncate(100, user_id));  -- Round to hundreds
```

#### 4. Identity (Low Cardinality)

```sql
-- Direct column value (use sparingly)
CREATE TABLE events (
  event_type string,
  region string,
  event_time timestamp,
  data string
) PARTITIONED BY (region);  -- Only if few distinct regions
```

**Caution:** Identity partitioning can lead to unbalanced partitions. Use only for low-cardinality columns.

### Partition Evolution Example

```sql
-- Start: Expect low volume, use daily partitions
CREATE TABLE events (...)
PARTITIONED BY (days(event_time));

-- After 6 months: Volume increases, switch to hourly
ALTER TABLE events
ADD PARTITION FIELD hours(event_time);

ALTER TABLE events
DROP PARTITION FIELD days(event_time);

-- Historical data keeps daily partitioning
-- New data uses hourly partitioning
-- Queries work transparently across both
```

### Performance Optimization

#### File Sizing

**Target File Size:**
- **Parquet/ORC:** 512MB - 1GB per file
- **Small files (< 100MB):** Hurt query performance
- **Large files (> 1GB):** Reduce parallelism

**Configuration:**

```sql
CREATE TABLE events (...)
TBLPROPERTIES (
  'write.target-file-size-bytes' = '536870912'  -- 512MB
);
```

#### Predicate Pushdown

Iceberg uses manifest files for aggressive predicate pushdown:

```sql
-- Query
SELECT * FROM events
WHERE event_date = '2025-10-19'
  AND user_id = 'user123';

-- Iceberg:
-- 1. Prunes partitions via manifest list (event_date)
-- 2. Prunes files via manifest entries (user_id column stats)
-- 3. Only reads necessary files
```

**Column Metrics Tracked:**
- Row count
- Null count
- Lower bound
- Upper bound

#### Sorting Within Files

```sql
-- Sort data during compaction
CALL catalog.system.rewrite_data_files(
  table => 'db.events',
  strategy => 'sort',
  sort_order => 'user_id, event_time DESC'
);

-- Set default sort order on table
ALTER TABLE catalog.db.events
WRITE ORDERED BY (user_id, event_time DESC);
```

**Benefits:**
- Improved filtering on sorted columns
- Better compression
- Faster min/max checks

#### Compaction Strategies

**Bin-Packing (Default):**
- Combines small files into larger files
- Preserves existing sort order
- Fast, simple

```sql
CALL catalog.system.rewrite_data_files(
  strategy => 'binpack',
  options => map('target-file-size-bytes', '536870912')
);
```

**Sorting:**
- Rewrites files with specified sort order
- Slower but better query performance
- Use when sort order matters

```sql
CALL catalog.system.rewrite_data_files(
  strategy => 'sort',
  sort_order => 'user_id, event_time'
);
```

**Z-Ordering (Some engines):**
- Multi-dimensional clustering
- Good for multiple filter columns
- Not all engines support

## Common Table Properties

### Write Settings

```sql
CREATE TABLE events (...)
TBLPROPERTIES (
  -- File format
  'write.format.default' = 'parquet',  -- or 'orc', 'avro'

  -- Target file size
  'write.target-file-size-bytes' = '536870912',  -- 512MB

  -- Parquet compression
  'write.parquet.compression-codec' = 'zstd',  -- or 'snappy', 'gzip'

  -- Metadata compression
  'write.metadata.compression-codec' = 'gzip',

  -- Write mode for updates/deletes
  'write.update.mode' = 'copy-on-write',  -- or 'merge-on-read'
  'write.delete.mode' = 'copy-on-write',
  'write.merge.mode' = 'copy-on-write',

  -- Parquet settings
  'write.parquet.page-size-bytes' = '1048576',  -- 1MB
  'write.parquet.row-group-size-bytes' = '134217728',  -- 128MB

  -- Object storage
  'write.object-storage.enabled' = 'true',
  'write.object-storage.path' = 's3://bucket/path'
);
```

### Read Settings

```sql
ALTER TABLE events SET TBLPROPERTIES (
  -- Split size for readers
  'read.split.target-size' = '134217728',  -- 128MB

  -- Parquet vectorization
  'read.parquet.vectorization.enabled' = 'true',
  'read.parquet.vectorization.batch-size' = '5000'
);
```

### Snapshot Retention

```sql
ALTER TABLE events SET TBLPROPERTIES (
  -- Minimum snapshots to retain
  'history.expire.min-snapshots-to-keep' = '10',

  -- Maximum snapshot age
  'history.expire.max-snapshot-age-ms' = '604800000'  -- 7 days
);
```

### Compaction Triggers

```sql
ALTER TABLE events SET TBLPROPERTIES (
  -- Trigger compaction on commit
  'commit.manifest.min-count-to-merge' = '5',
  'commit.manifest-merge.enabled' = 'true'
);
```

## Best Practices

### 1. Snapshot Retention

**Strategy:**
- Retain snapshots for compliance/audit requirements
- Balance storage cost vs time travel needs
- Typical: 7-30 days

**Configuration:**

```sql
-- Expire weekly, keep minimum 10 snapshots
CALL catalog.system.expire_snapshots(
  table => 'db.events',
  older_than => TIMESTAMP '2025-10-12 00:00:00',
  retain_last => 10
);
```

**Schedule:** Run daily or weekly via Airflow/cron.

### 2. Compaction Cadence

**When to Compact:**
- **Streaming workloads:** Daily (many small files)
- **Batch workloads:** Weekly or after major writes
- **After deletes/updates:** If > 20% of data affected

**Signals to Compact:**
- Query planning time increases
- Large number of small files (< 100MB)
- High file count in metadata tables

**Example Monitoring:**

```sql
-- Check file sizes
SELECT
  COUNT(*) as file_count,
  AVG(file_size_in_bytes) / 1024 / 1024 as avg_mb,
  MIN(file_size_in_bytes) / 1024 / 1024 as min_mb,
  MAX(file_size_in_bytes) / 1024 / 1024 as max_mb
FROM catalog.db.events.files
WHERE file_size_in_bytes < 104857600;  -- < 100MB
```

### 3. Choosing Partition Strategy

**Decision Matrix:**

| Query Pattern | Partition Strategy |
|---------------|-------------------|
| Time-series (most queries filter by date) | `days(timestamp)` or `hours(timestamp)` |
| High-cardinality column (user_id, device_id) | `bucket(N, column)` |
| Low-cardinality categorical (region, status) | `identity(column)` (use sparingly) |
| Multiple filter columns | Composite: `days(timestamp), bucket(N, user_id)` |
| Growing data volume | Start simple, use partition evolution |

**Rules of Thumb:**
- Start with time-based partitioning (days)
- Aim for 100MB - 1GB per partition
- Avoid over-partitioning (< 1000 partitions ideal)
- Use partition evolution as data grows

### 4. Handling Schema Changes

**Safe Operations:**
- Add nullable columns
- Rename columns (metadata-only)
- Widen types (int → long, float → double)

**Risky Operations:**
- Drop columns (data inaccessible but not deleted)
- Narrow types (may lose precision)
- Change nullability (can break reads)

**Example:**

```sql
-- Safe: Add column
ALTER TABLE events ADD COLUMN new_field string;

-- Safe: Rename column (metadata update)
ALTER TABLE events RENAME COLUMN old_name TO new_name;

-- Safe: Widen type
ALTER TABLE events ALTER COLUMN int_col TYPE bigint;

-- Risky: Drop column (data remains but inaccessible)
ALTER TABLE events DROP COLUMN unused_col;
```

### 5. Write Modes (Copy-on-Write vs Merge-on-Read)

**Copy-on-Write (Default, Recommended):**
- Updates/deletes rewrite entire data files
- Slower writes, faster reads
- No separate delete files
- Best for read-heavy workloads

**Merge-on-Read (v2+):**
- Updates/deletes create position/equality delete files
- Faster writes, slower reads (merge on read)
- Best for write-heavy, low latency ingestion

**Configuration:**

```sql
ALTER TABLE events SET TBLPROPERTIES (
  'write.update.mode' = 'merge-on-read',
  'write.delete.mode' = 'merge-on-read'
);
```

**When to use MoR:**
- Streaming ingestion with frequent updates
- Low-latency write requirements
- Periodic compaction can merge delete files

### 6. Monitoring & Observability

**Key Metrics to Track:**

```sql
-- Snapshot count
SELECT COUNT(*) as snapshot_count
FROM catalog.db.events.snapshots;

-- File count and sizes
SELECT
  COUNT(*) as total_files,
  SUM(file_size_in_bytes) / 1024 / 1024 / 1024 as total_gb,
  AVG(file_size_in_bytes) / 1024 / 1024 as avg_mb
FROM catalog.db.events.files;

-- Partition distribution
SELECT partition, COUNT(*) as file_count
FROM catalog.db.events.files
GROUP BY partition
ORDER BY file_count DESC
LIMIT 20;

-- Recent commits
SELECT
  committed_at,
  snapshot_id,
  operation,
  summary
FROM catalog.db.events.snapshots
ORDER BY committed_at DESC
LIMIT 10;
```

## Quick Reference

### Essential SQL Commands

```sql
-- Create table
CREATE TABLE catalog.db.table (...) USING iceberg PARTITIONED BY (...);

-- Write
INSERT INTO catalog.db.table VALUES (...);
INSERT INTO catalog.db.table SELECT ...;

-- Read
SELECT * FROM catalog.db.table WHERE ...;

-- Time travel
SELECT * FROM catalog.db.table FOR TIMESTAMP AS OF '...';
SELECT * FROM catalog.db.table FOR VERSION AS OF snapshot_id;

-- Update
UPDATE catalog.db.table SET col = value WHERE ...;

-- Delete
DELETE FROM catalog.db.table WHERE ...;

-- Merge
MERGE INTO catalog.db.table t USING updates u ON t.id = u.id
WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *;

-- Maintenance
CALL catalog.system.expire_snapshots(...);
CALL catalog.system.rewrite_data_files(...);
CALL catalog.system.remove_orphan_files(...);
CALL catalog.system.rewrite_manifests(...);

-- Metadata
SELECT * FROM catalog.db.table.snapshots;
SELECT * FROM catalog.db.table.files;
SELECT * FROM catalog.db.table.manifests;
SELECT * FROM catalog.db.table.history;
```

### PySpark Snippets

```python
# Read
df = spark.table("catalog.db.table")

# Write
df.writeTo("catalog.db.table").append()

# Time travel
df = spark.read.format("iceberg") \
    .option("snapshot-id", snapshot_id) \
    .load("catalog.db.table")

# Incremental read
df = spark.read.format("iceberg") \
    .option("start-snapshot-id", start_id) \
    .option("end-snapshot-id", end_id) \
    .load("catalog.db.table")
```

### Maintenance Checklist

- ✅ **Daily/Weekly**: Expire old snapshots
- ✅ **Weekly/Monthly**: Compact small files
- ✅ **Monthly**: Rewrite manifests if needed
- ✅ **After major deletes**: Remove orphan files
- ✅ **Monitor**: File counts, sizes, snapshot count
- ✅ **Optimize**: Sort order for common queries

### Configuration Priorities

1. **Format Version**: Use v2 (stable), v3 if using Spark/Flink and need deletion vectors or encryption
2. **Partitioning**: Start simple (time-based), evolve as needed
3. **File Size**: Target 512MB - 1GB
4. **Compression**: zstd for Parquet (balance speed/size)
5. **Write Mode**: Copy-on-write for reads, merge-on-read for writes
6. **Retention**: 7-30 days for snapshots

---

When helping users with Apache Iceberg:
1. **Start with fundamentals** - Understand table architecture before optimizations
2. **Partition wisely** - Use hidden partitioning, start simple, evolve as data grows
3. **Maintain regularly** - Expire snapshots, compact files on schedule
4. **Monitor metrics** - Track file counts/sizes, snapshot growth
5. **Leverage time travel** - For debugging, auditing, reproducibility
6. **Choose right catalog** - Hive for compatibility, Glue for AWS, Nessie for Git-like features
7. **Optimize for workload** - Copy-on-write for reads, merge-on-read for writes
8. **Use metadata operations** - Snapshot, files, manifests tables for insights
9. **Test partition evolution** - Powerful but requires understanding implications
10. **Integrate with ecosystem** - Spark for batch, Flink for streaming, Trino for queries
