# Quack MCP

The best CSV and Excel analyst that pulls everything into DuckDB in order to provide LLM agents the ability to explore and analyze the data with accuracy and efficiency.

## Features

- **CSV Loading**: Load CSV files into DuckDB for fast analysis
- **Excel Support**: Load and analyze Excel (.xlsx) files with sheet and range selection
- **SQL Querying**: Execute complex SQL queries on your data
- **Data Analysis**: Built-in statistical analysis tools
- **Schema Inspection**: Examine table structures and metadata
- **Expense Optimization**: Analyze spending patterns and identify savings opportunities
- **Anomaly Detection**: Detect irregularities and outliers in datasets
- **Multi-File Processing**: Load and combine multiple CSV or Excel files efficiently
- **MCP Integration**: Works seamlessly with MCP clients like Claude Code

## Installation

### Local Installation

**Prerequisites:**
- **Node.js 24+** (required)

```bash
npm install
```

**Why Node.js 24 is required:**
- **Native TypeScript support** - Run `.ts` files directly without compilation
- **Modern ES modules** - Full support for `import`/`export` syntax used throughout the codebase
- **Built-in test runner** - Uses Node.js native test runner (`node --test`)
- **Security updates** - Latest security patches and improvements

This eliminates the need for build tools like `tsc`, `ts-node`, or bundlers, making development faster and deployments simpler.

### Docker Installation

#### Prerequisites
- Docker and Docker Compose installed
- Access to CSV files on your host system

#### Building and Running

```bash
# Build the Docker image
docker build -t quack-mcp .

# Or use docker-compose for easier management
docker-compose up quack-mcp
```

#### Development Mode

```bash
# Run with hot reload for development
docker-compose up quack-mcp-dev
```

## Usage

### Local Usage

The server runs via stdin/stdout transport for MCP protocol:

```bash
node src/index.ts
```

### Docker Usage

```bash
# Run with docker-compose (recommended)
docker-compose up quack-mcp

# Or run directly with Docker
docker run -it --rm \
  -v $(pwd)/data:/app/data:ro \
  -v /path/to/your/csv/files:/app/csv-data:ro \
  quack-mcp
```

**Note**: Mount your CSV files as volumes so the container can access them.

## Available Tools

### Core Analysis Tools

#### `load_csv`
Load a CSV file into DuckDB for analysis.

**Parameters:**
- `file_path` (required): Path to the CSV file
- `table_name` (optional): Name for the table (defaults to filename)
- `delimiter` (optional): CSV delimiter (default: ",")
- `header` (optional): Whether CSV has header row (default: true)

#### `query_csv`
Execute SQL queries on loaded CSV data.

**Parameters:**
- `query` (required): SQL query to execute

#### `describe_table`
Get schema information for a loaded table.

**Parameters:**
- `table_name` (required): Name of the table to describe

#### `list_tables`
List all currently loaded tables.

#### `analyze_csv`
Perform basic statistical analysis on CSV data.

**Parameters:**
- `table_name` (required): Name of the table to analyze
- `columns` (optional): Array of specific column names to analyze (if not provided, analyzes row counts and general statistics)

### Multi-File CSV Tools

#### `load_multiple_csvs`
Load multiple CSV files using glob patterns or file lists into DuckDB for analysis.

**Parameters:**
- `pattern_or_files` (required): Glob pattern (e.g., "data/*.csv", "reports/**/*.csv") or array of specific file paths
- `table_name` (optional): Name for the combined table (defaults to "multi_csv_data")
- `union_by_name` (optional): Combine files by column name instead of position (default: false)
- `include_filename` (optional): Include a filename column to track source file for each row (default: false)
- `delimiter` (optional): CSV delimiter (default: ",")
- `header` (optional): Whether CSV files have header rows (default: true)

**Examples:**
- Load all CSV files in a directory: `"data/*.csv"`
- Load files recursively: `"reports/**/*.csv"`
- Load specific files: `["sales_q1.csv", "sales_q2.csv"]`
- Mix patterns: `["data/sales_*.csv", "archive/legacy_*.csv"]`

