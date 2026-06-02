# Quack MCP Development Guidelines

This document outlines the development guidelines, coding conventions, and best practices for the Quack MCP server project.

## Project Overview

Quack MCP is a Model Context Protocol (MCP) server that provides CSV analysis capabilities using DuckDB. The project emphasizes type safety, performance, and maintainability through strict TypeScript configuration and clear architectural patterns.

## TypeScript Configuration

### Strict Mode Requirements

The project uses the strictest possible TypeScript configuration:

```json
{
  "compilerOptions": {
    "noEmit": true,
    "target": "esnext", 
    "module": "nodenext",
    "moduleResolution": "nodenext",
    "allowImportingTsExtensions": true,
    "rewriteRelativeImportExtensions": true,
    "erasableSyntaxOnly": true,
    "verbatimModuleSyntax": true,
    "strict": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true
  }
}
```

**Key Rules:**
- **All type annotations must be explicit** - No implicit `any` types
- **Strict null checks enabled** - Handle `undefined` and `null` explicitly
- **No unused variables or imports** - Clean, minimal code only
- **Consistent file naming** - Use kebab-case for files, PascalCase for classes

## Architecture Guidelines

### Class Structure

All classes follow a consistent structure:

```typescript
class QuackMCPServer {
  // 1. Private properties first
  private server: Server;
  private db: Database.Database;
  private loadedTables: Map<string, string> = new Map();

  // 2. Constructor
  constructor() {
    // Initialize properties
    this.setupToolHandlers();
  }

  // 3. Private setup methods
  private setupToolHandlers() {
    // Configuration logic
  }

  // 4. Public methods (tool handlers)
  async loadCSV(args: any) {
    // Implementation
  }

  // 5. Private utility methods
  private async executeQuery(query: string): Promise<any[]> {
    // Implementation
  }
}
```

### Method Naming Conventions

- **Tool handlers**: Use camelCase matching the tool name (`loadCSV`, `queryCSV`)
- **Private methods**: Use camelCase with descriptive names (`executeQuery`, `inspectTableSchema`)
- **Async methods**: Always mark as `async` and return `Promise<T>`

### Error Handling

All errors must be handled consistently using the MCP error system:

```typescript
try {
  // Operation
} catch (error) {
  throw new McpError(
    ErrorCode.InternalError,
    `Operation failed: ${error instanceof Error ? error.message : String(error)}`
  );
}
```

**Rules:**
- Always catch and wrap errors in `McpError`
- Provide descriptive error messages
- Use appropriate `ErrorCode` values
- Never let raw exceptions propagate

## Import/Export Standards

### Import Organization

Imports must be organized in this order:

```typescript
// 1. External libraries
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import Database from 'duckdb';

// 2. Node.js built-ins
import fs from 'fs/promises';
import path from 'path';

// 3. Internal modules (if any)
import { utility } from './utils.js';
```

### ES Modules Requirements

- All imports must use `.js` extensions (even for `.ts` files)
- Use ES module syntax exclusively (`import`/`export`)
- No CommonJS (`require`/`module.exports`)

### Export Patterns

```typescript
// Default export for main classes
export default class QuackMCPServer { }

// Named exports for utilities
export { QuackMCPServer };
```

## MCP Tool Implementation

### Tool Definition Schema

All tools must have complete JSON schema definitions:

```typescript
{
  name: 'tool_name',
  description: 'Clear, concise description of what this tool does',
  inputSchema: {
    type: 'object',
    properties: {
      required_param: {
        type: 'string',
        description: 'What this parameter does',
      },
      optional_param: {
        type: 'boolean', 
        description: 'What this parameter does (optional)',
        default: false,
      },
    },
    required: ['required_param'],
  },
}
```

**Schema Rules:**
- All parameters must have descriptions
- Use appropriate JSON Schema types (`string`, `boolean`, `array`, `object`)
- Specify `required` array for mandatory parameters
- Include `default` values for optional parameters
- Use `oneOf` for union types when appropriate

### Tool Handler Implementation

