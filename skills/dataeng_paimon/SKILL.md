---
name: paimon
description: Apache Paimon 流式湖仓格式专家知识，用于实时数据摄入和湖仓架构。涵盖主键表与变更日志、Flink CDC 入湖、物化表、PyPaimon、删除向量以及与 Spark 的兼容集成。
---

# Apache Paimon Expert

Apache Paimon is a streaming lake format designed for real-time data ingestion and lakehouse architectures. This skill helps build streaming lakehouses with Paimon, focusing on Flink-native patterns and practical streaming data pipelines.

## Version Information

**Current Stable:** Paimon 1.3.1 (November 2025)
**Python SDK:** PyPaimon 1.3.1 (pure Python, no JDK required)
**Recommended Flink:** Flink 1.19+, Flink 2.0+ (latest features)
**Recommended Spark:** Spark 3.4.3

**Key 2025/2026 Developments:**
- Flink 2.0 integration with native Materialized Tables
- Deletion vectors for primary key tables
- Improved lookup join performance with in-memory cache option
- Nested projection pushdown
- Flink CDC 3.5 with Paimon 1.2.0+
- Enhanced Spark query optimization (37% improvement on TpcDS)
- Iceberg compatibility: expose Paimon tables as Iceberg via Hadoop, Hive, or REST catalog
- Data Evolution Mode for append tables (partial column updates without full file rewrites)
- PyPaimon rewritten as pure Python (no JDK dependency)
- REST Catalog with row-level and column-level auth interfaces
- Blob storage for multimodal data (images, audio, video) via Data Evolution mode

**Paimon 2.0 Roadmap (announced):**
- Unified storage for structured, multimodal, and vector data
- Vector Store and Global Vector Index
- Global Index framework and Global Inverted Index
- Enhanced Python SDK with Ray support

## Core Concepts

### What is Apache Paimon?

Apache Paimon is a streaming lake format that enables building **Realtime Lakehouse Architecture** with Flink and Spark for both streaming and batch operations. Unlike batch-first formats (Iceberg, Delta), Paimon is **designed for streaming-first** workloads.

**Key Characteristics:**
- **Flink-Native**: Deep integration with Apache Flink
- **LSM Tree Structure**: Log-Structured Merge tree for efficient updates
- **Streaming-First**: Minute-level latency (checkpoint interval)
- **ACID Transactions**: Serializable isolation
- **Changelog Production**: Native CDC support
- **Unified Batch + Streaming**: Same table, both read modes

### Lake Format Architecture

Paimon innovatively combines the **lake format** and **LSM (Log-Structured Merge) tree structure** to support real-time streaming updates in the lake architecture.

**Three-Layer Architecture:**

1. **Catalog Layer**
   - Filesystem catalog (default)
   - Hive Metastore
   - JDBC catalog
   - Stores table metadata pointers

2. **Metadata Layer**
   - Snapshots (table versions)
   - Manifests (file lists)
   - Schema files
   - Statistics

3. **Data Layer**
   - Data files (Parquet, ORC, Avro)
   - Delete files (for primary key tables)
   - Changelog files

### LSM Tree Structure

Each **bucket** is a separate LSM tree containing multiple sorted runs:

**Write Path:**
1. Data arrives in streaming job
2. Flink checkpoint triggers flush to **Level 0** (L0) files
3. Background compaction merges L0 → L1 → L2 → ...
4. Sorted runs merged to limit query overhead

**Compaction Strategy:**
- Similar to RocksDB's universal compaction
- Asynchronous compaction in separate threads
- Writers pause if sorted runs exceed threshold
- Trade-off: write performance vs query performance

### Bucket Organization

**Bucket** = smallest unit for read/write parallelism

**Unpartitioned table:**
```
table/
  bucket-0/
  bucket-1/
  bucket-2/
```

**Partitioned table:**
```
table/
  dt=2025-10-19/
    bucket-0/
    bucket-1/
  dt=2025-10-20/
    bucket-0/
    bucket-1/
```

**Bucket Modes:**
1. **Fixed Bucket** (`bucket = N`): Hash-based, fixed count
2. **Dynamic Bucket** (`bucket = -1`): Auto-expand based on data volume
3. **Single Bucket** (default): Single parallelism (not recommended)

### Changelog Production

Paimon produces **changelogs** natively for downstream consumers:

**Changelog Modes:**
- **+I** (Insert): New record
- **-U** (Update Before): Old value before update
- **+U** (Update After): New value after update
- **-D** (Delete): Record deletion

**Changelog Producers:**
- `none`: No changelog
- `input`: Pass through upstream changelog
- `lookup`: Full changelog via lookup (primary key tables)
- `full-compaction`: Full changelog via compaction

## Table Types

### Primary Key Tables

Tables with one or more primary keys for identifying unique records.

**Characteristics:**
- Support INSERT, UPDATE, DELETE, UPSERT
- Merge records with same primary key
- LSM tree structure per bucket
- Suitable for: Dimension tables, SCD, mutable data

**Create Primary Key Table:**

```sql
-- Flink SQL
CREATE TABLE users (
  user_id BIGINT,
  name STRING,
  email STRING,
  age INT,
  updated_at TIMESTAMP(3),
  PRIMARY KEY (user_id) NOT ENFORCED
) WITH (
  'bucket' = '4'
);
```