#### `discover_csv_files`
Discover CSV files matching a glob pattern without loading them.

**Parameters:**
- `pattern` (required): Glob pattern to search for CSV files

**Returns:** List of matching files with metadata (size, modification date, existence status)

**Note:** The existing `load_csv` tool now also automatically detects and handles glob patterns when the file path contains `*`, `?`, or `[` characters for backward compatibility.

### Excel Analysis Tools

#### `load_excel`
Load an Excel (.xlsx) file into DuckDB for analysis.

**Parameters:**
- `file_path` (required): Path to the Excel file (.xlsx only)
- `table_name` (optional): Name for the table (defaults to filename)
- `sheet` (optional): Name or index of the sheet to load (defaults to first sheet)
- `range` (optional): Cell range to load (e.g., "A1:C10", loads all data by default)
- `header` (optional): Whether Excel file has header row (default: true)
- `all_varchar` (optional): Force all columns to be treated as text (default: false)

**Examples:**
- Basic: `file_path: "data.xlsx"`
- Specific sheet: `file_path: "workbook.xlsx", sheet: "Sales"`
- Range selection: `file_path: "report.xlsx", range: "B2:E50"`
- All options: `file_path: "complex.xlsx", sheet: "Data", range: "A1:Z100", header: false`

#### `load_multiple_excels`
Load multiple Excel files using glob patterns or file lists into DuckDB for analysis.

**Parameters:**
- `pattern_or_files` (required): Glob pattern (e.g., "data/*.xlsx", "reports/**/*.xlsx") or array of specific file paths
- `table_name` (optional): Name for the combined table (defaults to "multi_excel_data")
- `union_by_name` (optional): Combine files by column name instead of position (default: false)
- `include_filename` (optional): Include a filename column to track source file for each row (default: false)
- `sheet` (optional): Name or index of the sheet to load from all files (defaults to first sheet)
- `header` (optional): Whether Excel files have header rows (default: true)
- `all_varchar` (optional): Force all columns to be treated as text (default: false)

**Examples:**
- Load all Excel files: `"data/*.xlsx"`
- Load files recursively: `"reports/**/*.xlsx"`
- Load specific files: `["report1.xlsx", "report2.xlsx"]`
- With sheet selection: `pattern_or_files: "*.xlsx", sheet: "Summary"`

#### `discover_excel_files`
Discover Excel files matching a glob pattern without loading them.

**Parameters:**
- `pattern` (required): Glob pattern to search for Excel files

**Returns:** List of matching Excel files with metadata (size, modification date, existence status), separated from non-Excel files

**Important:** Only .xlsx files are supported. Legacy .xls files must be converted to .xlsx format first.

### Specialized Analysis Tools

#### `optimize_expenses`
Analyze credit card or bank transaction data to identify expense optimization opportunities with actionable recommendations and realistic savings estimates.

**Parameters:**
- `table_name` (required): Name of the loaded table containing transaction data
- `amount_column` (optional, default: "Amount"): Column containing transaction amounts
- `name_column` (optional, default: "Name"): Column containing merchant/transaction descriptions
- `date_column` (optional, default: "Date"): Column containing transaction dates

**Required Data Format:**
- **Amount**: Numeric values (negative for expenses, positive for income)
- **Name**: Text description of the merchant or transaction
- **Date**: Date of the transaction (YYYY-MM-DD or similar format)

**Features:**
- 📊 Monthly spending analysis with trends and largest purchases
- 🔄 Subscription detection - automatically finds recurring charges (2+ occurrences, <$100)
- ☕ Small purchase categorization - groups coffee, dining, treats, etc.
- 🛒 Grocery spending optimization - analyzes shopping patterns for major stores
- 💰 Savings estimates - calculates realistic monthly savings potential based on spending patterns
- 📋 Action prioritization - orders recommendations by impact vs. effort

#### `detect_anomalies`
Detect anomalies and irregularities in dataset using statistical analysis and business logic rules.

