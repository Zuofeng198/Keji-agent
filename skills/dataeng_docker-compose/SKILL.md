---
name: docker-compose
description: Docker Compose V2+ 专家知识，用于编写正确且生产就绪的编排文件。涵盖多容器编排、网络、卷、密钥管理、构建上下文以及开发/生产环境一致性配置。
---

# Docker Compose V2 Expert

This skill covers modern Docker Compose (V2+). It helps write correct, production-ready docker-compose.yml files using current syntax and best practices, focusing on what actually works in Docker Compose V2 and avoiding deprecated patterns.

## Critical Syntax Rules (V2+)

### ❌ DEPRECATED - Do NOT Use

```yaml
# ❌ WRONG - version field is obsolete in Compose V2
version: '3.8'

# ❌ WRONG - unnecessary "services:" wrapper at wrong level
version: '3.8'
service:
  app:
    image: nginx
```

### ✅ CORRECT - Modern V2 Syntax

```yaml
# ✅ START DIRECTLY WITH SERVICE NAMES
# No version field needed - V2 uses latest Compose Specification automatically

services:
  app:
    image: nginx:alpine
    ports:
      - "80:80"

networks:
  frontend:

volumes:
  data:
```

**Key Points:**
- **NO** `version:` field at top (obsolete since V2)
- **NO** `service:` wrapper - use `services:` (plural)
- Root-level keys: `services`, `networks`, `volumes`, `configs`, `secrets`
- Use 2-space indentation consistently
- Service names must be lowercase, start with letter/number, use only `a-z`, `0-9`, `_`, `-`

## Command Changes V1 → V2

```bash
# OLD (V1)
docker-compose up
docker-compose down

# NEW (V2) - space instead of hyphen
docker compose up
docker compose down
```

**Container Naming:**
- V1: Used underscores (`myproject_app_1`)
- V2: Uses hyphens (`myproject-app-1`)

## Modern Best Practices

### 1. Service Dependencies with Health Checks

**❌ Basic depends_on (NOT recommended for production)**
```yaml
services:
  app:
    image: myapp
    depends_on:
      - db  # ❌ Only waits for container to START, not be READY
```

**✅ Health-aware dependencies (RECOMMENDED)**
```yaml
services:
  db:
    image: postgres:16-alpine
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 10s
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}

  app:
    image: myapp:latest
    depends_on:
      db:
        condition: service_healthy  # ✅ Waits for health check to pass
    environment:
      DATABASE_URL: postgres://postgres:${DB_PASSWORD}@db:5432/mydb
```

**Health Check Parameters:**
- `test`: Command to run (exit 0 = healthy)
- `interval`: Time between checks (default: 30s)
- `timeout`: Max time for test to complete (default: 30s)
- `retries`: Consecutive failures before unhealthy (default: 3)
- `start_period`: Grace period before counting failures (default: 0s)
- `start_interval`: Time between checks during start period (default: 5s)

### 2. Common Health Check Commands

```yaml
# PostgreSQL
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres}"]
  interval: 5s
  timeout: 5s
  retries: 5

# MySQL/MariaDB
healthcheck:
  test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-u", "root", "-p${MYSQL_ROOT_PASSWORD}"]
  interval: 5s
  timeout: 5s
  retries: 5

# Redis
healthcheck:
  test: ["CMD", "redis-cli", "ping"]
  interval: 5s
  timeout: 3s
  retries: 5

# MongoDB
healthcheck:
  test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
  interval: 10s
  timeout: 5s
  retries: 5

# HTTP endpoint
healthcheck:
  test: ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"]
  interval: 10s
  timeout: 5s
  retries: 3
  start_period: 30s

# Custom app with nc (netcat)
healthcheck:
  test: ["CMD-SHELL", "nc -z localhost 3000 || exit 1"]
  interval: 10s
  timeout: 5s
  retries: 3
```

### 3. Environment Variables

**✅ Using env_file (RECOMMENDED)**
```yaml
services:
  app:
    image: myapp
    env_file:
      - .env              # Default environment
      - .env.production   # Override with prod-specific vars
```

