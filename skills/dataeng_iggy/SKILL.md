---
name: iggy
description: Apache Iggy（孵化中）Rust 原生消息流平台专家知识。涵盖流/主题/分区设计、消息保留策略、QUIC/TCP 传输、生产者/消费者模式以及与 MCP 的集成。
---

# Apache Iggy Streaming Expert

Apache Iggy (Incubating) is a Rust-native persistent message streaming platform. This skill helps deploy, configure, and develop with Iggy for high-performance event streaming, including Docker deployment, Python SDK usage, CLI operations, and MCP integration for AI workflows.

## Version Information

**Server:** v0.7.0 (February 25, 2026)
**Python SDK:** `apache-iggy` v0.7.0 (PyPI)
**Status:** Apache Incubating since February 4, 2025; graduation expected 2026–2027
**Docker Images:** `apache/iggy`, `apache/iggy-web-ui`, `apache/iggy-mcp`, `apache/iggy-connect`

## Core Concepts

### What is Apache Iggy?

Apache Iggy is a **Rust-native persistent message streaming platform** created in April
2023 by Łukasz Szostek. It entered the Apache Incubator on February 4, 2025 and
is now developed under the Apache Software Foundation as **Apache Iggy
(Incubating)**.

It occupies a similar space to Kafka, Redpanda, and NATS JetStream — a durable,
ordered message log — but trades ecosystem breadth for raw performance and
operational simplicity. There is no JVM, no ZooKeeper, no KRaft. A single Rust
binary handles everything.

### Comparison

| | Iggy | Kafka | Redpanda | NATS JetStream |
|---|---|---|---|---|
| Language | Rust | Java/Scala | C++ | Go |
| Persistence | Append-only log, io_uring | Append-only log | Append-only log | File-backed Raft |
| Latency (P99) | <1–2 ms | ~300 ms+ | ~10 ms | ~5 ms |
| Throughput | ~20M msg/s, 3 GB/s writes | ~2M msg/s | ~1M msg/s | ~500K msg/s |
| Dependencies | None (single binary) | JVM + ZK/KRaft | None | None |
| Maturity | Incubating | Production (10+ yr) | Production | Production |
| Protocols | TCP, QUIC, HTTP, WebSocket | Kafka protocol | Kafka protocol | NATS protocol |
| MCP Support | Official | No | No | No |

### Key Differentiators

- **Thread-per-core, shared-nothing** architecture with **io_uring** for I/O.
- **Four transport protocols** (TCP, QUIC, HTTP, WebSocket) from a single server.
- **Built-in MCP server** for LLM/AI integration.
- **Zero external dependencies** — no JVM, no coordinator service.
- **Web UI** ships as a separate container (`apache/iggy-web-ui`).

---

## Architecture & Concepts

### Data Hierarchy

```
Server
 └── Stream        (logical namespace, like a Kafka cluster)
      └── Topic    (like a Kafka topic)
           └── Partition   (ordered, append-only log)
                └── Segment (on-disk file chunk)
```

- **Streams** are top-level namespaces. A server can host many streams.
- **Topics** live inside a stream. Each topic has one or more partitions.
- **Partitions** provide ordering guarantees and parallelism. Messages within a
  partition are strictly ordered by offset.
- **Segments** are the on-disk storage units within a partition. Segments are
  append-only and rotated by size.

### Message Model

Each message has:
- **ID** (u128, auto-generated or user-supplied)
- **Offset** (u64, partition-scoped, monotonically increasing)
- **Timestamp** (u64, microseconds)
- **Checksum** (u32)
- **Payload** (bytes)
- **Headers** (optional key-value map)

### Consumer Groups

Consumer groups distribute partitions across multiple consumers. Iggy tracks
offsets per consumer group. When a consumer joins or leaves, partitions are
rebalanced.

### Retention