**Parameters:**
- `table_name` (required): Name of the table to analyze for anomalies
- `anomaly_types` (optional): Types of anomalies to detect: statistical, duplicates, nulls, outliers, patterns, business_logic (default: ['statistical', 'duplicates', 'nulls', 'outliers', 'patterns'])
- `focus_columns` (optional): Specific columns to focus anomaly detection on
- `severity_threshold` (optional, default: "medium"): Minimum severity level to report (low, medium, high, critical)

## Common Use Cases

### 💳 Family Credit Card Analysis
*"I use Quack MCP to analyze my family's credit card expenses with summaries, anomalies and detailed breakdowns."*

**Real-world example:**
- Load multiple credit card CSV exports from different family members
- Generate monthly spending summaries by person and category
- Detect unusual spending patterns or potential fraud
- Identify subscription services we forgot about
- Find opportunities to reduce dining out or entertainment costs
- Track progress on budget goals month-over-month

```
Load all credit card files: ["dad_card.csv", "mom_card.csv", "family_card.csv"]
Run expense optimization analysis to find savings opportunities
Detect anomalies to catch any unusual transactions
Show me monthly trends and biggest expense categories by family member
```

### 📊 Business Sales Analytics
**Scenario:** E-commerce business analyzing quarterly performance
- Load sales data from multiple sources (website, retail, wholesale)
- Compare performance across different quarters and regions  
- Identify top-performing products and seasonal trends
- Analyze customer behavior and lifetime value

### 📈 Excel Financial Reports Analysis
*"I analyze financial reports from Excel files with complex worksheets and multiple data ranges."*

**Real-world example:**
- Load Excel files from accounting system exports
- Extract specific worksheet ranges (e.g., "Summary!B5:F50")
- Combine multiple quarterly Excel reports into unified analysis
- Process both CSV bank exports and Excel financial statements
- Generate consolidated financial insights across different data sources

```
Load Excel financial data: "Q1_2024_financials.xlsx" (sheet: "Summary", range: "A1:G100")
Load multiple quarterly reports: ["Q1.xlsx", "Q2.xlsx", "Q3.xlsx", "Q4.xlsx"] 
Combine with CSV bank data for comprehensive financial analysis
Run expense optimization to identify cost-saving opportunities
```

### 🏠 Real Estate Investment Analysis  
**Scenario:** Property investor tracking rental income and expenses
- Combine rental income, maintenance costs, and property taxes
- Calculate ROI and cash flow for each property
- Identify properties needing attention or generating losses
- Track market trends and appreciation

### 📈 Stock Portfolio Performance
**Scenario:** Personal investment tracking and analysis
- Load transaction history from multiple brokerage accounts
- Calculate gains/losses, dividend income, and portfolio allocation
- Identify underperforming investments
- Track sector diversification and rebalancing needs

### 🛒 Retail Inventory Management
**Scenario:** Small business optimizing inventory and purchasing
- Analyze sales velocity and seasonal patterns
- Identify slow-moving inventory
- Optimize reorder points and quantities
- Track supplier performance and costs

## Example Workflows

### Basic CSV Analysis
1. Load a CSV file: `load_csv` with your file path
2. Examine the structure: `describe_table` or `list_tables`
3. Query your data: `query_csv` with SQL queries
4. Analyze patterns: `analyze_csv` for statistical insights

### Family Expense Analysis Workflow
1. **Gather data**: Export CSV files from all credit cards/bank accounts
2. **Load multiple files**: `load_multiple_csvs` with family member files
3. **Get overview**: `optimize_expenses` for spending patterns and savings opportunities
4. **Find issues**: `detect_anomalies` to catch unusual transactions or potential fraud
5. **Deep dive**: Use custom SQL queries to analyze specific categories or time periods
6. **Track progress**: Compare month-over-month trends and budget performance