**✅ Using environment block**
```yaml
services:
  app:
    image: myapp
    environment:
      NODE_ENV: production
      DATABASE_URL: postgres://user:${DB_PASSWORD}@db:5432/mydb
      REDIS_URL: redis://redis:6379
      LOG_LEVEL: ${LOG_LEVEL:-info}  # Default to 'info' if not set
```

**Best Practices:**
- Never commit secrets to git
- Use `.env` files (add to `.gitignore`)
- Provide `.env.example` with dummy values
- Use `${VAR:-default}` syntax for defaults
- Reference secrets via Docker secrets for production

### 4. Volumes: Named vs Bind Mounts

**Named Volumes (RECOMMENDED for data persistence)**
```yaml
services:
  db:
    image: postgres:16-alpine
    volumes:
      - db_data:/var/lib/postgresql/data  # ✅ Managed by Docker

volumes:
  db_data:  # Named volume definition
    driver: local
```

**Bind Mounts (for development)**
```yaml
services:
  app:
    image: node:20-alpine
    volumes:
      - ./src:/app/src:ro           # Read-only source code
      - ./node_modules:/app/node_modules  # Prevent overwrite
      - ./logs:/app/logs            # Log output
    working_dir: /app
```

**When to Use:**
- **Named volumes**: Database data, persistent app state, production
- **Bind mounts**: Source code (dev), config files, log collection

### 5. Network Configuration

**Default Bridge Network (automatic)**
```yaml
services:
  app:
    image: nginx
  db:
    image: postgres
  # Both can communicate via service names (app → db, db → app)
```

**Custom Networks (RECOMMENDED for isolation)**
```yaml
services:
  frontend:
    image: nginx
    networks:
      - frontend_net

  api:
    image: myapi
    networks:
      - frontend_net
      - backend_net

  db:
    image: postgres
    networks:
      - backend_net  # Only accessible to api, not frontend

networks:
  frontend_net:
    driver: bridge
  backend_net:
    driver: bridge
    internal: true  # No external internet access
```

**Network Aliases**
```yaml
services:
  api:
    image: myapi
    networks:
      backend:
        aliases:
          - api.internal
          - api-service
```

### 6. Resource Limits

**Modern Syntax (Compose V2, docker-compose 1.28+)**
```yaml
services:
  app:
    image: myapp
    cpus: "1.5"              # 1.5 CPU cores
    mem_limit: 1024M         # 1GB RAM hard limit
    mem_reservation: 512M    # 512MB soft limit

  db:
    image: postgres:16-alpine
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 2G
        reservations:
          cpus: "1.0"
          memory: 1G
```

**Best Practices:**
- Always set memory limits to prevent OOM crashes
- Use `mem_reservation` for soft limits
- CPU limits as decimal strings: "0.5", "1.5", "2.0"
- Memory units: `b`, `k`, `m`, `g` or `kb`, `mb`, `gb`

### 7. Port Mapping Patterns

```yaml
services:
  # Standard mapping
  web:
    ports:
      - "8080:80"           # host:container

  # Multiple ports
  api:
    ports:
      - "3000:3000"
      - "3001:3001"

  # Bind to specific interface
  db:
    ports:
      - "127.0.0.1:5432:5432"  # Only localhost access

  # Random host port
  app:
    ports:
      - "80"                # Docker assigns random host port

  # Protocol specification
  dns:
    ports:
      - "53:53/udp"
      - "53:53/tcp"

  # Internal only (no host exposure)
  cache:
    expose:
      - "6379"              # Accessible to other services, not host
```

## Complete Templates

### Template 1: Web App + PostgreSQL