- **Size-based**: delete oldest segments when partition exceeds a byte limit.
- **Time-based**: delete messages older than a configured expiry (seconds).
- **None**: retain forever (default).

Retention is checked periodically (`message_expiry_check_interval`, default 60s).

### Persistence

Messages are buffered in memory and flushed to disk by a background saver
(`message_saver`). The saver runs on a configurable interval and/or message
count threshold. On clean shutdown, all buffered messages are flushed.

---

## Docker Deployment

### Images

| Image | Purpose |
|---|---|
| `apache/iggy` | Server (main) |
| `apache/iggy-web-ui` | Web management UI |
| `apache/iggy-mcp` | MCP server for LLM integration |
| `apache/iggy-connect` | Connectors |

Legacy pre-Apache image: `iggyrs/iggy` (still on Docker Hub).

Also available on GitHub Container Registry: `ghcr.io/apache/iggy`.

### Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| 3000 | HTTP | REST API |
| 8080 | QUIC (UDP) | Low-latency binary protocol |
| 8090 | TCP | High-throughput binary protocol |
| 8092 | WebSocket | Browser/WS clients |

### Required Container Capabilities

Iggy uses io_uring and thread affinity, which require elevated permissions:

```yaml
cap_add:
  - SYS_NICE
security_opt:
  - seccomp:unconfined
ulimits:
  memlock:
    soft: -1
    hard: -1
```

Without these, the server may fail to start or run with degraded performance.

### Data Volume

All persistent data lives at `/local_data` inside the container. Mount a volume
here for durability.

### Default Credentials

**WARNING**: If `IGGY_ROOT_USERNAME` and `IGGY_ROOT_PASSWORD` are NOT set, the
server generates a **random password** and prints it to stdout. It does NOT
default to `iggy`/`iggy`. Always set these env vars explicitly.

On first startup (when `/local_data` is empty), the server creates a root user
using the provided env vars. **Once the data directory exists, the env vars are
ignored on subsequent starts.** To reset credentials, wipe the data directory.

### Docker Compose Example

```yaml
services:
  iggy:
    image: apache/iggy:latest
    container_name: iggy
    restart: unless-stopped
    cap_add:
      - SYS_NICE
    security_opt:
      - seccomp:unconfined
    ulimits:
      memlock:
        soft: -1
        hard: -1
    environment:
      - IGGY_HTTP_ADDRESS=0.0.0.0:3000    # Default is 127.0.0.1 — must override for Docker
      - IGGY_TCP_ADDRESS=0.0.0.0:8090     # Default is 127.0.0.1 — must override for Docker
      - IGGY_ROOT_USERNAME=iggy            # REQUIRED — no default
      - IGGY_ROOT_PASSWORD=iggy            # REQUIRED — random if omitted
    ports:
      - "3000:3000"   # HTTP API
      - "8080:8080"   # QUIC
      - "8090:8090"   # TCP
      - "8092:8092"   # WebSocket
    volumes:
      - iggy-data:/local_data
    healthcheck:
      test: ["CMD", "iggy", "ping"]       # Binary is on PATH, not at /iggy
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 15s

  iggy-web-ui:
    image: apache/iggy-web-ui:latest
    container_name: iggy-web-ui
    ports:
      - "8888:3050"                                   # Web UI listens on 3050, not 3000
    environment:
      - IGGY_API_URL=http://iggy:3000                 # Server-side proxy (internal)
      - PUBLIC_IGGY_API_URL=http://localhost:3000      # Client-side API calls (browser-accessible)
    depends_on:
      - iggy

volumes:
  iggy-data:
    driver: local
```

### Health Check

- **HTTP**: `GET http://localhost:3000/health` → 200 OK
- **CLI**: `/iggy ping` (binary is bundled in the server image)

---

## Python SDK (`apache-iggy`)

### Installation

```bash
pip install apache-iggy
```

