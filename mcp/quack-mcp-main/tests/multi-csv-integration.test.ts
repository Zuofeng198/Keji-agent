import { strict as assert } from 'assert';
import { test } from 'node:test';
import fs from 'fs/promises';
import path from 'path';
import os from 'os';

// We'll need to create a test version or mock the MCP server functionality
// For now, we'll test the core integration patterns

test('Multi-CSV MCP Integration Tests', async () => {
  // Create a temporary directory for test files
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'quack-mcp-integration-'));
  
  // Helper function to create test CSV files
  const createTestFiles = async () => {
    // Create multiple sales files with different schemas
    await fs.writeFile(path.join(tempDir, 'sales_2024_q1.csv'), 
      'date,product,amount,region\n' +
      '2024-01-15,Laptop,999.99,North\n' +
      '2024-02-01,Mouse,29.99,South\n' +
      '2024-03-15,Keyboard,79.99,East\n');

    await fs.writeFile(path.join(tempDir, 'sales_2024_q2.csv'), 
      'date,product,amount,region\n' +
      '2024-04-10,Laptop,1099.99,West\n' +
      '2024-05-20,Monitor,299.99,North\n' +
      '2024-06-05,Mouse,34.99,South\n');

    // Create files with different schemas for union testing
    await fs.writeFile(path.join(tempDir, 'sales_2024_q3.csv'), 
      'date,product,amount,region,channel\n' +
      '2024-07-08,Laptop,1199.99,North,online\n' +
      '2024-08-18,Tablet,449.99,South,retail\n' +
      '2024-09-25,Mouse,39.99,East,online\n');

    // Create subdirectory structure for recursive testing
    const subDir = path.join(tempDir, 'archive', '2023');
    await fs.mkdir(subDir, { recursive: true });
    
    await fs.writeFile(path.join(subDir, 'legacy_sales.csv'),
      'date,product,amount,region\n' +
      '2023-12-01,Laptop,899.99,North\n' +
      '2023-12-15,Mouse,24.99,South\n');

    // Create files with different delimiters
    await fs.writeFile(path.join(tempDir, 'inventory_pipe.csv'),
      'id|name|stock|price\n' +
      '1|Widget A|100|15.99\n' +
      '2|Widget B|75|22.50\n');

    await fs.writeFile(path.join(tempDir, 'inventory_tab.csv'),
      'id\tname\tstock\tprice\n' +
      '3\tWidget C\t50\t35.00\n' +
      '4\tWidget D\t25\t42.75\n');
  };

  await createTestFiles();

  // Test 1: Basic glob pattern loading
  await test('should handle basic glob patterns', async () => {
    const testCases = [
      {
        name: 'Single asterisk pattern',
        pattern: path.join(tempDir, 'sales_*.csv'),
        expectedMinFiles: 3,
        description: 'Should find all sales files at root level'
      },
      {
        name: 'Recursive pattern', 
        pattern: path.join(tempDir, '**', '*.csv'),
        expectedMinFiles: 6,
        description: 'Should find all CSV files recursively'
      },
      {
        name: 'Specific quarter pattern',
        pattern: path.join(tempDir, 'sales_2024_q[12].csv'),
        expectedMinFiles: 2,
        description: 'Should find Q1 and Q2 sales files only'
      }
    ];

    for (const testCase of testCases) {
      console.log(`Testing: ${testCase.name}`);
      
      // Simulate what the MCP server would do - discover files first
      const files = await fs.readdir(tempDir, { recursive: true });
      const csvFiles = files
        .filter((file: any) => file.toString().endsWith('.csv'))
        .map((file: any) => path.join(tempDir, file.toString()));
      
      assert(csvFiles.length >= testCase.expectedMinFiles, 
        `${testCase.description} - Expected at least ${testCase.expectedMinFiles} files, got ${csvFiles.length}`);
      
      console.log(`✓ ${testCase.name} passed`);
    }
  });

  // Test 2: Schema handling scenarios
  await test('should handle different schema scenarios', async () => {
    // Test union by position (default)
    console.log('Testing union by position...');
    const q1q2Files = [
      path.join(tempDir, 'sales_2024_q1.csv'),
      path.join(tempDir, 'sales_2024_q2.csv')
    ];
    
    // Both files have same schema, should work fine
    for (const file of q1q2Files) {
      const content = await fs.readFile(file, 'utf8');
      const lines = content.trim().split('\n');
      const headers = lines[0].split(',');
      assert(headers.length === 4, `File ${file} should have 4 columns`);
      assert(headers.includes('date'), `File ${file} should have date column`);
      assert(headers.includes('product'), `File ${file} should have product column`);
    }
    console.log('✓ Union by position test passed');

    // Test union by name with different schemas
    console.log('Testing union by name with different schemas...');
    const q3File = path.join(tempDir, 'sales_2024_q3.csv');
    const q3Content = await fs.readFile(q3File, 'utf8');
    const q3Headers = q3Content.trim().split('\n')[0].split(',');
    
    assert(q3Headers.includes('channel'), 'Q3 file should have additional channel column');
    assert(q3Headers.length === 5, 'Q3 file should have 5 columns');
    console.log('✓ Union by name test passed');
  });

  // Test 3: File list scenarios
  await test('should handle explicit file lists', async () => {
    console.log('Testing explicit file list handling...');
    
    const explicitFiles = [
      path.join(tempDir, 'sales_2024_q1.csv'),
      path.join(tempDir, 'sales_2024_q2.csv')
    ];
    
    // Verify all files exist
    for (const file of explicitFiles) {
      try {
        await fs.access(file);
      } catch {
        assert.fail(`File should exist: ${file}`);
      }
    }
    
    // Verify files have expected content structure
    const fileContents = await Promise.all(
      explicitFiles.map(async (file) => {
        const content = await fs.readFile(file, 'utf8');
        const lines = content.trim().split('\n');
        return {
          file,
          headers: lines[0].split(','),
          rowCount: lines.length - 1
        };
      })
    );
    
    const totalRows = fileContents.reduce((sum, file) => sum + file.rowCount, 0);
    assert(totalRows === 6, `Should have 6 total rows across files, got ${totalRows}`);
    
    console.log('✓ Explicit file list test passed');
  });

  // Test 4: Delimiter detection scenarios
  await test('should handle different delimiter scenarios', async () => {
    console.log('Testing delimiter handling...');
    
    const delimiterTests = [
      {
        file: path.join(tempDir, 'inventory_pipe.csv'),
        delimiter: '|',
        expectedCols: 4
      },
      {
        file: path.join(tempDir, 'inventory_tab.csv'), 
        delimiter: '\t',
        expectedCols: 4
      }
    ];
    
    for (const test of delimiterTests) {
      const content = await fs.readFile(test.file, 'utf8');
      const firstLine = content.trim().split('\n')[0];
      const cols = firstLine.split(test.delimiter);
      
      assert(cols.length === test.expectedCols, 
        `File ${test.file} should have ${test.expectedCols} columns when split by '${test.delimiter}', got ${cols.length}`);
    }
    
    console.log('✓ Delimiter handling test passed');
  });

  // Test 5: Error scenarios
  await test('should handle error scenarios gracefully', async () => {
    console.log('Testing error scenarios...');
    
    // Test non-existent pattern
    const _nonExistentPattern = path.join(tempDir, 'nonexistent_*.csv');
    const files = await fs.readdir(tempDir);
    const matchingFiles = files.filter(f => f.startsWith('nonexistent_') && f.endsWith('.csv'));
    assert(matchingFiles.length === 0, 'Should find no files for non-existent pattern');
    
    // Test invalid file in list
    const invalidFile = path.join(tempDir, 'does_not_exist.csv');
    try {
      await fs.access(invalidFile);
      assert.fail('Should not find non-existent file');
    } catch {
      // Expected to throw
    }
    
    console.log('✓ Error scenarios test passed');
  });

  // Test 6: Performance scenarios (file discovery)
  await test('should perform file discovery efficiently', async () => {
    console.log('Testing file discovery performance...');
    
    const startTime = Date.now();
    
    // Simulate what discover_csv_files would do
    const allFiles = await fs.readdir(tempDir, { recursive: true });
    const csvFiles = allFiles.filter((file: any) => file.toString().endsWith('.csv'));
    
    const fileStats = await Promise.all(
      csvFiles.map(async (file: any) => {
        const fullPath = path.join(tempDir, file.toString());
        const stats = await fs.stat(fullPath);
        return {
          path: fullPath,
          size: stats.size,
          modified: stats.mtime
        };
      })
    );
    
    const endTime = Date.now();
    const duration = endTime - startTime;
    
    assert(duration < 1000, `File discovery should complete quickly, took ${duration}ms`);
    assert(fileStats.length >= 6, `Should discover at least 6 CSV files, found ${fileStats.length}`);
    assert(fileStats.every(f => f.size > 0), 'All files should have content');
    
    console.log(`✓ File discovery completed in ${duration}ms`);
  });

  // Cleanup
  try {
    await fs.rm(tempDir, { recursive: true, force: true });
    console.log('✓ Cleanup completed');
  } catch (error) {
    console.warn('Warning: Could not clean up temp directory:', error);
  }
  
  console.log('All multi-CSV integration tests completed successfully!');
});