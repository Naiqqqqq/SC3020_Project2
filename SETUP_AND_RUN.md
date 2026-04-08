# Setup and Run Guide (Windows)

This guide is only for getting the project running end-to-end.

## 1. Prerequisites

- Windows machine
- PostgreSQL installed and running
- Python 3.11+ installed
- Project folder cloned at:
  - C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2

## 2. Python Environment and Dependencies

From PowerShell in project root:

```powershell
C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/.venv/Scripts/python.exe -m pip install psycopg2-binary sqlglot
```

If .venv does not exist yet:

```powershell
python -m venv .venv
C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/.venv/Scripts/python.exe -m pip install --upgrade pip
C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/.venv/Scripts/python.exe -m pip install psycopg2-binary sqlglot
```

## 3. Prepare Database (TPC-H)

Use the same database you will enter in the GUI (example: sc3020proj).

### 3.1 Create schema and tables

```powershell
& "C:/Program Files/PostgreSQL/18/bin/psql.exe" -h localhost -U postgres -d sc3020proj -f "C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/tpch_schema_postgres.sql"
```

### 3.2 Set data file paths and load rows

The loader script currently points to:

- C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/TPC-H V3.0.1/dbgen/*.tbl

If your files are elsewhere, edit paths in tpch_copy_clean.sql first.

Then run:

```powershell
& "C:/Program Files/PostgreSQL/18/bin/psql.exe" -h localhost -U postgres -d sc3020proj -f "C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/tpch_copy_clean.sql"
```

### 3.3 Add constraints

```powershell
& "C:/Program Files/PostgreSQL/18/bin/psql.exe" -h localhost -U postgres -d sc3020proj -f "C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/tpch_constraints_postgres.sql"
```

### 3.4 Analyze for optimizer stats

```powershell
& "C:/Program Files/PostgreSQL/18/bin/psql.exe" -h localhost -U postgres -d sc3020proj -f "C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/tpch_post_load.sql"
```

## 4. Verify Data Loaded

```powershell
& "C:/Program Files/PostgreSQL/18/bin/psql.exe" -h localhost -U postgres -d sc3020proj -c "select 'customer' as t, count(*) from tpch.customer union all select 'orders', count(*) from tpch.orders union all select 'nation', count(*) from tpch.nation;"
```

Expected non-zero counts (for SF1):

- customer around 150000
- orders around 1500000
- nation 25

## 5. Run the App

Always launch with the project venv interpreter:

```powershell
C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/.venv/Scripts/python.exe project.py
```

In GUI:

- Host: localhost
- Port: 5432
- Database: sc3020proj (or your actual DB)
- User: postgres
- Password: your PostgreSQL password

Then click Run Annotation.

## 6. Run in CLI (Optional)

Single query:

```powershell
C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/.venv/Scripts/python.exe project.py --nogui --query "select * from tpch.customer" --host localhost --port 5432 --dbname sc3020proj --user postgres --password YOUR_PASSWORD
```

All demo queries:

```powershell
C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/.venv/Scripts/python.exe project.py --nogui --query-file demo_queries.sql --all-queries --host localhost --port 5432 --dbname sc3020proj --user postgres --password YOUR_PASSWORD
```

## 7. Common Issues

### psql is not recognized

Use full path:

```powershell
& "C:/Program Files/PostgreSQL/18/bin/psql.exe" ...
```

### pip is not recognized

Use Python module form:

```powershell
C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/.venv/Scripts/python.exe -m pip install psycopg2-binary sqlglot
```

### psycopg2 not installed popup in GUI

You launched with a different Python interpreter. Start app with:

```powershell
C:/Users/mings/OneDrive/Documents/GitHub/SC3020_Project2/.venv/Scripts/python.exe project.py
```

### relation tpch.<table> does not exist

Your data is not in tpch schema, or was loaded into another DB/schema.

Check:

```sql
SELECT to_regclass('tpch.customer'), to_regclass('tpch.orders'), to_regclass('tpch.nation');
```

### extra data after last expected column during COPY

Your source may be raw dbgen output with trailing delimiter. Use cleaned files or preprocess to remove final trailing pipe before loading.
