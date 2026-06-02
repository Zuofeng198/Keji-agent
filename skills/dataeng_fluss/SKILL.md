---
name: fluss
description: Apache Fluss（孵化中）流式存储专家知识，用于实时分析和湖仓架构。涵盖低延迟数据摄入、Delta Join、Paimon/Iceberg 分层存储以及 Flink/Spark 目录集成。
---

# Apache Fluss Expert

Apache Fluss (Incubating) is a streaming storage built for real-time analytics and lakehouse architectures. This skill helps build low-latency streaming pipelines with Fluss, focusing on its columnar storage, tiered architecture, and deep Flink integration.

## Version Information

**Current Stable:** Fluss 0.9.0 (March 2, 2026)
**Previous Releases:** 0.8.0 (November 9, 2025 — first Apache release), 0.7.0 (June 2025)
**Status:** Apache Incubator (joined ASF June 2025, graduation timeline TBD)
**Recommended Flink:** Flink 1.19+, Flink 2.0+, Flink 2.2 (Delta Join support)
**Recommended Spark:** Supported from 0.9.0 (catalog, batch/stream reads and writes)
**Flink CDC:** 3.5.0+ (Fluss Pipeline Connector available)
**Java Minimum:** Java 11 (upgraded from Java 8 in 0.8.0)

**Key 0.9.0 Features (March 2026):**
- Apache Spark integration (catalog support, batch/stream unified analytics)
- Complex type support (nested ARRAY, MAP, ROW types)
- Zero-copy schema evolution (add columns without affecting existing jobs)
- Auto-increment columns for dictionary tables
- Aggregation merge engine (pushes aggregations to storage layer)
- Change Data Feed: virtual `$changelog` and `$binlog` tables for audit trails
- Compacted log format (row-oriented storage option for full-row scans)
- Dynamic sink shuffle (runtime-aware partition load balancing)
- KV snapshot lease (consumer-aware snapshot lifecycle management)
- Cluster rebalance (automatic bucket redistribution during scaling)
- Azure cloud support (Blob Storage, ADLS Gen2)
- Flink 2.2 compatibility with enhanced Delta Join support
- Java Client POJO support

**Key 0.8.0 Features (November 2025):**
- First Apache release under ASF
- Apache Iceberg tiering support (real-time ingestion with native upsert/delete)
- Lance format tiering support (AI/ML vector and embedding data)
- Built-in compaction service with optimized snapshot management
- Delta Joins with Flink (80% less CPU/memory, checkpoints reduced from 90s to 1s)
- Materialized Tables (continuously refreshed result tables with freshness targets)
- Dynamic configuration updates without restarts
- Graceful shutdown and leadership migration for rolling upgrades
- Coordinator recovery accelerated from 10 minutes to 20 seconds
- Kubernetes Helm charts for full cluster deployment
- Metrics telemetry reduced by 90%
- 35+ stability fixes validated through Alibaba Double 11 production

**Roadmap (planned):**
- ZooKeeper removal — migration to KvStore + Raft coordination
- Zero Disks Architecture — S3/cloud-native storage for serverless operation
- Python Client SDK (PyArrow/Pandas ecosystem)
- Trino and DuckDB connectors

## Core Concepts

### What is Apache Fluss?

Apache Fluss is a **streaming storage** built for **real-time analytics** that serves as the low-latency data layer in modern **Lakehouse architectures**. It combines:

- **Sub-second latency**: Streaming reads and writes
- **Columnar storage**: Apache Arrow IPC format (10x read performance vs row-based)
- **Tiered architecture**: Hot data in-memory/SSD, cold data in lakehouse (Paimon, Iceberg)
- **Unified semantics**: Both log (Kafka-like) and table (database-like) abstractions
- **Flink-native**: Purpose-built for Apache Flink integration

**Key Differentiators:**
- **Columnar-first**: Unlike Kafka (row-based), Fluss stores data in columnar format
- **Streaming + Lakehouse**: Built-in tiering to lakehouse storage (Paimon, Iceberg)
- **Real-time tables**: Primary key tables provide log + cache semantics in one system
- **Lower latency than Paimon**: Optimized for sub-second streaming, offloads to Paimon for historical data

### Unified Streaming and Lakehouse Architecture

**Fluss Architecture Layers:**

```
┌─────────────────────────────────────────────────┐
│   Query Engines (Flink, Spark, Trino)          │
├─────────────────────────────────────────────────┤
│   Fluss Server (Hot Data - Real-time)          │
│   - In-memory/SSD                               │
│   - Sub-second latency                          │
│   - Columnar Arrow IPC                          │
├─────────────────────────────────────────────────┤
│   Tiering Service                               │
│   (Policy-driven data pipeline)                 │
├─────────────────────────────────────────────────┤
│   Lakehouse Storage (Cold Data)                 │
│   - Paimon / Iceberg                            │
│   - Object storage (S3, HDFS)                   │
│   - Historical analytics                        │
└─────────────────────────────────────────────────┘
```

**Data Flow:**
1. **Write**: Real-time data → Fluss server (hot storage)
2. **Tier**: Tiering service → Continuously moves data to lakehouse
3. **Read**: Query engines read hot (Fluss) + cold (lakehouse) seamlessly

**Benefits:**
- Fresh data (minutes old) in Fluss for low-latency queries
- Historical data tiered to cheap lakehouse storage
- Unified queries across hot and cold data
- Cost-efficient storage (hot data small, cold data large)

### Coordination Architecture

**Cluster Components:**

