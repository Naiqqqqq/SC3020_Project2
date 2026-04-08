"""Utilities for preparing query inputs and retrieving PostgreSQL plans."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import psycopg2
except ImportError:  # pragma: no cover - handled at runtime in user environment.
    psycopg2 = None


@dataclass
class DBConfig:
    host: str
    port: int
    dbname: str
    user: str
    password: str


@dataclass
class AQPRecord:
    setting: str
    value: str
    plan_json: Dict[str, Any]
    total_cost: float
    note: str = ""


@dataclass
class PlanBundle:
    query: str
    qep_json: Dict[str, Any]
    qep_total_cost: float
    aqps: List[AQPRecord] = field(default_factory=list)


DEFAULT_PLANNER_SETTINGS: Sequence[str] = (
    "enable_nestloop",
    "enable_hashjoin",
    "enable_mergejoin",
    "enable_seqscan",
    "enable_indexscan",
    "enable_bitmapscan",
)


def normalize_query(query: str) -> str:
    """Trim whitespace while preserving SQL content."""
    cleaned = query.strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1]
    return cleaned.strip()


def load_query_from_file(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as sql_file:
        return normalize_query(sql_file.read())


def connect_postgres(config: DBConfig):
    if psycopg2 is None:
        raise ImportError(
            "psycopg2 is not installed. Install it with: pip install psycopg2-binary"
        )

    return psycopg2.connect(
        host=config.host,
        port=config.port,
        dbname=config.dbname,
        user=config.user,
        password=config.password,
    )


def _parse_explain_payload(payload: Any) -> Dict[str, Any]:
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
    cursor.execute(f"EXPLAIN (FORMAT JSON, COSTS TRUE) {query}")
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("PostgreSQL returned no EXPLAIN output.")
    return _parse_explain_payload(row[0])


def extract_total_cost(plan_json: Dict[str, Any]) -> float:
    return float(plan_json.get("Plan", {}).get("Total Cost", 0.0))


def get_qep_and_aqps(
    conn,
    query: str,
    planner_settings: Optional[Sequence[str]] = None,
) -> PlanBundle:
    """Return the baseline QEP and representative AQPs by disabling one planner method at a time."""
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
                        setting=setting,
                        value="off",
                        plan_json={},
                        total_cost=float("inf"),
                        note=f"Failed to generate AQP: {exc}",
                    )
                )
                continue

        aqps.append(
            AQPRecord(
                setting=setting,
                value="off",
                plan_json=alt_plan_json,
                total_cost=extract_total_cost(alt_plan_json),
            )
        )

    return PlanBundle(query=query, qep_json=qep_json, qep_total_cost=qep_total_cost, aqps=aqps)


def _iter_plan_nodes(plan_node: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    yield plan_node
    for child in plan_node.get("Plans", []):
        yield from _iter_plan_nodes(child)


def format_plan_tree(plan_json: Dict[str, Any]) -> str:
    """Build a compact tree view suitable for GUI text display."""
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

        extras: List[str] = []
        if relation:
            if alias and alias != relation:
                extras.append(f"{relation} as {alias}")
            else:
                extras.append(str(relation))
        if startup is not None and total is not None:
            extras.append(f"cost={startup:.2f}..{total:.2f}")

        suffix = f" ({'; '.join(extras)})" if extras else ""
        lines.append(f"{indent}- {node_type}{suffix}")

        for key in ("Hash Cond", "Merge Cond", "Join Filter", "Filter"):
            if key in node:
                lines.append(f"{indent}    {key}: {node[key]}")

        for child in node.get("Plans", []):
            walk(child, depth + 1)

    walk(root, depth=0)
    return "\n".join(lines)


def extract_table_aliases(query: str) -> List[Tuple[str, Optional[str]]]:
    """Extract table-alias pairs from the FROM clause without schema hardcoding."""
    query_one_line = " ".join(query.split())
    from_match = re.search(
        r"\bfrom\b\s+(.*?)(\bwhere\b|\bgroup\b|\border\b|\blimit\b|\bhaving\b|$)",
        query_one_line,
        flags=re.IGNORECASE,
    )
    if not from_match:
        return []

    from_clause = from_match.group(1)
    pattern = re.compile(
        r"(?:^|,|\bjoin\b)\s*([a-zA-Z_][\w\.]*)(?:\s+(?:as\s+)?([a-zA-Z_][\w]*))?",
        flags=re.IGNORECASE,
    )

    pairs: List[Tuple[str, Optional[str]]] = []
    for match in pattern.finditer(from_clause):
        table_name = match.group(1)
        alias = match.group(2)
        pairs.append((table_name, alias))

    return pairs