```yaml
services:
  db:
    image: postgres:16-alpine
    container_name: myapp-db
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 10s
    environment:
      POSTGRES_USER: ${DB_USER:-postgres}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: ${DB_NAME:-myapp}
    volumes:
      - db_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    networks:
      - backend
    deploy:
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 512M

  app:
    image: myapp:latest
    container_name: myapp-web
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:3000/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 30s
    environment:
      NODE_ENV: production
      DATABASE_URL: postgres://${DB_USER:-postgres}:${DB_PASSWORD}@db:5432/${DB_NAME:-myapp}
      PORT: 3000
    ports:
      - "3000:3000"
    networks:
      - frontend
      - backend
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 512M

  nginx:
    image: nginx:alpine
    container_name: myapp-nginx
    restart: unless-stopped
    depends_on:
      app:
        condition: service_healthy
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    networks:
      - frontend

networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true

volumes:
  db_data:
    driver: local
```

### Template 2: App + Redis + PostgreSQL

```yaml
services:
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: myapp
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - backend

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    healthcheck:
      test: ["CMD", "redis-cli", "--raw", "incr", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    volumes:
      - redis_data:/data
    networks:
      - backend

  app:
    build: .
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 40s
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql://postgres:${DB_PASSWORD}@db:5432/myapp
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379
      CELERY_BROKER_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
    ports:
      - "8000:8000"
    volumes:
      - ./logs:/app/logs
      - media_files:/app/media
    networks:
      - frontend
      - backend
    cpus: "1.5"
    mem_limit: 1G

  worker:
    build: .
    restart: unless-stopped
    command: celery -A myapp worker --loglevel=info
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql://postgres:${DB_PASSWORD}@db:5432/myapp
      CELERY_BROKER_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
    volumes:
      - ./logs:/app/logs
    networks:
      - backend
    cpus: "1.0"
    mem_limit: 512M

networks:
  frontend:
  backend:
    internal: true

volumes:
  postgres_data:
  redis_data:
  media_files:
```

### Template 3: Microservices Architecture

```yaml
services:
  # API Gateway
  gateway:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "80:80"
    volumes:
      - ./gateway/nginx.conf:/etc/nginx/nginx.conf:ro
    networks:
      - frontend
    depends_on:
      - user-service
      - product-service
      - order-service

  # User Service
  user-service:
    build: ./services/user
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8001/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 3
    depends_on:
      user-db:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      DATABASE_URL: postgres://postgres:${DB_PASSWORD}@user-db:5432/users
      REDIS_URL: redis://redis:6379/0
      SERVICE_PORT: 8001
    networks:
      - frontend
      - user-backend
    cpus: "0.5"
    mem_limit: 512M

  user-db:
    image: postgres:16-alpine
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: users
    volumes:
      - user_db_data:/var/lib/postgresql/data
    networks:
      - user-backend

  # Product Service
  product-service:
    build: ./services/product
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8002/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 3
    depends_on:
      product-db:
        condition: service_healthy
    environment:
      DATABASE_URL: postgres://postgres:${DB_PASSWORD}@product-db:5432/products
      SERVICE_PORT: 8002
    networks:
      - frontend
      - product-backend
    cpus: "0.5"
    mem_limit: 512M

  product-db:
    image: postgres:16-alpine
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: products
    volumes:
      - product_db_data:/var/lib/postgresql/data
    networks:
      - product-backend

  # Order Service
  order-service:
    build: ./services/order
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8003/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 3
    depends_on:
      order-db:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    environment:
      DATABASE_URL: postgres://postgres:${DB_PASSWORD}@order-db:5432/orders
      RABBITMQ_URL: amqp://guest:${RABBITMQ_PASSWORD}@rabbitmq:5672/
      SERVICE_PORT: 8003
    networks:
      - frontend
      - order-backend
      - messaging
    cpus: "0.5"
    mem_limit: 512M

  order-db:
    image: postgres:16-alpine
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: orders
    volumes:
      - order_db_data:/var/lib/postgresql/data
    networks:
      - order-backend

  # Shared Services
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    volumes:
      - redis_data:/data
    networks:
      - user-backend
      - product-backend

  rabbitmq:
    image: rabbitmq:3-management-alpine
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "rabbitmq-diagnostics -q ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    environment:
      RABBITMQ_DEFAULT_USER: guest
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASSWORD}
    ports:
      - "15672:15672"  # Management UI
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    networks:
      - messaging

networks:
  frontend:
  user-backend:
    internal: true
  product-backend:
    internal: true
  order-backend:
    internal: true
  messaging:
    internal: true

volumes:
  user_db_data:
  product_db_data:
  order_db_data:
  redis_data:
  rabbitmq_data:
```