1. **CoordinatorServer**
   - Similar to KRaft in Kafka
   - Manages cluster metadata
   - Assigns replicas and tablets
   - Manages tiering state
   - Currently uses ZooKeeper (moving to KvStore + Raft)

2. **TabletServer**
   - Stores data tablets (buckets)
   - Handles read/write operations
   - Manages replication
   - Executes compaction

**Coordination:**
- ZooKeeper (current): Cluster coordination, metadata storage, config management
- Future (roadmap): KvStore for metadata, Raft for coordination and consistency

### Log and Table Abstraction

**Log Tables:**
- Append-only event log (Kafka-like)
- Ordered by arrival time
- Supports partitioning and bucketing
- Tiering to lakehouse

**Primary Key Tables:**
- Mutable keyed tables (database-like)
- Support INSERT, UPDATE, DELETE
- Emit changelog streams
- Unify log + cache in single system

**Unified Semantics:**
Both table types provide streaming and batch query interfaces through Flink.

## Table Types

### Log Tables (Append-Only)

**Characteristics:**
- Append-only, no updates or deletes
- Stored in columnar Apache Arrow IPC format
- Kafka-like semantics with sub-second latency
- Support tiering to lakehouse storage
- Ideal for: Event logs, clickstreams, sensor data

**Create Log Table:**

```sql
-- Flink SQL
CREATE TABLE events (
  event_id STRING,
  user_id BIGINT,
  event_type STRING,
  event_time TIMESTAMP(3),
  payload STRING
) WITH (
  'connector' = 'fluss',
  'bootstrap.servers' = 'fluss-server:9123',
  'bucket.num' = '8'
);
```

**With Partitioning:**

```sql
CREATE TABLE events (
  event_id STRING,
  user_id BIGINT,
  event_type STRING,
  event_time TIMESTAMP(3),
  payload STRING,
  dt STRING
) PARTITIONED BY (dt)
WITH (
  'connector' = 'fluss',
  'bootstrap.servers' = 'fluss-server:9123',
  'bucket.num' = '4'
);
```

**Auto-Partitioning:**

```sql
CREATE TABLE events (
  event_id STRING,
  event_time TIMESTAMP(3),
  data STRING
) WITH (
  'connector' = 'fluss',
  'bootstrap.servers' = 'fluss-server:9123',
  'bucket.num' = '8',
  'table.auto-partition.enabled' = 'true',
  'table.auto-partition.time-unit' = 'day'  -- or 'hour'
);
```

### Primary Key Tables (Mutable)

**Characteristics:**
- Primary key uniqueness enforced
- Support INSERT, UPDATE, DELETE
- Emit changelogs (+I, -U, +U, -D)
- Combine log + cache semantics
- Ideal for: Dimension tables, CDC, mutable state

**Create Primary Key Table:**

```sql
CREATE TABLE users (
  user_id BIGINT,
  name STRING,
  email STRING,
  age INT,
  updated_at TIMESTAMP(3),
  PRIMARY KEY (user_id) NOT ENFORCED
) WITH (
  'connector' = 'fluss',
  'bootstrap.servers' = 'fluss-server:9123',
  'bucket.num' = '4'
);
```

**Partitioned Primary Key Table:**

```sql
CREATE TABLE orders (
  order_id BIGINT,
  user_id BIGINT,
  amount DECIMAL(10,2),
  status STRING,
  order_date STRING,
  PRIMARY KEY (order_id, order_date) NOT ENFORCED
) PARTITIONED BY (order_date)
WITH (
  'connector' = 'fluss',
  'bootstrap.servers' = 'fluss-server:9123',
  'bucket.num' = '8'
);
```

**Composite Primary Key:**

```sql
CREATE TABLE user_sessions (
  user_id BIGINT,
  session_id STRING,
  start_time TIMESTAMP(3),
  end_time TIMESTAMP(3),
  PRIMARY KEY (user_id, session_id) NOT ENFORCED
) WITH (
  'connector' = 'fluss',
  'bootstrap.servers' = 'fluss-server:9123',
  'bucket.num' = '16'
);
```

### Bucket Configuration

**Bucket** = unit of parallelism for reads and writes

**Within each partition:**
```
partition/
  bucket-0/  (replicated log tablet)
  bucket-1/
  bucket-2/
  ...
```

**Bucket Configuration:**

```sql
CREATE TABLE events (...) WITH (
  'bucket.num' = '8'  -- 8 buckets = 8 parallel readers/writers
);
```

**Guidelines:**
- **Too few buckets**: Limited parallelism, hot spots
- **Too many buckets**: Overhead, small files
- **Rule of thumb**: 1-2 buckets per CPU core
- **Typical range**: 4-32 buckets

**Same-Tablet Colocation:**
- `LogTablets` and `KvTablets` with same `tablet_id` allocated to same `TabletServer`
- Enables efficient local state access

## Creating Fluss Tables

### Using Fluss Catalog

```sql
-- Create Fluss catalog
CREATE CATALOG fluss_catalog WITH (
  'type' = 'fluss',
  'bootstrap.servers' = 'fluss-server:9123'
);

USE CATALOG fluss_catalog;

-- Create database
CREATE DATABASE IF NOT EXISTS analytics;

-- Create table
CREATE TABLE analytics.events (
  event_id STRING,
  user_id BIGINT,
  event_time TIMESTAMP(3),
  data STRING
) WITH (
  'bucket.num' = '8'
);
```

### Inline Connector (No Catalog)

