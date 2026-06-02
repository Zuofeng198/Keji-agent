import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ErrorCode,
  ListToolsRequestSchema,
  McpError,
} from '@modelcontextprotocol/sdk/types.js';
import Database from 'duckdb';
import fs from 'fs/promises';
import path from 'path';


export class QuackMCPServer {
  private server: Server;
  private db: Database.Database;
  private loadedTables: Map<string, string> = new Map();

  constructor() {
    this.server = new Server(
      {
        name: 'quack-mcp',
        version: '1.0.0',
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    this.db = new Database.Database(':memory:');
    this.setupToolHandlers();
  }

  private setupToolHandlers() {
    this.server.setRequestHandler(ListToolsRequestSchema, async () => ({
      tools: [
        {
          name: 'load_csv',
          description: 'Load a CSV file into DuckDB for analysis',
          inputSchema: {
            type: 'object',
            properties: {
              file_path: {
                type: 'string',
                description: 'Path to the CSV file to load',
              },
              table_name: {
                type: 'string',
                description: 'Name for the table (optional, defaults to filename)',
              },
              delimiter: {
                type: 'string',
                description: 'CSV delimiter (default: ",")',
                default: ',',
              },
              header: {
                type: 'boolean',
                description: 'Whether CSV has header row (default: true)',
                default: true,
              },
            },
            required: ['file_path'],
          },
        },
        {
          name: 'query_csv',
          description: 'Execute SQL query on loaded CSV data',
          inputSchema: {
            type: 'object',
            properties: {
              query: {
                type: 'string',
                description: 'SQL query to execute',
              },
            },
            required: ['query'],
          },
        },
        {
          name: 'describe_table',
          description: 'Get schema information for a loaded table',
          inputSchema: {
            type: 'object',
            properties: {
              table_name: {
                type: 'string',
                description: 'Name of the table to describe',
              },
            },
            required: ['table_name'],
          },
        },
        {
          name: 'list_tables',
          description: 'List all loaded tables',
          inputSchema: {
            type: 'object',
            properties: {},
          },
        },
        {
          name: 'analyze_csv',
          description: 'Perform basic statistical analysis on CSV data',
          inputSchema: {
            type: 'object',
            properties: {
              table_name: {
                type: 'string',
                description: 'Name of the table to analyze',
              },
              columns: {
                type: 'array',
                items: { type: 'string' },
                description: 'Specific columns to analyze (optional)',
              },
            },
            required: ['table_name'],
          },
        },
        {
          name: 'load_multiple_csvs',
          description: 'Load multiple CSV files using glob patterns or file lists into DuckDB for analysis',
          inputSchema: {
            type: 'object',
            properties: {
              pattern_or_files: {
                oneOf: [
                  {
                    type: 'string',
                    description: 'Glob pattern to match CSV files (e.g., "*.csv", "data/**/*.csv")',
                  },
                  {
                    type: 'array',
                    items: { type: 'string' },
                    description: 'Array of specific file paths to load',
                  },
                ],
                description: 'Glob pattern or array of file paths to load',
              },
              table_name: {
                type: 'string',
                description: 'Name for the combined table (optional, defaults to "multi_csv_data")',
              },
              union_by_name: {
                type: 'boolean',
                description: 'Combine files by column name instead of position (default: false)',
                default: false,
              },
              include_filename: {
                type: 'boolean',
                description: 'Include a filename column to track source file for each row (default: false)',
                default: false,
              },
              delimiter: {
                type: 'string',
                description: 'CSV delimiter (default: ",")',
                default: ',',
              },
              header: {
                type: 'boolean',
                description: 'Whether CSV files have header rows (default: true)',
                default: true,
              },
            },
            required: ['pattern_or_files'],
          },
        },
        {
          name: 'discover_csv_files',
          description: 'Discover CSV files matching a glob pattern',
          inputSchema: {
            type: 'object',
            properties: {
              pattern: {
                type: 'string',
                description: 'Glob pattern to search for CSV files (e.g., "*.csv", "data/**/*.csv")',
              },
            },
            required: ['pattern'],
          },
        },
        {
          name: 'optimize_expenses',
          description: 'Analyze credit card spending data to identify expense optimization opportunities with actionable recommendations and savings estimates',
          inputSchema: {
            type: 'object',
            properties: {
              table_name: {
                type: 'string',
                description: 'Name of the table containing transaction data',
              },
              amount_column: {
                type: 'string',
                description: 'Name of the column containing transaction amounts',
                default: 'Amount',
              },
              name_column: {
                type: 'string',
                description: 'Name of the column containing merchant/transaction names',
                default: 'Name',
              },
              date_column: {
                type: 'string',
                description: 'Name of the column containing transaction dates',
                default: 'Date',
              },
            },
            required: ['table_name'],
          },
        },
        {
          name: 'detect_anomalies',
          description: 'Detect anomalies and irregularities in dataset using statistical analysis and business logic rules',
          inputSchema: {
            type: 'object',
            properties: {
              table_name: {
                type: 'string',
                description: 'Name of the table to analyze for anomalies',
              },
              severity_threshold: {
                type: 'string',
                description: 'Minimum severity level to report (low, medium, high, critical)',
                default: 'medium',
                enum: ['low', 'medium', 'high', 'critical'],
              },
              focus_columns: {
                type: 'array',
                items: { type: 'string' },
                description: 'Specific columns to focus anomaly detection on (optional)',
              },
              anomaly_types: {
                type: 'array',
                items: { type: 'string' },
                description: 'Types of anomalies to detect: statistical, duplicates, nulls, outliers, patterns, business_logic',
                default: ['statistical', 'duplicates', 'nulls', 'outliers', 'patterns'],
              },
            },
            required: ['table_name'],
          },
        },
        {
          name: 'load_excel',
          description: 'Load an Excel (.xlsx) file into DuckDB for analysis',
          inputSchema: {
            type: 'object',
            properties: {
              file_path: {
                type: 'string',
                description: 'Path to the Excel file to load',
              },
              table_name: {
                type: 'string',
                description: 'Name for the table (optional, defaults to filename)',
              },
              sheet: {
                type: 'string',
                description: 'Name or index of the sheet to load (optional, defaults to first sheet)',
              },
              range: {
                type: 'string',
                description: 'Cell range to load (e.g., "A1:C10") (optional, loads all data by default)',
              },
              header: {
                type: 'boolean',
                description: 'Whether Excel file has header row (default: true)',
                default: true,
              },
              all_varchar: {
                type: 'boolean',
                description: 'Force all columns to be treated as text (default: false)',
                default: false,
              },
            },
            required: ['file_path'],
          },
        },
        {
          name: 'load_multiple_excels',
          description: 'Load multiple Excel files using glob patterns or file lists into DuckDB for analysis',
          inputSchema: {
            type: 'object',
            properties: {
              pattern_or_files: {
                oneOf: [
                  {
                    type: 'string',
                    description: 'Glob pattern to match Excel files (e.g., "*.xlsx", "data/**/*.xlsx")',
                  },
                  {
                    type: 'array',
                    items: { type: 'string' },
                    description: 'Array of specific Excel file paths to load',
                  },
                ],
                description: 'Glob pattern or array of file paths to load',
              },
              table_name: {
                type: 'string',
                description: 'Name for the combined table (optional, defaults to "multi_excel_data")',
              },
              union_by_name: {
                type: 'boolean',
                description: 'Combine files by column name instead of position (default: false)',
                default: false,
              },
              include_filename: {
                type: 'boolean',
                description: 'Include a filename column to track source file for each row (default: false)',
                default: false,
              },
              sheet: {
                type: 'string',
                description: 'Name or index of the sheet to load from all files (optional, defaults to first sheet)',
              },
              header: {
                type: 'boolean',
                description: 'Whether Excel files have header rows (default: true)',
                default: true,
              },
              all_varchar: {
                type: 'boolean',
                description: 'Force all columns to be treated as text (default: false)',
                default: false,
              },
            },
            required: ['pattern_or_files'],
          },
        },
        {
          name: 'discover_excel_files',
          description: 'Discover Excel files matching a glob pattern',
          inputSchema: {
            type: 'object',
            properties: {
              pattern: {
                type: 'string',
                description: 'Glob pattern to search for Excel files (e.g., "*.xlsx", "data/**/*.xlsx")',
              },
            },
            required: ['pattern'],
          },
        },
        {
          name: 'export_csv',
          description: 'Export a loaded table to a CSV file on disk',
          inputSchema: {
            type: 'object',
            properties: {
              table_name: {
                type: 'string',
                description: 'Name of the loaded table to export',
              },
              save_path: {
                type: 'string',
                description: 'Path where the CSV file will be saved',
              },
              delimiter: {
                type: 'string',
                description: 'CSV delimiter (default: ",")',
                default: ',',
              },
            },
            required: ['table_name', 'save_path'],
          },
        },
        {
          name: 'export_json',
          description: 'Export SQL query results to a JSON file on disk',
          inputSchema: {
            type: 'object',
            properties: {
              query: {
                type: 'string',
                description: 'SQL query to execute and export',
              },
              save_path: {
                type: 'string',
                description: 'Path where the JSON file will be saved',
              },
              pretty: {
                type: 'boolean',
                description: 'Pretty-print JSON output (default: false)',
                default: false,
              },
            },
            required: ['query', 'save_path'],
          },
        },
        {
          name: 'attach_database',
          description: 'Attach a persistent DuckDB database file for cross-database queries. Use this to connect to existing .db or .duckdb files and query them alongside loaded CSV data.',
          inputSchema: {
            type: 'object',
            properties: {
              db_path: {
                type: 'string',
                description: 'Path to the DuckDB database file (.db or .duckdb)',
              },
              alias: {
                type: 'string',
                description: 'Alias for the attached database (optional, defaults to filename without extension)',
              },
            },
            required: ['db_path'],
          },
        },
      ],
    }));

    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      switch (request.params.name) {
        case 'load_csv':
          return await this.loadCSV(request.params.arguments);
        case 'query_csv':
          return await this.queryCSV(request.params.arguments);
        case 'describe_table':
          return await this.describeTable(request.params.arguments);
        case 'list_tables':
          return await this.listTables();
        case 'analyze_csv':
          return await this.analyzeCSV(request.params.arguments);
        case 'load_multiple_csvs':
          return await this.loadMultipleCSVs(request.params.arguments);
        case 'discover_csv_files':
          return await this.discoverCSVFiles(request.params.arguments);
        case 'optimize_expenses':
          return await this.optimizeExpenses(request.params.arguments);
        case 'detect_anomalies':
          return await this.detectAnomalies(request.params.arguments);
        case 'load_excel':
          return await this.loadExcel(request.params.arguments);
        case 'load_multiple_excels':
          return await this.loadMultipleExcels(request.params.arguments);
        case 'discover_excel_files':
          return await this.discoverExcelFiles(request.params.arguments);
        case 'export_csv':
          return await this.exportCSV(request.params.arguments);
        case 'export_json':
          return await this.exportJSON(request.params.arguments);
        case 'attach_database':
          return await this.attachDatabase(request.params.arguments);
        default:
          throw new McpError(
            ErrorCode.MethodNotFound,
            `Unknown tool: ${request.params.name}`
          );
      }
    });
  }

