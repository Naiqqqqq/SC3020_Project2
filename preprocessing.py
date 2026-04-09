"""Utilities for preparing query inputs and retrieving PostgreSQL query plans.

This module handles:
- SQL query normalization and statement splitting
- PostgreSQL connection management
- QEP (Query Execution Plan) retrieval via EXPLAIN (FORMAT JSON)
- AQP (Alternative Query Plan) generation by toggling planner settings
- Plan tree formatting for display
- Table/alias extraction from SQL via sqlglot or regex fallback
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import psycopg2
except ImportError:
    psycopg2 = None

try:
    import sqlglot
    from sqlglot import exp
except ImportError:
    sqlglot = None
    exp = None


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DBConfig:
    """PostgreSQL connection parameters."""
    host: str
    port: int
    dbname: str
    user: str
    password: str


@dataclass
class AQPRecord:
    """One alternative query plan produced by disabling a planner setting."""
    setting: str
    value: str
    plan_json: Dict[str, Any]
    total_cost: float
    note: str = ""


@dataclass
class PlanBundle:
    """The baseline QEP together with all generated AQPs for a single query."""
    query: str
    qep_json: Dict[str, Any]
    qep_total_cost: float
    aqps: List[AQPRecord] = field(default_factory=list)


# All planner knobs we toggle to produce alternative plans.
DEFAULT_PLANNER_SETTINGS: Sequence[str] = (
    "enable_nestloop",
    "enable_hashjoin",
    "enable_mergejoin",
    "enable_seqscan",
    "enable_indexscan",
    "enable_indexonlyscan",
    "enable_bitmapscan",
    "enable_sort",
    "enable_material",
    "enable_hashagg",
)


# ---------------------------------------------------------------------------
# SQL text helpers
# ---------------------------------------------------------------------------

def normalize_query(query: str) -> str:
    """Strip surrounding whitespace and trailing semicolons."""
    cleaned = query.strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1]
    return cleaned.strip()


def _fallback_split_sql_statements(sql_text: str) -> List[str]:
    """Split SQL on semicolons while respecting quotes and comments."""
    statements: List[str] = []
    current: List[str] = []

    in_single_quote = False
    in_double_quote = False
    in_line_comment = False
    in_block_comment = False

    i = 0
    length = len(sql_text)
    while i < length:
        ch = sql_text[i]
        nxt = sql_text[i + 1] if i + 1 < length else ""

        if in_line_comment:
            current.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            current.append(ch)
            if ch == "*" and nxt == "/":
                current.append(nxt)
                i += 2
                in_block_comment = False
                continue
            i += 1
            continue

        if not in_single_quote and not in_double_quote:
            if ch == "-" and nxt == "-":
                current.append(ch)
                current.append(nxt)
                i += 2
                in_line_comment = True
                continue
            if ch == "/" and nxt == "*":
                current.append(ch)
                current.append(nxt)
                i += 2
                in_block_comment = True
                continue

        if ch == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            current.append(ch)
            i += 1
            continue

        if ch == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            current.append(ch)
            i += 1
            continue

        if ch == ";" and not in_single_quote and not in_double_quote:
            statement = normalize_query("".join(current))
            if statement:
                statements.append(statement)
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    tail = normalize_query("".join(current))
    if tail:
        statements.append(tail)

    return statements


def split_sql_statements(sql_text: str) -> List[str]:
    """Split SQL text into individual non-empty statements.

    Prefers sqlglot for robust PostgreSQL parsing; falls back to a
    character-level splitter when the parser is unavailable or chokes.
    """
    if not sql_text or not sql_text.strip():
        return []

    if sqlglot is not None:
        try:
            parsed = sqlglot.parse(sql_text, read="postgres")
            statements = [normalize_query(node.sql(dialect="postgres")) for node in parsed]
            return [stmt for stmt in statements if stmt]
        except Exception:
            pass

    return _fallback_split_sql_statements(sql_text)


def ensure_single_statement(query: str) -> str:
    """Return exactly one statement from *query*, or raise on 0 / 2+."""
    statements = split_sql_statements(query)
    if not statements:
        raise ValueError("SQL query is empty.")
    if len(statements) > 1:
        raise ValueError(
            "Multiple SQL statements detected. Provide a single query, "
            "or use --query-file with --query-index / --all-queries in CLI mode."
        )
    return statements[0]


def load_query_from_file(file_path: str) -> str:
    """Load the first SQL statement from a file."""
    with open(file_path, "r", encoding="utf-8") as sql_file:
        statements = split_sql_statements(sql_file.read())
    return statements[0] if statements else ""


def load_queries_from_file(file_path: str) -> List[str]:
    """Load all SQL statements from a file."""
    with open(file_path, "r", encoding="utf-8") as sql_file:
        return split_sql_statements(sql_file.read())


# ---------------------------------------------------------------------------
# PostgreSQL connection & EXPLAIN
# ---------------------------------------------------------------------------

def connect_postgres(config: DBConfig):
    """Open a psycopg2 connection or raise a clear error if the driver is missing."""
    if psycopg2 is None:
        raise ImportError(
            "psycopg2 is not installed. "
            f"Interpreter: {sys.executable}. "
            f"Install with: \"{sys.executable}\" -m pip install psycopg2-binary"
        )
    return psycopg2.connect(
        host=config.host,
        port=config.port,
        dbname=config.dbname,
        user=config.user,
        password=config.password,
    )


def _parse_explain_payload(payload: Any) -> Dict[str, Any]:
    """Normalise the raw EXPLAIN JSON output into a single dict."""
    if isinstance(payload, str):
        payload = json.loads(payload)
    if isinstance(payload, list):
        if not payload:
            raise ValueError("Empty EXPLAIN payload returned by PostgreSQL.")
        payload = payload[0]
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected EXPLAIN payload type: {type(payload)!r}")
    return payload


def _execute_explain(cursor, query: str) -> Dict[str, Any]:
    """Run EXPLAIN (FORMAT JSON) and return the parsed plan dict."""
    cursor.execute(f"EXPLAIN (FORMAT JSON, COSTS TRUE) {query}")
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("PostgreSQL returned no EXPLAIN output.")
    return _parse_explain_payload(row[0])


def extract_total_cost(plan_json: Dict[str, Any]) -> float:
    """Pull the root node's Total Cost from a plan dict."""
    return float(plan_json.get("Plan", {}).get("Total Cost", 0.0))