```sql
-- Create table with inline connector
CREATE TABLE events (
  event_id STRING,
  user_id BIGINT,
  event_time TIMESTAMP(3),
  data STRING
) WITH (
  'connector' = 'fluss',
  'bootstrap.servers' = 'fluss-server:9123',
  'table.name' = 'events',
  'bucket.num' = '8'
);
```

### Advanced Configuration

```sql
CREATE TABLE events (
  event_id STRING,
  user_id BIGINT,
  event_time TIMESTAMP(3),
  payload STRING,
  dt STRING
) PARTITIONED BY (dt)
WITH (
  'connector' = 'fluss',
  'bootstrap.servers' = 'fluss-server:9123',
  'bucket.num' = '16',

  -- Tiering configuration
  'table.datalake.enabled' = 'true',
  'table.datalake.format' = 'paimon',  -- or 'iceberg'

  -- Auto-partitioning
  'table.auto-partition.enabled' = 'true',
  'table.auto-partition.time-unit' = 'day',

  -- Replication
  'table.replication-factor' = '3',

  -- Log retention (before tiering)
  'log.retention.hours' = '24'
);
```

## Key Operations

### Writing Streaming Data

#### Append to Log Table

```sql
-- From Kafka to Fluss
CREATE TABLE kafka_source (
  event_id STRING,
  user_id BIGINT,
  event_time TIMESTAMP(3),
  data STRING
) WITH (
  'connector' = 'kafka',
  'topic' = 'events',
  'properties.bootstrap.servers' = 'kafka:9092',
  'format' = 'json'
);

CREATE TABLE fluss_events (...) WITH ('connector' = 'fluss', ...);

-- Stream Kafka → Fluss
INSERT INTO fluss_events
SELECT * FROM kafka_source;
```

#### Upsert to Primary Key Table

```sql
-- CDC from MySQL to Fluss
CREATE TABLE mysql_users (
  user_id BIGINT,
  name STRING,
  email STRING,
  PRIMARY KEY (user_id) NOT ENFORCED
) WITH (
  'connector' = 'mysql-cdc',
  'hostname' = 'mysql',
  'database-name' = 'mydb',
  'table-name' = 'users'
);

CREATE TABLE fluss_users (
  user_id BIGINT,
  name STRING,
  email STRING,
  PRIMARY KEY (user_id) NOT ENFORCED
) WITH (
  'connector' = 'fluss',
  'bootstrap.servers' = 'fluss-server:9123',
  'bucket.num' = '4'
);

-- Stream CDC → Fluss (upserts/deletes handled automatically)
INSERT INTO fluss_users
SELECT * FROM mysql_users;
```

### Reading Data

#### Streaming Read (Latest + Incremental)

```sql
-- Read from Fluss in streaming mode
SET 'execution.runtime-mode' = 'streaming';

SELECT * FROM fluss_events;
-- Reads latest snapshot, then subscribes to incremental updates
```

#### Batch Read (Latest Snapshot)

```sql
-- Read latest snapshot in batch mode
SET 'execution.runtime-mode' = 'batch';

SELECT * FROM fluss_events
WHERE event_date = '2025-10-19';
```

#### Lookup Join (Dimension Enrichment)

```sql
-- Fact stream
CREATE TABLE orders_stream (...);

-- Dimension table (Fluss Primary Key Table)
CREATE TABLE users (...) WITH ('connector' = 'fluss', ...);

-- Enrich stream with dimension
SELECT
  o.order_id,
  o.user_id,
  u.name,
  u.email,
  o.amount
FROM orders_stream o
LEFT JOIN users FOR SYSTEM_TIME AS OF o.order_time AS u
  ON o.user_id = u.user_id;
```

### Time Travel and Snapshot Queries

Fluss supports querying historical snapshots (similar to Kafka log compaction + time-based reads):

```sql
-- Query specific snapshot (if snapshots are retained)
SELECT * FROM fluss_events /*+ OPTIONS('scan.snapshot-id'='12345') */;

-- Query by timestamp
SELECT * FROM fluss_events /*+ OPTIONS('scan.timestamp-millis'='1698019200000') */;
```

**Note:** Time travel depends on snapshot retention configuration and tiering policy.

### Compaction for Primary Key Tables

Primary key tables use compaction to merge updates and maintain latest state:

**Automatic Compaction:**
- Triggered based on log size and time
- Merges records with same primary key
- Keeps latest version

**Compaction Configuration:**

```sql
CREATE TABLE users (...) WITH (
  'connector' = 'fluss',
  'bootstrap.servers' = 'fluss-server:9123',
  'bucket.num' = '4',
  'log.compaction.enabled' = 'true',
  'log.compaction.interval.ms' = '60000',  -- 1 minute
  'log.segment.bytes' = '104857600'  -- 100MB segments
);
```

## Tiered Storage

### Hot/Warm/Cold Architecture

**Storage Tiers:**

1. **Hot (Fluss Server)**
   - In-memory + local SSD
   - Sub-second latency
   - Recent data (minutes to hours)
   - Columnar Arrow IPC format

2. **Cold (Lakehouse)**
   - Object storage (S3, HDFS, OSS)
   - Historical data (hours to years)
   - Paimon or Iceberg format
   - Batch analytics optimized

**Tiering Service:**
- Policy-driven data pipeline
- Automatically moves data from Fluss → Lakehouse
- Configurable tiering policies
- Transparent to query engines

### Configuring Tiering

