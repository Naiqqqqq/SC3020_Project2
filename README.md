# SC3020 Project 2 - Query Plan-Based SQL Comprehension

This project annotates SQL queries using PostgreSQL query plans.

## Main Files

- `project.py` - entrypoint (GUI by default)
- `interface.py` - Tkinter GUI
- `preprocessing.py` - query normalization + QEP/AQP retrieval
- `annotation.py` - SQL annotation generation

## Setup

1. Install Python 3.11+
2. Install package:
   - `pip install psycopg2-binary`
3. Run:
   - `python project.py`

## SQL Utility Files

- `tpch_schema_postgres.sql`
- `tpch_constraints_postgres.sql`
- `tpch_post_load.sql`
- `tpch_copy_clean.sql`
- `demo_queries.sql`

## Notes

Large benchmark data and generated `.tbl` files are excluded from git by `.gitignore`.