def get_qep_and_aqps(
    conn,
    query: str,
    planner_settings: Optional[Sequence[str]] = None,
) -> PlanBundle:
    """Retrieve the baseline QEP and representative AQPs.

    For each planner setting, the method opens a transaction, disables that
    single knob with SET LOCAL, runs EXPLAIN, and rolls back so no session
    state leaks.
    """
    settings = tuple(planner_settings or DEFAULT_PLANNER_SETTINGS)

    with conn.cursor() as cursor:
        qep_json = _execute_explain(cursor, query)

    qep_total_cost = extract_total_cost(qep_json)
    aqps: List[AQPRecord] = []

    for setting in settings:
        with conn.cursor() as cursor:
            try:
                cursor.execute("BEGIN")
                cursor.execute(f"SET LOCAL {setting} TO off")
                alt_plan_json = _execute_explain(cursor, query)
                cursor.execute("ROLLBACK")
            except Exception as exc:
                conn.rollback()
                aqps.append(
                    AQPRecord(
                        setting=setting, value="off",
                        plan_json={}, total_cost=float("inf"),
                        note=f"Failed to generate AQP: {exc}",
                    )
                )
                continue

        aqps.append(
            AQPRecord(
                setting=setting, value="off",
                plan_json=alt_plan_json,
                total_cost=extract_total_cost(alt_plan_json),
            )
        )

    return PlanBundle(
        query=query, qep_json=qep_json,
        qep_total_cost=qep_total_cost, aqps=aqps,
    )


# ---------------------------------------------------------------------------
# Plan tree traversal and formatting
# ---------------------------------------------------------------------------

def iter_plan_nodes(plan_node: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    """Depth-first iterator over every node in a plan tree."""
    yield plan_node
    for child in plan_node.get("Plans", []):
        yield from iter_plan_nodes(child)


def format_plan_tree(plan_json: Dict[str, Any]) -> str:
    """Render a compact indented text tree from EXPLAIN JSON."""
    root = plan_json.get("Plan", {})
    if not root:
        return "No plan tree found."

    lines: List[str] = []

    def walk(node: Dict[str, Any], depth: int) -> None:
        indent = "  " * depth
        node_type = node.get("Node Type", "Unknown")
        relation = node.get("Relation Name")
        alias = node.get("Alias")
        startup = node.get("Startup Cost")
        total = node.get("Total Cost")
        rows = node.get("Plan Rows")

        extras: List[str] = []
        if relation:
            if alias and alias != relation:
                extras.append(f"{relation} as {alias}")
            else:
                extras.append(str(relation))
        if startup is not None and total is not None:
            extras.append(f"cost={startup:.2f}..{total:.2f}")
        if rows is not None:
            extras.append(f"rows={rows}")

        suffix = f" ({'; '.join(extras)})" if extras else ""
        lines.append(f"{indent}- {node_type}{suffix}")

        for key in ("Hash Cond", "Merge Cond", "Join Filter", "Filter",
                     "Sort Key", "Group Key", "Index Cond", "Recheck Cond"):
            val = node.get(key)
            if val is not None:
                display = val if isinstance(val, str) else ", ".join(str(v) for v in val)
                lines.append(f"{indent}    {key}: {display}")

        for child in node.get("Plans", []):
            walk(child, depth + 1)

    walk(root, depth=0)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SQL table/alias extraction
# ---------------------------------------------------------------------------

def extract_table_aliases(query: str) -> List[Tuple[str, Optional[str]]]:
    """Return (table_name, alias_or_None) pairs from a SELECT query.

    Uses sqlglot when available; falls back to regex otherwise.
    Neither path hard-codes any schema or table names.
    """
    if sqlglot is not None and exp is not None:
        try:
            root = sqlglot.parse_one(query, read="postgres")
            pairs: List[Tuple[str, Optional[str]]] = []
            seen: set = set()

            for table in root.find_all(exp.Table):
                table_parts = [table.catalog, table.db, table.name]
                table_name = ".".join([p for p in table_parts if p])
                alias_expr = table.args.get("alias")
                alias_name = alias_expr.name if alias_expr is not None else None
                item = (table_name, alias_name)
                if table_name and item not in seen:
                    seen.add(item)
                    pairs.append(item)
            return pairs
        except Exception:
            pass

    # Regex fallback
    query_one_line = " ".join(query.split())
    from_match = re.search(
        r"\bfrom\b\s+(.*?)(\bwhere\b|\bgroup\b|\border\b|\blimit\b|\bhaving\b|$)",
        query_one_line, flags=re.IGNORECASE,
    )
    if not from_match:
        return []

    from_clause = from_match.group(1)
    pattern = re.compile(
        r"(?:^|,|\bjoin\b)\s*([a-zA-Z_][\w\.]*)(?:\s+(?:as\s+)?([a-zA-Z_][\w]*))?",
        flags=re.IGNORECASE,
    )

    pairs = []
    for match in pattern.finditer(from_clause):
        pairs.append((match.group(1), match.group(2)))
    return pairs