**Merge Engines:**
- `deduplicate`: Keep last record (default)
- `partial-update`: Merge non-null fields
- `aggregation`: Aggregate fields (SUM, MAX, etc.)
- `first-row`: Keep first record

### Append-Only Tables

Tables without primary keys, allowing only INSERT operations.

**Characteristics:**
- No updates or deletes (streaming mode)
- No compaction overhead
- Suitable for: Logs, events, immutable data

**Create Append-Only Table:**

```sql
-- Flink SQL
CREATE TABLE events (
  event_id STRING,
  user_id BIGINT,
  event_time TIMESTAMP(3),
  event_type STRING,
  payload STRING
) WITH (
  'bucket' = '8',
  'bucket-key' = 'user_id'
);
```

**Note:** No PRIMARY KEY = append-only table

### Partitioned vs Unpartitioned Tables

**Partitioned Tables:**
```sql
CREATE TABLE orders (
  order_id BIGINT,
  user_id BIGINT,
  amount DECIMAL(10,2),
  order_date STRING,
  PRIMARY KEY (order_id, order_date) NOT ENFORCED
) PARTITIONED BY (order_date)
WITH (
  'bucket' = '4'
);
```

**Benefits:**
- Partition pruning for queries
- Independent compaction per partition
- Data lifecycle management (drop old partitions)

**Unpartitioned Tables:**
- Simpler for non-time-series data
- Single namespace for all data

## Creating Paimon Tables

### DDL Approach (Flink SQL)

**Basic Table:**

```sql
CREATE CATALOG paimon_catalog WITH (
  'type' = 'paimon',
  'warehouse' = 'hdfs:///paimon/warehouse'
);

USE CATALOG paimon_catalog;

CREATE DATABASE IF NOT EXISTS my_db;

CREATE TABLE my_db.users (
  user_id BIGINT,
  name STRING,
  email STRING,
  created_at TIMESTAMP(3),
  updated_at TIMESTAMP(3),
  PRIMARY KEY (user_id) NOT ENFORCED
) WITH (
  'bucket' = '4',
  'file.format' = 'parquet',
  'compaction.min.file-num' = '5',
  'compaction.max.file-num' = '10'
);
```

**With Partitioning:**

```sql
CREATE TABLE events (
  event_id STRING,
  user_id BIGINT,
  event_time TIMESTAMP(3),
  event_type STRING,
  dt STRING,
  PRIMARY KEY (event_id, dt) NOT ENFORCED
) PARTITIONED BY (dt)
WITH (
  'bucket' = '8',
  'file.format' = 'orc',
  'orc.compress' = 'zstd'
);
```

**Dynamic Bucket Table:**

```sql
CREATE TABLE logs (
  log_id STRING,
  message STRING,
  level STRING,
  timestamp TIMESTAMP(3)
) WITH (
  'bucket' = '-1',  -- Dynamic bucketing
  'dynamic-bucket.target-row-num' = '2000000',
  'dynamic-bucket.initial-buckets' = '4'
);
```

### Catalog Approaches

#### Filesystem Catalog (Default)

```sql
-- Flink SQL
CREATE CATALOG fs_catalog WITH (
  'type' = 'paimon',
  'warehouse' = 's3://bucket/warehouse'
);
```

```python
# PySpark
spark.conf.set("spark.sql.catalog.paimon", "org.apache.paimon.spark.SparkCatalog")
spark.conf.set("spark.sql.catalog.paimon.warehouse", "s3://bucket/warehouse")
```

#### Hive Metastore Catalog

```sql
-- Flink SQL
CREATE CATALOG hive_catalog WITH (
  'type' = 'paimon',
  'metastore' = 'hive',
  'uri' = 'thrift://metastore:9083',
  'warehouse' = 'hdfs:///warehouse'
);
```

```python
# PySpark
spark.conf.set("spark.sql.catalog.paimon", "org.apache.paimon.spark.SparkCatalog")
spark.conf.set("spark.sql.catalog.paimon.warehouse", "hdfs:///warehouse")
spark.conf.set("spark.sql.catalog.paimon.metastore", "hive")
spark.conf.set("spark.sql.catalog.paimon.uri", "thrift://metastore:9083")
```

## Key Operations

### Writing Streaming Data (Flink)

#### Direct Insert

```sql
-- Insert from Kafka
CREATE TABLE kafka_source (
  user_id BIGINT,
  name STRING,
  event_time TIMESTAMP(3),
  WATERMARK FOR event_time AS event_time - INTERVAL '5' SECOND
) WITH (
  'connector' = 'kafka',
  'topic' = 'users',
  'properties.bootstrap.servers' = 'kafka:9092',
  'format' = 'json',
  'scan.startup.mode' = 'latest-offset'
);

-- Stream into Paimon
INSERT INTO paimon_catalog.my_db.users
SELECT user_id, name, NULL, event_time, event_time
FROM kafka_source;
```

#### Flink DataStream API

```java
StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
StreamTableEnvironment tEnv = StreamTableEnvironment.create(env);

// Create Paimon catalog
tEnv.executeSql(
    "CREATE CATALOG paimon WITH (" +
    "'type'='paimon'," +
    "'warehouse'='hdfs:///warehouse'" +
    ")"
);

// Use catalog
tEnv.useCatalog("paimon");

// Write DataStream to Paimon
DataStream<Row> dataStream = ...;
Table table = tEnv.fromDataStream(dataStream);
table.executeInsert("my_table");
```