```sql
CREATE TABLE events (
  event_id STRING,
  event_time TIMESTAMP(3),
  data STRING
) WITH (
  'connector' = 'fluss',
  'bootstrap.servers' = 'fluss-server:9123',
  'bucket.num' = '8',

  -- Enable tiering to Paimon
  'table.datalake.enabled' = 'true',
  'table.datalake.format' = 'paimon',

  -- Lakehouse storage location
  'remote.data.dir' = 's3://bucket/lakehouse/events',

  -- Tiering policy
  'log.retention.hours' = '24',  -- Keep 24h in Fluss
  'log.tiering.interval.ms' = '300000'  -- Tier every 5 minutes
);
```

**Paimon Integration:**

```yaml
# Fluss → Paimon tiering
table.datalake.enabled: true
table.datalake.format: paimon
remote.data.dir: s3://bucket/lakehouse/
```

**Iceberg Integration (0.8+):**

```yaml
# Fluss → Iceberg tiering (native upsert/delete support)
table.datalake.enabled: true
table.datalake.format: iceberg
remote.data.dir: s3://bucket/lakehouse/
```

**Lance Integration (0.8+):**

```yaml
# Fluss → Lance tiering (AI/ML vector and embedding workloads)
table.datalake.enabled: true
table.datalake.format: lance
remote.data.dir: s3://bucket/lance/
```

### Query Unified Hot + Cold Data

```sql
-- Query spans Fluss (hot) + Paimon/Iceberg (cold) automatically
SELECT user_id, COUNT(*) as event_count
FROM fluss_events
WHERE event_time >= '2025-01-01'  -- Includes both hot and cold data
GROUP BY user_id;
```

## Integration Patterns

### Flink SQL Integration

**Complete Pipeline Example:**

```sql
-- 1. Create Fluss catalog
CREATE CATALOG fluss WITH (
  'type' = 'fluss',
  'bootstrap.servers' = 'fluss-server:9123'
);

USE CATALOG fluss;
CREATE DATABASE analytics;

-- 2. Create log table (events)
CREATE TABLE analytics.events (
  event_id STRING,
  user_id BIGINT,
  event_type STRING,
  event_time TIMESTAMP(3),
  payload STRING,
  dt STRING,
  WATERMARK FOR event_time AS event_time - INTERVAL '5' SECOND
) PARTITIONED BY (dt)
WITH (
  'bucket.num' = '16',
  'table.datalake.enabled' = 'true',
  'table.datalake.format' = 'paimon'
);

-- 3. Create primary key table (users)
CREATE TABLE analytics.users (
  user_id BIGINT,
  name STRING,
  email STRING,
  tier STRING,
  updated_at TIMESTAMP(3),
  PRIMARY KEY (user_id) NOT ENFORCED
) WITH (
  'bucket.num' = '4'
);

-- 4. Create Kafka source
CREATE CATALOG default_catalog WITH ('type' = 'generic_in_memory');
USE CATALOG default_catalog;

CREATE TABLE kafka_events (
  event_id STRING,
  user_id BIGINT,
  event_type STRING,
  event_time TIMESTAMP(3),
  payload STRING,
  WATERMARK FOR event_time AS event_time - INTERVAL '5' SECOND
) WITH (
  'connector' = 'kafka',
  'topic' = 'events',
  'properties.bootstrap.servers' = 'kafka:9092',
  'format' = 'json'
);

CREATE TABLE kafka_users (
  user_id BIGINT,
  name STRING,
  email STRING,
  tier STRING
) WITH (
  'connector' = 'kafka',
  'topic' = 'users',
  'properties.bootstrap.servers' = 'kafka:9092',
  'format' = 'json'
);

-- 5. Stream Kafka → Fluss
INSERT INTO fluss.analytics.events
SELECT
  event_id,
  user_id,
  event_type,
  event_time,
  payload,
  DATE_FORMAT(event_time, 'yyyy-MM-dd') as dt
FROM kafka_events;

INSERT INTO fluss.analytics.users
SELECT
  user_id,
  name,
  email,
  tier,
  CURRENT_TIMESTAMP as updated_at
FROM kafka_users;

-- 6. Query enriched stream
SELECT
  e.event_id,
  e.user_id,
  u.name,
  u.tier,
  e.event_type,
  e.event_time
FROM fluss.analytics.events e
LEFT JOIN fluss.analytics.users FOR SYSTEM_TIME AS OF e.event_time AS u
  ON e.user_id = u.user_id
WHERE u.tier = 'premium';
```

### Flink DataStream API

```java
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.table.api.bridge.java.StreamTableEnvironment;

StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
StreamTableEnvironment tEnv = StreamTableEnvironment.create(env);

// Create Fluss catalog
tEnv.executeSql(
    "CREATE CATALOG fluss WITH (" +
    "'type'='fluss'," +
    "'bootstrap.servers'='fluss-server:9123'" +
    ")"
);

tEnv.useCatalog("fluss");

// Create table
tEnv.executeSql(
    "CREATE TABLE events (" +
    "  event_id STRING," +
    "  user_id BIGINT," +
    "  event_time TIMESTAMP(3)" +
    ") WITH (" +
    "'bucket.num'='8'" +
    ")"
);

// Insert data
DataStream<RowData> dataStream = ...;
Table table = tEnv.fromDataStream(dataStream);
table.executeInsert("events");
```

### Apache Spark Integration (0.9+)

Fluss 0.9 added Spark catalog support for unified batch and streaming analytics.

