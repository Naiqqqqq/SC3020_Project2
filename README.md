# SC3020 Project 2 - Query Plan-Based SQL Comprehension

This project analyzes a SQL query using PostgreSQL's optimizer output, then produces a human-readable annotated version of the query.

At a high level, it does three things:

1. Gets the baseline Query Execution Plan (QEP) via EXPLAIN FORMAT JSON.
2. Generates alternative plans (AQPs) by disabling one planner method at a time.
3. Maps plan operators back to query components and explains likely optimizer decisions using estimated costs.

The app supports both:

- GUI mode (default): Tkinter desktop interface.
- CLI mode: script-friendly, prints output directly to console.

## What This Project Is For

Use this tool when you want to:

- Understand why PostgreSQL picked certain join or scan operators.
- Relate plan nodes to SQL components in an explainable way.
- Compare baseline and alternative plans using cost ratios.
- Demo query-plan reasoning on TPC-H style datasets.

## Repository Structure

Core Python modules:

- [project.py](project.py): Main entrypoint, argument parsing, pipeline orchestration.
- [interface.py](interface.py): Tkinter GUI with connection settings, query input, and result tabs.
- [preprocessing.py](preprocessing.py): Database connection, query normalization, QEP/AQP retrieval, plan tree formatting.
- [annotation.py](annotation.py): Plan-to-query mapping logic and final annotation text generation.

SQL helper scripts:

- [tpch_schema_postgres.sql](tpch_schema_postgres.sql): Creates tpch schema and base tables.
- [tpch_constraints_postgres.sql](tpch_constraints_postgres.sql): Adds PK/FK constraints.
- [tpch_copy_clean.sql](tpch_copy_clean.sql): Loads clean .tbl files with \copy (paths need customization).
- [tpch_post_load.sql](tpch_post_load.sql): Runs ANALYZE after data load.
- [demo_queries.sql](demo_queries.sql): Example queries for testing and demos.

Other:

- [PROJECT 2.pdf](PROJECT%202.pdf): Project report/spec document.
- [.gitignore](.gitignore): Excludes virtual environment and heavy generated benchmark data.

## How It Works Internally

### 1) Query Input and Normalization

Input comes from GUI text box, CLI --query, or CLI --query-file.

Normalization in preprocessing.normalize_query:

- Trims surrounding whitespace.
- Removes trailing semicolon if present.

This keeps SQL content intact while ensuring clean EXPLAIN execution.

### 2) Database Connection

Connection parameters are collected from GUI fields or CLI flags:

- host
- port
- dbname
- user
- password

Connection is created through psycopg2 in preprocessing.connect_postgres.

### 3) Baseline QEP Retrieval

The app executes:

EXPLAIN (FORMAT JSON, COSTS TRUE) <query>

The JSON payload is normalized to a Python dictionary and stored as qep_json.
The root plan's Total Cost is extracted as qep_total_cost.

### 4) Alternative Plan (AQP) Generation

For each planner setting below, the app disables it inside a transaction, runs EXPLAIN again, and rolls back:

- enable_nestloop
- enable_hashjoin
- enable_mergejoin
- enable_seqscan
- enable_indexscan
- enable_bitmapscan

Important behavior:

- Uses SET LOCAL <setting> TO off so changes are transaction-local.
- Uses BEGIN ... ROLLBACK for each setting.
- On failure for a setting, records a note instead of crashing the whole pipeline.

Each AQP record stores:

- setting name
- value (off)
- plan_json
- total_cost
- note (if generation failed)

### 5) Plan-to-Query Annotation Logic

annotation.generate_annotation combines multiple note builders:

- Scan notes:
   - Extracts table aliases from the FROM clause.
   - Matches each table/alias to scan node types in the plan.
   - Produces lines like Table X is accessed via Seq Scan.

- Join notes:
   - Walks plan nodes to find Nested Loop, Hash Join, Merge Join.
   - Extracts join condition from Hash Cond / Merge Cond / Join Filter if available.
   - Produces lines describing which join operator executes each condition.

- Reasoning notes:
   - For join operators seen in QEP, looks up the corresponding AQP where that operator is disabled.
   - Compares AQP cost to baseline QEP cost.
   - If ratio is significantly higher (> 1.05), explains that disabling the operator worsened estimated cost.
   - Otherwise, explains that costs are similar and choice may depend on row/distribution estimates.

### 6) Outputs Produced

The pipeline returns four key outputs:

- Annotated query text block.
- QEP tree (compact human-readable tree).
- AQP summary table.
- Raw QEP JSON dictionary.

In GUI mode, these appear in tabs.
In CLI mode, these are printed to stdout.