#### UPSERT Pattern

```sql
-- Primary key table automatically handles upserts
INSERT INTO users (user_id, name, email, updated_at)
VALUES (1, 'Alice', 'alice@example.com', CURRENT_TIMESTAMP);

-- Later update (same user_id)
INSERT INTO users (user_id, name, email, updated_at)
VALUES (1, 'Alice Updated', 'alice@newdomain.com', CURRENT_TIMESTAMP);

-- Result: Single record with user_id=1, latest values
```

### Reading Data

#### Batch Read (Latest Snapshot)

```sql
-- Flink SQL (batch mode)
SET 'execution.runtime-mode' = 'batch';

SELECT * FROM users WHERE age > 18;
```

```python
# Spark
df = spark.table("paimon.my_db.users")
df.filter("age > 18").show()
```

#### Streaming Read (Incremental)

```sql
-- Flink SQL (streaming mode)
SET 'execution.runtime-mode' = 'streaming';

SELECT * FROM users;
-- Reads latest snapshot first, then incremental updates
```

**Streaming Read Options:**

```sql
-- Read only incremental (skip initial snapshot)
SELECT * FROM users /*+ OPTIONS('scan.mode'='from-timestamp', 'scan.timestamp-millis'='1698019200000') */;

-- Read from specific snapshot
SELECT * FROM users /*+ OPTIONS('scan.mode'='from-snapshot', 'scan.snapshot-id'='5') */;
```

#### Time Travel (Snapshot Queries)

```sql
-- Flink SQL: Query specific snapshot
SELECT * FROM users /*+ OPTIONS('scan.snapshot-id'='10') */;

-- Query by timestamp
SELECT * FROM users /*+ OPTIONS('scan.timestamp-millis'='1698019200000') */;
```

```python
# Spark (requires Spark 3.3+)
df = spark.read \
    .format("paimon") \
    .option("snapshot-id", "10") \
    .table("paimon.my_db.users")
```

#### Incremental Read (Between Snapshots)

```sql
-- Spark SQL
SELECT * FROM paimon.my_db.incremental_table(
  start_snapshot => 5,
  end_snapshot => 10
);
```

### CDC Integration (Flink CDC)

#### MySQL CDC to Paimon

```sql
-- Create MySQL CDC source
CREATE TABLE mysql_users (
  user_id BIGINT,
  name STRING,
  email STRING,
  PRIMARY KEY (user_id) NOT ENFORCED
) WITH (
  'connector' = 'mysql-cdc',
  'hostname' = 'mysql',
  'port' = '3306',
  'username' = 'root',
  'password' = 'password',
  'database-name' = 'mydb',
  'table-name' = 'users'
);

-- Sync to Paimon (preserves CDC semantics)
INSERT INTO paimon_catalog.my_db.users
SELECT * FROM mysql_users;
```

**Flink CDC 3.5 Features (2025):**
- Full changelog to Paimon
- Append-only table support
- Schema evolution handling
- Optimized checkpoint time
- Truncate & drop table operations

#### Debezium JSON Format

```sql
CREATE TABLE kafka_cdc (
  user_id BIGINT,
  name STRING,
  email STRING
) WITH (
  'connector' = 'kafka',
  'topic' = 'dbserver1.mydb.users',
  'properties.bootstrap.servers' = 'kafka:9092',
  'format' = 'debezium-json'
);

INSERT INTO paimon_catalog.my_db.users
SELECT * FROM kafka_cdc;
```

## Streaming Features

### Streaming Reads and Writes

**Streaming Write:**
```sql
SET 'execution.runtime-mode' = 'streaming';
SET 'execution.checkpointing.interval' = '1min';

-- Continuous streaming insert
INSERT INTO paimon_table
SELECT * FROM kafka_source;
```

**Streaming Read:**
```sql
-- Subscribe to table changes
CREATE TEMPORARY VIEW user_changes AS
SELECT * FROM paimon_table;

-- Process incremental updates
INSERT INTO downstream_sink
SELECT * FROM user_changes;
```

### Lookup Joins

Paimon supports **lookup joins** (dimensional joins) with Flink:

```sql
-- Fact stream
CREATE TABLE orders_stream (
  order_id BIGINT,
  user_id BIGINT,
  amount DECIMAL(10,2),
  order_time TIMESTAMP(3),
  WATERMARK FOR order_time AS order_time - INTERVAL '5' SECOND
) WITH (
  'connector' = 'kafka',
  ...
);

-- Dimension table (Paimon)
CREATE TABLE users (
  user_id BIGINT,
  name STRING,
  email STRING,
  PRIMARY KEY (user_id) NOT ENFORCED
) WITH (
  'bucket' = '4'
);

-- Lookup join (enrichment)
SELECT
  o.order_id,
  o.user_id,
  u.name,
  u.email,
  o.amount,
  o.order_time
FROM orders_stream o
LEFT JOIN users FOR SYSTEM_TIME AS OF o.order_time AS u
  ON o.user_id = u.user_id;
```