### Business Intelligence Workflow
1. **Load datasets**: Use glob patterns to load all relevant CSV files
2. **Data quality check**: `detect_anomalies` to identify data issues
3. **Exploratory analysis**: `analyze_csv` for statistical overview
4. **Custom analysis**: Complex SQL queries for business-specific metrics
5. **Generate reports**: Create formatted summaries and actionable insights

### Data Quality Assessment
1. Load your dataset: `load_csv` with your data file
2. Run anomaly detection: `detect_anomalies` to identify data issues
3. Clean data based on findings and re-analyze

### Excel Analysis Workflow
1. **Discover Excel files**: `discover_excel_files` to find available Excel files
2. **Load Excel data**: `load_excel` with specific sheet and range if needed
3. **Examine structure**: Review schema and data types automatically displayed
4. **Advanced analysis**: Use SQL queries for complex Excel data analysis
5. **Combine sources**: Mix Excel and CSV data for comprehensive insights

### Multi-Format Data Integration
1. **Load Excel files**: `load_multiple_excels` for quarterly/annual Excel reports
2. **Load CSV data**: `load_multiple_csvs` for transaction exports
3. **Unified analysis**: Query across both Excel and CSV tables with JOINs
4. **Generate insights**: Create reports combining both data sources

## Using with Claude Code

### Prerequisites
- Claude Code installed and configured
- Either Node.js installed (for local) OR Docker installed (for containerized)

### Local Configuration

For local installation, add the following to your Claude Code MCP configuration file (usually `~/.config/claude-code/mcp_servers.json`):

```json
{
  "mcpServers": {
    "quack-csv": {
      "command": "node",
      "args": ["/absolute/path/to/quack-mcp/src/index.ts"],
      "env": {}
    }
  }
}
```

### Docker Configuration

For Docker deployment, configure Claude Code to use the containerized server:

```json
{
  "mcpServers": {
    "quack-csv": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-v", "/absolute/path/to/your/csv/files:/app/csv-data:ro",
        "-v", "/absolute/path/to/quack-mcp/data:/app/data:ro",
        "quack-mcp"
      ],
      "env": {}
    }
  }
}
```

Or with docker-compose:

```json
{
  "mcpServers": {
    "quack-csv": {
      "command": "docker-compose",
      "args": [
        "-f", "/absolute/path/to/quack-mcp/docker-compose.yml",
        "run", "--rm", "quack-mcp"
      ],
      "env": {},
      "cwd": "/absolute/path/to/quack-mcp"
    }
  }
}
```

**Important:** 
- Replace paths with actual full paths to your directories
- Ensure CSV files are accessible via volume mounts for Docker setup
- For Docker setup, build the image first: `docker build -t quack-mcp .`

### Usage Examples

#### Basic CSV Analysis

**Local:**
```
Load the CSV file at /path/to/your/data.csv
```

**Docker:**
```
Load the CSV file at /app/csv-data/data.csv
```
*(Mount your CSV directory to `/app/csv-data` in Docker configuration)*

#### Expense Analysis

**Local:**
```
I have credit card data at /Users/me/transactions.csv. Load it and run an expense optimization analysis.
```

**Docker:**
```
I have credit card data at /app/csv-data/transactions.csv. Load it and run an expense optimization analysis.
```

#### Complex Data Analysis

**Local:**
```
I have sales data at /Users/me/sales_2024.csv. Load it and then:
1. Show me monthly sales trends
2. Find the top 10 customers by revenue
3. Calculate average order value by product category
```

**Docker:**
```
I have sales data at /app/csv-data/sales_2024.csv. Load it and then:
1. Show me monthly sales trends
2. Find the top 10 customers by revenue
3. Calculate average order value by product category
```

#### Data Quality Assessment

**Local:**
```
Load /path/to/customer_data.csv and help me understand:
- How many missing values are in each column
- What's the distribution of customer ages  
- Are there any duplicate customer IDs
```

**Docker:**
```
Load /app/csv-data/customer_data.csv and help me understand:
- How many missing values are in each column
- What's the distribution of customer ages
- Are there any duplicate customer IDs
```

#### Multi-CSV Analysis

