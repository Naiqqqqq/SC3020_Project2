"""Generate rich SQL annotations from QEP and representative AQPs.

The annotation engine walks the EXPLAIN JSON plan tree to:
1. Map scan operators to the SQL tables they access and explain *why*
   that scan type was chosen (e.g. no index -> seq scan).
2. Map join operators to join predicates and compare QEP cost against
   AQPs where that join method is disabled.
3. Annotate sort, aggregate, and filter operations with their keys and
   estimated costs.
4. Produce both a plain-text annotation block and a structured object
   that the GUI can render inline alongside the original SQL.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from preprocessing import AQPRecord, PlanBundle, extract_table_aliases, iter_plan_nodes


# ---------------------------------------------------------------------------
# Operator <-> setting mappings
# ---------------------------------------------------------------------------

SETTING_TO_OPERATOR: Dict[str, str] = {
    "enable_nestloop": "Nested Loop",
    "enable_hashjoin": "Hash Join",
    "enable_mergejoin": "Merge Join",
    "enable_seqscan": "Seq Scan",
    "enable_indexscan": "Index Scan",
    "enable_indexonlyscan": "Index Only Scan",
    "enable_bitmapscan": "Bitmap Scan",
    "enable_sort": "Sort",
    "enable_material": "Materialize",
    "enable_hashagg": "HashAggregate",
}

OPERATOR_TO_SETTING: Dict[str, str] = {v: k for k, v in SETTING_TO_OPERATOR.items()}

JOIN_OPERATORS = {"Nested Loop", "Hash Join", "Merge Join"}
SCAN_OPERATORS = {"Seq Scan", "Index Scan", "Index Only Scan",
                  "Bitmap Heap Scan", "Bitmap Index Scan"}


# ---------------------------------------------------------------------------
# Structured annotation data classes
# ---------------------------------------------------------------------------

@dataclass
class InlineAnnotation:
    """A single annotation anchored to SQL line(s)."""
    start_line: int
    end_line: int
    category: str  # scan | join | reasoning | aggregate | sort | filter
    text: str


@dataclass
class StructuredAnnotation:
    """Complete structured output from the annotation engine."""
    sql_lines: List[str]
    inline_annotations: List[InlineAnnotation] = field(default_factory=list)
    component_notes: List[str] = field(default_factory=list)
    reasoning_notes: List[str] = field(default_factory=list)


class AnnotationResult(dict):
    """Dict-like container so callers can use result['key'] access.

    Keys: annotated_query, component_notes, reasoning_notes, structured.
    """


# ---------------------------------------------------------------------------
# Internal plan helpers
# ---------------------------------------------------------------------------

def _find_primary_join_operator(plan_json: Dict[str, Any]) -> Optional[str]:
    """Return the first join operator found in a depth-first walk."""
    root = plan_json.get("Plan", {})
    if not root:
        return None
    for node in iter_plan_nodes(root):
        if node.get("Node Type", "") in JOIN_OPERATORS:
            return node["Node Type"]
    return None


def _collect_scan_info(plan_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Gather detailed scan node info: type, relation, alias, index, filter, cost."""
    root = plan_json.get("Plan", {})
    results: List[Dict[str, Any]] = []
    for node in iter_plan_nodes(root):
        node_type = node.get("Node Type", "")
        if "Scan" not in node_type:
            continue
        results.append({
            "node_type": node_type,
            "relation": node.get("Relation Name"),
            "alias": node.get("Alias"),
            "index_name": node.get("Index Name"),
            "filter": node.get("Filter"),
            "index_cond": node.get("Index Cond"),
            "recheck_cond": node.get("Recheck Cond"),
            "rows": node.get("Plan Rows"),
            "startup_cost": node.get("Startup Cost"),
            "total_cost": node.get("Total Cost"),
        })
    return results