**Performance Tips:**
- Flink 2.0 significantly improved lookup join performance
- **In-memory cache** (new in 1.2+): Set `'lookup.cache' = 'memory'` instead of the default RocksDB cache for faster lookups when dimension tables fit in memory

### Compaction in Streaming Mode

**Asynchronous Compaction:**

```sql
CREATE TABLE events (
  event_id STRING,
  data STRING,
  event_time TIMESTAMP(3)
) WITH (
  'compaction.min.file-num' = '5',
  'compaction.max.file-num' = '10',
  'compaction.optimization-interval' = '1h'
);
```

**Dedicated Compaction Job:**

```sql
-- Run separate compaction job (recommended for production)
INSERT OVERWRITE events /*+ OPTIONS('compaction.optimization-interval'='30min') */
SELECT * FROM events;
```

**Compaction Modes:**
- **Full Compaction**: Merge all levels when incremental data exceeds threshold
- **Lookup Compaction**: Aggressive strategy for lookup changelog producers
- **Incremental Compaction**: Merge only necessary sorted runs

### Watermark and Late Data Handling

```sql
CREATE TABLE events (
  event_id STRING,
  user_id BIGINT,
  event_time TIMESTAMP(3),
  dt STRING,
  WATERMARK FOR event_time AS event_time - INTERVAL '1' HOUR,
  PRIMARY KEY (event_id, dt) NOT ENFORCED
) PARTITIONED BY (dt)
WITH (
  'bucket' = '8',
  'scan.watermark.alignment.group' = 'event_alignment',
  'scan.watermark.idle-timeout' = '5min'
);
```

**Late Data:**
- Paimon supports out-of-order writes
- Compaction eventually merges late data
- Use watermarks to handle late arrivals

## Bucket Configuration Strategies

### Fixed Bucket Mode

```sql
CREATE TABLE users (
  user_id BIGINT,
  name STRING,
  PRIMARY KEY (user_id) NOT ENFORCED
) WITH (
  'bucket' = '8',
  'bucket-key' = 'user_id'
);
```

**Bucket Calculation:**
```
bucket = Math.abs(hash(bucket-key) % num_buckets)
```

**Guidelines:**
- **Too many buckets** → Too many small files
- **Too few buckets** → Poor parallelism, large files
- **Rule of thumb**: 1-2 buckets per CPU core
- **Typical range**: 4-32 buckets

### Dynamic Bucket Mode

```sql
CREATE TABLE logs (
  log_id STRING,
  message STRING
) WITH (
  'bucket' = '-1',
  'dynamic-bucket.target-row-num' = '2000000',
  'dynamic-bucket.initial-buckets' = '4'
);
```

**When to Use:**
- Unknown data volume
- Gradually growing tables
- Avoid over-provisioning buckets

**Limitation:** ⚠️ **Single writer only** - Do not run multiple jobs writing to same partition.

### Bucket-Key Selection

**Good bucket keys:**
- High cardinality (user_id, device_id)
- Even distribution
- Frequently used in queries

**Bad bucket keys:**
- Low cardinality (country, status)
- Skewed distribution
- Timestamp fields

**Example:**

```sql
-- Good: High cardinality, even distribution
CREATE TABLE events (...) WITH ('bucket' = '16', 'bucket-key' = 'user_id');

-- Bad: Low cardinality, skewed
CREATE TABLE events (...) WITH ('bucket' = '16', 'bucket-key' = 'country');
```

## Integration Patterns

### Flink SQL

**Complete Example:**

```sql
-- 1. Create catalog
CREATE CATALOG paimon WITH (
  'type' = 'paimon',
  'warehouse' = 'hdfs:///warehouse'
);

USE CATALOG paimon;
CREATE DATABASE analytics;

-- 2. Create Paimon table
CREATE TABLE analytics.user_activity (
  user_id BIGINT,
  activity_type STRING,
  activity_time TIMESTAMP(3),
  metadata STRING,
  dt STRING,
  PRIMARY KEY (user_id, dt) NOT ENFORCED
) PARTITIONED BY (dt)
WITH (
  'bucket' = '8',
  'changelog-producer' = 'lookup'
);

-- 3. Create Kafka source
CREATE CATALOG default_catalog WITH ('type' = 'generic_in_memory');
USE CATALOG default_catalog;

CREATE TABLE kafka_activity (
  user_id BIGINT,
  activity_type STRING,
  activity_time TIMESTAMP(3),
  metadata STRING,
  WATERMARK FOR activity_time AS activity_time - INTERVAL '5' SECOND
) WITH (
  'connector' = 'kafka',
  'topic' = 'user_activity',
  'properties.bootstrap.servers' = 'kafka:9092',
  'format' = 'json'
);

-- 4. Stream Kafka → Paimon
INSERT INTO paimon.analytics.user_activity
SELECT
  user_id,
  activity_type,
  activity_time,
  metadata,
  DATE_FORMAT(activity_time, 'yyyy-MM-dd') as dt
FROM kafka_activity;
```

### Flink DataStream API