- **PyPI package**: `apache-iggy` (version 0.7.0 as of Feb 25, 2026)
- **Legacy package**: `iggy-py` (archived at 0.4.0 — do not use)
- **Python**: 3.10+
- **No runtime dependencies** — pre-compiled Rust binary via PyO3/Maturin
- **Source**: `https://github.com/apache/iggy/tree/master/foreign/python`

### Connection

```python
from apache_iggy import IggyClient

# Connection string format: iggy+{protocol}://{user}:{pass}@{host}:{port}
client = IggyClient.from_connection_string("iggy+tcp://iggy:iggy@localhost:8090")
await client.connect()
await client.login_user("iggy", "iggy")
```

Supported protocols in connection string:
- `iggy+tcp://` — highest throughput (default)
- `iggy+quic://` — lowest latency
- `iggy+http://` — REST-based

Optional TLS:
```python
"iggy+tcp://iggy:iggy@localhost:8090?tls=true&ca_cert_path=/path/to/ca.pem"
```

### Fully Async

The entire SDK is async-only. All I/O methods require `await`. There is no
synchronous API.

### Creating Streams and Topics

```python
# Create a stream (namespace)
await client.create_stream("crypto")

# Create a topic with 3 partitions
await client.create_topic(
    "crypto",              # stream name or ID
    "prices",              # topic name
    partitions_count=3,
    # Optional parameters:
    # compression_algorithm=...,
    # replication_factor=...,
    # message_expiry=...,      # seconds, 0 = never
    # max_topic_size=...,      # bytes
)
```

### Producing Messages

```python
from apache_iggy import SendMessage

messages = [
    SendMessage('{"pair":"BTC-USD","price":72910.30}'),
    SendMessage('{"pair":"ETH-USD","price":2265.06}'),
]

await client.send_messages(
    "crypto",          # stream
    "prices",          # topic
    partitioning,      # partitioning strategy
    messages,
)
```

`SendMessage` accepts `str` or `bytes`.

### Consuming Messages (Polling)

```python
from apache_iggy import PollingStrategy

messages = await client.poll_messages(
    "crypto",                          # stream
    "prices",                          # topic
    partition_id=0,
    polling_strategy=PollingStrategy.Offset(0),  # Next() needs consumer group
    count=100,                         # max messages to fetch
    auto_commit=False,                 # plain bool, NOT AutoCommit.Disabled()
)

for msg in messages:
    payload = msg.payload()       # bytes
    offset  = msg.offset()        # int
    ts      = msg.timestamp()     # int (microseconds)
    msg_id  = msg.id()            # int
```

### Polling Strategies

```python
PollingStrategy.Offset(value=0)    # Start from specific offset
PollingStrategy.Timestamp(value=…) # Start from specific timestamp
PollingStrategy.First()            # From beginning
PollingStrategy.Last()             # Most recent
PollingStrategy.Next()             # After last consumed
```

### Auto-Commit Options

**WARNING (v0.7.0):** The `AutoCommit` enum class exists in the module but
cannot be used as the `auto_commit` parameter — it raises a TypeError. Use a
plain `bool` instead:

```python
auto_commit=False   # disable auto-commit
auto_commit=True    # enable auto-commit
```

The enum classes (`AutoCommit.Disabled()`, `AutoCommit.Interval(...)` etc.)
may become usable in a future SDK release.

### Consumer Groups (High-Level Consumer)

```python
consumer = await client.consumer_group(...)

# Async iterator pattern
async for message in consumer.iter_messages():
    payload = message.payload()
    # process...

# Or callback pattern
async def handle(msg):
    print(msg.payload())

await consumer.consume_messages(handle, shutdown_event)
```

Consumer group methods:
```python
consumer.name()                                    # str
consumer.stream()                                  # str | int
consumer.topic()                                   # str | int
consumer.partition_id()                            # int
await consumer.get_last_consumed_offset(part_id)   # int | None
await consumer.get_last_stored_offset(part_id)     # int | None
await consumer.store_offset(offset, part_id)       # None
await consumer.delete_offset(part_id)              # None
```