### Template 4: Development vs Production

**docker-compose.yml (base)**
```yaml
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      NODE_ENV: ${NODE_ENV:-development}
    volumes:
      - ./src:/app/src
    networks:
      - app-network

networks:
  app-network:
```

**docker-compose.override.yml (development - auto-loaded)**
```yaml
services:
  app:
    build:
      target: development
    command: npm run dev
    volumes:
      - ./src:/app/src
      - ./tests:/app/tests
      - /app/node_modules  # Prevent overwrite
    ports:
      - "3000:3000"
      - "9229:9229"  # Node debugger
    environment:
      DEBUG: "*"
      LOG_LEVEL: debug
```

**docker-compose.prod.yml (production)**
```yaml
services:
  app:
    build:
      target: production
    restart: unless-stopped
    command: npm start
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:3000/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    environment:
      NODE_ENV: production
      LOG_LEVEL: info
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 1G
        reservations:
          cpus: "1.0"
          memory: 512M

# Run with: docker compose -f docker-compose.yml -f docker-compose.prod.yml up
```

## Common Patterns

### Pattern: Init Containers

```yaml
services:
  db-init:
    image: postgres:16-alpine
    depends_on:
      db:
        condition: service_healthy
    command: >
      sh -c "
        psql -h db -U postgres -c 'CREATE DATABASE IF NOT EXISTS myapp;'
        psql -h db -U postgres myapp < /init.sql
      "
    volumes:
      - ./init.sql:/init.sql:ro
    environment:
      PGPASSWORD: ${DB_PASSWORD}
    networks:
      - backend
    restart: "no"  # Run once and exit

  app:
    depends_on:
      db-init:
        condition: service_completed_successfully
```

### Pattern: Volume Permissions

```yaml
services:
  app:
    image: node:20-alpine
    user: "1000:1000"  # Match host UID:GID
    volumes:
      - ./app:/app
    environment:
      # Fix permissions on startup
      FIXUID: 1000
      FIXGID: 1000
```

### Pattern: Secrets (Docker Swarm/Compose V2.17+)

```yaml
services:
  app:
    image: myapp
    secrets:
      - db_password
      - api_key
    environment:
      DB_PASSWORD_FILE: /run/secrets/db_password
      API_KEY_FILE: /run/secrets/api_key

secrets:
  db_password:
    file: ./secrets/db_password.txt
  api_key:
    file: ./secrets/api_key.txt
```

### Pattern: Multi-Stage Builds

```yaml
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
      target: ${BUILD_TARGET:-production}
      args:
        NODE_VERSION: 20
        BUILD_DATE: ${BUILD_DATE}
      cache_from:
        - myapp:latest
        - myapp:cache
```

## Troubleshooting

### Essential Debug Commands

```bash
# Validate compose file syntax
docker compose config

# Validate with detailed output
docker compose config --quiet

# View resolved configuration
docker compose config --resolve-image-digests

# Check service status
docker compose ps
docker compose ps --all  # Include stopped containers

# View logs
docker compose logs
docker compose logs -f service_name  # Follow logs
docker compose logs --tail=100 service_name
docker compose logs --since 30m

# Execute commands in running container
docker compose exec service_name sh
docker compose exec -u root service_name bash

# Run one-off command
docker compose run --rm service_name python manage.py migrate

# View resource usage
docker stats $(docker compose ps -q)

# Inspect networks
docker network ls
docker network inspect myproject_default

# Inspect volumes
docker volume ls
docker volume inspect myproject_db_data
```

### Common Errors & Fixes

#### 1. Port Already in Use