  /** Normalize file path for DuckDB SQL: convert backslashes to forward slashes */
  private _sqlPath(file_path: string): string {
    return file_path.replace(/'/g, "''").replace(/\\/g, '/');
  }

  async loadCSV(args: any) {
    try {
      const file_path = args.file_path || args.path || '';
      const table_name = args.table_name || args.table || '';
      const header = args.header !== undefined ? args.header : true;
      const delimiter = args.delimiter;

      // Detect if file_path contains glob patterns
      const isGlobPattern = file_path.includes('*') || file_path.includes('?') || file_path.includes('[');

      if (isGlobPattern) {
        // Use glob pattern - first discover files
        const globQuery = `SELECT file FROM glob('${this._sqlPath(file_path)}')`;
        const globResult = await this.executeQuery(globQuery);
        const discoveredFiles = globResult.map((row: any) => row.file);

        if (discoveredFiles.length === 0) {
          throw new Error(`No CSV files found matching pattern: ${file_path}`);
        }

        // Generate table name from pattern if not provided
        const tableName = table_name || `csv_${file_path.replace(/[^a-zA-Z0-9_]/g, '_')}`;

        // Build query for multiple files
        const escapedPath = this._sqlPath(file_path);
        let query: string;

        if (delimiter) {
          query = `
            CREATE OR REPLACE TABLE "${tableName}" AS 
            SELECT * FROM read_csv('${escapedPath}', 
              header=${header},
              delim='${delimiter}'
            )
          `;
        } else {
          query = `
            CREATE OR REPLACE TABLE "${tableName}" AS 
            SELECT * FROM read_csv('${escapedPath}', 
              header=${header}
            )
          `;
        }

        console.error('Executing glob CSV query:', query);
        await this.executeQuery(query);

        // Check if the table has any rows
        const rowCountQuery = `SELECT COUNT(*) as row_count FROM "${tableName}"`;
        const rowCountResult = await this.executeQuery(rowCountQuery);
        const rowCount = Number(rowCountResult[0]?.row_count || 0);

        if (rowCount === 0) {
          await this.executeQuery(`DROP TABLE IF EXISTS "${tableName}"`);
          throw new Error('No data was loaded from the CSV files');
        }

        this.loadedTables.set(tableName, file_path);

        // Automatically inspect the schema and data
        const schemaInfo = await this.inspectTableSchema(tableName);

        return {
          content: [
            {
              type: 'text',
              text: `Successfully loaded ${discoveredFiles.length} CSV files matching "${file_path}" as table "${tableName}"\n\nFiles: ${discoveredFiles.slice(0, 5).join(', ')}${discoveredFiles.length > 5 ? '...' : ''}\n\n${schemaInfo}`,
            },
          ],
        };
      } else {
        // Single file mode (original behavior)

        // Check if file exists
        await fs.access(file_path);

        const tableName = table_name || path.basename(file_path, path.extname(file_path)).replace(/[^a-zA-Z0-9_]/g, '_');

        // Build query for single file
        const escapedPath = this._sqlPath(file_path);
        let query: string;

        if (delimiter) {
          query = `
            CREATE OR REPLACE TABLE "${tableName}" AS 
            SELECT * FROM read_csv('${escapedPath}', 
              header=${header},
              delim='${delimiter}'
            )
          `;
        } else {
          query = `
            CREATE OR REPLACE TABLE "${tableName}" AS 
            SELECT * FROM read_csv('${escapedPath}', 
              header=${header}
            )
          `;
        }

        console.error('Executing single CSV query:', query);
        await this.executeQuery(query);

        // Check if the table has any rows
        const rowCountQuery = `SELECT COUNT(*) as row_count FROM "${tableName}"`;
        const rowCountResult = await this.executeQuery(rowCountQuery);
        const rowCount = Number(rowCountResult[0]?.row_count || 0);

        if (rowCount === 0) {
          // Drop the empty table to clean up
          await this.executeQuery(`DROP TABLE IF EXISTS "${tableName}"`);
          throw new Error('CSV file is empty or contains no valid data');
        }

        this.loadedTables.set(tableName, file_path);

        // Automatically inspect the schema and data
        const schemaInfo = await this.inspectTableSchema(tableName);

        return {
          content: [
            {
              type: 'text',
              text: `Successfully loaded CSV file "${file_path}" as table "${tableName}"\n\n${schemaInfo}`,
            },
          ],
        };
      }
    } catch (error) {
      throw new McpError(
        ErrorCode.InternalError,
        `Failed to load CSV: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  private async queryCSV(args: any) {
    try {
      const query = args.query || args.sql || args.statement || '';
      if (!query) throw new Error('SQL query expected');
      const result = await this.executeQuery(query);

      return {
        content: [
          {
            type: 'text',
            text: this.safeStringify(result, null, 2),
          },
        ],
      };
    } catch (error) {
      throw new McpError(
        ErrorCode.InternalError,
        `Query failed: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  private async describeTable(args: any) {
    try {
      const table_name = args.table_name || args.table || args.name || '';
      if (!table_name) throw new Error('table_name is required');
      const result = await this.executeQuery(`DESCRIBE "${table_name}"`);

      return {
        content: [
          {
            type: 'text',
            text: `Schema for table "${table_name}":\n${this.safeStringify(result, null, 2)}`,
          },
        ],
      };
    } catch (error) {
      throw new McpError(
        ErrorCode.InternalError,
        `Failed to describe table: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  private async listTables() {
    try {
      const tables = Array.from(this.loadedTables.entries()).map(([name, path]) => ({
        table_name: name,
        file_path: path,
      }));

      return {
        content: [
          {
            type: 'text',
            text: `Loaded tables:\n${this.safeStringify(tables, null, 2)}`,
          },
        ],
      };
    } catch (error) {
      throw new McpError(
        ErrorCode.InternalError,
        `Failed to list tables: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  private async analyzeCSV(args: any) {
    try {
      const { table_name, columns } = args;

      let query: string;
      if (columns && columns.length > 0) {
        const columnStats = columns
          .map((col: string) => `
            COUNT(${col}) as ${col}_count,
            COUNT(DISTINCT ${col}) as ${col}_unique,
            MIN(${col}) as ${col}_min,
            MAX(${col}) as ${col}_max,
            AVG(TRY_CAST(${col} AS DOUBLE)) as ${col}_avg
          `)
          .join(',');
        query = `SELECT ${columnStats} FROM ${table_name}`;
      } else {
        query = `
          SELECT 
            COUNT(*) as total_rows,
            COUNT(*) - COUNT(*) as missing_values
          FROM ${table_name}
        `;
      }

      const result = await this.executeQuery(query);

      return {
        content: [
          {
            type: 'text',
            text: `Analysis for table "${table_name}":\n${this.safeStringify(result, null, 2)}`,
          },
        ],
      };
    } catch (error) {
      throw new McpError(
        ErrorCode.InternalError,
        `Analysis failed: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  private async loadMultipleCSVs(args: any) {
    try {
      const pattern_or_files = args.pattern_or_files || args.path || args.file_path || args.pattern || '';
      const table_name = args.table_name || args.table || 'multi_csv_data';
      const union_by_name = args.union_by_name !== undefined ? args.union_by_name : false;
      const include_filename = args.include_filename !== undefined ? args.include_filename : false;
      const delimiter = args.delimiter || ',';
      const header = args.header !== undefined ? args.header : true;

      // Validate table name
      const tableName = table_name.replace(/[^a-zA-Z0-9_]/g, '_');

      let discoveredFiles: string[] = [];

      if (typeof pattern_or_files === 'string') {
        // Discover files if it's a glob pattern
        if (pattern_or_files.includes('*') || pattern_or_files.includes('?') || pattern_or_files.includes('[')) {
          const globQuery = `SELECT file FROM glob('${pattern_or_files.replace(/'/g, "''")}')`;
          const globResult = await this.executeQuery(globQuery);
          discoveredFiles = globResult.map((row: any) => row.file);

          if (discoveredFiles.length === 0) {
            throw new Error(`No CSV files found matching pattern: ${pattern_or_files}`);
          }
        }
      } else if (Array.isArray(pattern_or_files)) {
        // For arrays, we'll create a list format that DuckDB can handle
        discoveredFiles = pattern_or_files;

        // Check if all files exist
        for (const filePath of pattern_or_files) {
          try {
            await fs.access(filePath);
          } catch {
            throw new Error(`File not found: ${filePath}`);
          }
        }
      } else {
        throw new Error('pattern_or_files must be a string (glob pattern) or array of file paths');
      }

      // Build the DuckDB query based on input type
      let query: string;

      if (typeof pattern_or_files === 'string') {
        // Use direct string for glob patterns
        const escapedPattern = this._sqlPath(pattern_or_files);
        query = `
          CREATE OR REPLACE TABLE "${tableName}" AS 
          SELECT * FROM read_csv('${escapedPattern}',
            header=${header},
            delim='${delimiter}',
            union_by_name=${union_by_name},
            filename=${include_filename}
          )
        `;
      } else {
        // Use array format for file lists
        const fileList = pattern_or_files.map(f => `'${this._sqlPath(f)}'`).join(', ');
        query = `
          CREATE OR REPLACE TABLE "${tableName}" AS 
          SELECT * FROM read_csv([${fileList}],
            header=${header},
            delim='${delimiter}',
            union_by_name=${union_by_name},
            filename=${include_filename}
          )
        `;
      }

      console.error('Executing multi-CSV query:', query);
      await this.executeQuery(query);

      // Check if the table has any rows
      const rowCountQuery = `SELECT COUNT(*) as row_count FROM "${tableName}"`;
      const rowCountResult = await this.executeQuery(rowCountQuery);
      const rowCount = Number(rowCountResult[0]?.row_count || 0);

      if (rowCount === 0) {
        await this.executeQuery(`DROP TABLE IF EXISTS "${tableName}"`);
        throw new Error('No data was loaded from the CSV files');
      }

      // Store the table reference
      this.loadedTables.set(tableName, typeof pattern_or_files === 'string' ? pattern_or_files : pattern_or_files.join(', '));

      // Get schema and sample information
      const schemaInfo = await this.inspectTableSchema(tableName);

      const fileCountText = discoveredFiles.length > 0
        ? `${discoveredFiles.length} files`
        : 'multiple files';

      return {
        content: [
          {
            type: 'text',
            text: `Successfully loaded ${fileCountText} as table "${tableName}"\n\nFiles processed: ${discoveredFiles.length > 0 ? discoveredFiles.slice(0, 10).join(', ') + (discoveredFiles.length > 10 ? '...' : '') : 'matched by pattern'}\n\n${schemaInfo}`,
          },
        ],
      };
    } catch (error) {
      throw new McpError(
        ErrorCode.InternalError,
        `Multi-CSV loading failed: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  private async discoverCSVFiles(args: any) {
    try {
      const { pattern } = args;

      // Use DuckDB's glob function to find matching files
      const query = `SELECT file FROM glob('${pattern.replace(/'/g, "''")}') ORDER BY file`;
      const result = await this.executeQuery(query);

      const files = result.map((row: any) => row.file);

      // Get additional file info if possible
      const fileInfo = await Promise.all(files.map(async (filePath: string) => {
        try {
          const stats = await fs.stat(filePath);
          return {
            path: filePath,
            size: stats.size,
            modified: stats.mtime.toISOString(),
            exists: true
          };
        } catch (error) {
          return {
            path: filePath,
            size: 0,
            modified: null,
            exists: false,
            error: error instanceof Error ? error.message : 'Unknown error'
          };
        }
      }));

      const totalSize = fileInfo.reduce((sum, info) => sum + (info.exists ? info.size : 0), 0);
      const existingFiles = fileInfo.filter(info => info.exists);

      return {
        content: [
          {
            type: 'text',
            text: `Found ${files.length} files matching pattern "${pattern}"\n\nExisting files: ${existingFiles.length}\nTotal size: ${(totalSize / 1024 / 1024).toFixed(2)} MB\n\nFile Details:\n${fileInfo.map(info =>
              `- ${info.path} (${info.exists ? `${(info.size / 1024).toFixed(1)} KB, modified: ${info.modified}` : 'NOT FOUND'})`
            ).join('\n')}`,
          },
        ],
      };
    } catch (error) {
      throw new McpError(
        ErrorCode.InternalError,
        `CSV file discovery failed: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  async optimizeExpenses(args: any) {
    try {
      const {
        table_name,
        amount_column = 'Amount',
        name_column = 'Name',
        date_column = 'Date'
      } = args;

      const report = await this.generateExpenseOptimizationReport(
        table_name,
        amount_column,
        name_column,
        date_column
      );

      return {
        content: [
          {
            type: 'text',
            text: report,
          },
        ],
      };
    } catch (error) {
      throw new McpError(
        ErrorCode.InternalError,
        `Expense optimization failed: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  async detectAnomalies(args: any) {
    try {
      const {
        table_name,
        severity_threshold = 'medium',
        focus_columns = [],
        anomaly_types = ['statistical', 'duplicates', 'nulls', 'outliers', 'patterns']
      } = args;

      const report = await this.generateAnomalyReport(
        table_name,
        severity_threshold,
        focus_columns,
        anomaly_types
      );

      return {
        content: [
          {
            type: 'text',
            text: report,
          },
        ],
      };
    } catch (error) {
      throw new McpError(
        ErrorCode.InternalError,
        `Anomaly detection failed: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  async loadExcel(args: any) {
    try {
      const { file_path, table_name, sheet, range, header = true, all_varchar = false } = args;

      // Validate file extension
      if (!file_path.toLowerCase().endsWith('.xlsx')) {
        throw new Error('Only .xlsx files are supported. Please convert .xls files to .xlsx format.');
      }

      // Check if file exists
      await fs.access(file_path);

      // Ensure Excel extension is loaded
      await this.#ensureExcelExtension();

      const tableName = table_name || path.basename(file_path, path.extname(file_path)).replace(/[^a-zA-Z0-9_]/g, '_');

      // Build query parameters
      const escapedPath = this._sqlPath(file_path);
      const queryParams: string[] = [`'${escapedPath}'`];

      // Add optional parameters
      const options: string[] = [];
      if (sheet) options.push(`sheet='${sheet.replace(/'/g, "''")}'`);
      if (range) options.push(`range='${range.replace(/'/g, "''")}'`);
      options.push(`header=${header}`);
      if (all_varchar) options.push(`all_varchar=${all_varchar}`);

      const optionsStr = options.length > 0 ? `, ${options.join(', ')}` : '';

      const query = `
        CREATE OR REPLACE TABLE "${tableName}" AS 
        SELECT * FROM read_xlsx(${queryParams[0]}${optionsStr})
      `;

      console.error('Executing Excel query:', query);
      await this.executeQuery(query);

      // Check if the table has any rows
      const rowCountQuery = `SELECT COUNT(*) as row_count FROM "${tableName}"`;
      const rowCountResult = await this.executeQuery(rowCountQuery);
      const rowCount = Number(rowCountResult[0]?.row_count || 0);

      if (rowCount === 0) {
        await this.executeQuery(`DROP TABLE IF EXISTS "${tableName}"`);
        throw new Error('Excel file is empty or contains no valid data in the specified sheet/range');
      }

      this.loadedTables.set(tableName, file_path);

      // Automatically inspect the schema and data
      const schemaInfo = await this.inspectTableSchema(tableName);

      const sheetInfo = sheet ? ` (sheet: ${sheet})` : '';
      const rangeInfo = range ? ` (range: ${range})` : '';

      return {
        content: [
          {
            type: 'text',
            text: `Successfully loaded Excel file "${file_path}"${sheetInfo}${rangeInfo} as table "${tableName}"\n\n${schemaInfo}`,
          },
        ],
      };
    } catch (error) {
      throw new McpError(
        ErrorCode.InternalError,
        `Failed to load Excel: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  async loadMultipleExcels(args: any) {
    try {
      const {
        pattern_or_files,
        table_name = 'multi_excel_data',
        union_by_name = false,
        include_filename = false,
        sheet,
        header = true,
        all_varchar = false
      } = args;

      // Validate table name
      const tableName = table_name.replace(/[^a-zA-Z0-9_]/g, '_');

      let discoveredFiles: string[] = [];

      if (typeof pattern_or_files === 'string') {
        // Discover files if it's a glob pattern
        if (pattern_or_files.includes('*') || pattern_or_files.includes('?') || pattern_or_files.includes('[')) {
          const globQuery = `SELECT file FROM glob('${pattern_or_files.replace(/'/g, "''")}')`;
          const globResult = await this.executeQuery(globQuery);
          discoveredFiles = globResult.map((row: any) => row.file);

          if (discoveredFiles.length === 0) {
            throw new Error(`No Excel files found matching pattern: ${pattern_or_files}`);
          }
        } else {
          // Single file path - validate it's xlsx and exists
          if (!pattern_or_files.toLowerCase().endsWith('.xlsx')) {
            throw new Error('Only .xlsx files are supported. Please convert .xls files to .xlsx format.');
          }
          try {
            await fs.access(pattern_or_files);
          } catch {
            throw new Error(`File not found: ${pattern_or_files}`);
          }
          discoveredFiles = [pattern_or_files];
        }
      } else if (Array.isArray(pattern_or_files)) {
        discoveredFiles = pattern_or_files;

        // Check if all files exist and are xlsx files
        for (const filePath of pattern_or_files) {
          if (!filePath.toLowerCase().endsWith('.xlsx')) {
            throw new Error(`Only .xlsx files are supported. Found non-xlsx file: ${filePath}`);
          }
          try {
            await fs.access(filePath);
          } catch {
            throw new Error(`File not found: ${filePath}`);
          }
        }
      } else {
        throw new Error('pattern_or_files must be a string (glob pattern) or array of file paths');
      }

      // Validate that we found xlsx files
      const nonXlsxFiles = discoveredFiles.filter(file => !file.toLowerCase().endsWith('.xlsx'));
      if (nonXlsxFiles.length > 0) {
        throw new Error(`Found non-xlsx files: ${nonXlsxFiles.join(', ')}. Only .xlsx files are supported.`);
      }

      // Ensure Excel extension is loaded
      await this.#ensureExcelExtension();

      // Build the DuckDB query based on input type
      let query: string;

      if (typeof pattern_or_files === 'string' && pattern_or_files.includes('*')) {
        // Use direct string for glob patterns
        const escapedPattern = pattern_or_files.replace(/'/g, "''");
        const options: string[] = [];
        if (sheet) options.push(`sheet='${sheet.replace(/'/g, "''")}'`);
        options.push(`header=${header}`);
        options.push(`union_by_name=${union_by_name}`);
        options.push(`filename=${include_filename}`);
        if (all_varchar) options.push(`all_varchar=${all_varchar}`);

        const optionsStr = options.join(', ');
        query = `
          CREATE OR REPLACE TABLE "${tableName}" AS 
          SELECT * FROM read_xlsx('${escapedPattern}', ${optionsStr})
        `;
      } else {
        // Use array format for file lists
        const fileList = discoveredFiles.map(f => `'${f.replace(/'/g, "''")}'`).join(', ');
        const options: string[] = [];
        if (sheet) options.push(`sheet='${sheet.replace(/'/g, "''")}'`);
        options.push(`header=${header}`);
        options.push(`union_by_name=${union_by_name}`);
        options.push(`filename=${include_filename}`);
        if (all_varchar) options.push(`all_varchar=${all_varchar}`);

        const optionsStr = options.join(', ');
        query = `
          CREATE OR REPLACE TABLE "${tableName}" AS 
          SELECT * FROM read_xlsx([${fileList}], ${optionsStr})
        `;
      }

      console.error('Executing multi-Excel query:', query);
      await this.executeQuery(query);

      // Check if the table has any rows
      const rowCountQuery = `SELECT COUNT(*) as row_count FROM "${tableName}"`;
      const rowCountResult = await this.executeQuery(rowCountQuery);
      const rowCount = Number(rowCountResult[0]?.row_count || 0);

      if (rowCount === 0) {
        await this.executeQuery(`DROP TABLE IF EXISTS "${tableName}"`);
        throw new Error('No data was loaded from the Excel files');
      }

      // Store the table reference
      this.loadedTables.set(tableName, typeof pattern_or_files === 'string' ? pattern_or_files : pattern_or_files.join(', '));

      // Get schema and sample information
      const schemaInfo = await this.inspectTableSchema(tableName);

      const fileCountText = discoveredFiles.length > 0
        ? `${discoveredFiles.length} files`
        : 'multiple files';

      const sheetInfo = sheet ? ` (sheet: ${sheet})` : '';

      return {
        content: [
          {
            type: 'text',
            text: `Successfully loaded ${fileCountText} Excel files${sheetInfo} as table "${tableName}"\n\nFiles processed: ${discoveredFiles.length > 0 ? discoveredFiles.slice(0, 10).join(', ') + (discoveredFiles.length > 10 ? '...' : '') : 'matched by pattern'}\n\n${schemaInfo}`,
          },
        ],
      };
    } catch (error) {
      throw new McpError(
        ErrorCode.InternalError,
        `Multi-Excel loading failed: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  async discoverExcelFiles(args: any) {
    try {
      const { pattern } = args;

      // Use DuckDB's glob function to find matching files
      const query = `SELECT file FROM glob('${pattern.replace(/'/g, "''")}') ORDER BY file`;
      const result = await this.executeQuery(query);

      const files = result.map((row: any) => row.file);

      // Filter to only Excel files and get additional info
      const excelFiles = files.filter(file => file.toLowerCase().endsWith('.xlsx'));
      const nonExcelFiles = files.filter(file => !file.toLowerCase().endsWith('.xlsx'));

      // Get additional file info for Excel files
      const fileInfo = await Promise.all(excelFiles.map(async (filePath: string) => {
        try {
          const stats = await fs.stat(filePath);
          return {
            path: filePath,
            size: stats.size,
            modified: stats.mtime.toISOString(),
            exists: true
          };
        } catch (error) {
          return {
            path: filePath,
            size: 0,
            modified: null,
            exists: false,
            error: error instanceof Error ? error.message : 'Unknown error'
          };
        }
      }));

      const totalSize = fileInfo.reduce((sum, info) => sum + (info.exists ? info.size : 0), 0);
      const existingFiles = fileInfo.filter(info => info.exists);

      let response = `Found ${files.length} files matching pattern "${pattern}"\n\n`;
      response += `Excel files (.xlsx): ${excelFiles.length}\n`;
      response += `Other files: ${nonExcelFiles.length}\n`;

      if (excelFiles.length > 0) {
        response += `Existing Excel files: ${existingFiles.length}\n`;
        response += `Total Excel file size: ${(totalSize / 1024 / 1024).toFixed(2)} MB\n\n`;
      }

      if (nonExcelFiles.length > 0) {
        response += `\n⚠️  Non-Excel files found (will be ignored by Excel tools):\n`;
        nonExcelFiles.slice(0, 5).forEach(file => {
          response += `- ${file}\n`;
        });
        if (nonExcelFiles.length > 5) {
          response += `... and ${nonExcelFiles.length - 5} more\n`;
        }
      }

      if (excelFiles.length > 0) {
        response += `\n📊 Excel File Details:\n`;
        fileInfo.forEach(info => {
          response += `- ${info.path} (${info.exists ? `${(info.size / 1024).toFixed(1)} KB, modified: ${info.modified}` : 'NOT FOUND'})\n`;
        });
      } else {
        response += `\nNo Excel (.xlsx) files found matching the pattern.`;
      }

      return {
        content: [
          {
            type: 'text',
            text: response,
          },
        ],
      };
    } catch (error) {
      throw new McpError(
        ErrorCode.InternalError,
        `Excel file discovery failed: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  private async generateAnomalyReport(
    tableName: string,
    severityThreshold: string,
    focusColumns: string[],
    anomalyTypes: string[]
  ): Promise<string> {
    const anomalies: any[] = [];
    const sevOrder = { low: 1, medium: 2, high: 3, critical: 4 };
    const minSeverity = sevOrder[severityThreshold as keyof typeof sevOrder] || 2;

    // Get table schema for analysis
    const schema = await this.executeQuery(`DESCRIBE ${tableName}`);
    const totalRows = (await this.executeQuery(`SELECT COUNT(*) as count FROM ${tableName}`))[0].count;

    let report = `# 🔍 Anomaly Detection Report\n**Table:** ${tableName} (${totalRows.toLocaleString()} rows)\n**Severity Threshold:** ${severityThreshold}\n\n`;

    // 1. DUPLICATE DETECTION
    if (anomalyTypes.includes('duplicates')) {
      const duplicateQueries = await this.checkDuplicates(tableName, schema, focusColumns);
      for (const dup of duplicateQueries) {
        if (sevOrder[dup.severity as keyof typeof sevOrder] >= minSeverity) {
          anomalies.push(dup);
        }
      }
    }

    // 2. NULL VALUE ANALYSIS  
    if (anomalyTypes.includes('nulls')) {
      const nullAnomalies = await this.checkNullValues(tableName, schema, totalRows, focusColumns);
      for (const null_anomaly of nullAnomalies) {
        if (sevOrder[null_anomaly.severity as keyof typeof sevOrder] >= minSeverity) {
          anomalies.push(null_anomaly);
        }
      }
    }

    // 3. STATISTICAL OUTLIERS
    if (anomalyTypes.includes('statistical') || anomalyTypes.includes('outliers')) {
      const outlierAnomalies = await this.checkStatisticalOutliers(tableName, schema, focusColumns);
      for (const outlier of outlierAnomalies) {
        if (sevOrder[outlier.severity as keyof typeof sevOrder] >= minSeverity) {
          anomalies.push(outlier);
        }
      }
    }

    // 4. PATTERN ANALYSIS
    if (anomalyTypes.includes('patterns')) {
      const patternAnomalies = await this.checkPatternAnomalies(tableName, schema, focusColumns);
      for (const pattern of patternAnomalies) {
        if (sevOrder[pattern.severity as keyof typeof sevOrder] >= minSeverity) {
          anomalies.push(pattern);
        }
      }
    }

    // 5. BUSINESS LOGIC RULES
    if (anomalyTypes.includes('business_logic')) {
      const businessAnomalies = await this.checkBusinessLogicAnomalies(tableName, schema);
      for (const business of businessAnomalies) {
        if (sevOrder[business.severity as keyof typeof sevOrder] >= minSeverity) {
          anomalies.push(business);
        }
      }
    }

    // Sort anomalies by severity
    anomalies.sort((a, b) => sevOrder[b.severity as keyof typeof sevOrder] - sevOrder[a.severity as keyof typeof sevOrder]);

    // Format report
    if (anomalies.length === 0) {
      report += `✅ **No anomalies detected** above ${severityThreshold} severity threshold.\n`;
    } else {
      const criticalCount = anomalies.filter(a => a.severity === 'critical').length;
      const highCount = anomalies.filter(a => a.severity === 'high').length;
      const mediumCount = anomalies.filter(a => a.severity === 'medium').length;
      const lowCount = anomalies.filter(a => a.severity === 'low').length;

      report += `## 📊 Summary\n`;
      if (criticalCount > 0) report += `🚨 **Critical:** ${criticalCount} anomalies\n`;
      if (highCount > 0) report += `⚠️ **High:** ${highCount} anomalies\n`;
      if (mediumCount > 0) report += `🔶 **Medium:** ${mediumCount} anomalies\n`;
      if (lowCount > 0) report += `🔵 **Low:** ${lowCount} anomalies\n`;

      report += `\n## 🔍 Detailed Findings\n\n`;

      for (const anomaly of anomalies) {
        const icon = anomaly.severity === 'critical' ? '🚨' :
          anomaly.severity === 'high' ? '⚠️' :
            anomaly.severity === 'medium' ? '🔶' : '🔵';

        report += `### ${icon} ${anomaly.title}\n`;
        report += `**Severity:** ${anomaly.severity.toUpperCase()}\n`;
        report += `**Impact:** ${anomaly.impact}\n`;
        if (anomaly.affected_records) report += `**Affected Records:** ${anomaly.affected_records.toLocaleString()}\n`;
        if (anomaly.percentage) report += `**Percentage:** ${anomaly.percentage}%\n`;
        report += `**Details:** ${anomaly.description}\n`;
        if (anomaly.examples) {
          report += `**Examples:**\n\`\`\`\n${anomaly.examples}\`\`\`\n`;
        }
        if (anomaly.recommendation) report += `**Recommendation:** ${anomaly.recommendation}\n`;
        report += '\n---\n\n';
      }
    }

    return report;
  }

  private async checkDuplicates(tableName: string, schema: any[], focusColumns: string[]): Promise<any[]> {
    const anomalies: any[] = [];
    const columnsToCheck = focusColumns.length > 0 ? focusColumns : schema.map(col => col.column_name);

    for (const column of columnsToCheck.slice(0, 8)) { // Check more columns
      const duplicateQuery = `
        SELECT ${column}, COUNT(*) as duplicate_count
        FROM ${tableName} 
        WHERE ${column} IS NOT NULL
        GROUP BY ${column}
        HAVING COUNT(*) > 1
        ORDER BY duplicate_count DESC
        LIMIT 10
      `;

      try {
        const duplicates = await this.executeQuery(duplicateQuery);

        if (duplicates.length > 0) {
          const totalDuplicateRecords = duplicates.reduce((sum, dup) => sum + Number(dup.duplicate_count || 0), 0);
          const maxDuplicates = Math.max(...duplicates.map(d => Number(d.duplicate_count || 0)));

          let severity = 'low';
          if (maxDuplicates > 50000) severity = 'critical'; // Lowered from 1000 to catch tracking number issue
          else if (maxDuplicates > 1000) severity = 'high';
          else if (maxDuplicates > 10) severity = 'medium';
          else if (maxDuplicates > 1) severity = 'low'; // Report any duplicates

          const examples = duplicates.slice(0, 3).map(d =>
            `${Object.values(d)[0]}: ${d.duplicate_count} occurrences`
          ).join('\n');

          anomalies.push({
            type: 'duplicate',
            severity,
            title: `Duplicate Values in ${column}`,
            impact: 'Data integrity, potential processing errors',
            affected_records: totalDuplicateRecords,
            description: `Found ${duplicates.length} unique values with duplicates, max ${maxDuplicates} occurrences`,
            examples,
            recommendation: maxDuplicates > 1000 ? 'URGENT: Investigate data corruption, tracking number system failure' : 'Review business logic for duplicates'
          });
        }
      } catch (error) {
        console.error(`Failed to analyze duplicates for column ${column}:`, error);
      }
    }

    return anomalies;
  }

  private async checkNullValues(tableName: string, schema: any[], totalRows: number, focusColumns: string[]): Promise<any[]> {
    const anomalies: any[] = [];
    const columnsToCheck = focusColumns.length > 0 ? focusColumns : schema.map(col => col.column_name);

    for (const column of columnsToCheck) {
      const nullQuery = `
        SELECT 
          COUNT(*) - COUNT(${column}) as null_count,
          ROUND((COUNT(*) - COUNT(${column})) * 100.0 / COUNT(*), 2) as null_percentage
        FROM ${tableName}
      `;

      try {
        const result = await this.executeQuery(nullQuery);
        const nullCount = result[0]?.null_count || 0;
        const nullPercentage = result[0]?.null_percentage || 0;

        if (nullCount > 0) {
          let severity = 'low';
          if (nullPercentage > 50) severity = 'critical';
          else if (nullPercentage > 25) severity = 'high';
          else if (nullPercentage > 10) severity = 'medium';

          if (severity !== 'low' || nullCount > 100) {
            anomalies.push({
              type: 'null_values',
              severity,
              title: `High Null Rate in ${column.column_name}`,
              impact: 'Data completeness, analysis accuracy',
              affected_records: nullCount,
              percentage: nullPercentage,
              description: `${nullCount} null values (${nullPercentage}% of total)`,
              recommendation: nullPercentage > 25 ? 'Investigate data source, implement validation' : 'Consider default values or imputation'
            });
          }
        }
      } catch (error) {
        console.error(`Failed to analyze duplicates for column ${column}:`, error);
      }
    }

    return anomalies;
  }

  private async checkStatisticalOutliers(tableName: string, schema: any[], focusColumns: string[]): Promise<any[]> {
    const anomalies: any[] = [];
    const numericColumns = schema.filter(col =>
      ['DOUBLE', 'BIGINT', 'INTEGER', 'DECIMAL'].includes(col.column_type.toUpperCase())
    );

    const columnsToCheck = focusColumns.length > 0
      ? numericColumns.filter(col => focusColumns.includes(col.column_name))
      : numericColumns;

    for (const column of columnsToCheck.slice(0, 5)) {
      const statsQuery = `
        SELECT 
          AVG(${column.column_name}) as mean,
          MIN(${column.column_name}) as min_val,
          MAX(${column.column_name}) as max_val,
          STDDEV(${column.column_name}) as stddev,
          COUNT(*) as total_count
        FROM ${tableName} 
        WHERE ${column.column_name} IS NOT NULL
      `;

      try {
        const stats = await this.executeQuery(statsQuery);
        const { mean, min_val, max_val, stddev, total_count } = stats[0] || {};

        if (stddev && stddev > 0) {
          let outlierCount = 0;
          let outlierQuery = '';
          let method = '';

          // Use IQR method for small datasets (< 30 rows), 3-sigma for larger ones
          if (Number(total_count) < 30) {
            // Use IQR method: Q1 - 1.5*IQR and Q3 + 1.5*IQR
            const iqrQuery = `
              SELECT 
                percentile_cont(0.25) WITHIN GROUP (ORDER BY ${column.column_name}) as q1,
                percentile_cont(0.75) WITHIN GROUP (ORDER BY ${column.column_name}) as q3
              FROM ${tableName}
              WHERE ${column.column_name} IS NOT NULL
            `;
            const iqrResult = await this.executeQuery(iqrQuery);
            const q1 = Number(iqrResult[0]?.q1 || 0);
            const q3 = Number(iqrResult[0]?.q3 || 0);
            const iqr = q3 - q1;
            const lowerBound = q1 - 1.5 * iqr;
            const upperBound = q3 + 1.5 * iqr;

            outlierQuery = `
              SELECT COUNT(*) as outlier_count
              FROM ${tableName}
              WHERE ${column.column_name} IS NOT NULL 
                AND (${column.column_name} < ${lowerBound} OR ${column.column_name} > ${upperBound})
            `;
            method = `IQR (Q1=${Math.round(q1 * 100) / 100}, Q3=${Math.round(q3 * 100) / 100})`;
          } else {
            // Use 3-sigma method for larger datasets
            outlierQuery = `
              SELECT COUNT(*) as outlier_count
              FROM ${tableName}
              WHERE ${column.column_name} IS NOT NULL 
                AND (${column.column_name} > ${mean + 3 * stddev} OR ${column.column_name} < ${mean - 3 * stddev})
            `;
            method = `3σ (mean: ${Math.round(mean * 100) / 100}, σ: ${Math.round(stddev * 100) / 100})`;
          }

          const outlierResult = await this.executeQuery(outlierQuery);
          outlierCount = Number(outlierResult[0]?.outlier_count || 0);
          const outlierPercentage = (outlierCount / Number(total_count)) * 100;

          if (outlierCount > 0) {
            let severity = 'low';
            if (outlierPercentage > 5) severity = 'high';
            else if (outlierPercentage > 1) severity = 'medium';

            // Get examples of outliers - reuse the same query logic
            const exampleQuery = outlierQuery.replace('COUNT(*) as outlier_count', `${column.column_name}`).replace('SELECT', 'SELECT') + ' ORDER BY ABS(' + column.column_name + ' - ' + mean + ') DESC LIMIT 5';

            const examples = await this.executeQuery(exampleQuery);
            const exampleText = examples.map(e => `${e[column.column_name]}`).join(', ');

            anomalies.push({
              type: 'statistical_outlier',
              severity,
              title: `Statistical Outliers in ${column.column_name}`,
              impact: 'Potential data quality issues, skewed analysis',
              affected_records: outlierCount,
              percentage: Math.round(outlierPercentage * 100) / 100,
              description: `${outlierCount} values identified using ${method}`,
              examples: `Range: ${min_val} to ${max_val}\nOutlier examples: ${exampleText}`,
              recommendation: 'Investigate extreme values, consider data validation rules'
            });
          }
        }
      } catch (error) {
        console.error(`Failed to analyze duplicates for column ${column}:`, error);
      }
    }

    return anomalies;
  }

  private async checkPatternAnomalies(tableName: string, schema: any[], focusColumns: string[]): Promise<any[]> {
    const anomalies: any[] = [];

    // Check for suspicious patterns in string columns
    const stringColumns = schema.filter(col =>
      col.column_type.toUpperCase().includes('VARCHAR') || col.column_type.toUpperCase().includes('TEXT')
    );

    const columnsToCheck = focusColumns.length > 0
      ? stringColumns.filter(col => focusColumns.includes(col.column_name))
      : stringColumns.slice(0, 3); // Limit to prevent excessive queries

    for (const column of columnsToCheck) {
      // Check for unusual length patterns
      const lengthQuery = `
        SELECT 
          LENGTH(${column.column_name}) as str_length,
          COUNT(*) as count
        FROM ${tableName}
        WHERE ${column.column_name} IS NOT NULL
        GROUP BY LENGTH(${column.column_name})
        ORDER BY count DESC
        LIMIT 20
      `;

      try {
        const lengthResults = await this.executeQuery(lengthQuery);

        // Look for extremely short or long values
        const extremeLengths = lengthResults.filter(r => r.str_length > 200 || r.str_length < 1);
        if (extremeLengths.length > 0) {
          const affectedCount = extremeLengths.reduce((sum, r) => sum + r.count, 0);

          anomalies.push({
            type: 'length_pattern',
            severity: affectedCount > 100 ? 'medium' : 'low',
            title: `Unusual Length Patterns in ${column.column_name}`,
            impact: 'Potential data truncation or corruption',
            affected_records: affectedCount,
            description: `Found values with extreme lengths`,
            examples: extremeLengths.map(r => `Length ${r.str_length}: ${r.count} records`).join('\n'),
            recommendation: 'Review data input validation and field constraints'
          });
        }
      } catch (error) {
        console.error(`Failed to analyze length patterns for column ${column.column_name}:`, error);
      }
    }

    return anomalies;
  }

  private async checkBusinessLogicAnomalies(tableName: string, schema: any[]): Promise<any[]> {
    const anomalies: any[] = [];

    // Generic business logic checks
    try {
      // Check for zero/negative values in amount columns
      const amountColumns = schema.filter(col =>
        col.column_name.toLowerCase().includes('amount') ||
        col.column_name.toLowerCase().includes('charge') ||
        col.column_name.toLowerCase().includes('price')
      );

      for (const column of amountColumns) {
        const negativeQuery = `
          SELECT COUNT(*) as negative_count
          FROM ${tableName}
          WHERE ${column.column_name} < 0
        `;

        const zeroQuery = `
          SELECT COUNT(*) as zero_count  
          FROM ${tableName}
          WHERE ${column.column_name} = 0
        `;

        const [negativeResult, zeroResult] = await Promise.all([
          this.executeQuery(negativeQuery),
          this.executeQuery(zeroQuery)
        ]);

        const _negativeCount = negativeResult[0]?.negative_count || 0;
        const zeroCount = zeroResult[0]?.zero_count || 0;

        if (zeroCount > 50) {
          anomalies.push({
            type: 'business_logic',
            severity: zeroCount > 500 ? 'high' : 'medium',
            title: `Excessive Zero Values in ${column.column_name}`,
            impact: 'Revenue loss, processing errors',
            affected_records: zeroCount,
            description: `${zeroCount} records with zero charges - potential pricing or billing errors`,
            recommendation: 'Review billing logic and pricing rules'
          });
        }
      }

      // Check for date consistency
      const dateColumns = schema.filter(col =>
        col.column_type.toUpperCase().includes('DATE') || col.column_type.toUpperCase().includes('TIMESTAMP')
      );

      if (dateColumns.length >= 2) {
        // Check for impossible date sequences (e.g., end before start)
        const dateColumn1 = dateColumns[0].column_name;
        const dateColumn2 = dateColumns[1].column_name;

        const dateOrderQuery = `
          SELECT COUNT(*) as invalid_order_count
          FROM ${tableName}
          WHERE ${dateColumn1} IS NOT NULL AND ${dateColumn2} IS NOT NULL
            AND ${dateColumn1} > ${dateColumn2}
        `;

        const invalidOrderResult = await this.executeQuery(dateOrderQuery);
        const invalidOrderCount = invalidOrderResult[0]?.invalid_order_count || 0;

        if (invalidOrderCount > 0) {
          anomalies.push({
            type: 'business_logic',
            severity: invalidOrderCount > 100 ? 'high' : 'medium',
            title: `Invalid Date Sequence`,
            impact: 'Data integrity, timeline analysis errors',
            affected_records: invalidOrderCount,
            description: `${invalidOrderCount} records where ${dateColumn1} > ${dateColumn2}`,
            recommendation: 'Review data entry process and add validation constraints'
          });
        }
      }

    } catch (error) {
      console.error('Failed to perform business logic anomaly checks:', error);
    }

    return anomalies;
  }

  private async inspectTableSchema(tableName: string): Promise<string> {
    try {
      // Get schema information
      const schema = await this.executeQuery(`DESCRIBE ${tableName}`);

      // Get row count
      const countResult = await this.executeQuery(`SELECT COUNT(*) as row_count FROM ${tableName}`);
      const rowCount = countResult[0]?.row_count || 0;

      // Get sample data (first 3 rows)
      const sampleData = await this.executeQuery(`SELECT * FROM ${tableName} LIMIT 3`);

      // Format the inspection result
      let inspection = `📊 TABLE INSPECTION: "${tableName}"\n`;
      inspection += `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n`;
      inspection += `📈 Total Rows: ${rowCount.toLocaleString()}\n\n`;

      inspection += `🏗️ SCHEMA:\n`;
      schema.forEach((col: any, index: number) => {
        const icon = this.getColumnTypeIcon(col.column_type);
        inspection += `  ${index + 1}. ${icon} ${col.column_name} (${col.column_type})${col.null ? ' - nullable' : ''}\n`;
      });

      if (sampleData.length > 0) {
        inspection += `\n👀 SAMPLE DATA (first ${sampleData.length} rows):\n`;
        inspection += this.formatSampleData(sampleData, schema);
      }

      inspection += `\n💡 Ready for analysis! Use query_csv to explore the data with SQL.`;

      return inspection;
    } catch (error) {
      return `Schema inspection failed: ${error instanceof Error ? error.message : String(error)}`;
    }
  }

  private getColumnTypeIcon(type: string): string {
    const lowerType = type.toLowerCase();
    if (lowerType.includes('int') || lowerType.includes('bigint') || lowerType.includes('double') || lowerType.includes('decimal')) return '🔢';
    if (lowerType.includes('varchar') || lowerType.includes('text') || lowerType.includes('string')) return '📝';
    if (lowerType.includes('date') || lowerType.includes('timestamp')) return '📅';
    if (lowerType.includes('bool')) return '✅';
    return '📊';
  }

  private formatSampleData(data: any[], schema: any[]): string {
    if (data.length === 0) return '  No data available\n';

    let result = '';
    const columnNames = schema.map(col => col.column_name);

    // Create header
    result += '  ' + columnNames.map(name => name.padEnd(15)).join(' | ') + '\n';
    result += '  ' + columnNames.map(() => '─'.repeat(15)).join('─┼─') + '\n';

    // Add data rows
    data.forEach((row: any) => {
      const values = columnNames.map(name => {
        const value = row[name];
        const strValue = value === null || value === undefined ? 'NULL' : String(value);
        return strValue.length > 15 ? strValue.substring(0, 12) + '...' : strValue.padEnd(15);
      });
      result += '  ' + values.join(' | ') + '\n';
    });

    return result;
  }

  async #ensureExcelExtension(): Promise<void> {
    try {
      await this.executeQuery('INSTALL excel');
      await this.executeQuery('LOAD excel');
    } catch (error) {
      console.error('Excel extension already loaded or failed to load:', error);
    }
  }

  private executeQuery(query: string): Promise<any[]> {
    return new Promise((resolve, reject) => {
      this.db.all(query, (err, rows) => {
        if (err) {
          reject(err);
        } else {
          resolve(rows);
        }
      });
    });
  }

  private safeStringify(obj: any, replacer?: any, space?: string | number): string {
    return JSON.stringify(obj, (key, value) => {
      if (typeof value === 'bigint') {
        // Convert BigInt to number if it fits in safe integer range
        if (value <= Number.MAX_SAFE_INTEGER && value >= Number.MIN_SAFE_INTEGER) {
          return Number(value);
        }
        // Otherwise convert to string with suffix to indicate it was a BigInt
        return value.toString() + 'n';
      }
      return replacer ? replacer(key, value) : value;
    }, space);
  }

  private async generateExpenseOptimizationReport(
    tableName: string,
    amountCol: string,
    nameCol: string,
    dateCol: string
  ): Promise<string> {
    // 1. Monthly expense summary
    const monthlyQuery = `
      SELECT 
        strftime('%Y-%m', ${dateCol}) as month,
        COUNT(*) as transaction_count,
        ROUND(SUM(CASE WHEN ${amountCol} < 0 THEN ABS(${amountCol}) ELSE 0 END), 2) as total_expenses,
        ROUND(MAX(CASE WHEN ${amountCol} < 0 THEN ABS(${amountCol}) ELSE 0 END), 2) as largest_expense
      FROM ${tableName} 
      GROUP BY strftime('%Y-%m', ${dateCol})
      ORDER BY month
    `;

    // 2. Subscription analysis (recurring charges)
    const subscriptionQuery = `
      SELECT 
        ${nameCol} as name,
        ROUND(ABS(${amountCol}), 2) as amount,
        COUNT(*) as frequency,
        ROUND(SUM(ABS(${amountCol})), 2) as total_spent,
        MIN(${dateCol}) as first_charge,
        MAX(${dateCol}) as last_charge
      FROM ${tableName} 
      WHERE ${amountCol} < 0 
      GROUP BY ${nameCol}, ROUND(ABS(${amountCol}), 2)
      HAVING COUNT(*) >= 2 AND ABS(${amountCol}) < 100
      ORDER BY frequency DESC, total_spent DESC
      LIMIT 10
    `;

    // 3. Small frequent purchases analysis
    const smallPurchasesQuery = `
      SELECT 
        CASE 
          WHEN ${nameCol} LIKE '%COFFEE%' OR ${nameCol} LIKE '%STARBUCKS%' OR ${nameCol} LIKE '%DUNKIN%' THEN 'Coffee Shops'
          WHEN ${nameCol} LIKE '%CUSTARD%' OR ${nameCol} LIKE '%ICE CREAM%' THEN 'Ice Cream/Desserts'
          WHEN ${nameCol} LIKE '%RESTAURANT%' OR ${nameCol} LIKE '%GRILL%' OR ${nameCol} LIKE '%PIZZA%' OR ${nameCol} LIKE '%TACO%' OR ${nameCol} LIKE '%CULVERS%' THEN 'Restaurants'
          WHEN ${nameCol} LIKE '%GAS%' OR ${nameCol} LIKE '%FUEL%' OR ${nameCol} LIKE '%SHELL%' THEN 'Gas Stations'
          WHEN ABS(${amountCol}) < 10 THEN 'Small Purchases (<$10)'
          WHEN ABS(${amountCol}) BETWEEN 10 AND 25 THEN 'Medium Purchases ($10-25)'
          ELSE 'Other'
        END as category,
        COUNT(*) as transaction_count,
        ROUND(SUM(ABS(${amountCol})), 2) as total_spent,
        ROUND(AVG(ABS(${amountCol})), 2) as avg_amount
      FROM ${tableName} 
      WHERE ${amountCol} < 0 AND ABS(${amountCol}) < 50
      GROUP BY category
      HAVING transaction_count >= 3
      ORDER BY total_spent DESC
    `;

    // 4. Grocery spending analysis
    const groceryQuery = `
      SELECT 
        strftime('%Y-%m', ${dateCol}) as month,
        COUNT(*) as grocery_trips,
        ROUND(SUM(ABS(${amountCol})), 2) as total_grocery_spend,
        ROUND(AVG(ABS(${amountCol})), 2) as avg_per_trip,
        ROUND(MIN(ABS(${amountCol})), 2) as min_spend,
        ROUND(MAX(ABS(${amountCol})), 2) as max_spend
      FROM ${tableName} 
      WHERE ${amountCol} < 0 AND (${nameCol} LIKE '%KROGER%' OR ${nameCol} LIKE '%TARGET%')
      GROUP BY strftime('%Y-%m', ${dateCol})
      ORDER BY month
    `;

    // Execute all queries
    const [monthlyData, subscriptions, smallPurchases, groceryData] = await Promise.all([
      this.executeQuery(monthlyQuery),
      this.executeQuery(subscriptionQuery),
      this.executeQuery(smallPurchasesQuery),
      this.executeQuery(groceryQuery)
    ]);

    // Generate the formatted report
    return this.formatOptimizationReport(monthlyData, subscriptions, smallPurchases, groceryData);
  }

  private formatOptimizationReport(
    monthlyData: any[],
    subscriptions: any[],
    smallPurchases: any[],
    groceryData: any[]
  ): string {
    let report = '## 💰 Expense Optimization Report\n\n';

    // Monthly summary
    report += '### 📊 Monthly Spending Overview\n';
    report += '| Month | Total Expenses | Largest Purchase | Transactions |\n';
    report += '|-------|---------------|------------------|-------------|\n';
    monthlyData.forEach(month => {
      report += `| ${month.month} | $${month.total_expenses?.toLocaleString() || '0'} | $${month.largest_expense?.toLocaleString() || '0'} | ${month.transaction_count || 0} |\n`;
    });
    report += '\n';

    // High-impact optimization opportunities
    report += '### 🎯 HIGH-IMPACT Opportunities (Save $100+ monthly)\n\n';

    // Subscription analysis
    if (subscriptions.length > 0) {
      const subscriptionTotal = subscriptions.reduce((sum, sub) => sum + (sub.total_spent || 0), 0);
      const monthlySubTotal = subscriptionTotal / 3; // Assuming 3-month period

      report += `**1. Subscription Audit** - Potential savings: $${Math.round(monthlySubTotal * 0.3)}/month\n`;
      report += '```\n';
      subscriptions.slice(0, 5).forEach(sub => {
        report += `• ${sub.name}: $${sub.amount} × ${sub.frequency} times = $${sub.total_spent}\n`;
      });
      report += '```\n';
      report += '**Actions**: Cancel unused services, switch to annual plans for discounts\n\n';
    }

    // Small purchases analysis
    const coffeeData = smallPurchases.find(cat => cat.category === 'Coffee Shops');
    const treatData = smallPurchases.find(cat => cat.category === 'Ice Cream/Desserts');
    const restaurantData = smallPurchases.find(cat => cat.category === 'Restaurants');

    if (coffeeData || treatData) {
      const coffeeMonthly = (coffeeData?.total_spent || 0) / 3;
      const treatMonthly = (treatData?.total_spent || 0) / 3;
      const totalSavings = Math.round((coffeeMonthly + treatMonthly) * 0.7);

      report += `**2. Coffee & Treats** - Potential savings: $${totalSavings}/month\n`;
      if (coffeeData) report += `• Coffee shops: ${coffeeData.transaction_count} visits = $${Math.round(coffeeMonthly)}/month\n`;
      if (treatData) report += `• Treats/desserts: ${treatData.transaction_count} visits = $${Math.round(treatMonthly)}/month\n`;
      report += '**Actions**: Make coffee at home, limit treats to weekends\n\n';
    }

    if (restaurantData) {
      const restaurantMonthly = restaurantData.total_spent / 3;
      const restaurantSavings = Math.round(restaurantMonthly * 0.4);

      report += `**3. Dining Out** - Potential savings: $${restaurantSavings}/month\n`;
      report += `• ${restaurantData.transaction_count} restaurant visits = $${Math.round(restaurantMonthly)}/month\n`;
      report += '**Actions**: Limit to 1-2 restaurant visits per week, meal prep\n\n';
    }

    // Medium-impact opportunities
    report += '### 🔍 MEDIUM-IMPACT Opportunities (Save $25-100 monthly)\n\n';

    // Grocery optimization
    if (groceryData.length > 0) {
      const avgGrocerySpend = groceryData.reduce((sum, month) => sum + (month.total_grocery_spend || 0), 0) / groceryData.length;
      const potentialSavings = Math.round(avgGrocerySpend * 0.15);

      report += `**4. Grocery Optimization** - Potential savings: $${potentialSavings}/month\n`;
      report += '```\n';
      groceryData.forEach(month => {
        report += `${month.month}: ${month.grocery_trips} trips, $${Math.round(month.avg_per_trip || 0)} avg/trip\n`;
      });
      report += '```\n';
      report += '**Actions**: Plan weekly meals, set $75 budget per trip, use store apps for coupons\n\n';
    }

    // Small purchases breakdown
    const smallPurchasesTotal = smallPurchases.reduce((sum, cat) => sum + (cat.total_spent || 0), 0);
    if (smallPurchasesTotal > 0) {
      report += `**5. Small Purchase Optimization** - Potential savings: $${Math.round(smallPurchasesTotal * 0.2 / 3)}/month\n`;
      report += '```\n';
      smallPurchases.slice(0, 4).forEach(cat => {
        report += `• ${cat.category}: ${cat.transaction_count} purchases = $${cat.total_spent}\n`;
      });
      report += '```\n';
      report += '**Actions**: Use 24-hour rule for non-essentials, batch small purchases\n\n';
    }

    // Summary
    const totalPotentialSavings = Math.round(
      (subscriptions.reduce((sum, sub) => sum + sub.total_spent, 0) * 0.3 / 3) +
      ((coffeeData?.total_spent || 0) + (treatData?.total_spent || 0)) * 0.7 / 3 +
      ((restaurantData?.total_spent || 0) * 0.4 / 3) +
      (smallPurchasesTotal * 0.2 / 3)
    );

    report += `### 📈 **Total Monthly Savings Potential: $${totalPotentialSavings}+**\n\n`;
    report += '**Implementation Priority**:\n';
    report += '1. **Subscription audit** (easiest, immediate impact)\n';
    report += '2. **Coffee routine change** (highest ROI)\n';
    report += '3. **Meal planning** (reduces grocery + restaurant costs)\n';
    report += '4. **Small purchase discipline** (builds long-term habits)\n\n';
    report += '💡 **Tip**: Start with one category per month to build sustainable habits.';

    return report;
  }

  async exportCSV(args: any) {
    try {
      const { table_name, save_path, delimiter = ',' } = args;

      if (!this.loadedTables.has(table_name)) {
        throw new Error(`Table "${table_name}" not found. Available: ${[...this.loadedTables.keys()].join(', ') || '(none)'}`);
      }

      const resolvedPath = path.resolve(save_path);
      const escapedPath = resolvedPath.replace(/'/g, "''");

      console.error(`Exporting table "${table_name}" to ${resolvedPath}`);
      await this.executeQuery(`COPY "${table_name}" TO '${escapedPath}' (HEADER, DELIMITER '${delimiter}')`);

      const stats = await fs.stat(resolvedPath);
      return {
        content: [
          { type: 'text', text: `Exported table "${table_name}" → ${resolvedPath} (${(stats.size / 1024).toFixed(1)} KB)` },
        ],
      };
    } catch (error) {
      throw new McpError(
        ErrorCode.InternalError,
        `Export CSV failed: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  async exportJSON(args: any) {
    try {
      const { query, save_path, pretty = false } = args;

      const resolvedPath = path.resolve(save_path);
      console.error(`Exporting query result to ${resolvedPath}`);

      const rows = await this.executeQuery(query);
      const jsonStr = pretty
        ? this.safeStringify(rows, null, 2)
        : this.safeStringify(rows);

      await fs.writeFile(resolvedPath, jsonStr, 'utf-8');

      return {
        content: [
          { type: 'text', text: `Exported ${rows.length} rows → ${resolvedPath} (${(jsonStr.length / 1024).toFixed(1)} KB)` },
        ],
      };
    } catch (error) {
      throw new McpError(
        ErrorCode.InternalError,
        `Export JSON failed: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  async attachDatabase(args: any) {
    try {
      const { db_path, alias } = args;

      const resolvedPath = path.resolve(db_path);
      const escapedPath = resolvedPath.replace(/'/g, "''");

      console.error(`Attaching database: ${resolvedPath}`);
      if (alias) {
        await this.executeQuery(`ATTACH '${escapedPath}' AS ${alias}`);
      } else {
        await this.executeQuery(`ATTACH '${escapedPath}'`);
      }

      // Verify the attach worked by listing databases
      const dbList = await this.executeQuery('SELECT current_database() as db');
      const dbName = alias || path.basename(resolvedPath, path.extname(resolvedPath));

      return {
        content: [
          { type: 'text', text: `Attached database "${dbName}" from ${resolvedPath}\n\nUse "${dbName}" as schema prefix in queries, e.g.: SELECT * FROM ${dbName}.your_table\n\nConnected databases: ${dbList.map((r: any) => r.db).join(', ')}` },
        ],
      };
    } catch (error) {
      throw new McpError(
        ErrorCode.InternalError,
        `Attach database failed: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  async run() {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error('Quack MCP Server running on stdio');
  }
}