### Inspecting Streams and Topics

```python
stream = await client.get_stream("crypto")
# stream.id, stream.name, stream.messages_count, stream.topics_count

topic = await client.get_topic("crypto", "prices")
# topic.id, topic.name, topic.messages_count, topic.partitions_count
```

### Complete Producer Example

```python
import asyncio
import json
from apache_iggy import IggyClient, SendMessage

async def main():
    client = IggyClient.from_connection_string(
        "iggy+tcp://iggy:iggy@localhost:8090"
    )
    await client.connect()
    await client.login_user("iggy", "iggy")

    # Ensure stream and topic exist
    await client.create_stream("crypto")
    await client.create_topic("crypto", "prices", partitions_count=3)

    tick = {"pair": "BTC-USD", "price": 72910.30, "volume_24h": 12345.67}
    msg = SendMessage(json.dumps(tick))
    await client.send_messages("crypto", "prices", None, [msg])

asyncio.run(main())
```

### Complete Consumer Example

```python
import asyncio
import json
from apache_iggy import IggyClient, PollingStrategy

async def main():
    client = IggyClient.from_connection_string(
        "iggy+tcp://iggy:iggy@localhost:8090"
    )
    await client.connect()
    await client.login_user("iggy", "iggy")

    offset = 0
    while True:
        messages = await client.poll_messages(
            "crypto", "prices",
            partition_id=0,
            polling_strategy=PollingStrategy.Offset(offset),
            count=100,
            auto_commit=False,
        )
        for msg in messages:
            tick = json.loads(msg.payload())
            print(f"{tick['pair']}: ${tick['price']}")
            offset = msg.offset() + 1

        if not messages:
            await asyncio.sleep(0.1)

asyncio.run(main())
```

---

## HTTP API

**Base URL**: `http://localhost:3000`

### Authentication

Iggy uses JWT tokens. Obtain a token first:

```bash
curl -X POST http://localhost:3000/users/login \
  -H "Content-Type: application/json" \
  -d '{"username":"iggy","password":"iggy"}'
```

Response includes a token (expires in 3600s by default). Use it in subsequent
requests:

```
Authorization: Bearer <token>
```

### Key Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Health check |
| GET | `/stats` | Server statistics |
| POST | `/streams` | Create stream |
| GET | `/streams` | List streams |
| GET | `/streams/{id}` | Get stream details |
| DELETE | `/streams/{id}` | Delete stream |
| POST | `/streams/{id}/topics` | Create topic |
| GET | `/streams/{id}/topics` | List topics |
| GET | `/streams/{id}/topics/{id}` | Get topic details |
| DELETE | `/streams/{id}/topics/{id}` | Delete topic |
| POST | `/streams/{id}/topics/{id}/messages` | Send messages |
| GET | `/streams/{id}/topics/{id}/messages` | Poll messages |
| POST | `/streams/{id}/topics/{id}/consumer-groups` | Create consumer group |
| GET | `/users` | List users |
| POST | `/users/login` | Login (get JWT) |
| POST | `/personal-access-tokens` | Create PAT |

### CORS

Configurable in server config under `[http.cors]`:
```toml
[http.cors]
enabled = true
allowed_methods = ["GET", "POST", "PUT", "DELETE"]
allowed_origins = ["*"]
```

---

## CLI Tool

The CLI binary is at `/usr/local/bin/iggy` inside the `apache/iggy` Docker
image (on `PATH`, so just `iggy` works). It can also be installed standalone
via Cargo:

```bash
cargo install iggy-cli
```

### Connection

**The CLI requires `--username` and `--password` for every command** (except
`ping`). Without them you get "Missing iggy server credentials".

```bash
# Default: TCP on localhost:8090
iggy --username iggy --password iggy stream list

# Override transport
iggy --address 127.0.0.1:3000 --transport http --username iggy --password iggy stream list
```