```sql
-- Create Fluss catalog in Spark
CREATE CATALOG fluss WITH (
  'type' = 'fluss',
  'bootstrap.servers' = 'fluss-server:9123'
);

USE CATALOG fluss;

-- Batch read
SELECT * FROM analytics.events WHERE dt = '2026-03-18';

-- Streaming read
SELECT * FROM analytics.events /*+ OPTIONS('scan.startup.mode'='latest') */;

-- Write to Fluss from Spark
INSERT INTO analytics.events
SELECT * FROM other_catalog.raw_events;
```

### Delta Joins (0.8+)

Delta Joins reduce CPU/memory by up to 80% compared to regular temporal joins. Flink reads only changed records from Fluss rather than full snapshots.

```sql
-- Delta Join (Flink 2.0+)
-- Fluss automatically detects when delta joins are possible
SELECT
  o.order_id,
  o.amount,
  u.name,
  u.tier
FROM orders_stream o
LEFT JOIN users FOR SYSTEM_TIME AS OF o.order_time AS u
  ON o.user_id = u.user_id;
-- With Fluss primary key tables, this uses delta join internally
-- Checkpoints reduced from 90s to ~1s, state nearly eliminated
```

### Aggregation Merge Engine (0.9+)

Push real-time aggregations to the storage layer for near-stateless Flink jobs.

```sql
CREATE TABLE page_views_agg (
  page_id STRING,
  view_count BIGINT,
  last_viewed TIMESTAMP(3),
  PRIMARY KEY (page_id) NOT ENFORCED
) WITH (
  'connector' = 'fluss',
  'bootstrap.servers' = 'fluss-server:9123',
  'bucket.num' = '8',
  'table.merge-engine' = 'aggregation'
);
```

### Change Data Feed (0.9+)

Virtual `$changelog` and `$binlog` tables provide complete audit trails without extra compute.

```sql
-- Read full changelog (INSERT, UPDATE_BEFORE, UPDATE_AFTER, DELETE)
SELECT * FROM fluss.analytics.users$changelog;

-- Read binlog format
SELECT * FROM fluss.analytics.users$binlog;
```

### Schema Evolution (0.9+)

Zero-copy schema evolution — adding new columns does not affect existing running jobs after client upgrade.

```sql
-- Add column to existing table (all clients must be on 0.9+)
ALTER TABLE analytics.events ADD COLUMN source STRING;
-- Existing jobs continue without restart
```

### CDC Integration Patterns

#### Flink CDC 3.5 Pipeline Connector

```yaml
# pipeline.yaml
source:
  type: mysql
  hostname: mysql-host
  port: 3306
  username: root
  password: password
  database-name: mydb
  table-name: users

sink:
  type: fluss
  bootstrap.servers: fluss-server:9123
  database-name: analytics
  table-name: users

pipeline:
  name: mysql-to-fluss
  parallelism: 4
```

**Run Pipeline:**

```bash
flink-cdc.sh pipeline.yaml
```

#### MySQL CDC → Fluss (SQL)

```sql
CREATE TABLE mysql_orders (
  order_id BIGINT,
  user_id BIGINT,
  amount DECIMAL(10,2),
  status STRING,
  PRIMARY KEY (order_id) NOT ENFORCED
) WITH (
  'connector' = 'mysql-cdc',
  'hostname' = 'mysql',
  'database-name' = 'shop',
  'table-name' = 'orders'
);

CREATE TABLE fluss_orders (
  order_id BIGINT,
  user_id BIGINT,
  amount DECIMAL(10,2),
  status STRING,
  PRIMARY KEY (order_id) NOT ENFORCED
) WITH (
  'connector' = 'fluss',
  'bootstrap.servers' = 'fluss-server:9123',
  'bucket.num' = '8'
);

-- Sync CDC → Fluss
INSERT INTO fluss_orders
SELECT * FROM mysql_orders;
```

### Lakehouse Integration

**Fluss → Paimon:**

```sql
-- Data flows: Source → Fluss (hot) → Paimon (cold)
CREATE TABLE fluss_events (...) WITH (
  'table.datalake.enabled' = 'true',
  'table.datalake.format' = 'paimon',
  'remote.data.dir' = 's3://bucket/paimon/'
);

-- Query Paimon directly (cold data)
CREATE CATALOG paimon WITH (
  'type' = 'paimon',
  'warehouse' = 's3://bucket/paimon/'
);

SELECT * FROM paimon.analytics.events
WHERE event_date < '2025-10-01';  -- Historical data
```

**Fluss → Iceberg:**

```sql
CREATE TABLE fluss_events (...) WITH (
  'table.datalake.enabled' = 'true',
  'table.datalake.format' = 'iceberg',
  'remote.data.dir' = 's3://bucket/iceberg/'
);
```

## Streaming Features

### Real-Time Ingestion Patterns

**Pattern: Kafka → Fluss → Enrichment → Downstream**

```sql
-- Ingest from Kafka
CREATE TABLE kafka_raw (...);
CREATE TABLE fluss_events (...);

INSERT INTO fluss_events SELECT * FROM kafka_raw;

-- Enrich and transform
CREATE TABLE enriched_stream AS
SELECT
  e.event_id,
  e.user_id,
  u.name,
  u.tier,
  e.payload
FROM fluss_events e
LEFT JOIN fluss_users FOR SYSTEM_TIME AS OF e.event_time AS u
  ON e.user_id = u.user_id;

-- Sink to downstream
INSERT INTO kafka_sink SELECT * FROM enriched_stream;
```

### Consumer Groups and Offset Management

Fluss inherits Kafka-like consumer group semantics:

**Consumer Group Configuration:**