**Local:**
```
Load all CSV files matching the pattern /path/to/sales_*.csv and combine them into a single table
```

```
Load multiple quarterly sales files: ["sales_q1.csv", "sales_q2.csv", "sales_q3.csv", "sales_q4.csv"] with filename tracking
```

```
Discover what CSV files are available in /path/to/data/ directory matching the pattern *.csv
```

**Docker:**
```
Load all CSV files in /app/csv-data/reports/ recursively using the pattern /app/csv-data/reports/**/*.csv
```

```
Load monthly data files with different schemas using union by name: /app/csv-data/monthly_*.csv
```

**Advanced Multi-CSV Examples:**
```
I have sales data split across multiple files in /path/to/sales/ directory:
1. Load all files matching sales_2024_*.csv
2. Include filename column to track data sources
3. Use union_by_name since some files have extra columns
4. Analyze total revenue by quarter and source file
```

```
Load transaction data from multiple sources:
- All files in transactions/ directory
- Include legacy data from archive/2023/
- Combine using pattern ["transactions/*.csv", "archive/2023/*.csv"]
- Generate monthly spending report
```

#### Excel Analysis

**Local:**
```
Load the Excel file at /path/to/financial_report.xlsx and analyze the Summary sheet
```

```
Load Excel data from specific range: /path/to/budget.xlsx sheet "Q1" range "B5:G50"
```

**Docker:**
```
Load the Excel file at /app/csv-data/sales_data.xlsx from the "Monthly Sales" sheet
```

```
Load multiple Excel quarterly reports: /app/csv-data/reports/*.xlsx with filename tracking
```

#### Mixed Data Analysis

**Local:**
```
I have both Excel and CSV data:
1. Load Excel file /path/to/budget_2024.xlsx (sheet: "Summary")
2. Load CSV transaction data /path/to/transactions.csv  
3. Join the data to compare budget vs actual spending
4. Generate variance analysis report
```

**Docker:**
```
Load financial data from mixed sources:
- Excel budget: /app/csv-data/budget.xlsx (sheet: "Annual", range: "A1:F12")
- CSV transactions: /app/csv-data/transactions_*.csv pattern
- Combine and analyze budget performance by month
```

#### Excel-Specific Examples

**Local:**
```
I have an Excel workbook with multiple sheets at /path/to/company_data.xlsx:
1. Load the "Sales" sheet with range A1:Z100
2. Load the "Expenses" sheet separately  
3. Create a profit analysis combining both sheets
4. Identify top revenue sources and biggest cost centers
```

**Docker:**
```
Load Excel files from accounting system:
- Multiple files: /app/csv-data/monthly_*.xlsx
- Extract "P&L" sheet from each file
- Include filename to track months
- Generate year-over-year comparison
```

### Available Tools in Claude Code

#### `load_csv`
- **Usage**: "Load the CSV at /path/to/file.csv"
- **Features**: Automatic delimiter detection, schema analysis, sample preview, glob pattern support

#### `query_csv`
- **Usage**: "Query the data to find all records where column > value"
- **Features**: Full SQL support including JOINs, aggregations, window functions

#### `describe_table`
- **Usage**: "Describe the structure of table_name"

#### `list_tables`
- **Usage**: "What tables are currently loaded?"

#### `analyze_csv`
- **Usage**: "Analyze the numerical columns in my data"
- **Features**: Count, unique values, min/max, averages

#### `optimize_expenses`
- **Usage**: "Analyze my spending for optimization opportunities"
- **Features**: Subscription detection, category analysis, savings calculations

#### `detect_anomalies`
- **Usage**: "Find anomalies in my dataset"
- **Features**: Statistical outliers, data quality issues, pattern detection

#### `load_multiple_csvs`
- **Usage**: "Load all CSV files matching data/*.csv pattern"
- **Features**: Glob patterns, file lists, schema unification, filename tracking

#### `discover_csv_files`
- **Usage**: "What CSV files are available in the reports/ directory?"
- **Features**: File discovery, metadata, size and modification info

