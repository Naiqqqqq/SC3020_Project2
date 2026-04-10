# SC3020 Project 2 — Streamlit GUI Setup & Usage

This document covers how to set up and run the Streamlit-based graphical interface for the SQL Query Annotation tool.

## Prerequisites

- **Python 3.9+**
- **PostgreSQL** running locally (or remotely accessible)
- **TPC-H data** loaded into your PostgreSQL database (see the SQL scripts in this repo)

## Quick Start

### 1. Create a virtual environment

```bash
cd SC3020_Project2
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows
```

### 2. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

The `requirements.txt` includes:

- `psycopg2-binary` — PostgreSQL driver
- `sqlglot` — SQL parser for table/alias extraction
- `streamlit` — web-based GUI framework
- `graphviz` — Python bindings for visual QEP tree rendering

### 3. Install system Graphviz (for visual tree)

The visual QEP tree requires the Graphviz system binary (not just the Python package).

```bash
# macOS
brew install graphviz

# Ubuntu / Debian
sudo apt install graphviz

# Windows (via choco)
choco install graphviz
```

If you skip this step, the app still works — it will show a text-based tree instead.

### 4. Run the app

```bash
python project.py
```

This launches the Streamlit server. Your browser will open automatically at:

```
http://localhost:8501
```

You can also launch Streamlit directly:

```bash
streamlit run interface.py
```

## Using the App

### Sidebar — Connection Settings

Fill in your PostgreSQL connection details:

| Field    | Default     |
|----------|-------------|
| Host     | `localhost` |
| Port     | `5432`      |
| Database | `sc3020`    |
| User     | `argel`     |

Enter your password, then click **Test Connection** to verify. On success, it displays the PostgreSQL version string.

### Sidebar — Demo Queries

Select a preloaded query from the dropdown. These are loaded from `demo_queries.sql` in the project root. The selected query replaces the text in the query input box.

### Main Area — Query Input

Type or paste any SQL query. You can also load queries from the demo dropdown or type your own.

Click **Run Annotation** to execute the pipeline.

### Results — Three Tabs

#### Tab 1: Annotated Query

Two-column layout:

- **Left**: Your SQL with line numbers and colour-coded highlights
  - Blue = table access (scan operations)
  - Green = join operations
  - Amber = cost-based reasoning
  - Pink = sort operations
  - Teal = aggregate operations

- **Right**: Annotation cards grouped by category, each explaining what the query optimizer is doing and why

#### Tab 2: QEP Tree

Three sub-tabs:

- **Visual Tree** — Graphviz-rendered tree with colour-coded nodes (requires system Graphviz)
- **Text Tree** — Indented text representation of the plan
- **Raw JSON** — The full EXPLAIN JSON output from PostgreSQL

#### Tab 3: AQP Comparison

Shows how the query plan changes when individual planner settings are disabled:

- **Baseline cost** metric at the top
- Table with each planner setting, the resulting top join operator, total cost, ratio vs QEP, and a status pill (Similar / Worse / Much worse / Better)

## CLI Mode

The CLI still works independently of Streamlit:

```bash
# Single query
python project.py --nogui \
  --query "SELECT * FROM customer C, orders O WHERE C.c_custkey = O.o_custkey" \
  --dbname sc3020 --user argel --password yourpassword

# From file
python project.py --nogui --query-file demo_queries.sql --all-queries \
  --dbname sc3020 --user argel --password yourpassword

# Single statement from file (1-based index)
python project.py --nogui --query-file demo_queries.sql --query-index 3 \
  --dbname sc3020 --user argel --password yourpassword
```

## File Structure

| File               | Role                                          |
|--------------------|-----------------------------------------------|
| `project.py`       | Entry point — launches Streamlit or CLI mode   |
| `interface.py`     | Streamlit GUI — all UI rendering logic         |
| `annotation.py`    | Annotation engine — plan-to-SQL mapping        |
| `preprocessing.py` | DB connection, EXPLAIN, AQP generation         |
| `demo_queries.sql` | Sample TPC-H queries for the demo dropdown     |
| `requirements.txt` | Python dependencies                            |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: No module named 'streamlit'` | Run `pip install -r requirements.txt` inside your venv |
| Visual tree shows warning instead of diagram | Install system Graphviz: `brew install graphviz` |
| Connection always fails | Check that PostgreSQL is running and the credentials are correct |
| Port error | Make sure the port field contains only a number (e.g. `5432`) |
| Demo queries not loading | Ensure `demo_queries.sql` exists in the same directory as `interface.py` |
| App won't start on Windows | Use `.venv\Scripts\activate` and `python project.py` |
