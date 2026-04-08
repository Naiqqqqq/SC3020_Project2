"""Generate SQL annotations from QEP and representative AQPs."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from preprocessing import AQPRecord, PlanBundle, extract_table_aliases


SETTING_TO_OPERATOR = {
    "enable_nestloop": "Nested Loop",
    "enable_hashjoin": "Hash Join",
    "enable_mergejoin": "Merge Join",
    "enable_seqscan": "Seq Scan",
    "enable_indexscan": "Index Scan",
    "enable_bitmapscan": "Bitmap Scan",
}

OPERATOR_TO_SETTING = {
    "Nested Loop": "enable_nestloop",
    "Hash Join": "enable_hashjoin",
    "Merge Join": "enable_mergejoin",
}


class AnnotationResult(dict):
    """Dictionary-like container for pipeline outputs.

    Keys:
        annotated_query: SQL text with annotation block.
        component_notes: per-component annotation lines.
        reasoning_notes: cost-based rationale lines.
    """


def _iter_plan_nodes(plan_node: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    yield plan_node
    for child in plan_node.get("Plans", []):
        yield from _iter_plan_nodes(child)


def _find_primary_join_operator(plan_json: Dict[str, Any]) -> Optional[str]:
    root = plan_json.get("Plan", {})
    if not root:
        return None

    for node in _iter_plan_nodes(root):
        node_type = node.get("Node Type", "")
        if node_type in ("Nested Loop", "Hash Join", "Merge Join"):
            return node_type
    return None


def _collect_scan_operators(plan_json: Dict[str, Any]) -> Dict[str, str]:
    root = plan_json.get("Plan", {})
    results: Dict[str, str] = {}

    for node in _iter_plan_nodes(root):
        node_type = node.get("Node Type", "")
        if "Scan" not in node_type:
            continue

        relation = node.get("Relation Name")
        alias = node.get("Alias")
        if alias:
            results[alias] = node_type
        if relation:
            results[relation] = node_type

    return results


def _collect_join_notes(plan_json: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    root = plan_json.get("Plan", {})
    notes: List[str] = []
    operators: List[str] = []

    for node in _iter_plan_nodes(root):
        node_type = node.get("Node Type", "")
        if node_type not in ("Nested Loop", "Hash Join", "Merge Join"):
            continue

        operators.append(node_type)
        cond = (
            node.get("Hash Cond")
            or node.get("Merge Cond")
            or node.get("Join Filter")
            or "join predicate from SQL"
        )
        notes.append(f"Join condition {cond} is executed using {node_type}.")

    return notes, operators


def _find_aqp(aqps: Sequence[AQPRecord], setting: str) -> Optional[AQPRecord]:
    for rec in aqps:
        if rec.setting == setting and not rec.note:
            return rec
    return None


def _build_scan_notes(query: str, plan_json: Dict[str, Any]) -> List[str]:
    table_aliases = extract_table_aliases(query)
    scan_ops = _collect_scan_operators(plan_json)

    notes: List[str] = []
    for table_name, alias in table_aliases:
        display_name = f"{table_name} {alias}" if alias else table_name
        op = None

        if alias and alias in scan_ops:
            op = scan_ops[alias]
        elif table_name in scan_ops:
            op = scan_ops[table_name]
        else:
            short_name = table_name.split(".")[-1]
            op = scan_ops.get(short_name)

        if op:
            notes.append(f"Table {display_name} is accessed via {op}.")

    return notes


def _build_reasoning_notes(bundle: PlanBundle, qep_join_ops: Sequence[str]) -> List[str]:
    baseline = bundle.qep_total_cost
    if baseline <= 0:
        return []

    unique_join_ops = []
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

        alt_join = _find_primary_join_operator(aqp.plan_json) or "another join operator"
        ratio = aqp.total_cost / baseline if baseline else float("inf")

        if ratio > 1.05:
            notes.append(
                f"{op} appears preferred because disabling it ({setting}=off) "
                f"changes the plan to {alt_join} and increases estimated cost "
                f"from {baseline:.2f} to {aqp.total_cost:.2f} ({ratio:.2f}x)."
            )
        else:
            notes.append(
                f"Disabling {op} ({setting}=off) keeps a similar estimated cost "
                f"({aqp.total_cost:.2f} vs {baseline:.2f}), so operator choice is likely "
                f"influenced by row-count and distribution estimates."
            )

    return notes


def generate_annotation(query: str, bundle: PlanBundle) -> AnnotationResult:
    scan_notes = _build_scan_notes(query, bundle.qep_json)
    join_notes, join_ops = _collect_join_notes(bundle.qep_json)
    reasoning_notes = _build_reasoning_notes(bundle, join_ops)

    component_notes = scan_notes + join_notes
    all_notes = component_notes + reasoning_notes

    lines: List[str] = [query.strip(), "", "/* PLAN-BASED ANNOTATIONS"]
    if not all_notes:
        lines.append("No plan-to-query mapping could be extracted for this query.")
    else:
        for idx, note in enumerate(all_notes, start=1):
            lines.append(f"{idx}. {note}")
    lines.append("*/")

    return AnnotationResult(
        annotated_query="\n".join(lines),
        component_notes=component_notes,
        reasoning_notes=reasoning_notes,
    )


def format_aqp_summary(bundle: PlanBundle) -> str:
    baseline = bundle.qep_total_cost
    rows: List[str] = [
        f"QEP estimated total cost: {baseline:.2f}",
        "",
        "setting              top_join      total_cost   ratio_vs_qep   note",
        "--------------------------------------------------------------------------",
    ]

    for rec in bundle.aqps:
        if rec.note:
            rows.append(
                f"{rec.setting:<20} {'N/A':<12} {'N/A':<11} {'N/A':<13} {rec.note}"
            )
            continue

        top_join = _find_primary_join_operator(rec.plan_json) or "N/A"
        ratio = rec.total_cost / baseline if baseline > 0 else float("inf")
        rows.append(
            f"{rec.setting:<20} {top_join:<12} {rec.total_cost:<11.2f} {ratio:<13.2f} generated"
        )

    return "\n".join(rows)