```java
import org.apache.paimon.flink.FlinkCatalogFactory;
import org.apache.paimon.catalog.Catalog;
import org.apache.paimon.table.Table;

StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
StreamTableEnvironment tEnv = StreamTableEnvironment.create(env);

// Create Paimon catalog
Catalog catalog = FlinkCatalogFactory.createCatalog(
    "paimon",
    Collections.singletonMap("warehouse", "hdfs:///warehouse"),
    new Configuration(),
    Thread.currentThread().getContextClassLoader()
);

// Register catalog
tEnv.registerCatalog("paimon", new FlinkCatalog(catalog));
tEnv.useCatalog("paimon");

// DataStream operations
DataStream<RowData> stream = ...;
Table table = tEnv.fromDataStream(stream, $("user_id"), $("name"), $("timestamp"));
table.executeInsert("users");
```

### Spark Integration

**Batch Queries:**

```python
# Configure Spark
spark = SparkSession.builder \
    .appName("Paimon Batch") \
    .config("spark.sql.catalog.paimon", "org.apache.paimon.spark.SparkCatalog") \
    .config("spark.sql.catalog.paimon.warehouse", "hdfs:///warehouse") \
    .getOrCreate()

# Read Paimon table
df = spark.table("paimon.analytics.user_activity")

# Query
result = df.filter("dt = '2025-10-19'") \
    .groupBy("activity_type") \
    .count()

result.show()
```

**Time Travel:**

```python
# Read specific snapshot
df = spark.read \
    .format("paimon") \
    .option("snapshot-id", "15") \
    .table("paimon.analytics.users")
```

**Incremental Query:**

```sql
-- Spark SQL
SELECT * FROM paimon.analytics.incremental_users(
  start_snapshot => 10,
  end_snapshot => 20
);
```

### Catalog Implementations

**Filesystem Catalog:**
```yaml
type: paimon
warehouse: s3://bucket/warehouse
```

**Hive Metastore:**
```yaml
type: paimon
metastore: hive
uri: thrift://metastore:9083
warehouse: hdfs:///warehouse
```

**JDBC Catalog:**
```yaml
type: paimon
metastore: jdbc
uri: jdbc:mysql://mysql:3306/paimon_catalog
jdbc.user: paimon
jdbc.password: password
```

## Iceberg Compatibility

Paimon can expose tables as Iceberg-compatible, allowing engines like Trino, Presto, Doris, and StarRocks to read Paimon data through Iceberg readers — no Paimon-specific connector needed.

### How It Works

When enabled, Paimon generates Iceberg-compatible metadata alongside its own metadata on every commit. Downstream Iceberg readers see a standard Iceberg table.

### Storage Modes

**Hadoop Catalog (recommended for SQL users):**

```sql
CREATE TABLE users (
  user_id BIGINT,
  name STRING,
  PRIMARY KEY (user_id) NOT ENFORCED
) WITH (
  'bucket' = '4',
  'metadata.iceberg.storage' = 'hadoop-catalog'
);
```

**Hive Catalog:**

```sql
CREATE TABLE users (...) WITH (
  'metadata.iceberg.storage' = 'hive-catalog'
);
```

**REST Catalog (for Iceberg REST catalog services like Polaris):**

```sql
CREATE TABLE users (...) WITH (
  'metadata.iceberg.storage' = 'rest-catalog',
  'metadata.iceberg.rest.uri' = 'http://polaris:8181/api/v1'
);
```

**Table Location (for Java API users):**

```sql
CREATE TABLE users (...) WITH (
  'metadata.iceberg.storage' = 'table-location'
);
```

### Iceberg-Compatible Deletion Vectors

```sql
CREATE TABLE users (...) WITH (
  'delete-vectors.bitmap64' = 'true',  -- Iceberg-compatible deletion vectors
  'metadata.iceberg.storage' = 'hadoop-catalog'
);
```

### Tag Synchronization

When a Paimon Tag is created or deleted, the corresponding Iceberg metadata is also updated. This keeps Paimon and Iceberg views consistent.

### Metadata Compaction

```sql
CREATE TABLE users (...) WITH (
  'metadata.iceberg.compaction.min.file-num' = '10',
  'metadata.iceberg.compaction.max.file-num' = '50'
);
```

### Important Notes

- Iceberg compatibility must be set at `CREATE TABLE` time — `ALTER TABLE` cannot enable it after the fact
- Requires `paimon-iceberg` jar and JDK 11+
- Read-only from the Iceberg side: writes must go through Paimon

## Data Evolution Mode

Data Evolution Mode is a feature for **append tables** that allows partial column updates without rewriting entire data files. New column data is written to separate files and merged during reads.

### Why This Matters

- **Schema changes without file rewrites**: Adding columns to large append tables no longer means rewriting terabytes of data
- **Efficient partial updates**: Update a subset of columns via Spark `MERGE INTO` — only changed columns are written
- **Unchanged read performance**: The merge during reads is highly optimized

### Enabling Data Evolution

```sql
-- Spark SQL
CREATE TABLE target_table (id INT, b INT, c INT)
TBLPROPERTIES (
  'row-tracking.enabled' = 'true',
  'data-evolution.enabled' = 'true'
);
```

### Partial Column Update

```sql
-- Only updates columns 'b' and 'c', leaving other columns untouched
-- Does NOT rewrite original data files
MERGE INTO target_table t
USING source_table s
ON t.id = s.id
WHEN MATCHED THEN UPDATE SET t.b = s.b, t.c = s.c;
```

### Blob Storage for Multimodal Data

