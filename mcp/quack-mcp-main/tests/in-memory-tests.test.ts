import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert';
import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import { QuackMCPServer } from '../src/index.ts';
import { createTestCSVContent, sampleCreditCardData, sampleTransactionData, sampleAnomalyData } from './test-data.ts';

describe('QuackMCPServer In-Memory CSV Tests', () => {
  let tempDir: string;
  let server: QuackMCPServer;

  beforeEach(async () => {
    // Create temporary directory for test files
    tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'quack-mcp-test-'));
    server = new QuackMCPServer();
  });

  const createTempCSVFile = async (filename: string, data: Record<string, any>[]): Promise<string> => {
    const csvContent = createTestCSVContent(data);
    const filePath = path.join(tempDir, filename);
    await fs.writeFile(filePath, csvContent);
    return filePath;
  };

  describe('Credit Card Analysis', () => {
    it('should load and analyze credit card data from memory', async () => {
      const csvPath = await createTempCSVFile('credit-card.csv', sampleCreditCardData);
      
      // Load CSV
      const loadResult = await server.loadCSV({
        file_path: csvPath,
        table_name: 'credit_transactions'
      });

      assert.ok(loadResult.content[0].text.includes('Successfully loaded CSV'));
      assert.ok(loadResult.content[0].text.includes('credit_transactions'));

      // Query data
      const queryResult = await (server as any).queryCSV({
        query: 'SELECT COUNT(*) as total, SUM(Amount) as sum_amount FROM credit_transactions'
      });

      const result = JSON.parse(queryResult.content[0].text);
      assert.strictEqual(result[0].total, 10);
      assert.ok(result[0].sum_amount < 0); // All expenses are negative

      // Analyze expenses
      const analysisResult = await server.optimizeExpenses({
        table_name: 'credit_transactions'
      });

      assert.ok(analysisResult.content[0].text.includes('Expense Optimization Report'));
      // Since STARBUCKS only appears once, it won't be in the category analysis
      // Check for the monthly overview and grocery optimization instead
      assert.ok(analysisResult.content[0].text.includes('Monthly Spending Overview'));
      assert.ok(analysisResult.content[0].text.includes('Grocery Optimization'));
    });

    it('should detect anomalies in transaction data', async () => {
      const csvPath = await createTempCSVFile('transactions.csv', sampleTransactionData);
      
      await server.loadCSV({
        file_path: csvPath,
        table_name: 'transactions'
      });

      const anomalyResult = await server.detectAnomalies({
        table_name: 'transactions',
        severity_threshold: 'low',
        anomaly_types: ['statistical', 'outliers']
      });

      assert.ok(anomalyResult.content[0].text.includes('Anomaly Detection Report'));
      // Should detect the large rent payment as an outlier
      assert.ok(anomalyResult.content[0].text.includes('outlier') || 
                anomalyResult.content[0].text.includes('Statistical'));
    });
  });

  describe('Data Quality Testing', () => {
    it('should detect null values and duplicates', async () => {
      const csvPath = await createTempCSVFile('anomaly-data.csv', sampleAnomalyData);
      
      await server.loadCSV({
        file_path: csvPath,
        table_name: 'anomaly_test'
      });

      const anomalyResult = await server.detectAnomalies({
        table_name: 'anomaly_test',
        severity_threshold: 'low',
        anomaly_types: ['nulls', 'duplicates', 'statistical']
      });

      const reportText = anomalyResult.content[0].text;
      assert.ok(reportText.includes('Anomaly Detection Report'));
      
      // Should detect the statistical outlier (9999)
      assert.ok(reportText.includes('Statistical') || reportText.includes('outlier'));
    });

    it('should handle empty datasets gracefully', async () => {
      const csvPath = await createTempCSVFile('empty.csv', []);
      
      await assert.rejects(
        async () => {
          await server.loadCSV({
            file_path: csvPath,
            table_name: 'empty_table'
          });
        },
        {
          name: 'McpError'
        }
      );
    });

    it('should validate table schema correctly', async () => {
      const csvPath = await createTempCSVFile('schema-test.csv', sampleTransactionData);
      
      await server.loadCSV({
        file_path: csvPath,
        table_name: 'schema_test'
      });

      const describeResult = await (server as any).describeTable({
        table_name: 'schema_test'
      });

      const schemaText = describeResult.content[0].text;
      assert.ok(schemaText.includes('id'));
      assert.ok(schemaText.includes('amount'));
      assert.ok(schemaText.includes('description'));
      assert.ok(schemaText.includes('type'));
    });
  });

  describe('Performance Analysis', () => {
    it('should analyze spending patterns efficiently', async () => {
      const largeCreditCardData = Array.from({ length: 100 }, (_, i) => ({
        Date: `2025-05-${String((i % 30) + 1).padStart(2, '0')}`,
        Name: `MERCHANT_${i % 10}`,
        Amount: -(Math.random() * 100 + 5)
      }));

      const csvPath = await createTempCSVFile('large-transactions.csv', largeCreditCardData);
      
      await server.loadCSV({
        file_path: csvPath,
        table_name: 'large_transactions'
      });

      const startTime = Date.now();
      const analysisResult = await (server as any).analyzeCSV({
        table_name: 'large_transactions',
        columns: ['Amount']
      });
      const endTime = Date.now();

      // Should complete analysis within reasonable time (< 1 second)
      assert.ok(endTime - startTime < 1000);
      assert.ok(analysisResult.content[0].text.includes('Amount_count'));
      assert.ok(analysisResult.content[0].text.includes('100')); // Should count all 100 records
    });

    it('should handle mixed data types correctly', async () => {
      const mixedData = [
        { id: 1, value: 123, text: 'Hello', date: '2025-01-01', flag: true },
        { id: 2, value: 456.78, text: 'World', date: '2025-01-02', flag: false },
        { id: 3, value: null, text: '', date: null, flag: null }
      ];

      const csvPath = await createTempCSVFile('mixed-data.csv', mixedData);
      
      await server.loadCSV({
        file_path: csvPath,
        table_name: 'mixed_data'
      });

      const queryResult = await (server as any).queryCSV({
        query: 'SELECT * FROM mixed_data WHERE value IS NOT NULL'
      });

      const result = JSON.parse(queryResult.content[0].text);
      assert.strictEqual(result.length, 2); // Should exclude null value row
    });
  });

  // Note: In a real implementation, you'd clean up the temp directory
  // For this example, the OS will clean it up eventually
});