```typescript
async toolName(args: any) {
  try {
    // 1. Destructure and validate arguments
    const { required_param, optional_param = false } = args;
    
    // 2. Input validation
    if (!required_param) {
      throw new Error('required_param is required');
    }
    
    // 3. Business logic
    const result = await this.performOperation(required_param);
    
    // 4. Return MCP response format
    return {
      content: [
        {
          type: 'text',
          text: `Operation completed successfully: ${result}`,
        },
      ],
    };
  } catch (error) {
    throw new McpError(
      ErrorCode.InternalError,
      `Tool failed: ${error instanceof Error ? error.message : String(error)}`
    );
  }
}
```

## Database Operations

### Query Execution Pattern

```typescript
private async executeQuery(query: string): Promise<any[]> {
  return new Promise((resolve, reject) => {
    this.db.all(query, (err, result) => {
      if (err) {
        reject(err);
      } else {
        resolve(result);
      }
    });
  });
}
```

### SQL Query Construction

- **Use template literals** for query building
- **Always escape user input** using `replace(/'/g, "''")`
- **Use parameterized queries** when possible
- **Add query logging** for debugging: `console.error('Executing query:', query)`

```typescript
const escapedPath = file_path.replace(/'/g, "''");
const query = `
  CREATE OR REPLACE TABLE "${tableName}" AS 
  SELECT * FROM read_csv('${escapedPath}', 
    header=${header},
    delim='${delimiter}'
  )
`;
```

### Table Management

- **Validate table names**: Replace invalid characters with underscores
- **Check for empty results**: Drop tables with zero rows
- **Track loaded tables**: Use `this.loadedTables` Map for reference

```typescript
const tableName = table_name.replace(/[^a-zA-Z0-9_]/g, '_');

// Check if the table has any rows
const rowCountQuery = `SELECT COUNT(*) as row_count FROM "${tableName}"`;
const rowCountResult = await this.executeQuery(rowCountQuery);
const rowCount = Number(rowCountResult[0]?.row_count || 0);

if (rowCount === 0) {
  await this.executeQuery(`DROP TABLE IF EXISTS "${tableName}"`);
  throw new Error('No data was loaded from the CSV files');
}

this.loadedTables.set(tableName, file_path);
```

## Testing Standards

### Test File Organization

```
tests/
├── unit-test.test.ts          # Core functionality tests
├── integration.test.ts        # End-to-end integration tests  
├── multi-csv.test.ts          # Feature-specific tests
├── multi-csv-integration.test.ts # Feature integration tests
└── test-data.ts               # Shared test utilities
```

### Test Structure

```typescript
import { strict as assert } from 'assert';
import { test } from 'node:test';
import fs from 'fs/promises';
import path from 'path';
import os from 'os';

test('Feature description', async () => {
  // Setup
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'quack-mcp-test-'));
  
  // Test cases
  await test('should do specific thing', async () => {
    // Arrange
    // Act  
    // Assert
  });
  
  // Cleanup
  await fs.rm(tempDir, { recursive: true, force: true });
});
```

### Test Data Management

- **Create test data at runtime** - Don't rely on static files
- **Use temporary directories** for file-based tests
- **Clean up resources** after tests complete
- **Handle BigInt values** from DuckDB: `Number(result[0].count)`

### Assertion Patterns

```typescript
// DuckDB returns BigInt, convert for comparison
assert(Number(countResult[0].count) === 9, `Expected 9 rows, got ${countResult[0].count}`);

// Array assertions
assert(result.length >= 3, 'Should find at least 3 files');
assert(result.every((row: any) => row.file.endsWith('.csv')), 'All files should be CSV');

// Schema validation
const hasColumn = schemaResult.some((col: any) => col.column_name === 'expected_column');
assert(hasColumn, 'Should include expected column');
```

## File and Path Handling

### File System Operations

```typescript
// Always use fs/promises for async operations
import fs from 'fs/promises';

// Check file existence
try {
  await fs.access(file_path);
} catch (error) {
  throw new Error(`File not found: ${file_path}`);
}

// File metadata
const stats = await fs.stat(filePath);
const fileInfo = {
  size: stats.size,
  modified: stats.mtime.toISOString(),
};
```

### Path Normalization

```typescript
// Normalize paths for cross-platform compatibility
const globPattern = path.join(tempDir, 'sales_q*.csv').replace(/\\/g, '/');

// Use absolute paths for reliability
const absolutePath = path.resolve(relativePath);
```