Leveraging Data Evolution mode, Paimon supports **blob columns** for storing large binary data (images, audio, video). Blob columns are split out and managed separately with decoupled compaction, making Paimon usable for AI and multimodal workloads.

### Current Limitations

- Only Spark's `MERGE INTO` is supported for partial column updates (Flink support planned)
- Requires `row-tracking.enabled = true`

## PyPaimon (Python SDK)

PyPaimon is a **pure Python** implementation for reading and writing Paimon tables — no JDK installation required.

### Installation

```bash
pip install pypaimon
```

### Catalog and Table Operations

```python
from pypaimon import Catalog

# Create filesystem catalog
catalog = Catalog.create({'warehouse': 's3://bucket/warehouse'})

# Get table
table = catalog.get_table('my_db.users')
```

### Reading Data

```python
# Read as PyArrow Table
read_builder = table.new_read_builder()
splits = read_builder.new_scan().plan().splits()
reader = read_builder.new_read()
arrow_table = reader.to_arrow(splits)

# Convert to Pandas
df = arrow_table.to_pandas()
```

### Incremental Reads

```python
# Read records between snapshots
from pypaimon import SnapshotManager

snapshot_mgr = SnapshotManager(table)
# Read incrementally between timestamps
incremental_splits = read_builder \
    .with_incremental_between(start_timestamp, end_timestamp) \
    .new_scan().plan().splits()
```

### Writing Data

```python
# Batch write with two-phase commit
write_builder = table.new_batch_write_builder()
writer = write_builder.new_write()
committer = write_builder.new_commit()

writer.write_arrow(arrow_table)
committables = writer.prepare_commit()
committer.commit(committables)

writer.close()
committer.close()
```

### Partition Overwrite

```python
# Overwrite specific partitions
write_builder = table.new_batch_write_builder() \
    .overwrite({'dt': '2025-10-19'})
```

### Data Evolution Support

```python
# Update columns in data evolution tables
table_update = table.new_table_update()
table_update.update_by_arrow_with_row_id(arrow_table)
```

### Supported Catalogs

- Filesystem catalog (default)
- REST catalog
- JDBC catalog (via py4j fallback)
- Hive Metastore (via py4j fallback)

## Performance & Maintenance

### Compaction Strategies

**Full Compaction:**

```sql
-- Trigger full compaction
CALL sys.compact('my_db.users');

-- Partition-specific
CALL sys.compact('my_db.users', 'dt=2025-10-19');
```

**Configuration:**

```sql
CREATE TABLE users (...) WITH (
  -- Compaction trigger
  'compaction.min.file-num' = '5',
  'compaction.max.file-num' = '10',

  -- Full compaction threshold
  'full-compaction.delta-commits' = '10',

  -- Optimization interval
  'compaction.optimization-interval' = '1h'
);
```

**Incremental vs Full:**
- **Incremental**: Merge small runs continuously
- **Full**: Merge all levels when delta exceeds threshold
- **Tradeoff**: Incremental = faster writes, Full = better reads

### File Formats and Compression

**Supported Formats:**
- **Parquet** (default, recommended)
- **ORC**
- **Avro**

**Per-Level Format:**

```sql
CREATE TABLE events (...) WITH (
  'file.format' = 'parquet',
  'file.format.per.level' = '0:avro,1:avro',  -- L0/L1 use Avro, rest Parquet
  'file.compression' = 'zstd',
  'file.compression.zstd-level' = '3'
);
```

**Compression Codecs:**
- **zstd** (default, level 1): Best balance
- **snappy**: Fastest
- **gzip**: Smaller files
- **lz4**: Fast decompression

### Snapshot Expiration

**Automatic Expiration:**

```sql
CREATE TABLE users (...) WITH (
  'snapshot.num-retained.min' = '10',
  'snapshot.num-retained.max' = '50',
  'snapshot.time-retained' = '1h'
);
```

**Manual Expiration:**

```sql
CALL sys.expire_snapshots('my_db.users', '2025-10-19 00:00:00');
```

**Async Expiration:**

```sql
CREATE TABLE users (...) WITH (
  'snapshot.expire.execution-mode' = 'async'
);
```

**Caution:** Don't use async mode for batch jobs (may not complete).

### Tag Management

**Automatic Tag Creation:**

```sql
CREATE TABLE users (...) WITH (
  'tag.automatic-creation' = 'process-time',  -- or 'watermark', 'batch'
  'tag.creation-period' = 'daily',            -- daily, hourly, two-hours
  'tag.num-retained-max' = '30'
);
```

**Manual Tags:**

```sql
-- Create tag
CALL sys.create_tag('my_db.users', 'prod_v1', 15);  -- Tag snapshot 15

-- Delete tag
CALL sys.delete_tag('my_db.users', 'prod_v1');

-- Rollback to tag
CALL sys.rollback_to('my_db.users', 'prod_v1');
```

**Tag Benefits:**
- Prevent snapshot expiration
- Version control for data
- Safe rollback points

## Common Patterns

### Real-Time Data Ingestion

**Pattern: Kafka → Flink → Paimon**