**Error:**
```
Error: Cannot start service web: Ports are not available:
listen tcp 0.0.0.0:8080: bind: address already in use
```

**Debug:**
```bash
# Find what's using the port
sudo lsof -i :8080
sudo netstat -tulnp | grep :8080
sudo ss -tulnp | grep :8080

# Kill the process
sudo kill -9 <PID>

# Or change port in compose file
ports:
  - "8081:80"  # Use different host port
```

#### 2. Service Dependency Race Condition

**Problem:** App crashes because DB isn't ready yet

**❌ Wrong:**
```yaml
app:
  depends_on:
    - db  # Only ensures container starts, not that DB is ready
```

**✅ Fix:**
```yaml
db:
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U postgres"]
    interval: 5s
    retries: 5

app:
  depends_on:
    db:
      condition: service_healthy  # Wait for health check
```

#### 3. Volume Permission Denied

**Error:**
```
Permission denied: '/var/lib/postgresql/data'
```

**Fixes:**

**Option 1: Match UIDs**
```yaml
services:
  db:
    image: postgres:16-alpine
    user: "1000:1000"  # Match your host user
    volumes:
      - db_data:/var/lib/postgresql/data
```

**Option 2: Use named volumes (recommended)**
```yaml
services:
  db:
    image: postgres:16-alpine
    volumes:
      - db_data:/var/lib/postgresql/data  # Docker manages permissions

volumes:
  db_data:
```

**Option 3: Fix host permissions**
```bash
# Change ownership of bind mount directory
sudo chown -R 1000:1000 ./data
chmod -R 755 ./data
```

**Option 4: Init container**
```yaml
services:
  init-permissions:
    image: alpine
    command: chown -R 999:999 /data  # Postgres UID
    volumes:
      - db_data:/data
    restart: "no"

  db:
    depends_on:
      init-permissions:
        condition: service_completed_successfully
    volumes:
      - db_data:/var/lib/postgresql/data
```

#### 4. Service Keeps Restarting

**Debug:**
```bash
# Check logs for crash reason
docker compose logs service_name

# Check last 50 lines
docker compose logs --tail=50 service_name

# See exit code
docker compose ps
# Look for "Exit X" where X is exit code
```

**Keep container alive for debugging:**
```yaml
services:
  app:
    # Override entrypoint to keep container running
    entrypoint: ["sh", "-c", "sleep 2073600"]
    # Then exec into it
    # docker compose exec app sh
```

#### 5. Network Connectivity Issues

**Services can't communicate:**

**Debug:**
```bash
# Check networks
docker network ls
docker network inspect myproject_default

# Test connectivity
docker compose exec app ping db
docker compose exec app nc -zv db 5432
docker compose exec app curl http://api:3000/health
```

**Fix: Ensure same network**
```yaml
services:
  app:
    networks:
      - backend
  db:
    networks:
      - backend  # Must be on same network

networks:
  backend:
```

#### 6. Build Cache Issues

**Problem:** Changes not reflected in build

```bash
# Rebuild without cache
docker compose build --no-cache

# Remove old images and rebuild
docker compose down --rmi all
docker compose build --pull
docker compose up
```

#### 7. YAML Syntax Errors

**Error:**
```
yaml: line 15: mapping values are not allowed in this context
```

**Common causes:**
- Incorrect indentation (use 2 spaces, not tabs)
- Missing quotes around strings with special chars
- Misaligned colons

**Validate:**
```bash
docker compose config  # Will show syntax errors
```

#### 8. Container OOM (Out of Memory)

**Check:**
```bash
# View container stats
docker stats

# Check logs for OOM killer
dmesg | grep -i "killed process"
```

**Fix:**
```yaml
services:
  app:
    mem_limit: 2G        # Increase limit
    mem_reservation: 1G  # Soft limit
```

### Network Troubleshooting