### Commands

```bash
# Health (no auth required)
iggy ping

# Server stats
iggy --username iggy --password iggy stats

# Streams
iggy --username iggy --password iggy stream create my-stream
iggy --username iggy --password iggy stream list
iggy --username iggy --password iggy stream delete my-stream

# Topics
iggy --username iggy --password iggy topic create my-stream my-topic --partitions 3
iggy --username iggy --password iggy topic list my-stream

# Messages
iggy --username iggy --password iggy message send my-stream my-topic "Hello Iggy"
iggy --username iggy --password iggy message poll my-stream my-topic 0 --count 10
```

### Running CLI Inside Docker

```bash
docker exec -it iggy iggy ping
docker exec -it iggy iggy --username iggy --password iggy stream list
docker exec -it iggy iggy --username iggy --password iggy message send crypto prices '{"pair":"BTC-USD"}'
```

---

## MCP Server

Iggy ships an **official MCP server** as a separate Docker image.

### Image

```bash
docker pull apache/iggy-mcp
```

### Purpose

Allows LLMs (Claude, etc.) to inspect and interact with Iggy streams in
real-time via the Model Context Protocol. Use cases:
- AI monitoring of streaming data
- LLM-powered troubleshooting of message pipelines
- Data exploration via natural language

### Transports

- **STDIO** — recommended for Claude Desktop and local tools
- **HTTP** — for remote/networked access

### Configuration

Supports TOML, YAML, or JSON. Minimal TOML example:

```toml
[iggy]
address = "localhost:8090"
username = "iggy"
password = "iggy"

[transport]
type = "stdio"   # or "http"

[permissions]
create = true
read = true
update = false
delete = false
```

Environment variable overrides follow the pattern:
`IGGY_MCP_SECTION_NAME.KEY_NAME`

### Docker Compose

```yaml
iggy-mcp:
  image: apache/iggy-mcp:latest
  container_name: iggy-mcp
  environment:
    - IGGY_MCP_IGGY.ADDRESS=iggy:8090
    - IGGY_MCP_IGGY.USERNAME=iggy
    - IGGY_MCP_IGGY.PASSWORD=iggy
    - IGGY_MCP_TRANSPORT.TYPE=http
    - IGGY_MCP_PERMISSIONS.READ=true
    - IGGY_MCP_PERMISSIONS.CREATE=false
    - IGGY_MCP_PERMISSIONS.UPDATE=false
    - IGGY_MCP_PERMISSIONS.DELETE=false
  ports:
    - "3100:3000"
  depends_on:
    - iggy
```

### Documentation

Official docs: `https://iggy.apache.org/docs/ai/mcp/`

---

## Server Configuration

The server is configured via a TOML file. If no file is found, embedded defaults
are used.

### Config File Location

- Set via `IGGY_CONFIG_PATH` environment variable
- Default search: `./configs/server.toml`
- Override any setting via env vars: `IGGY_{SECTION}_{KEY}` (uppercased)

### Key Configuration Sections

```toml
# --- System ---
[system]
path = "local_data"           # Data directory

[system.encryption]
enabled = false
key = ""                      # 32-byte base64 key for AES-256-GCM

# --- HTTP Transport ---
[http]
enabled = true
address = "0.0.0.0:3000"

[http.cors]
enabled = true
allowed_methods = ["GET", "POST", "PUT", "DELETE"]
allowed_origins = ["*"]

# --- TCP Transport ---
[tcp]
enabled = true
address = "0.0.0.0:8090"

# --- QUIC Transport ---
[quic]
enabled = true
address = "0.0.0.0:8080"

# --- WebSocket Transport ---
[websocket]
enabled = true
address = "0.0.0.0:8092"

# --- Partition Defaults ---
[partition]
message_expiry = 0                        # seconds; 0 = never
message_expiry_check_interval = 60        # seconds

[partition.message_saver]
enabled = true
interval = 5                              # seconds between flushes
# messages_required_to_save = 1000        # flush after N messages

# --- Topic Defaults ---
[topic]
# default_partitions_count = 1
# default_max_topic_size = 0              # 0 = unlimited

# --- Cluster / Replication ---
# [cluster]
# enabled = false
# ...
```