#### `load_excel`
- **Usage**: "Load the Excel file at /path/to/data.xlsx" or "Load sheet 'Summary' from financial_report.xlsx"
- **Features**: Sheet selection, range specification, automatic schema detection, .xlsx support only

#### `load_multiple_excels`
- **Usage**: "Load all Excel files matching reports/*.xlsx pattern" or "Load quarterly Excel files with filename tracking"
- **Features**: Glob patterns, file lists, sheet selection, schema unification, filename tracking

#### `discover_excel_files`
- **Usage**: "What Excel files are available in the financial/ directory?"
- **Features**: Excel file discovery, metadata, differentiation from other file types

## Glob Pattern Reference

Multi-CSV and Excel tools support glob patterns for flexible file matching:

| Pattern | Description | CSV Example | Excel Example |
|---------|-------------|-------------|---------------|
| `*` | Matches any characters | `sales_*.csv` matches `sales_q1.csv` | `report_*.xlsx` matches `report_q1.xlsx` |
| `**` | Matches directories recursively | `data/**/*.csv` finds CSVs at any depth | `reports/**/*.xlsx` finds Excel files at any depth |
| `?` | Matches single character | `report_?.csv` matches `report_1.csv` | `data_?.xlsx` matches `data_1.xlsx` |
| `[abc]` | Matches any character in brackets | `sales_[123].csv` | `budget_[ABC].xlsx` |
| `[a-z]` | Matches character range | `file_[a-c].csv` | `sheet_[a-c].xlsx` |

**Example Patterns:**
- `*.csv` / `*.xlsx` - All CSV/Excel files in current directory
- `data/*.csv` / `data/*.xlsx` - All files in data directory
- `reports/**/*.csv` / `reports/**/*.xlsx` - All files in reports directory and subdirectories
- `sales_2024_*.csv` / `financial_2024_*.xlsx` - All files for 2024
- `**/monthly_[0-9][0-9].csv` / `**/quarterly_[1-4].xlsx` - Numbered files anywhere in directory tree

**Note:** All patterns work with local files. DuckDB handles the glob expansion internally.

## Tips for Best Results

### 1. Use Clear, Natural Language
Instead of technical commands, use natural descriptions:
- ❌ "Execute load_csv with file_path=/data/sales.csv"
- ✅ "Load the sales data from /data/sales.csv"

### 2. Leverage Claude's SQL Knowledge
Ask for complex analysis in plain English:
- "Show me the correlation between price and sales volume"
- "Find seasonal patterns in the data"
- "Identify outliers in the revenue column"

### 3. Iterative Analysis
Build on previous queries:
- "Now filter that result to only include 2024 data"
- "Add a column showing the percentage change from last month"

### 4. Data Visualization Requests
Ask for formatted output:
- "Create a summary table of sales by region"
- "Show the top 10 results formatted nicely"

### 5. Multi-File Best Practices
When working with multiple CSV or Excel files:
- **Use `union_by_name=true`** when files have different column orders or missing columns
- **Enable `filename=true`** to track which file each row came from
- **Use `discover_csv_files` or `discover_excel_files`** first to see what files match your pattern
- **Start with a small pattern** to test schema compatibility before loading all files
- **Use descriptive table names** when loading multiple datasets

### 6. Excel-Specific Best Practices
When working with Excel files:
- **Specify sheet names** when workbooks have multiple sheets: `sheet: "Summary"`
- **Use range selection** for large workbooks: `range: "A1:G100"`
- **Convert .xls to .xlsx** - only .xlsx format is supported
- **Test with single files** before loading multiple Excel files
- **Use `all_varchar=true`** if Excel has mixed data types causing issues

**Examples:**
- ✅ "Load quarterly Excel reports with specific sheet: reports/*.xlsx, sheet: 'Q1 Summary'"
- ✅ "Load Excel range B5:F50 from the 'Data' sheet in financial_report.xlsx"
- ✅ "First discover what Excel files are available, then load with filename tracking"
- ✅ "Load multiple Excel files and combine with CSV transaction data"