```sql
-- Source: Kafka
CREATE TABLE kafka_events (
  event_id STRING,
  user_id BIGINT,
  event_type STRING,
  event_time TIMESTAMP(3),
  payload STRING,
  WATERMARK FOR event_time AS event_time - INTERVAL '10' SECOND
) WITH (
  'connector' = 'kafka',
  'topic' = 'events',
  'properties.bootstrap.servers' = 'kafka:9092',
  'scan.startup.mode' = 'latest-offset',
  'format' = 'json'
);

-- Sink: Paimon
CREATE TABLE paimon_events (
  event_id STRING,
  user_id BIGINT,
  event_type STRING,
  event_time TIMESTAMP(3),
  payload STRING,
  dt STRING,
  PRIMARY KEY (event_id, dt) NOT ENFORCED
) PARTITIONED BY (dt)
WITH (
  'bucket' = '16',
  'changelog-producer' = 'input'
);

-- Pipeline
INSERT INTO paimon_events
SELECT
  event_id,
  user_id,
  event_type,
  event_time,
  payload,
  DATE_FORMAT(event_time, 'yyyy-MM-dd') as dt
FROM kafka_events;
```

### Batch + Streaming Hybrid

**Pattern: Historical batch load + Streaming updates**

```sql
-- 1. Batch load historical data
SET 'execution.runtime-mode' = 'batch';

INSERT OVERWRITE paimon_users PARTITION (dt='2025-10-01')
SELECT * FROM parquet_users WHERE dt = '2025-10-01';

-- 2. Switch to streaming for incremental updates
SET 'execution.runtime-mode' = 'streaming';

INSERT INTO paimon_users
SELECT * FROM kafka_users;
```

### Slowly Changing Dimensions (SCD)

**SCD Type 2 (Track History):**

```sql
CREATE TABLE dim_users (
  user_id BIGINT,
  name STRING,
  email STRING,
  valid_from TIMESTAMP(3),
  valid_to TIMESTAMP(3),
  is_current BOOLEAN,
  PRIMARY KEY (user_id, valid_from) NOT ENFORCED
) WITH (
  'merge-engine' = 'deduplicate'
);

-- Insert new version (downstream logic tracks history)
INSERT INTO dim_users
SELECT
  user_id,
  name,
  email,
  CURRENT_TIMESTAMP as valid_from,
  CAST(NULL AS TIMESTAMP(3)) as valid_to,
  TRUE as is_current
FROM user_updates;
```

**SCD Type 1 (Overwrite):**

```sql
CREATE TABLE dim_products (
  product_id BIGINT,
  product_name STRING,
  category STRING,
  price DECIMAL(10,2),
  PRIMARY KEY (product_id) NOT ENFORCED
) WITH (
  'merge-engine' = 'deduplicate'  -- Latest record wins
);

-- Upserts automatically update
INSERT INTO dim_products
SELECT * FROM product_updates;
```

### Streaming Joins

**Dual-Stream Join:**

```sql
-- Stream 1: Orders
CREATE TABLE orders_stream (...);

-- Stream 2: Payments
CREATE TABLE payments_stream (...);

-- Join streams (both in memory)
SELECT
  o.order_id,
  o.user_id,
  p.payment_id,
  p.amount
FROM orders_stream o
JOIN payments_stream p
  ON o.order_id = p.order_id
WHERE o.event_time BETWEEN p.event_time - INTERVAL '5' MINUTE
  AND p.event_time + INTERVAL '5' MINUTE;
```

**Lookup Join (Stream + Dimension):**

```sql
-- Stream: Orders
CREATE TABLE orders_stream (...);

-- Dimension: Users (Paimon)
CREATE TABLE users (...);

-- Enrich stream with dimension
SELECT
  o.order_id,
  o.user_id,
  u.name,
  u.tier,
  o.amount
FROM orders_stream o
LEFT JOIN users FOR SYSTEM_TIME AS OF o.event_time AS u
  ON o.user_id = u.user_id;
```

## Best Practices

### 1. Choose Right Table Type

**Primary Key Table:**
- Dimension tables
- Mutable data (user profiles, product catalog)
- CDC from databases
- Need updates/deletes

**Append-Only Table:**
- Fact tables (logs, events)
- Immutable data
- No updates needed
- Lower overhead (no compaction)

### 2. Bucket Configuration

**Guidelines:**
- Start with `bucket = num_cores * 2`
- Use dynamic bucketing for unpredictable volume
- High-cardinality bucket keys (user_id, device_id)
- Avoid low-cardinality keys (status, country)

**Example:**
```sql
-- 8-core cluster → 16 buckets
CREATE TABLE events (...) WITH ('bucket' = '16', 'bucket-key' = 'user_id');
```

### 3. Compaction Tuning

**Streaming Workloads:**
- Enable async compaction
- Run dedicated compaction job
- Lower `compaction.min.file-num` (e.g., 3-5)

**Batch Workloads:**
- Higher thresholds (10-20 files)
- Periodic full compaction

**Configuration:**
```sql
CREATE TABLE events (...) WITH (
  'compaction.min.file-num' = '5',
  'compaction.max.file-num' = '20',
  'full-compaction.delta-commits' = '10'
);
```

### 4. Partition Strategy

**Time-Based Partitioning:**
- Daily: Most common (`PARTITIONED BY (dt)`)
- Hourly: High-volume streams
- Monthly: Low-volume, long retention

