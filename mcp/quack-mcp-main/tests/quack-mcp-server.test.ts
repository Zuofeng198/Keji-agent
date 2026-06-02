import { describe, it } from 'node:test';
import assert from 'node:assert';
import { QuackMCPServer } from '../src/index.ts';

describe('QuackMCPServer', () => {
  describe('constructor', () => {
    it('should create a server instance with correct configuration', () => {
      const server = new QuackMCPServer();
      assert.ok(server);
    });
  });

  describe('loadCSV', () => {
    it('should throw error for non-existent file', async () => {
      const server = new QuackMCPServer();

      await assert.rejects(
        async () => {
          await server.loadCSV({ file_path: '/non/existent/file.csv' });
        },
        {
          name: 'McpError',
          message: /Failed to load CSV.*ENOENT/
        }
      );
    });

    describe('queryCSV', () => {
      it('should execute SQL query successfully', async (t) => {
        const server = new QuackMCPServer();

        // Mock the database query execution
        const mockResult = [{ count: 42, name: 'test' }];
        t.mock.method(server as any, 'executeQuery', async () => mockResult);

        const result = await (server as any).queryCSV({
          query: 'SELECT COUNT(*) as count FROM test'
        });

        assert.ok(result.content);
        assert.strictEqual(result.content.length, 1);
        assert.ok(result.content[0].text.includes('42'));
      });

      it('should handle query execution errors', async (t) => {
        const server = new QuackMCPServer();

        // Mock database to throw error
        t.mock.method(server as any, 'executeQuery', async () => {
          throw new Error('SQL syntax error');
        });

        await assert.rejects(
          async () => {
            await (server as any).queryCSV({ query: 'INVALID SQL' });
          },
          {
            name: 'McpError',
            message: /Query failed.*SQL syntax error/
          }
        );
      });
    });

    describe('describeTable', () => {
      it('should return table schema information', async (t) => {
        const server = new QuackMCPServer();

        const mockSchema = [
          { column_name: 'id', column_type: 'INTEGER', null: 'NO' },
          { column_name: 'amount', column_type: 'DOUBLE', null: 'YES' }
        ];
        t.mock.method(server as any, 'executeQuery', async () => mockSchema);

        const result = await (server as any).describeTable({ table_name: 'test_table' });

        assert.ok(result.content);
        assert.strictEqual(result.content.length, 1);
        assert.ok(result.content[0].text.includes('Schema for table "test_table"'));
        assert.ok(result.content[0].text.includes('INTEGER'));
        assert.ok(result.content[0].text.includes('DOUBLE'));
      });
    });

    describe('listTables', () => {
      it('should return list of loaded tables', async () => {
        const server = new QuackMCPServer();

        // Add some tables to the internal map
        (server as any).loadedTables.set('table1', '/path/to/table1.csv');
        (server as any).loadedTables.set('table2', '/path/to/table2.csv');

        const result = await (server as any).listTables();

        assert.ok(result.content);
        assert.strictEqual(result.content.length, 1);
        assert.ok(result.content[0].text.includes('table1'));
        assert.ok(result.content[0].text.includes('table2'));
        assert.ok(result.content[0].text.includes('/path/to/table1.csv'));
      });

      it('should return empty list when no tables loaded', async () => {
        const server = new QuackMCPServer();

        const result = await (server as any).listTables();

        assert.ok(result.content);
        assert.strictEqual(result.content.length, 1);
        assert.ok(result.content[0].text.includes('[]'));
      });
    });

    describe('analyzeCSV', () => {
      it('should analyze specific columns when provided', async (t) => {
        const server = new QuackMCPServer();

        const mockAnalysis = [{
          amount_count: 100,
          amount_unique: 95,
          amount_min: 10.5,
          amount_max: 500.75,
          amount_avg: 125.25
        }];
        t.mock.method(server as any, 'executeQuery', async () => mockAnalysis);

        const result = await (server as any).analyzeCSV({
          table_name: 'transactions',
          columns: ['amount']
        });

        assert.ok(result.content);
        assert.strictEqual(result.content.length, 1);
        assert.ok(result.content[0].text.includes('Analysis for table "transactions"'));
        assert.ok(result.content[0].text.includes('125.25'));
      });

      it('should analyze all columns when none specified', async (t) => {
        const server = new QuackMCPServer();

        const mockAnalysis = [{
          total_rows: 1000,
          missing_values: 0
        }];
        t.mock.method(server as any, 'executeQuery', async () => mockAnalysis);

        const result = await (server as any).analyzeCSV({
          table_name: 'transactions'
        });

        assert.ok(result.content);
        assert.strictEqual(result.content.length, 1);
        assert.ok(result.content[0].text.includes('1000'));
      });
    });

    describe('optimizeExpenses', () => {
      it('should generate expense optimization report', async (t) => {
        const server = new QuackMCPServer();

        // Mock the report generation method
        t.mock.method(server as any, 'generateExpenseOptimizationReport', async () => {
          return '## 💰 Expense Optimization Report\n\nMocked report content';
        });

        const result = await server.optimizeExpenses({
          table_name: 'credit_card',
          amount_column: 'Amount',
          name_column: 'Name',
          date_column: 'Date'
        });

        assert.ok(result.content);
        assert.strictEqual(result.content.length, 1);
        assert.ok(result.content[0].text.includes('Expense Optimization Report'));
        assert.ok(result.content[0].text.includes('Mocked report content'));
      });
    });

    describe('detectAnomalies', () => {
      it('should generate anomaly detection report', async (t) => {
        const server = new QuackMCPServer();

        // Mock the report generation method
        t.mock.method(server as any, 'generateAnomalyReport', async () => {
          return '# 🔍 Anomaly Detection Report\n\nMocked anomaly findings';
        });

        const result = await server.detectAnomalies({
          table_name: 'transactions',
          severity_threshold: 'medium',
          focus_columns: ['amount'],
          anomaly_types: ['statistical', 'outliers']
        });

        assert.ok(result.content);
        assert.strictEqual(result.content.length, 1);
        assert.ok(result.content[0].text.includes('Anomaly Detection Report'));
        assert.ok(result.content[0].text.includes('Mocked anomaly findings'));
      });
    });
  });
})