## Troubleshooting

### Server Not Found
If Claude Code can't find the MCP server:

**Local Installation:**
1. Check that the path in your configuration is absolute and correct
2. Verify Node.js is installed and accessible
3. Restart Claude Code after configuration changes

**Docker Installation:**
1. Ensure Docker image is built: `docker build -t quack-mcp .`
2. Check Docker is running and accessible
3. Verify volume mount paths are correct and absolute
4. Restart Claude Code after configuration changes

### Permission Errors

**Local Installation:**
1. Ensure the CSV file path is correct and accessible
2. Check file permissions
3. Use absolute paths for CSV files

**Docker Installation:**
1. Ensure CSV files are mounted as volumes in Docker configuration
2. Check volume mount paths are correct: `-v /host/path:/app/csv-data:ro`
3. Verify Docker has permission to access the mounted directories
4. Use paths relative to container mount points (e.g., `/app/csv-data/file.csv`)

### Container Issues

**Docker-specific problems:**
1. **Container won't start**: Check Docker logs with `docker logs <container-id>`
2. **File not found**: Ensure CSV files are properly mounted as volumes
3. **Permission denied**: Check file permissions on host system
4. **Memory issues**: DuckDB requires sufficient container memory for large CSV files

### SQL Errors
If queries fail:
1. Check the table name (use `list_tables` to verify)
2. Verify column names with `describe_table`
3. Remember DuckDB uses standard SQL syntax

### Performance Issues
For large CSV files:

**Both Local and Docker:**
1. DuckDB is optimized for analytics but very large files may take time to load
2. Consider using `LIMIT` clauses for initial exploration
3. The server loads data into memory - ensure sufficient RAM

**Docker-specific:**
1. Increase container memory limits if needed
2. Consider mounting CSV files read-only for better performance

## MCP Client Configuration

### Local Installation
For other MCP clients, add to your configuration:

```json
{
  "mcpServers": {
    "quack-mcp": {
      "command": "node",
      "args": ["/path/to/quack-mcp/src/index.ts"]
    }
  }
}
```

### Docker Installation
For containerized deployment with other MCP clients:

```json
{
  "mcpServers": {
    "quack-mcp": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-v", "/path/to/csv/files:/app/csv-data:ro",
        "quack-mcp"
      ]
    }
  }
}
```

Or with docker-compose:

```json
{
  "mcpServers": {
    "quack-mcp": {
      "command": "docker-compose",
      "args": [
        "-f", "/path/to/quack-mcp/docker-compose.yml",
        "run", "--rm", "quack-mcp"
      ],
      "cwd": "/path/to/quack-mcp"
    }
  }
}
```

## Contributing

We'd love your help making Quack MCP even better! 🦆 Whether you're fixing a bug, adding a feature, or improving documentation, all contributions are welcome.

### Getting Started

1. **Fork the repository** and clone it locally
2. **Install dependencies**: `npm install`
3. **Make your changes** following our coding conventions (see `CLAUDE.md`)
4. **Test your changes**: `npm test`
5. **Submit a pull request** with a clear description

### What We're Looking For

- 🐛 **Bug fixes** - Found something broken? We'd love a fix!
- ✨ **New analysis tools** - Got an idea for a useful CSV analysis feature?
- 📚 **Documentation improvements** - Clearer examples, better explanations
- 🧪 **Test coverage** - More tests mean more confidence
- 🚀 **Performance improvements** - Making things faster is always welcome

### Development Guidelines

- **Follow TypeScript strict mode** - We use strict typing for reliability
- **Write tests** - New features should include tests
- **Keep it simple** - Clear, readable code is preferred
- **Document your changes** - Update README.md if you add new features

### Need Help?

- Check out `CLAUDE.md` for detailed development guidelines
- Look at existing code for patterns and conventions
- Open an issue if you're unsure about something

### Code of Conduct

Be kind, be respectful, and remember we're all here to make data analysis easier and more accessible. Let's build something great together! 🎉

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.