### Environment Variable Overrides

Any TOML setting can be overridden:

```bash
IGGY_HTTP_ADDRESS=0.0.0.0:3000
IGGY_TCP_ADDRESS=0.0.0.0:8090
IGGY_QUIC_ADDRESS=0.0.0.0:8080
IGGY_WEBSOCKET_ADDRESS=0.0.0.0:8092
IGGY_ROOT_USERNAME=admin
IGGY_ROOT_PASSWORD=secretpass
```

---

## Performance Characteristics

### Benchmarks (from official sources)

| Metric | Value |
|--------|-------|
| Messages/sec (produce) | ~20M msg/s |
| Write throughput | ~3 GB/s |
| Read throughput (cached) | ~10 GB/s |
| P99 latency (TCP) | <1–2 ms |
| P99 latency (Kafka comparison) | ~300 ms+ |

### Transport Performance

| Transport | Throughput | Latency | Best For |
|-----------|-----------|---------|----------|
| TCP | Highest (~5 GB/s+) | Low | Production streaming |
| QUIC | Moderate | Lowest (µs range) | Latency-sensitive |
| HTTP | Lowest | Moderate | Admin/API calls |
| WebSocket | Moderate | Low | Browser clients |

### Performance Tuning

- **More throughput**: increase `message_saver.interval`, increase
  `messages_required_to_save`, use TCP transport.
- **Lower latency**: decrease `message_saver.interval`, use QUIC transport.
- **Less memory**: reduce partition count, enable segment rotation.
- **io_uring**: requires `SYS_NICE` capability and `seccomp:unconfined`.

---

## Limitations & Caveats (March 2026)

### Maturity

- Apache Incubating — not yet an Apache Top-Level Project.
- Cluster/replication mode is still maturing.
- Smaller community and ecosystem compared to Kafka.

### Missing vs Kafka

- No Schema Registry equivalent.
- No Kafka Connect API compatibility.
- No exactly-once semantics (at-least-once only).
- No multi-topic transactions.
- No native Kubernetes operator (community Helm charts exist).

### Recommended Use Cases

- High-performance event streaming where Kafka is overkill.
- Edge/embedded streaming (single binary, low resource).
- AI/LLM integration via MCP.
- Learning and prototyping streaming architectures.

### Not Recommended For

- Regulated production systems requiring proven ecosystem maturity.
- Workloads depending on Kafka Connect or Schema Registry.
- Multi-datacenter replication (not yet production-ready).

---

## Official SDK Support

| Language | Package | Status |
|----------|---------|--------|
| Rust | `iggy` (crates.io) | Official, primary |
| Python | `apache-iggy` (PyPI) | Official |
| Java | `apache-iggy` (Maven) | Official |
| Go | `github.com/apache/iggy-go-client` | Official |
| Node.js | `@apache-iggy/iggy-node-client` | Official |
| C# | `Apache.Iggy` (NuGet) | Official |

---

## Verified Gotchas (March 2026, v0.7.0)

These were discovered through hands-on implementation, not documentation.

### Docker / Server

1. **Server binds to 127.0.0.1 by default.** In Docker, other containers cannot
   reach it. You MUST set `IGGY_HTTP_ADDRESS=0.0.0.0:3000` and
   `IGGY_TCP_ADDRESS=0.0.0.0:8090`.

2. **Root password is random if not set.** The server does NOT default to
   `iggy`/`iggy`. Set `IGGY_ROOT_USERNAME` and `IGGY_ROOT_PASSWORD` explicitly
   or check stdout for the generated password.