```java
// Flink consumer with consumer group
tEnv.executeSql(
    "CREATE TABLE fluss_source (...) WITH (" +
    "'connector'='fluss'," +
    "'bootstrap.servers'='fluss-server:9123'," +
    "'properties.group.id'='my-consumer-group'" +  // Consumer group
    ")"
);
```

**Offset Management:**
- Offsets tracked per consumer group
- Auto-commit or manual commit
- Reset to specific offset or timestamp
- Similar to Kafka offset management

### Exactly-Once Semantics

Fluss with Flink provides exactly-once processing:

**Enable Checkpointing:**

```java
StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
env.enableCheckpointing(60000);  // 1 minute
env.getCheckpointConfig().setCheckpointingMode(CheckpointingMode.EXACTLY_ONCE);
```

**Transactional Writes:**
- Flink checkpoints coordinate with Fluss transactions
- Atomically commit offsets and outputs
- No duplicates or data loss

### Watermark Handling

```sql
CREATE TABLE events (
  event_id STRING,
  user_id BIGINT,
  event_time TIMESTAMP(3),
  data STRING,
  WATERMARK FOR event_time AS event_time - INTERVAL '10' SECOND
) WITH (
  'connector' = 'fluss',
  'bootstrap.servers' = 'fluss-server:9123'
);

-- Use watermarks for windowing
SELECT
  TUMBLE_START(event_time, INTERVAL '1' MINUTE) as window_start,
  user_id,
  COUNT(*) as event_count
FROM events
GROUP BY TUMBLE(event_time, INTERVAL '1' MINUTE), user_id;
```

### Late Data Processing

```sql
-- Define watermark with allowed lateness
CREATE TABLE events (
  event_id STRING,
  event_time TIMESTAMP(3),
  data STRING,
  WATERMARK FOR event_time AS event_time - INTERVAL '1' HOUR
) WITH ('connector' = 'fluss', ...);

-- Window with late data handling
SELECT
  window_start,
  COUNT(*) as cnt
FROM TABLE(
  TUMBLE(TABLE events, DESCRIPTOR(event_time), INTERVAL '5' MINUTE)
)
GROUP BY window_start, window_end
-- Late events (within 1 hour) update window results
```

## Storage & Performance

### Bucket and Partition Strategies

**Bucket Count Guidelines:**

| Data Volume | Bucket Count | Parallelism |
|-------------|--------------|-------------|
| Low (< 1GB/day) | 2-4 | 2-4 |
| Medium (1-10GB/day) | 4-8 | 4-8 |
| High (10-100GB/day) | 8-16 | 8-16 |
| Very High (> 100GB/day) | 16-32+ | 16-32+ |

**Partition Strategies:**

```sql
-- Time-based (most common)
PARTITIONED BY (dt)  -- Daily

-- Auto-partitioning (recommended)
WITH (
  'table.auto-partition.enabled' = 'true',
  'table.auto-partition.time-unit' = 'day'  -- or 'hour'
)

-- Composite partitioning
PARTITIONED BY (region, dt)
```

### Compaction Policies

**Log Compaction (Primary Key Tables):**

```sql
CREATE TABLE users (...) WITH (
  'connector' = 'fluss',
  'log.compaction.enabled' = 'true',
  'log.compaction.interval.ms' = '60000',  -- Compact every minute
  'log.segment.bytes' = '104857600',  -- 100MB segments
  'log.compaction.min.cleanable.ratio' = '0.5'  -- Compact when 50% dirty
);
```

**Compaction Behavior:**
- Keeps latest value per primary key
- Deletes obsolete versions
- Runs asynchronously on TabletServer

### Retention Policies

**Time-Based Retention:**

```sql
CREATE TABLE events (...) WITH (
  'log.retention.hours' = '24',  -- Keep 24 hours in Fluss
  'table.datalake.enabled' = 'true'  -- Tier to lakehouse
);
```

**Size-Based Retention:**

```sql
CREATE TABLE events (...) WITH (
  'log.retention.bytes' = '10737418240',  -- 10GB max
  'log.segment.bytes' = '104857600'  -- 100MB segments
);
```

**Retention + Tiering Strategy:**
```sql
CREATE TABLE events (...) WITH (
  'log.retention.hours' = '24',  -- Hot: 24 hours
  'table.datalake.enabled' = 'true',
  'log.tiering.interval.ms' = '300000'  -- Tier every 5 min
);
```

### Log Segment Management

**Segment Configuration:**

```sql
CREATE TABLE events (...) WITH (
  'log.segment.bytes' = '104857600',  -- 100MB per segment
  'log.roll.hours' = '1',  -- New segment every hour
  'log.segment.delete.delay.ms' = '60000'  -- Delete after 1 min
);
```

**Segment Behavior:**
- Immutable once written
- Compaction creates new segments
- Old segments deleted per retention policy

## Deployment & Operations

### Cluster Setup Basics

**Cluster Components:**

1. **CoordinatorServer**
   - Metadata management
   - Replica assignment
   - Tiering coordination
   - Typically 3 nodes (HA)

2. **TabletServer**
   - Data storage
   - Read/write serving
   - Replication
   - Scale horizontally (N nodes)

**Minimal Cluster:**