def _collect_join_info(plan_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Gather join nodes with their conditions and costs."""
    root = plan_json.get("Plan", {})
    results: List[Dict[str, Any]] = []
    for node in iter_plan_nodes(root):
        node_type = node.get("Node Type", "")
        if node_type not in JOIN_OPERATORS:
            continue
        cond = (node.get("Hash Cond")
                or node.get("Merge Cond")
                or node.get("Join Filter")
                or None)
        results.append({
            "node_type": node_type,
            "join_type": node.get("Join Type", "Inner"),
            "condition": cond,
            "startup_cost": node.get("Startup Cost"),
            "total_cost": node.get("Total Cost"),
            "rows": node.get("Plan Rows"),
        })
    return results


def _collect_other_ops(plan_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Gather Sort, Aggregate, and other notable non-scan/join nodes."""
    root = plan_json.get("Plan", {})
    interesting = {"Sort", "Aggregate", "HashAggregate", "GroupAggregate",
                   "Limit", "Materialize", "Gather", "Gather Merge",
                   "Unique", "Append", "SetOp"}
    results: List[Dict[str, Any]] = []
    for node in iter_plan_nodes(root):
        node_type = node.get("Node Type", "")
        if node_type not in interesting:
            continue
        info: Dict[str, Any] = {
            "node_type": node_type,
            "startup_cost": node.get("Startup Cost"),
            "total_cost": node.get("Total Cost"),
            "rows": node.get("Plan Rows"),
        }
        sort_key = node.get("Sort Key")
        if sort_key:
            info["sort_key"] = sort_key if isinstance(sort_key, str) else ", ".join(str(k) for k in sort_key)
        group_key = node.get("Group Key")
        if group_key:
            info["group_key"] = group_key if isinstance(group_key, str) else ", ".join(str(k) for k in group_key)
        strategy = node.get("Strategy")
        if strategy:
            info["strategy"] = strategy
        results.append(info)
    return results


def _find_aqp(aqps: Sequence[AQPRecord], setting: str) -> Optional[AQPRecord]:
    """Find the AQP record for a given setting, skipping failed ones."""
    for rec in aqps:
        if rec.setting == setting and not rec.note:
            return rec
    return None


# ---------------------------------------------------------------------------
# Note builders
# ---------------------------------------------------------------------------

def _build_scan_notes(
    query: str,
    plan_json: Dict[str, Any],
    bundle: PlanBundle,
) -> List[str]:
    """Build notes explaining how each table is accessed and why."""
    table_aliases = extract_table_aliases(query)
    scan_info = _collect_scan_info(plan_json)

    # Build lookup: alias/relation -> scan details
    scan_by_key: Dict[str, Dict[str, Any]] = {}
    for si in scan_info:
        if si["alias"]:
            scan_by_key[si["alias"].lower()] = si
        if si["relation"]:
            scan_by_key[si["relation"].lower()] = si

    notes: List[str] = []
    for table_name, alias in table_aliases:
        display = f"{table_name} ({alias})" if alias else table_name
        lookup_keys = []
        if alias:
            lookup_keys.append(alias.lower())
        lookup_keys.append(table_name.lower())
        lookup_keys.append(table_name.split(".")[-1].lower())

        si = None
        for key in lookup_keys:
            if key in scan_by_key:
                si = scan_by_key[key]
                break

        if not si:
            continue

        op = si["node_type"]
        note = f"Table {display} is accessed using {op}."

        # Explain *why* this scan type was chosen
        if op == "Seq Scan":
            # Check if disabling seqscan changes the cost
            aqp = _find_aqp(bundle.aqps, "enable_seqscan")
            if aqp and aqp.total_cost < float("inf"):
                ratio = aqp.total_cost / bundle.qep_total_cost if bundle.qep_total_cost > 0 else 1.0
                if ratio > 1.5:
                    note += (f" Sequential scan is chosen because alternative scans "
                             f"increase cost by {ratio:.1f}x.")
                else:
                    note += " No suitable index exists on the filtered/joined columns."
            else:
                note += " This is likely because no index exists on the accessed columns."
        elif "Index" in op and si.get("index_name"):
            note += f" Index used: {si['index_name']}."

        if si.get("filter"):
            note += f" A filter is applied: {si['filter']}."

        notes.append(note)

    return notes


def _build_join_notes(plan_json: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """Build notes for each join operator found in the plan."""
    join_info = _collect_join_info(plan_json)
    notes: List[str] = []
    operators: List[str] = []

    for ji in join_info:
        operators.append(ji["node_type"])
        cond_str = ji["condition"] or "implicit join predicate"
        join_type = ji["join_type"]
        note = f"The {join_type} join on {cond_str} is implemented using {ji['node_type']}."
        if ji.get("rows") is not None:
            note += f" Estimated output: {ji['rows']} rows."
        notes.append(note)

    return notes, operators


def _build_reasoning_notes(bundle: PlanBundle, qep_join_ops: Sequence[str]) -> List[str]:
    """Compare QEP join costs against AQPs to explain *why* the optimizer chose them.

    This directly addresses the project spec requirement: e.g.
    'Hash join is chosen because NL and merge join increase cost by 10x and 7x.'
    """
    baseline = bundle.qep_total_cost
    if baseline <= 0:
        return []

    unique_join_ops: List[str] = []
    for op in qep_join_ops:
        if op not in unique_join_ops:
            unique_join_ops.append(op)

    notes: List[str] = []
    for op in unique_join_ops:
        setting = OPERATOR_TO_SETTING.get(op)
        if not setting:
            continue

        aqp = _find_aqp(bundle.aqps, setting)
        if not aqp:
            continue

        alt_join = _find_primary_join_operator(aqp.plan_json) or "another operator"
        ratio = aqp.total_cost / baseline if baseline else float("inf")

        # Collect all *other* join alternatives and their costs for a richer message
        other_costs: List[Tuple[str, float]] = []
        for alt_op in JOIN_OPERATORS - {op}:
            alt_setting = OPERATOR_TO_SETTING.get(alt_op)
            if not alt_setting:
                continue
            alt_aqp = _find_aqp(bundle.aqps, alt_setting)
            if alt_aqp and alt_aqp.total_cost < float("inf"):
                alt_ratio = alt_aqp.total_cost / baseline
                if alt_ratio > 1.05:
                    other_costs.append((alt_op, alt_ratio))

        if ratio > 1.05:
            note = (f"{op} is the preferred join strategy. "
                    f"Disabling it increases estimated cost from "
                    f"{baseline:.2f} to {aqp.total_cost:.2f} ({ratio:.1f}x).")

            # Add comparison with other disabled joins (spec example style)
            if other_costs:
                comparisons = [f"disabling {name} increases cost by {r:.1f}x"
                               for name, r in sorted(other_costs, key=lambda x: -x[1])]
                note += " Similarly, " + "; ".join(comparisons) + "."
            notes.append(note)
        else:
            notes.append(
                f"{op} and {alt_join} have similar estimated costs "
                f"({aqp.total_cost:.2f} vs {baseline:.2f}). The optimizer's choice "
                f"is likely influenced by row counts and data distribution."
            )

    return notes


def _build_other_notes(plan_json: Dict[str, Any]) -> List[str]:
    """Annotate sort, aggregate, and other operations visible in the plan."""
    ops = _collect_other_ops(plan_json)
    notes: List[str] = []

    for op in ops:
        nt = op["node_type"]
        cost = op.get("total_cost")
        cost_str = f" (estimated cost: {cost:.2f})" if cost is not None else ""

        if nt in ("Sort",):
            key = op.get("sort_key", "unspecified columns")
            notes.append(f"A Sort operation orders rows by {key}{cost_str}.")
        elif nt in ("Aggregate", "HashAggregate", "GroupAggregate"):
            key = op.get("group_key")
            strategy = op.get("strategy", "")
            if key:
                notes.append(
                    f"A {strategy + ' ' if strategy else ''}{nt} groups rows by {key}{cost_str}."
                )
            else:
                notes.append(f"A {nt} computes aggregate values{cost_str}.")
        elif nt == "Limit":
            notes.append(f"A Limit caps the result set{cost_str}.")
        elif nt == "Materialize":
            notes.append(f"A Materialize node caches intermediate results{cost_str}.")

    return notes


# ---------------------------------------------------------------------------
# SQL line-range finders (for inline annotations in the GUI)
# ---------------------------------------------------------------------------

def _find_sql_line(sql_lines: List[str], pattern: str) -> int:
    for idx, line in enumerate(sql_lines):
        if re.search(pattern, line, re.IGNORECASE):
            return idx
    return -1


def _find_clause_range(
    sql_lines: List[str],
    start_kw: str,
    stop_kws: Sequence[str],
) -> Tuple[int, int]:
    """Generic clause range finder: from *start_kw* until one of *stop_kws*."""
    start = _find_sql_line(sql_lines, rf"\b{start_kw}\b")
    if start < 0:
        return (-1, -1)

    end = start
    for i in range(start + 1, len(sql_lines)):
        stripped = sql_lines[i].strip().lower()
        if stripped and any(stripped.startswith(kw) for kw in stop_kws):
            break
        end = i
    return (start, end)


_AFTER_FROM = ("where", "group", "order", "having", "limit", "union", "except", "intersect", "window")
_AFTER_WHERE = ("group", "order", "having", "limit", "union", "except", "intersect", "window")
_AFTER_GROUP = ("having", "order", "limit", "union", "except", "intersect", "window")
_AFTER_ORDER = ("limit", "union", "except", "intersect", "window")


def _build_inline_annotations(
    sql_lines: List[str],
    scan_notes: List[str],
    join_notes: List[str],
    reasoning_notes: List[str],
    other_notes: List[str],
) -> List[InlineAnnotation]:
    """Map notes to specific SQL line ranges for inline display."""
    annotations: List[InlineAnnotation] = []

    from_s, from_e = _find_clause_range(sql_lines, "from", _AFTER_FROM)
    where_s, where_e = _find_clause_range(sql_lines, "where", _AFTER_WHERE)
    group_s, group_e = _find_clause_range(sql_lines, "group", _AFTER_GROUP)
    order_s, order_e = _find_clause_range(sql_lines, "order", _AFTER_ORDER)
    select_s = _find_sql_line(sql_lines, r"\bselect\b")

    def _safe(start: int, end: int, fallback_s: int = 0, fallback_e: int = 0) -> Tuple[int, int]:
        s = start if start >= 0 else fallback_s
        e = end if end >= 0 else fallback_e
        return (s, max(s, e))

    scan_range = _safe(from_s, from_e)
    join_range = _safe(where_s, where_e, from_s, from_e)
    agg_range = _safe(select_s, select_s)
    sort_range = _safe(order_s, order_e, select_s, select_s)
    group_range = _safe(group_s, group_e, select_s, select_s)

    for note in scan_notes:
        annotations.append(InlineAnnotation(scan_range[0], scan_range[1], "scan", note))

    for note in join_notes:
        annotations.append(InlineAnnotation(join_range[0], join_range[1], "join", note))

    for note in reasoning_notes:
        annotations.append(InlineAnnotation(join_range[0], join_range[1], "reasoning", note))

    for note in other_notes:
        lower = note.lower()
        if "sort" in lower or "order" in lower:
            r = sort_range
            cat = "sort"
        elif "group" in lower or "aggregate" in lower:
            r = group_range
            cat = "aggregate"
        else:
            r = agg_range
            cat = "filter"
        annotations.append(InlineAnnotation(r[0], r[1], cat, note))

    return annotations


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_annotation(query: str, bundle: PlanBundle) -> AnnotationResult:
    """Produce both plain-text and structured annotations for *query*.

    Returns an AnnotationResult (dict subclass) with keys:
        annotated_query  - SQL + annotation comment block
        component_notes  - per-component annotation lines
        reasoning_notes  - cost-based rationale lines
        structured       - StructuredAnnotation for GUI rendering
    """
    scan_notes = _build_scan_notes(query, bundle.qep_json, bundle)
    join_notes, join_ops = _build_join_notes(bundle.qep_json)
    reasoning_notes = _build_reasoning_notes(bundle, join_ops)
    other_notes = _build_other_notes(bundle.qep_json)

    component_notes = scan_notes + join_notes + other_notes
    all_notes = component_notes + reasoning_notes

    # Plain-text annotated query (also used by CLI mode)
    lines: List[str] = [query.strip(), "", "/* === PLAN-BASED ANNOTATIONS ==="]
    if not all_notes:
        lines.append("  No plan-to-query mapping could be extracted for this query.")
    else:
        for idx, note in enumerate(all_notes, start=1):
            lines.append(f"  {idx}. {note}")
    lines.append("*/")

    sql_lines = query.strip().splitlines()
    inline = _build_inline_annotations(sql_lines, scan_notes, join_notes,
                                        reasoning_notes, other_notes)

    structured = StructuredAnnotation(
        sql_lines=sql_lines,
        inline_annotations=inline,
        component_notes=component_notes,
        reasoning_notes=reasoning_notes,
    )

    return AnnotationResult(
        annotated_query="\n".join(lines),
        component_notes=component_notes,
        reasoning_notes=reasoning_notes,
        structured=structured,
    )


def format_aqp_summary(bundle: PlanBundle) -> str:
    """Render a text table comparing the QEP against every AQP."""
    baseline = bundle.qep_total_cost
    rows: List[str] = [
        f"QEP estimated total cost: {baseline:.2f}",
        "",
        f"{'Setting':<24} {'Top Join':<14} {'Total Cost':>12} {'Ratio':>10}   Note",
        "-" * 85,
    ]

    for rec in bundle.aqps:
        if rec.note:
            rows.append(f"{rec.setting:<24} {'N/A':<14} {'N/A':>12} {'N/A':>10}   {rec.note}")
            continue

        top_join = _find_primary_join_operator(rec.plan_json) or "N/A"
        ratio = rec.total_cost / baseline if baseline > 0 else float("inf")
        rows.append(
            f"{rec.setting:<24} {top_join:<14} {rec.total_cost:>12.2f} {ratio:>9.2f}x   OK"
        )

    return "\n".join(rows)
