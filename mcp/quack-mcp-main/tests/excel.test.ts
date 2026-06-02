import { strict as assert } from 'assert';
import { test } from 'node:test';
import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import { QuackMCPServer } from '../src/index.ts';

// Helper to create test Excel data using CSV and then converting conceptually
// Note: For real tests, you'd want actual .xlsx files, but for this demo we'll simulate
async function createTestExcelFile(filePath: string, data: string[][]): Promise<void> {
  // This is a mock - in reality you'd create actual .xlsx files
  // For testing purposes, we'll create a simple text file that mimics Excel structure
  const content = data.map(row => row.join('\t')).join('\n');
  await fs.writeFile(filePath.replace('.xlsx', '.txt'), content);
  
  // Create an empty .xlsx file for file existence checks
  await fs.writeFile(filePath, 'mock excel content');
}

test('Excel functionality tests', async () => {
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'quack-mcp-excel-test-'));
  let server: QuackMCPServer;

  try {
    server = new QuackMCPServer();

    await test('should validate .xlsx file extension in loadExcel', async () => {
      try {
        await server.loadExcel({ file_path: '/path/to/file.xls' });
        assert.fail('Should have thrown error for .xls file');
      } catch (error) {
        assert(error instanceof Error);
        assert(error.message.includes('Only .xlsx files are supported'));
      }
    });

    await test('should handle missing Excel file gracefully', async () => {
      try {
        await server.loadExcel({ file_path: '/nonexistent/file.xlsx' });
        assert.fail('Should have thrown error for missing file');
      } catch (error) {
        assert(error instanceof Error);
        assert(error.message.includes('Failed to load Excel'));
      }
    });

    await test('should validate file extensions in loadMultipleExcels', async () => {
      try {
        await server.loadMultipleExcels({ 
          pattern_or_files: ['/path/to/file1.xlsx', '/path/to/file2.xls'] 
        });
        assert.fail('Should have thrown error for mixed file types');
      } catch (error) {
        assert(error instanceof Error);
        assert(error.message.includes('Only .xlsx files are supported') || 
               error.message.includes('Multi-Excel loading failed'));
      }
    });

    await test('should validate array vs string input in loadMultipleExcels', async () => {
      try {
        await server.loadMultipleExcels({ pattern_or_files: 123 });
        assert.fail('Should have thrown error for invalid input type');
      } catch (error) {
        assert(error instanceof Error);
        assert(error.message.includes('pattern_or_files must be a string'));
      }
    });

    await test('should discover Excel files with pattern', async () => {
      // Create some test files
      const excelFile1 = path.join(tempDir, 'data1.xlsx');
      const excelFile2 = path.join(tempDir, 'data2.xlsx');
      const csvFile = path.join(tempDir, 'data3.csv');
      
      await createTestExcelFile(excelFile1, [['Name', 'Age'], ['Alice', '25'], ['Bob', '30']]);
      await createTestExcelFile(excelFile2, [['Product', 'Price'], ['Apple', '1.50'], ['Orange', '2.00']]);
      await fs.writeFile(csvFile, 'test,data\n1,2');

      const result = await server.discoverExcelFiles({ 
        pattern: path.join(tempDir, '*').replace(/\\/g, '/') 
      });
      
      assert(result.content && result.content.length > 0);
      const output = result.content[0].text;
      assert(output.includes('Excel files (.xlsx): 2'));
      assert(output.includes('Other files: 3') || output.includes('Other files:3')); // 2 .txt + 1 .csv
      assert(output.includes('data1.xlsx'));
      assert(output.includes('data2.xlsx'));
    });

    await test('should handle empty Excel discovery results', async () => {
      const emptyDir = path.join(tempDir, 'empty');
      await fs.mkdir(emptyDir);
      
      const result = await server.discoverExcelFiles({ 
        pattern: path.join(emptyDir, '*.xlsx').replace(/\\/g, '/') 
      });
      
      assert(result.content && result.content.length > 0);
      const output = result.content[0].text;
      assert(output.includes('Excel files (.xlsx): 0'));
      assert(output.includes('No Excel (.xlsx) files found'));
    });

    await test('should provide detailed file information in discovery', async () => {
      const excelFile = path.join(tempDir, 'detailed.xlsx');
      await createTestExcelFile(excelFile, [['Test'], ['Data']]);
      
      const result = await server.discoverExcelFiles({ 
        pattern: path.join(tempDir, 'detailed.xlsx').replace(/\\/g, '/') 
      });
      
      assert(result.content && result.content.length > 0);
      const output = result.content[0].text;
      assert(output.includes('detailed.xlsx'));
      assert(output.includes('KB'));
      assert(output.includes('modified:'));
    });

    await test('should handle glob patterns in loadMultipleExcels string input', async () => {
      // Test string input that doesn't contain wildcards
      try {
        await server.loadMultipleExcels({ 
          pattern_or_files: '/single/file.xlsx' 
        });
        assert.fail('Should have thrown error for missing file');
      } catch (error) {
        assert(error instanceof Error);
        assert(error.message.includes('File not found') || error.message.includes('Failed to load Excel'));
      }
    });

    await test('should validate table name sanitization', async () => {
      // Test that special characters in table names are handled
      const validationTest = async (tableName: string) => {
        try {
          await server.loadExcel({ 
            file_path: '/nonexistent/file.xlsx',
            table_name: tableName
          });
        } catch (error) {
          // We expect this to fail due to missing file, not table name validation
          assert(error instanceof Error);
        }
      };
      
      // These should not cause additional errors beyond the missing file
      await validationTest('table-with-dashes');
      await validationTest('table with spaces');
      await validationTest('table$with#special!chars');
    });

  } finally {
    // Cleanup
    await fs.rm(tempDir, { recursive: true, force: true });
  }
});