```yaml
# docker-compose.yml
services:
  coordinator:
    image: fluss/fluss:0.9.0
    command: coordinator-server
    environment:
      - FLUSS_PROPERTIES=
          zookeeper.address=zookeeper:2181
          bind.listeners=coord://0.0.0.0:9123
    ports:
      - "9123:9123"

  tablet-1:
    image: fluss/fluss:0.9.0
    command: tablet-server
    environment:
      - FLUSS_PROPERTIES=
          coordinator.servers=coordinator:9123
          bind.listeners=tablet://0.0.0.0:9124
          data.dir=/data
    volumes:
      - tablet1-data:/data

  zookeeper:
    image: zookeeper:3.8
    ports:
      - "2181:2181"

volumes:
  tablet1-data:
```

### Kubernetes Deployment (0.8+)

Helm charts are available for full cluster deployment:

```bash
helm repo add fluss https://fluss.apache.org/charts
helm install fluss fluss/fluss \
  --set coordinatorServer.replicas=3 \
  --set tabletServer.replicas=3
```

See official docs: https://fluss.apache.org/docs/install-deploy/deploying-with-helm/

### Coordinator and TabletServer Roles

**CoordinatorServer Responsibilities:**
- Maintain cluster metadata in ZooKeeper (future: KvStore)
- Assign table buckets to TabletServers
- Manage tiering jobs
- Monitor cluster health
- Handle table DDL operations

**TabletServer Responsibilities:**
- Store tablet data (LogTablets, KvTablets)
- Serve read/write requests
- Replicate data to other TabletServers
- Execute compaction
- Report metrics to Coordinator

### Replication Configuration

**Table-Level Replication:**

```sql
CREATE TABLE events (...) WITH (
  'table.replication-factor' = '3'  -- 3 replicas
);
```

**Rack-Aware Placement (0.7+):**

Fluss 0.7 automatically avoids placing replicas in the same rack, improving fault tolerance in multi-AZ deployments.

**Replication Behavior:**
- Synchronous replication (similar to Kafka ISR)
- Majority quorum for writes
- Automatic failover on TabletServer failure

### Monitoring and Metrics

**Key Metrics to Monitor:**

1. **Throughput**
   - Records/sec written
   - Records/sec read
   - Bytes/sec in/out

2. **Latency**
   - Write latency (p50, p99, p999)
   - Read latency
   - End-to-end pipeline latency

3. **Storage**
   - Disk usage per TabletServer
   - Segment count
   - Compaction lag

4. **Replication**
   - Under-replicated tablets
   - Leader election count
   - Replica lag

**Prometheus Metrics Endpoint:**

```yaml
# Enable metrics
metrics.reporter.promgateway.class: org.apache.flink.metrics.prometheus.PrometheusPushGatewayReporter
metrics.reporter.promgateway.host: prometheus-pushgateway
metrics.reporter.promgateway.port: 9091
```

**Grafana Dashboards:**
- Official Fluss Grafana dashboards available
- Monitor cluster health, throughput, latency

### Common Troubleshooting

**Issue: High write latency**
- Check TabletServer CPU/disk
- Increase bucket count for parallelism
- Reduce replication factor (if acceptable)
- Enable compression

**Issue: Slow reads**
- Use columnar projection pushdown
- Increase read parallelism
- Check if tiering is working (cold data access)

**Issue: Disk space growing**
- Check retention policy
- Verify tiering is enabled and working
- Run manual compaction if needed

**Issue: Under-replicated tablets**
- Check TabletServer health
- Verify network connectivity
- Review replica assignment (rack-aware)

## Common Use Cases

### Real-Time Data Pipelines

**Pattern: Kafka → Fluss → Flink → Sink**

```sql
-- Kafka source
CREATE TABLE kafka_events (...);

-- Fluss (real-time storage)
CREATE TABLE fluss_events (...) WITH (
  'connector' = 'fluss',
  'table.datalake.enabled' = 'true'
);

-- Ingest
INSERT INTO fluss_events SELECT * FROM kafka_events;

-- Real-time processing
CREATE TEMPORARY VIEW processed AS
SELECT
  user_id,
  TUMBLE_START(event_time, INTERVAL '1' MINUTE) as window_start,
  COUNT(*) as event_count
FROM fluss_events
GROUP BY user_id, TUMBLE(event_time, INTERVAL '1' MINUTE);

-- Sink to downstream
INSERT INTO elasticsearch_sink SELECT * FROM processed;
```

### Stream Processing with State

**Pattern: Stateful Processing with Fluss Lookups**

```sql
-- Event stream (Fluss log table)
CREATE TABLE events (...);

-- State table (Fluss primary key table)
CREATE TABLE user_state (
  user_id BIGINT,
  total_events BIGINT,
  last_event_time TIMESTAMP(3),
  PRIMARY KEY (user_id) NOT ENFORCED
) WITH ('connector' = 'fluss', ...);

-- Update state based on events
EXECUTE STATEMENT SET
BEGIN
  -- Aggregate events
  INSERT INTO user_state
  SELECT
    user_id,
    COUNT(*) as total_events,
    MAX(event_time) as last_event_time
  FROM events
  GROUP BY user_id;
END;
```

### Change Data Capture Workflows

**Pattern: MySQL → Fluss → Data Warehouse**

```sql
-- CDC source
CREATE TABLE mysql_products (
  product_id BIGINT,
  name STRING,
  price DECIMAL(10,2),
  PRIMARY KEY (product_id) NOT ENFORCED
) WITH ('connector' = 'mysql-cdc', ...);

-- Fluss (real-time CDC storage)
CREATE TABLE fluss_products (
  product_id BIGINT,
  name STRING,
  price DECIMAL(10,2),
  PRIMARY KEY (product_id) NOT ENFORCED
) WITH (
  'connector' = 'fluss',
  'table.datalake.enabled' = 'true',
  'table.datalake.format' = 'iceberg'
);

-- Sync CDC → Fluss
INSERT INTO fluss_products SELECT * FROM mysql_products;

-- Query from data warehouse (Iceberg via Trino)
-- Fresh data from Fluss + historical from Iceberg
```