### Glob Pattern Support

Support these standard glob patterns:
- `*` - matches any characters
- `**` - recursive directory matching
- `?` - single character (not supported for S3)
- `[abc]` - character sets
- `[a-z]` - character ranges

## Multi-CSV Feature Guidelines

### API Design

```typescript
// Flexible input - string or array
pattern_or_files: {
  oneOf: [
    { type: 'string', description: 'Glob pattern' },
    { type: 'array', items: { type: 'string' }, description: 'File list' }
  ]
}
```

### Implementation Pattern

```typescript
// Detect input type
if (typeof pattern_or_files === 'string') {
  // Handle glob pattern
  if (pattern_or_files.includes('*') || pattern_or_files.includes('?')) {
    // Use DuckDB glob discovery
    const globResult = await this.executeQuery(`SELECT file FROM glob('${pattern}')`);
  }
} else if (Array.isArray(pattern_or_files)) {
  // Handle file list
  for (const filePath of pattern_or_files) {
    await fs.access(filePath); // Validate existence
  }
}
```

### DuckDB Multi-File Features

Leverage DuckDB's native capabilities:

```typescript
// Glob patterns
SELECT * FROM read_csv('data/*.csv', header=true)

// File lists  
SELECT * FROM read_csv(['file1.csv', 'file2.csv'], header=true)

// Schema unification
SELECT * FROM read_csv('*.csv', header=true, union_by_name=true)

// Filename tracking
SELECT * FROM read_csv('*.csv', header=true, filename=true)
```

## Performance Guidelines

### Efficient Patterns

- **Leverage DuckDB's parallel processing** - Let DuckDB handle multiple files
- **Use schema detection sparingly** - Cache results when possible  
- **Batch operations** - Avoid multiple small queries
- **Stream large results** - Use appropriate limits for exploration

### Memory Management

```typescript
// Use in-memory database for temporary operations
this.db = new Database.Database(':memory:');

// Clean up empty tables
if (rowCount === 0) {
  await this.executeQuery(`DROP TABLE IF EXISTS "${tableName}"`);
}
```

## Documentation Standards

### Code Comments

- **Avoid inline comments** - Code should be self-documenting
- **Document complex business logic** - Explain the "why", not the "what"
- **Use JSDoc for public APIs** when needed

### Tool Documentation

Each tool requires:
- Clear description of purpose
- Parameter documentation with types
- Example usage patterns
- Error conditions

### README Maintenance

Keep README sections updated:
- Tool parameter lists
- Usage examples for all features  
- Docker configuration examples
- Troubleshooting guides

## Security Guidelines

### Input Validation

```typescript
// Validate file paths
if (file_path.includes('..')) {
  throw new Error('Path traversal not allowed');
}

// Escape SQL inputs
const escapedPath = file_path.replace(/'/g, "''");

// Validate table names
const tableName = table_name.replace(/[^a-zA-Z0-9_]/g, '_');
```

### Error Information

- **Don't expose internal paths** in error messages to users
- **Sanitize error messages** before returning
- **Log detailed errors** internally for debugging

## Deployment Guidelines

### Docker Considerations

- **Use Node.js 24 Alpine** base image
- **Install build dependencies** for native modules (DuckDB)
- **Run as non-root user** for security
- **Mount CSV data as read-only volumes**

### Environment Requirements

- **Node.js >= 24.0.0** (specified in package.json)
- **TypeScript in development** - Runtime uses Node.js directly
- **DuckDB native dependencies** - Ensure compatible build environment

## Development Workflow

### Before Committing

1. **Run tests**: `npm test`
2. **Run linter**: `npm run lint` 
3. **Verify TypeScript**: `tsc --noEmit`
4. **Test Docker build**: `docker build -t quack-mcp .`

### Code Review Checklist

- [ ] All new features have comprehensive tests
- [ ] Error handling follows MCP patterns
- [ ] TypeScript types are explicit and correct
- [ ] Documentation updated for public APIs
- [ ] Performance implications considered
- [ ] Security implications reviewed

This document serves as the authoritative guide for maintaining code quality and consistency across the Quack MCP project.