**Guidelines:**
- Partition by query filters
- Balance partition count (not too many)
- Drop old partitions for lifecycle management

### 5. Changelog Production

**Choose Right Producer:**
- **`none`**: Append-only tables, no changelog needed
- **`input`**: Pass-through CDC from Kafka/MySQL
- **`lookup`**: Need full changelog, primary key table
- **`full-compaction`**: Full changelog via compaction (heavy)

**Example:**
```sql
-- CDC ingestion
CREATE TABLE users (...) WITH ('changelog-producer' = 'input');

-- Downstream needs full changelog
CREATE TABLE users (...) WITH ('changelog-producer' = 'lookup');
```

### 6. Monitoring & Observability

**Check Snapshot Count:**
```sql
SELECT COUNT(*) FROM `paimon_table$snapshots`;
```

**Check File Count:**
```sql
SELECT COUNT(*) FROM `paimon_table$files`;
```

**Analyze Compaction:**
```sql
SELECT level, COUNT(*) as file_count, SUM(file_size_in_bytes) / 1024 / 1024 as total_mb
FROM `paimon_table$files`
GROUP BY level;
```

### 7. Write Performance

**Optimize Checkpointing:**
```yaml
execution.checkpointing.interval: 1min
execution.checkpointing.mode: EXACTLY_ONCE
state.backend: rocksdb
state.backend.incremental: true
```

**Parallelism:**
- Write parallelism = number of buckets
- Set Flink parallelism ≥ bucket count

**Example:**
```yaml
# 16 buckets → 16 parallelism
parallelism.default: 16
```

## Quick Reference

### Essential SQL Commands

```sql
-- Create catalog
CREATE CATALOG paimon WITH ('type'='paimon', 'warehouse'='hdfs:///warehouse');

-- Create table
CREATE TABLE users (user_id BIGINT, name STRING, PRIMARY KEY (user_id) NOT ENFORCED)
WITH ('bucket'='8');

-- Write
INSERT INTO users VALUES (1, 'Alice');

-- Read (batch)
SET 'execution.runtime-mode' = 'batch';
SELECT * FROM users;

-- Read (streaming)
SET 'execution.runtime-mode' = 'streaming';
SELECT * FROM users;

-- Time travel
SELECT * FROM users /*+ OPTIONS('scan.snapshot-id'='10') */;

-- Compaction
CALL sys.compact('db.users');

-- Snapshot management
CALL sys.expire_snapshots('db.users', '2025-10-19 00:00:00');

-- Tag management
CALL sys.create_tag('db.users', 'v1', 15);
```

### Common Table Options

```sql
-- Bucket configuration
'bucket' = '8'
'bucket' = '-1'  -- Dynamic
'bucket-key' = 'user_id'

-- File format
'file.format' = 'parquet'
'file.compression' = 'zstd'

-- Compaction
'compaction.min.file-num' = '5'
'compaction.max.file-num' = '10'
'full-compaction.delta-commits' = '10'

-- Changelog
'changelog-producer' = 'lookup'  -- or 'input', 'none', 'full-compaction'

-- Snapshot retention
'snapshot.num-retained.min' = '10'
'snapshot.num-retained.max' = '50'
'snapshot.time-retained' = '1h'

-- Merge engine
'merge-engine' = 'deduplicate'  -- or 'partial-update', 'aggregation'
```

### Flink Configuration

```yaml
# Checkpointing
execution.checkpointing.interval: 1min
execution.checkpointing.mode: EXACTLY_ONCE

# State backend
state.backend: rocksdb
state.backend.incremental: true

# Parallelism
parallelism.default: 16

# Runtime mode
execution.runtime-mode: streaming  # or batch
```

### Performance Checklist

- ✅ Use appropriate bucket count (1-2x cores)
- ✅ Choose high-cardinality bucket keys
- ✅ Enable async compaction for streaming
- ✅ Partition by query filter columns
- ✅ Set checkpoint interval (1-5 min)
- ✅ Expire old snapshots regularly
- ✅ Use tags for important versions
- ✅ Monitor file count per level
- ✅ Use Parquet with zstd compression
- ✅ Match Flink parallelism to buckets

---

When helping users with Apache Paimon:
1. **Emphasize streaming-first** - Paimon is designed for Flink streaming
2. **Bucket configuration is critical** - Wrong buckets = poor performance
3. **Understand LSM tree** - Compaction is key to query performance
4. **Leverage CDC integration** - Flink CDC 3.x has excellent Paimon support
5. **Choose right table type** - Primary key vs append-only based on use case
6. **Monitor compaction** - File count and level distribution matter
7. **Use lookup joins** - Efficient dimensional enrichment, with in-memory cache for smaller tables
8. **Partition wisely** - Time-based partitioning for most use cases
9. **Tag important snapshots** - Prevent expiration of critical versions
10. **Flink 2.0 features** - Materialized tables, improved lookup joins, nested projection pushdown
11. **Iceberg compatibility** - Expose Paimon tables to Iceberg readers for broader engine support
12. **Data Evolution Mode** - Partial column updates on append tables without costly file rewrites
13. **PyPaimon for Python users** - Pure Python SDK, no JDK needed, supports Arrow and Pandas
14. **Paimon 2.0 is coming** - Vector store, blob storage, global indexes for AI/multimodal workloads