### Event Streaming Architectures

**Pattern: Multi-Consumer Event Bus**

```sql
-- Central event log (Fluss)
CREATE TABLE event_bus (
  event_id STRING,
  event_type STRING,
  event_time TIMESTAMP(3),
  payload STRING
) WITH (
  'connector' = 'fluss',
  'bucket.num' = '32',
  'log.retention.hours' = '168'  -- 7 days
);

-- Consumer 1: Real-time analytics
INSERT INTO analytics_sink
SELECT * FROM event_bus
WHERE event_type IN ('purchase', 'view');

-- Consumer 2: ML feature store
INSERT INTO feature_store
SELECT user_id, event_type, event_time
FROM event_bus;

-- Consumer 3: Audit log
INSERT INTO audit_table
SELECT * FROM event_bus;
```

## Quick Reference

### Essential Configuration

```sql
-- Log table
CREATE TABLE events (...) WITH (
  'connector' = 'fluss',
  'bootstrap.servers' = 'fluss-server:9123',
  'bucket.num' = '8'
);

-- Primary key table
CREATE TABLE users (..., PRIMARY KEY (user_id) NOT ENFORCED) WITH (
  'connector' = 'fluss',
  'bootstrap.servers' = 'fluss-server:9123',
  'bucket.num' = '4'
);

-- With tiering
CREATE TABLE events (...) WITH (
  'connector' = 'fluss',
  'bucket.num' = '8',
  'table.datalake.enabled' = 'true',
  'table.datalake.format' = 'paimon',
  'log.retention.hours' = '24'
);
```

### Common Table Properties

```yaml
# Bucket configuration
bucket.num: 8

# Replication
table.replication-factor: 3

# Retention
log.retention.hours: 24
log.retention.bytes: 10737418240  # 10GB

# Compaction
log.compaction.enabled: true
log.compaction.interval.ms: 60000

# Tiering
table.datalake.enabled: true
table.datalake.format: paimon  # or iceberg or lance
log.tiering.interval.ms: 300000

# Auto-partitioning
table.auto-partition.enabled: true
table.auto-partition.time-unit: day  # or hour

# Log segments
log.segment.bytes: 104857600  # 100MB
log.roll.hours: 1
```

### Performance Checklist

- ✅ Set appropriate bucket count (1-2x cores)
- ✅ Enable tiering for long-term retention
- ✅ Configure retention policy (time or size)
- ✅ Use columnar reads (projection pushdown)
- ✅ Set replication factor (3 for HA)
- ✅ Enable auto-partitioning for time-series
- ✅ Use primary key tables for mutable data
- ✅ Use log tables for append-only streams
- ✅ Monitor tablet server disk usage
- ✅ Enable exactly-once semantics in Flink

## Upgrade Notes

### Upgrading to 0.9.0

**Breaking Changes:**
- **All clients must upgrade:** KV format v2 is incompatible with older versions; all clients must reach 0.9+ before using new features
- **Schema evolution requires coordinated upgrade:** All servers and clients must be on 0.9+ before adding columns to prevent schema inconsistency
- **Primary key encoding change:** Tables with bucket keys differing from primary keys now use Fluss default encoder; legacy tables retain v1 encoding but may need recreation
- **Configuration consolidation:** Three deprecated options merged into `server.io-pool.size` (default: 10):
  - `coordinator.io-pool.size` → `server.io-pool.size`
  - `remote.log.data-transfer-thread-num` → `server.io-pool.size`
  - `kv.snapshot.transfer-thread-num` → `server.io-pool.size`

**Paimon Integration Changes (0.9):**
- `fluss-lake-paimon` JAR no longer bundles paimon-bundle
- Users must manually add compatible paimon-bundle JAR to Flink lib directory
- Tested compatible: Paimon 1.1, 1.2, 1.3 (1.3 required for tiering services)
- Limitation: Partitioned tables with non-String keys cannot enable deletion vectors with Paimon format

### Upgrading to 0.8.0

- Backward compatible with 0.7 clients/servers for protocol and storage formats
- Package paths changed due to Apache Incubator restructuring — code adjustments needed
- Java 11 minimum (up from Java 8)

---

When helping users with Apache Fluss:
1. **Emphasize columnar advantage** - 10x read performance vs row-based
2. **Tiered architecture is key** - Hot (Fluss) + Cold (Lakehouse via Paimon, Iceberg, or Lance) = cost-efficient
3. **Choose right table type** - Log for immutable, PK for mutable
4. **Leverage Flink integration** - Purpose-built for Flink streaming, Delta Joins for efficiency
5. **Spark is now supported** - 0.9+ provides catalog support for unified batch/stream analytics
6. **Configure tiering policies** - Balance latency and storage cost
7. **Monitor replication** - Under-replicated tablets = data risk
8. **Use rack-aware placement** - Multi-AZ deployments (0.7+)
9. **Bucket count matters** - Parallelism and hot spot avoidance
10. **Aggregation merge engine** - Push aggregations to storage for near-stateless Flink jobs (0.9+)
11. **Schema evolution** - Zero-copy column additions without restarting jobs (0.9+)
12. **CDC with Flink CDC 3.5** - Native Fluss pipeline connector
13. **Upgrade carefully** - 0.9 has breaking KV format changes; all clients must upgrade together