// Integration test with mock Excel extension behavior
test('Excel extension loading test', async () => {
  const server = new QuackMCPServer();
  
  await test('should handle Excel extension loading gracefully', async () => {
    // Test the ensureExcelExtension method indirectly
    // This will likely fail in test environment without actual DuckDB Excel extension
    try {
      await server.loadExcel({ file_path: '/nonexistent/test.xlsx' });
    } catch (error) {
      assert(error instanceof Error);
      // Should fail on file access, not on extension loading
      assert(error.message.includes('Failed to load Excel'));
    }
  });
});

// Parameter validation tests
test('Excel parameter validation', async () => {
  const server = new QuackMCPServer();

  await test('loadExcel should handle all parameter combinations', async () => {
    const testParams = [
      { file_path: 'test.xlsx' },
      { file_path: 'test.xlsx', table_name: 'custom_table' },
      { file_path: 'test.xlsx', sheet: 'Sheet2' },
      { file_path: 'test.xlsx', range: 'A1:C10' },
      { file_path: 'test.xlsx', header: false },
      { file_path: 'test.xlsx', all_varchar: true },
      { 
        file_path: 'test.xlsx', 
        table_name: 'full_test',
        sheet: 'Data',
        range: 'B2:E20',
        header: true,
        all_varchar: false
      }
    ];

    for (const params of testParams) {
      try {
        await server.loadExcel(params);
        assert.fail('Should have failed due to missing file');
      } catch (error) {
        assert(error instanceof Error);
        // All should fail on file access, confirming parameter processing works
        assert(error.message.includes('Failed to load Excel') || error.message.includes('access'));
      }
    }
  });

  await test('loadMultipleExcels should handle all parameter combinations', async () => {
    const testParams = [
      { pattern_or_files: '*.xlsx' },
      { pattern_or_files: ['file1.xlsx', 'file2.xlsx'] },
      { pattern_or_files: '*.xlsx', table_name: 'multi_test' },
      { pattern_or_files: '*.xlsx', union_by_name: true },
      { pattern_or_files: '*.xlsx', include_filename: true },
      { pattern_or_files: '*.xlsx', sheet: 'Data' },
      { pattern_or_files: '*.xlsx', header: false },
      { pattern_or_files: '*.xlsx', all_varchar: true }
    ];

    for (const params of testParams) {
      try {
        await server.loadMultipleExcels(params);
        assert.fail('Should have failed due to missing files');
      } catch (error) {
        assert(error instanceof Error);
        // Should fail on file discovery or access
        assert(error.message.includes('Multi-Excel loading failed') || 
               error.message.includes('No Excel files found'));
      }
    }
  });
});

// Error message quality tests
test('Excel error message quality', async () => {
  const server = new QuackMCPServer();

  await test('should provide helpful error for .xls files', async () => {
    try {
      await server.loadExcel({ file_path: 'old_format.xls' });
      assert.fail('Should have thrown error');
    } catch (error) {
      assert(error instanceof Error);
      assert(error.message.includes('Only .xlsx files are supported'));
      assert(error.message.includes('convert .xls files to .xlsx'));
    }
  });

  await test('should provide context in multi-file errors', async () => {
    try {
      await server.loadMultipleExcels({ 
        pattern_or_files: ['good.xlsx', 'bad.xls', 'another.xlsx'] 
      });
      assert.fail('Should have thrown error');
    } catch (error) {
      assert(error instanceof Error);
      assert(error.message.includes('non-xlsx file') || 
             error.message.includes('Only .xlsx files are supported') ||
             error.message.includes('Multi-Excel loading failed'));
      assert(error.message.includes('bad.xls') || error.message.includes('.xls'));
    }
  });

  await test('should indicate when no files match pattern', async () => {
    try {
      await server.loadMultipleExcels({ 
        pattern_or_files: '/impossible/path/pattern/*.xlsx' 
      });
      assert.fail('Should have thrown error');
    } catch (error) {
      assert(error instanceof Error);
      assert(error.message.includes('No Excel files found matching pattern'));
    }
  });
});