FROM node:24.5.0-alpine

# Install build dependencies for native modules (DuckDB)
RUN apk add --no-cache \
    python3 \
    make \
    g++ \
    libc6-compat

# Create app directory
WORKDIR /app

# Create non-root user
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci --only=production && npm cache clean --force

# Copy source code
COPY --chown=nodejs:nodejs src/ ./src/
COPY --chown=nodejs:nodejs tsconfig.json ./

# Switch to non-root user
USER nodejs

# Start the application
CMD ["node", "src/index.ts"]
