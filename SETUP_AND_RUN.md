# Setup and Run (Windows)

This guide is machine-independent. Replace placeholder values before running commands.

## 1. Set your local values

```powershell
$PROJECT_ROOT = "<path to SC3020_Project2>"
$DB_NAME = "<your database name>"          # Example: sc3020proj
$DB_USER = "<your postgres user>"          # Example: postgres
$DB_HOST = "localhost"
$DB_PORT = "5432"

# Use psql if it's in PATH; otherwise use full path to psql.exe.
$PSQL = "psql"
```

## 2. Create virtual environment and install packages

```powershell
Set-Location $PROJECT_ROOT
python -m venv .venv
$PY = "$PROJECT_ROOT/.venv/Scripts/python.exe"
& $PY -m pip install --upgrade pip
& $PY -m pip install psycopg2-binary sqlglot
```

## 3. Build and load TPC-H data

Run scripts in this order on the same database you will use in the app:

```powershell
& $PSQL -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f "$PROJECT_ROOT/tpch_schema_postgres.sql"
& $PSQL -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f "$PROJECT_ROOT/tpch_copy_clean.sql"
& $PSQL -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f "$PROJECT_ROOT/tpch_constraints_postgres.sql"
& $PSQL -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f "$PROJECT_ROOT/tpch_post_load.sql"
```

If load fails, update file paths in tpch_copy_clean.sql to your local .tbl files.

## 4. Verify data loaded

```powershell
& $PSQL -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "select 'customer' as t, count(*) from tpch.customer union all select 'orders', count(*) from tpch.orders union all select 'nation', count(*) from tpch.nation;"
```

Expected non-zero counts:

- customer about 150000
- orders about 1500000
- nation 25

## 5. Run GUI

```powershell
& $PY "$PROJECT_ROOT/project.py"
```

GUI connection fields:

- Host: value of $DB_HOST
- Port: value of $DB_PORT
- Database: value of $DB_NAME
- User: value of $DB_USER
- Password: your PostgreSQL password

## 6. Optional CLI run

```powershell
& $PY "$PROJECT_ROOT/project.py" --nogui --query-file "$PROJECT_ROOT/demo_queries.sql" --all-queries --host $DB_HOST --port $DB_PORT --dbname $DB_NAME --user $DB_USER --password "<your password>"
```

## 7. Quick troubleshooting

- psql not recognized:
  - Set $PSQL to full path, for example C:/Program Files/PostgreSQL/18/bin/psql.exe
- psycopg2 missing in GUI:
  - Launch app with $PY, not global python
- relation tpch.<table> does not exist:
  - Data loaded into wrong database/schema or scripts were run against another DB