```bash
# Enter container network namespace
docker compose exec service_name sh

# Inside container:
# Install debugging tools (if needed)
apk add --no-cache curl netcat-openbsd bind-tools

# Test DNS resolution
nslookup db
dig db

# Test port connectivity
nc -zv db 5432

# Test HTTP endpoint
curl -v http://api:3000/health

# Check routing
ip route
```

### Volume Troubleshooting

```bash
# List volumes
docker volume ls

# Inspect volume
docker volume inspect myproject_db_data

# Check volume size
docker system df -v

# Backup volume
docker run --rm -v myproject_db_data:/data -v $(pwd):/backup alpine \
  tar czf /backup/db_backup.tar.gz -C /data .

# Restore volume
docker run --rm -v myproject_db_data:/data -v $(pwd):/backup alpine \
  tar xzf /backup/db_backup.tar.gz -C /data

# Remove unused volumes
docker volume prune
```

## Development Workflow

### Quick Start

```bash
# Start services
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down

# Stop and remove volumes
docker compose down -v

# Rebuild specific service
docker compose build app
docker compose up -d app
```

### Common Commands

```bash
# Start in foreground (Ctrl+C to stop)
docker compose up

# Start in background
docker compose up -d

# Stop without removing
docker compose stop

# Start stopped services
docker compose start

# Restart services
docker compose restart

# Restart specific service
docker compose restart app

# Scale service (creates replicas)
docker compose up -d --scale worker=3

# Remove stopped containers
docker compose rm

# Remove everything (containers, networks, NOT volumes)
docker compose down

# Remove everything including volumes
docker compose down -v

# Remove everything including images
docker compose down --rmi all

# Pull latest images
docker compose pull

# Build images
docker compose build

# Build with no cache
docker compose build --no-cache --pull
```

### Environment-Specific Runs

```bash
# Development (uses docker-compose.override.yml automatically)
docker compose up

# Production
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Testing
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm tests

# Use specific env file
docker compose --env-file .env.staging up
```

## Quick Reference

### File Structure

```
project/
├── docker-compose.yml          # Base configuration
├── docker-compose.override.yml # Development overrides (auto-loaded)
├── docker-compose.prod.yml     # Production configuration
├── docker-compose.test.yml     # Testing configuration
├── .env                        # Environment variables
├── .env.example                # Example env file (committed to git)
├── Dockerfile                  # Application build
└── services/
    ├── service1/
    │   └── Dockerfile
    └── service2/
        └── Dockerfile
```

### Modern V2 Checklist

- ✅ NO `version:` field at top
- ✅ Use `services:` (plural), not `service:`
- ✅ Start services directly under `services:`
- ✅ Use health checks with `depends_on: {condition: service_healthy}`
- ✅ Use named volumes for data persistence
- ✅ Set resource limits (`mem_limit`, `cpus`)
- ✅ Use custom networks for isolation
- ✅ Never commit secrets (use `.env` in `.gitignore`)
- ✅ Include `restart: unless-stopped` for production
- ✅ Use `docker compose` (space) not `docker-compose` (hyphen)

### Restart Policies

```yaml
services:
  app:
    restart: "no"              # Never restart (default)
    restart: always            # Always restart
    restart: on-failure        # Only on non-zero exit
    restart: on-failure:5      # Max 5 restart attempts
    restart: unless-stopped    # Always unless manually stopped (RECOMMENDED)
```

### Minimal Template

```yaml
services:
  app:
    image: nginx:alpine
    ports:
      - "80:80"
    restart: unless-stopped
```

---

When helping users with Docker Compose:
1. **Always omit the `version:` field** (obsolete in V2)
2. **Always use healthchecks with `depends_on`** for proper startup ordering
3. **Prefer named volumes** over bind mounts for data persistence
4. **Set resource limits** to prevent resource exhaustion
5. **Use custom networks** for service isolation
6. **Never hardcode secrets** - use env files or Docker secrets
7. **Include `restart: unless-stopped`** for production services
8. **Remember**: `docker compose` (space), not `docker-compose` (hyphen)
9. **Use 2-space indentation** consistently
10. **Validate with `docker compose config`** before deploying
