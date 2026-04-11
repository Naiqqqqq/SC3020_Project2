# SC3020 Project 2 — Setup & Run Instructions

## Prerequisites

| Requirement        | Version              |
|--------------------|----------------------|
| Python             | 3.9 or later         |
| PostgreSQL         | 12 or later          |
| Graphviz (system)  | Any recent release   |

> **Note:** The Graphviz *system binary* is required for visual plan trees. The Python `graphviz` package is just a wrapper — it will not work without the system binary installed.

---

## 1. Install System Dependencies

### macOS

```bash
brew install graphviz
```

### Ubuntu / Debian

```bash
sudo apt update && sudo apt install -y graphviz
```

### Windows

Download and install from [graphviz.org/download](https://graphviz.org/download/). Make sure the `bin` folder is in your system `PATH`.

---

## 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

This installs:

| Package            | Purpose                                      |
|--------------------|----------------------------------------------|
| `psycopg2-binary`  | PostgreSQL database driver                   |
| `sqlglot`          | SQL parsing and AST-based table extraction   |
| `streamlit`        | Web-based GUI framework                      |
| `graphviz`         | Python bindings for Graphviz DOT rendering   |

---

## 3. Set Up the TPC-H Database

### 3a. Create the database

```bash
createdb TPC-H
```

Or via `psql`:

```sql
CREATE DATABASE "TPC-H";
```

### 3b. Create the schema and tables

```bash
psql -d "TPC-H" -f tpch_schema_postgres.sql
```

### 3c. Load data

Edit `tpch_copy_clean.sql` to point the file paths to your local `.tbl` / `.csv` files, then:

```bash
psql -d "TPC-H" -f tpch_copy_clean.sql
```

### 3d. Add constraints and analyze

```bash
psql -d "TPC-H" -f tpch_constraints_postgres.sql
psql -d "TPC-H" -f tpch_post_load.sql
```

---

## 4. Running the Software

### Option A: Streamlit GUI (recommended)

```bash
python project.py
```

This launches the Streamlit web application at `http://localhost:8501`.

Alternatively, you can run Streamlit directly:

```bash
streamlit run interface.py
```

#### Using the GUI

1. **Configure the connection** in the sidebar (host, port, database name, user, password).
2. **Click "Test Connection"** to verify connectivity.
3. **Enter an SQL query** in the text area (a default example is pre-filled).
4. **Click "Run Annotation"** to generate results.
5. **Browse the tabs:**
   - **Annotated Query** — SQL with inline annotations and color-coded explanation cards.
   - **QEP Tree** — Visual (Graphviz), text, and raw JSON views of the query execution plan.
   - **AQP Comparison Table** — Cost comparison of all generated alternative query plans.
   - **AQP Comparison Trees** — Side-by-side visual comparison of QEP vs. any AQP.
   - **Custom AQP Config** — Toggle individual planner methods on/off and generate a custom AQP.

### Option B: Command-Line Interface (CLI)

Run a single inline query:

```bash
python project.py --nogui \
    --query "SELECT * FROM customer C, orders O WHERE C.c_custkey = O.o_custkey" \
    --host localhost --port 5432 --dbname "TPC-H" --user postgres --password ""
```

Run all queries from a file:

```bash
python project.py --nogui \
    --query-file demo_queries.sql --all-queries \
    --host localhost --port 5432 --dbname "TPC-H" --user postgres
```

Run a specific query from a file (1-based index):

```bash
python project.py --nogui \
    --query-file demo_queries.sql --query-index 3 \
    --host localhost --port 5432 --dbname "TPC-H" --user postgres
```

### CLI Flags Reference

| Flag             | Description                                        |
|------------------|----------------------------------------------------|
| `--nogui`        | Run in CLI mode (no GUI)                           |
| `--query`        | Inline SQL query string                            |
| `--query-file`   | Path to a `.sql` file                              |
| `--query-index`  | 1-based index of statement in file                 |
| `--all-queries`  | Process every statement in file                    |
| `--host`         | PostgreSQL host (default: `localhost`)              |
| `--port`         | PostgreSQL port (default: `5432`)                  |
| `--dbname`       | Database name (default: `postgres`)                |
| `--user`         | Database user (default: `postgres`)                |
| `--password`     | Database password (default: empty)                 |

---

## 5. Troubleshooting

| Issue                                    | Solution                                                                 |
|------------------------------------------|--------------------------------------------------------------------------|
| `ModuleNotFoundError: psycopg2`          | Run `pip install psycopg2-binary`                                        |
| `graphviz` renders text instead of graph | Install the system binary: `brew install graphviz` or `apt install graphviz` |
| Connection refused                       | Verify PostgreSQL is running and the host/port/credentials are correct   |
| `relation "customer" does not exist`     | Ensure TPC-H tables are loaded and `search_path` includes the schema     |
| Port must be a number                    | Ensure the port field contains only digits                               |

---

## 6. Project File Structure

```
SC3020_Project2/
├── project.py            # Main entry point (GUI launch or CLI)
├── interface.py          # Streamlit GUI
├── annotation.py         # Annotation generation engine
├── preprocessing.py      # SQL parsing, EXPLAIN, AQP generation
├── requirements.txt      # Python dependencies
├── demo_queries.sql      # Example TPC-H queries
├── tpch_schema_postgres.sql
├── tpch_constraints_postgres.sql
├── tpch_copy_clean.sql
└── tpch_post_load.sql
```