## Requirements

- Python 3.11+ (tested in this workspace with a newer Python as well).
- PostgreSQL server reachable from your machine.
- Python package:
   - psycopg2-binary
   - sqlglot

Install dependency:

```bash
python -m pip install psycopg2-binary sqlglot
```

If pip is not on PATH (common on Windows), run with your project venv interpreter:

```bash
C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/.venv/Scripts/python.exe -m pip install psycopg2-binary sqlglot
```

## Quick Start

### GUI Mode (Default)

Run:

```bash
python project.py
```

Then in the app:

1. Fill PostgreSQL connection settings.
2. Paste SQL or click Load SQL File.
3. Click Run Annotation.
4. Review results in:
    - Annotated Query
    - QEP Tree
    - AQP Summary

### CLI Mode

Run with inline query:

```bash
python project.py --nogui --query "select * from tpch.customer"
```

Run with SQL file:

```bash
python project.py --nogui --query-file demo_queries.sql
```

Run one statement from a multi-statement SQL file (1-based index):

```bash
python project.py --nogui --query-file demo_queries.sql --query-index 2
```

Run all statements from a multi-statement SQL file:

```bash
python project.py --nogui --query-file demo_queries.sql --all-queries
```

Supply DB credentials (as needed):

```bash
python project.py --nogui --query "select * from tpch.customer" --host localhost --port 5432 --dbname postgres --user postgres --password postgres
```

## Full CLI Arguments

- --nogui: Run CLI mode instead of Tkinter GUI.
- --query: SQL query text.
- --query-file: Path to SQL file.
- --query-index: 1-based statement index to run from a multi-statement file.
- --all-queries: Run all statements found in --query-file.
- --host: PostgreSQL host (default: localhost).
- --port: PostgreSQL port (default: 5432).
- --dbname: Database name (default: postgres).
- --user: Database user (default: postgres).
- --password: Database password (default: postgres).

## Database Setup (TPC-H Scripts)

If you want to run on TPC-H tables from this repo, execute scripts in this order:

1. Create schema and tables:

```sql
\i tpch_schema_postgres.sql
```

2. Load data (set paths in tpch_copy_clean.sql or pass with psql -v):

```sql
\i tpch_copy_clean.sql
```

3. Add PK/FK constraints:

```sql
\i tpch_constraints_postgres.sql
```

4. Update stats for optimizer:

```sql
\i tpch_post_load.sql
```

Notes:

- tpch_copy_clean.sql uses psql variables (for example, region_file, nation_file) so paths are machine-independent.
- Edit the variable values at the top of tpch_copy_clean.sql to point to your local .tbl files.
- Running ANALYZE is important for realistic planner estimates.

## Understanding the Result Tabs

### Annotated Query

Shows original SQL plus a PLAN-BASED ANNOTATIONS block that includes:

- table scan choices
- join operator usage
- short cost-based rationale from AQPs

### QEP Tree

Tree-style rendering of plan nodes with optional details:

- relation/alias
- startup/total cost range
- filter/join conditions when present

### AQP Summary

Table with one row per planner setting toggle:

- setting
- top_join observed in alternative plan
- total_cost
- ratio_vs_qep
- note (or generation status)

## Error Handling and Edge Cases

The app intentionally handles several failure modes safely:

- Missing psycopg2: raises clear install hint.
- Empty query: rejected early.
- Multi-statement query text in single-query mode: rejected with guidance to use --query-index/--all-queries.
- Invalid port: validation error.
- EXPLAIN returns no row or malformed payload: explicit exception.
- Single AQP failure: recorded as note; other AQPs still proceed.

## Known Limitations

- Annotation focuses mainly on scan and join nodes.
- Table alias extraction is parser-based when sqlglot is installed; a regex fallback is used only when parser support is unavailable.
- Reasoning uses estimated optimizer costs, not actual runtime.
- AQP exploration is limited to a fixed set of planner toggles.
- tpch_copy_clean.sql still requires setting local file paths, but no user-specific absolute paths are hardcoded.

## Development Notes

- Entry flow: project.main -> run_pipeline -> preprocessing + annotation.
- GUI and CLI share the same pipeline function, so logic is consistent across modes.
- Large benchmark data and generated .tbl files are intentionally excluded by [.gitignore](.gitignore).

## Suggested Next Improvements

- Add support for EXPLAIN ANALYZE toggle to compare actual runtime metrics.
- Expand annotations for sort/aggregate/hash materialization behavior.
- Add parser-backed SQL component mapping for higher robustness.
- Externalize planner settings into config file or CLI list.
- Add automated tests for plan parsing and annotation generation.