3. **Credentials persist in `/local_data`.** Once created on first boot, the
   root user env vars are ignored on subsequent starts. To reset, delete the
   data directory entirely.

4. **CLI binary is at `/usr/local/bin/iggy`**, not `/iggy`. It's on `PATH`, so
   healthchecks should use `["CMD", "iggy", "ping"]`.

5. **CLI requires `--username` and `--password`** for all commands except `ping`.
   Omitting them gives "Missing iggy server credentials".

### Web UI

6. **Web UI listens on port 3050**, not 3000. Map `8888:3050` in Docker Compose.

7. **Web UI root path is `/dashboard`**, not `/`. The root URL returns 404.

8. **Web UI needs `PUBLIC_IGGY_API_URL`** pointing to the browser-accessible
   Iggy HTTP API (e.g. `http://localhost:3000`). The `IGGY_API_URL` env var is
   for server-side proxy only. Without `PUBLIC_IGGY_API_URL`, login fails
   because the browser can't reach `http://iggy:3000` (Docker-internal hostname).

### Python SDK (apache-iggy 0.7.0)

9. **Connection string MUST include credentials.**
   `iggy+tcp://host:port` → `InvalidConnectionString`.
   Use `iggy+tcp://user:pass@host:port`.

10. **`send_messages()` partitioning parameter must be an int (0-indexed).**
    Passing `None` causes `TypeError`. Use `hash(key) % partition_count` for
    key-based routing.

11. **`poll_messages()` `auto_commit` parameter takes a plain `bool`**, not
    `AutoCommit.Disabled()`. The `AutoCommit` enum exists in the module but
    cannot be cast to bool in 0.7.0 and will raise a TypeError.

12. **`PollingStrategy.Next()` returns 0 messages without a consumer group.**
    For partition-level consumption, use `PollingStrategy.Offset(n)` with
    manual offset tracking, or `First()`/`Last()` for initial positioning.

13. **Stream/topic creation is NOT idempotent.** Creating a stream or topic
    that already exists throws an exception. Wrap in `try/except`.

14. **`SendMessage` does not support setting a message ID.** The constructor
    only accepts payload (`str` or `bytes`). The underlying Rust struct has a
    `u128` ID field, but no Python setter exists in 0.7.0. Server-side
    deduplication via `deduplicate_messages` cannot be controlled from Python.
    Implement application-level dedup using payload fields (e.g. sequence
    numbers).

---

## Quick Reference

```
Image:          apache/iggy:latest
Ports:          3000 (HTTP), 8080 (QUIC), 8090 (TCP), 8092 (WS)
Data:           /local_data
Credentials:    Set IGGY_ROOT_USERNAME / IGGY_ROOT_PASSWORD (NO default)
Config:         TOML, override via IGGY_* env vars
CLI in image:   /usr/local/bin/iggy (on PATH)
Health:         GET :3000/health  or  iggy ping
Python:         pip install apache-iggy
Connect:        iggy+tcp://user:pass@host:8090
Web UI:         apache/iggy-web-ui on port 3050, path /dashboard
```

---

## Sources

- Apache Iggy official site: https://iggy.apache.org/
- GitHub: https://github.com/apache/iggy
- Architecture docs: https://iggy.apache.org/docs/introduction/architecture/
- Configuration: https://iggy.apache.org/docs/server/configuration
- Python SDK source: https://github.com/apache/iggy/tree/master/foreign/python
- Python type stubs: https://github.com/apache/iggy/blob/master/foreign/python/apache_iggy.pyi
- PyPI: https://pypi.org/project/apache-iggy/
- Docker Hub: https://hub.docker.com/r/apache/iggy
- MCP docs: https://iggy.apache.org/docs/ai/mcp/
- Release notes (0.7.0): https://github.com/apache/iggy/releases/tag/server-0.7.0
- Incubation proposal: https://cwiki.apache.org/confluence/display/INCUBATOR/Iggy+Proposal
