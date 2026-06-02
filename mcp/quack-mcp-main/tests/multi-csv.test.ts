import { strict as assert } from 'assert';
import { test } from 'node:test';
import Database from 'duckdb';
import fs from 'fs/promises';
import path from 'path';
import os from 'os';

test('Multi-CSV functionality tests', async () => {
  const db = new Database.Database(':memory:');
  
  // Create a temporary directory for test files
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'quack-mcp-test-'));
  
  // Helper function to execute queries
  const executeQuery = (query: string): Promise<any[]> => {
    return new Promise((resolve, reject) => {
      db.all(query, (err, result) => {
        if (err) {
          reject(err);
        } else {
          resolve(result);
        }
      });
    });
  };

  // Helper function to create test CSV files
  const createTestFiles = async () => {
    // Create sales data files
    await fs.writeFile(path.join(tempDir, 'sales_q1.csv'), 
      'date,product,amount,region\n' +
      '2024-01-15,Widget A,150.00,North\n' +
      '2024-01-16,Widget B,200.50,South\n' +
      '2024-02-01,Widget A,175.00,East\n');

    await fs.writeFile(path.join(tempDir, 'sales_q2.csv'), 
      'date,product,amount,region\n' +
      '2024-04-10,Widget A,190.00,North\n' +
      '2024-04-20,Widget B,210.75,South\n' +
      '2024-05-05,Widget D,400.50,East\n');

    await fs.writeFile(path.join(tempDir, 'sales_q3.csv'), 
      'date,product,amount,region,customer_type\n' +
      '2024-07-08,Widget A,165.00,North,retail\n' +
      '2024-07-18,Widget B,245.25,South,wholesale\n' +
      '2024-08-03,Widget E,500.00,East,retail\n');

    // Create employee files
    await fs.writeFile(path.join(tempDir, 'employees_dept1.csv'),
      'employee_id,name,salary,department\n' +
      '101,Alice Johnson,75000,Engineering\n' +
      '102,Bob Smith,68000,Engineering\n' +
      '103,Carol Davis,72000,Engineering\n');

    await fs.writeFile(path.join(tempDir, 'employees_dept2.csv'),
      'employee_id,name,salary,department\n' +
      '201,David Wilson,65000,Marketing\n' +
      '202,Eve Brown,70000,Marketing\n' +
      '203,Frank Miller,63000,Marketing\n');

    // Create nested directory structure
    const nestedDir = path.join(tempDir, 'reports', '2024');
    await fs.mkdir(nestedDir, { recursive: true });
    
    await fs.writeFile(path.join(nestedDir, 'monthly_jan.csv'),
      'month,revenue,expenses,profit\n' +
      'January,50000,32000,18000\n');

    await fs.writeFile(path.join(nestedDir, 'monthly_feb.csv'),
      'month,revenue,expenses,profit\n' +
      'February,55000,34000,21000\n');
  };

  // Create test files
  await createTestFiles();

  // Test 1: Load multiple CSV files using glob pattern
  await test('should load multiple sales CSV files using glob pattern', async () => {
    // Load all sales_q*.csv files from temp directory
      const globPattern = path.join(tempDir, 'sales_q*.csv').replace(/\\/g, '/');
      
      const query = `
        CREATE OR REPLACE TABLE sales_all AS 
        SELECT * FROM read_csv('${globPattern}', header=true)
      `;
      
      await executeQuery(query);
      
      // Verify data was loaded
      const countResult = await executeQuery('SELECT COUNT(*) as count FROM sales_all');
      assert(Number(countResult[0].count) === 9, `Should have loaded 9 rows from 3 files, got ${countResult[0].count}`);
      
      // Verify we have data from different quarters
      const distinctProducts = await executeQuery('SELECT DISTINCT product FROM sales_all ORDER BY product');
      assert(distinctProducts.length >= 4, 'Should have multiple products from different files');
  });

  // Test 2: Load CSV files with different schemas using union_by_name
  await test('should handle different schemas with union_by_name', async () => {
    // sales_q3.csv has an additional column 'customer_type'
      const globPattern = path.join(tempDir, 'sales_q*.csv').replace(/\\/g, '/');
      const query = `
        CREATE OR REPLACE TABLE sales_union AS 
        SELECT * FROM read_csv('${globPattern}', header=true, union_by_name=true)
      `;
      
      await executeQuery(query);
      
      // Check if customer_type column exists and has nulls for Q1/Q2 data
      const schemaResult = await executeQuery("DESCRIBE sales_union");
      const hasCustomerType = schemaResult.some((col: any) => col.column_name === 'customer_type');
      assert(hasCustomerType, 'Should include customer_type column from Q3 data');
      
      // Check that some customer_type values are null (from Q1/Q2 files)
      const nullCount = await executeQuery("SELECT COUNT(*) as count FROM sales_union WHERE customer_type IS NULL");
      assert(Number(nullCount[0].count) === 6, `Should have 6 null values for Q1/Q2 data, got ${nullCount[0].count}`);
  });

  // Test 3: Load CSV files with filename tracking
  await test('should include filename column when requested', async () => {
    const globPattern = path.join(tempDir, 'sales_q*.csv').replace(/\\/g, '/');
    const query = `
      CREATE OR REPLACE TABLE sales_with_filename AS 
      SELECT * FROM read_csv('${globPattern}', header=true, filename=true)
    `;
    
    await executeQuery(query);
    
    // Check if filename column exists
    const schemaResult = await executeQuery("DESCRIBE sales_with_filename");
    const hasFilename = schemaResult.some((col: any) => col.column_name === 'filename');
    assert(hasFilename, 'Should include filename column');
    
    // Check that we have different filenames
    const filenameCount = await executeQuery("SELECT COUNT(DISTINCT filename) as count FROM sales_with_filename");
    assert(Number(filenameCount[0].count) === 3, `Should have 3 distinct filenames, got ${filenameCount[0].count}`);
  });

  // Test 4: Load specific CSV files using array syntax
  await test('should load specific files using array syntax', async () => {
    const file1 = path.join(tempDir, 'employees_dept1.csv').replace(/\\/g, '/');
    const file2 = path.join(tempDir, 'employees_dept2.csv').replace(/\\/g, '/');
    const query = `
      CREATE OR REPLACE TABLE employees_combined AS 
      SELECT * FROM read_csv(['${file1}', '${file2}'], header=true)
    `;
    
    await executeQuery(query);
    
    // Verify data from both departments
    const deptCount = await executeQuery("SELECT COUNT(DISTINCT department) as count FROM employees_combined");
    assert(Number(deptCount[0].count) === 2, `Should have data from 2 departments, got ${deptCount[0].count}`);
    
    const totalCount = await executeQuery("SELECT COUNT(*) as count FROM employees_combined");
    assert(Number(totalCount[0].count) === 6, `Should have 6 total employees, got ${totalCount[0].count}`);
  });

  // Test 5: Test recursive glob pattern
  await test('should handle recursive glob patterns', async () => {
    const recursivePattern = path.join(tempDir, '**', '*.csv').replace(/\\/g, '/');
    const query = `
      CREATE OR REPLACE TABLE reports_all AS 
      SELECT * FROM read_csv('${recursivePattern}', header=true, union_by_name=true)
    `;
    
    await executeQuery(query);
    
    // Should include files from nested directories
    const count = await executeQuery("SELECT COUNT(*) as count FROM reports_all");
    assert(Number(count[0].count) >= 2, `Should load files from nested directories, got ${count[0].count}`);
  });

  // Test 6: Test glob function for file discovery
  await test('should discover files using glob function', async () => {
    const globPattern = path.join(tempDir, 'sales_*.csv').replace(/\\/g, '/');
    const result = await executeQuery(`SELECT file FROM glob('${globPattern}') ORDER BY file`);
    
    assert(result.length === 3, 'Should find exactly 3 sales CSV files');
    assert(result.every((row: any) => row.file.includes('sales_')), 'All files should contain "sales_"');
    assert(result.every((row: any) => row.file.endsWith('.csv')), 'All files should end with .csv');
  });

  // Note: Using in-memory database, tables will be cleaned up automatically

  // Cleanup temp directory
  try {
    await fs.rm(tempDir, { recursive: true, force: true });
  } catch (error) {
    console.warn('Warning: Could not clean up temp directory:', error);
  }
  
});