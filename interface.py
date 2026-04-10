from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import streamlit as st

import annotation
import preprocessing
from annotation import StructuredAnnotation, InlineAnnotation

### PAGE CONFIG
st.set_page_config(
    page_title="SC3020 — SQL Query Annotation",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

### Theme works in both light and dark Streamlit themes
st.markdown("""
<style>
    /* General layout */
    .block-container { padding-top: 1rem; max-width: 1400px; }
    section[data-testid="stSidebar"] > div { padding-top: 1rem; }

    /* --- Badges --- */
    .cat-badge {
        display: inline-block; padding: 3px 10px; border-radius: 12px;
        font-size: 0.72rem; font-weight: 700; letter-spacing: 0.03em;
        text-transform: uppercase; margin-bottom: 6px;
    }
    .cat-badge-scan       { background: #3B82F6; color: #fff; }
    .cat-badge-join       { background: #10B981; color: #fff; }
    .cat-badge-reasoning  { background: #F59E0B; color: #fff; }
    .cat-badge-sort       { background: #EC4899; color: #fff; }
    .cat-badge-aggregate  { background: #14B8A6; color: #fff; }
    .cat-badge-filter     { background: #8B5CF6; color: #fff; }

    /* --- SQL display container --- */
    .sql-block {
        border-radius: 10px; padding: 16px 12px;
        border: 1px solid rgba(128,128,128,0.25);
        background: rgba(128,128,128,0.06);
        font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', 'Monaco', monospace;
        font-size: 0.92rem; line-height: 1.7; overflow-x: auto;
    }
    .sql-ln {
        padding: 1px 10px; border-left: 3px solid transparent;
        transition: background 0.15s;
    }
    .sql-ln-num {
        display: inline-block; width: 28px; text-align: right;
        margin-right: 12px; opacity: 0.35; font-size: 0.8rem;
        user-select: none;
    }
    /* Highlight colours — semi-transparent so they work on any bg */
    .sql-hl-scan       { background: rgba(59,130,246,0.12); border-left-color: #3B82F6; }
    .sql-hl-join       { background: rgba(16,185,129,0.12); border-left-color: #10B981; }
    .sql-hl-reasoning  { background: rgba(245,158,11,0.12); border-left-color: #F59E0B; }
    .sql-hl-sort       { background: rgba(236,72,153,0.12); border-left-color: #EC4899; }
    .sql-hl-aggregate  { background: rgba(20,184,166,0.12); border-left-color: #14B8A6; }
    .sql-hl-filter     { background: rgba(139,92,246,0.12); border-left-color: #8B5CF6; }

    /* --- Annotation cards --- */
    .ann-card {
        border-radius: 8px; padding: 10px 14px; margin: 6px 0;
        border: 1px solid rgba(128,128,128,0.2);
        background: rgba(128,128,128,0.05);
        font-size: 0.88rem; line-height: 1.5;
    }
    .ann-card-line-ref {
        font-size: 0.72rem; opacity: 0.5; margin-bottom: 2px;
    }
    .ann-card-scan      { border-left: 3px solid #3B82F6; }
    .ann-card-join      { border-left: 3px solid #10B981; }
    .ann-card-reasoning { border-left: 3px solid #F59E0B; }
    .ann-card-sort      { border-left: 3px solid #EC4899; }
    .ann-card-aggregate { border-left: 3px solid #14B8A6; }
    .ann-card-filter    { border-left: 3px solid #8B5CF6; }

    /* --- AQP status pills --- */
    .pill { display:inline-block; padding:2px 8px; border-radius:10px;
            font-size:0.72rem; font-weight:600; }
    .pill-much-worse { background:#FEE2E2; color:#991B1B; }
    .pill-worse      { background:#FEF3C7; color:#92400E; }
    .pill-similar    { background:#E0F2FE; color:#075985; }
    .pill-better     { background:#D1FAE5; color:#065F46; }
</style>
""", unsafe_allow_html=True)



### SIDEBAR
def _render_sidebar() -> Dict[str, str]:
    with st.sidebar:
        st.markdown("### Database Connection")

        host = st.text_input("Host", value="localhost")
        port = st.text_input("Port", value="5432")
        dbname = st.text_input("Database", value="sc3020")
        user = st.text_input("User", value="argel")
        password = st.text_input("Password", type="password")

        config = {"host": host, "port": port, "dbname": dbname,
                  "user": user, "password": password}

        if st.button("Test Connection"):
            try:
                db_port = int(port)
            except ValueError:
                st.error("Port must be a number.")
                return config
            try:
                db_cfg = preprocessing.DBConfig(
                    host=host, port=db_port, dbname=dbname,
                    user=user, password=password,
                )
                conn = preprocessing.connect_postgres(db_cfg)
                with conn.cursor() as cur:
                    cur.execute("SELECT version()")
                    ver = cur.fetchone()[0]
                conn.close()
                st.success(f"Connected!\n\n`{ver[:80]}`")
            except Exception as exc:
                st.error(f"Failed: {exc}")

        st.divider()
        st.markdown("### Demo Queries")
        demos = _load_demo_queries()
        if demos:
            labels = [d["label"] for d in demos]
            options = ["-- select --"] + labels

            def _on_demo_change() -> None:
                picked = st.session_state.get("demo_select", "-- select --")
                if picked != "-- select --":
                    idx = labels.index(picked)
                    st.session_state["sql_area"] = demos[idx]["sql"]
                    st.session_state["demo_select"] = "-- select --"

            st.selectbox(
                "Pick a demo query", options,
                key="demo_select",
                on_change=_on_demo_change,
                label_visibility="collapsed",
            )
        else:
            st.caption("demo_queries.sql not found.")

    return config


@st.cache_data
def _load_demo_queries() -> List[Dict[str, str]]:
    demo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_queries.sql")
    if not os.path.isfile(demo_path):
        return []
    with open(demo_path, "r", encoding="utf-8") as f:
        content = f.read()

    queries: List[Dict[str, str]] = []
    current_lines: List[str] = []
    current_label = ""

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") and not current_lines:
            current_label = stripped.lstrip("- ").strip()
            continue
        current_lines.append(line)
        if stripped.endswith(";"):
            sql = "\n".join(current_lines).strip()
            if sql:
                preview = sql.replace("\n", " ")[:60]
                label = f"{current_label}:  {preview}..." if current_label else f"{preview}..."
                queries.append({"label": label, "sql": sql})
            current_lines = []
            current_label = ""

    if current_lines:
        sql = "\n".join(current_lines).strip()
        if sql:
            queries.append({"label": current_label or sql[:60], "sql": sql})
    return queries

### PIPELINE
def _run(config: Dict[str, str], query: str) -> Any:
    from project import run_pipeline
    return run_pipeline(config, query)

### Tab 1 — Annotated Query
CATEGORY_META = {
    "scan":      ("Table Access",   "cat-badge-scan",      "ann-card-scan"),
    "join":      ("Join Operation", "cat-badge-join",      "ann-card-join"),
    "reasoning": ("Cost Reasoning", "cat-badge-reasoning", "ann-card-reasoning"),
    "sort":      ("Sort",           "cat-badge-sort",      "ann-card-sort"),
    "aggregate": ("Aggregate",      "cat-badge-aggregate", "ann-card-aggregate"),
    "filter":    ("Other",          "cat-badge-filter",    "ann-card-filter"),
}


def _render_annotated_query(structured: StructuredAnnotation) -> None:
    sql_lines = structured.sql_lines
    anns = structured.inline_annotations

    line_cats: Dict[int, str] = {}
    for ann in anns:
        for ln in range(ann.start_line, ann.end_line + 1):
            if ln not in line_cats:
                line_cats[ln] = ann.category

    col_sql, col_ann = st.columns([5, 6])

    # --- Left: SQL with line numbers + highlights ---
    with col_sql:
        st.markdown("##### SQL Query")
        parts: List[str] = ['<div class="sql-block">']
        for i, line in enumerate(sql_lines):
            cat = line_cats.get(i)
            hl = f"sql-hl-{cat}" if cat else ""
            escaped = (line.replace("&", "&amp;")
                           .replace("<", "&lt;")
                           .replace(">", "&gt;") or "&nbsp;")
            parts.append(
                f'<div class="sql-ln {hl}">'
                f'<span class="sql-ln-num">{i+1}</span>{escaped}</div>'
            )
        parts.append("</div>")
        st.markdown("\n".join(parts), unsafe_allow_html=True)

    # --- Right: Annotation cards grouped by category ---
    with col_ann:
        st.markdown("##### Annotations")

        if not anns:
            st.info("No annotations were generated for this query.")
            return

        by_cat: Dict[str, List[InlineAnnotation]] = {}
        for ann in anns:
            by_cat.setdefault(ann.category, []).append(ann)

        for cat in ("scan", "join", "reasoning", "sort", "aggregate", "filter"):
            items = by_cat.get(cat)
            if not items:
                continue

            label, badge_cls, card_cls = CATEGORY_META.get(
                cat, (cat.title(), "cat-badge-filter", "ann-card-filter"))

            st.markdown(f'<span class="cat-badge {badge_cls}">{label}</span>',
                        unsafe_allow_html=True)

            for ann in items:
                line_ref = (
                    f"Line {ann.start_line + 1}"
                    if ann.start_line == ann.end_line
                    else f"Lines {ann.start_line + 1}\u2013{ann.end_line + 1}"
                )
                text = (ann.text.replace("&", "&amp;")
                                .replace("<", "&lt;")
                                .replace(">", "&gt;"))
                st.markdown(
                    f'<div class="ann-card {card_cls}">'
                    # f'<div class="ann-card-line-ref">{line_ref}</div>'
                    f'{text}</div>',
                    unsafe_allow_html=True,
                )

            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)


### Tab 2 — QEP Tree
NODE_COLORS = {
    "Seq Scan": "#3B82F6", "Index Scan": "#10B981", "Index Only Scan": "#10B981",
    "Bitmap Heap Scan": "#6366F1", "Bitmap Index Scan": "#6366F1",
    "Hash Join": "#F59E0B", "Merge Join": "#EF4444", "Nested Loop": "#8B5CF6",
    "Sort": "#EC4899", "Aggregate": "#14B8A6", "HashAggregate": "#14B8A6",
    "GroupAggregate": "#14B8A6", "Hash": "#F97316", "Materialize": "#64748B",
    "Gather": "#0EA5E9", "Gather Merge": "#0EA5E9", "Limit": "#78716C",
}


def _render_qep_tree(plan_json: Dict[str, Any], qep_tree_text: str) -> None:
    root = plan_json.get("Plan")
    if not root:
        st.warning("No plan tree found.")
        return

    tab_vis, tab_txt, tab_json = st.tabs(["Visual Tree", "Text Tree", "Raw JSON"])

    with tab_vis:
        try:
            import graphviz
            dot = graphviz.Digraph(
                format="svg",
                graph_attr={"rankdir": "TB", "bgcolor": "transparent",
                            "nodesep": "0.6", "ranksep": "0.8", "pad": "0.3"},
                node_attr={"shape": "box", "style": "rounded,filled",
                           "fontname": "Helvetica", "fontsize": "10",
                           "fontcolor": "white", "margin": "0.18,0.1",
                           "penwidth": "0"},
                edge_attr={"color": "#94A3B8", "arrowsize": "0.8",
                           "penwidth": "1.5"},
            )
            _add_graphviz_nodes(dot, root, node_id=[0])
            st.graphviz_chart(dot, width="stretch")
        except Exception as exc:
            st.warning(
                f"Could not render visual tree: {exc}\n\n"
                "Install the system binary: `brew install graphviz` (macOS) "
                "or `sudo apt install graphviz` (Linux)."
            )
            st.code(qep_tree_text, language=None)

    with tab_txt:
        st.code(qep_tree_text, language=None)

    with tab_json:
        st.json(plan_json)


def _add_graphviz_nodes(
    dot: Any, node: Dict[str, Any],
    node_id: List[int], parent_id: Optional[str] = None,
) -> None:
    cur_id = str(node_id[0])
    node_id[0] += 1

    node_type = node.get("Node Type", "Unknown")
    color = NODE_COLORS.get(node_type, "#64748B")

    label_parts = [node_type]
    relation = node.get("Relation Name")
    alias = node.get("Alias")
    if relation:
        tbl = f"{relation} ({alias})" if alias and alias != relation else relation
        label_parts.append(tbl)

    startup = node.get("Startup Cost")
    total = node.get("Total Cost")
    if startup is not None:
        label_parts.append(f"Startup cost: {startup:,.2f}")
    if total is not None:
        label_parts.append(f"Total cost: {total:,.2f}")

    rows = node.get("Plan Rows")
    if rows is not None:
        label_parts.append(f"Rows: {rows:,}")

    for key in ("Hash Cond", "Merge Cond", "Join Filter", "Filter",
                "Index Cond", "Sort Key", "Group Key"):
        val = node.get(key)
        if val is not None:
            display = val if isinstance(val, str) else ", ".join(str(v) for v in val)
            if len(display) > 45:
                display = display[:42] + "..."
            label_parts.append(f"{key}: {display}")

    dot.node(cur_id, label="\\n".join(label_parts), fillcolor=color)
    if parent_id is not None:
        dot.edge(parent_id, cur_id)

    for child in node.get("Plans", []):
        _add_graphviz_nodes(dot, child, node_id, cur_id)

### Tab 3 — AQP Table
def _status_pill(status: str) -> str:
    cls_map = {
        "Much worse": "pill-much-worse", "Worse": "pill-worse",
        "Similar": "pill-similar", "Better (!)": "pill-better",
    }
    cls = cls_map.get(status, "pill-similar")
    return f'<span class="pill {cls}">{status}</span>'


def _render_aqp_table(bundle: preprocessing.PlanBundle) -> None:
    baseline = bundle.qep_total_cost

    c1, c2, c3 = st.columns(3)
    c1.metric("QEP Baseline Cost", f"{baseline:,.2f}")
    c2.metric("AQPs Generated", str(len(bundle.aqps)))
    worse = sum(1 for r in bundle.aqps
                if not r.note and r.total_cost / baseline > 1.05 and baseline > 0)
    c3.metric("Costlier Alternatives", str(worse))

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # Build HTML table for full control over styling
    header = (
        '<table style="width:100%; border-collapse:collapse; font-size:0.88rem;">'
        '<thead><tr style="border-bottom:2px solid rgba(128,128,128,0.3);">'
        '<th style="text-align:left; padding:8px;">Disabled Setting</th>'
        '<th style="text-align:left; padding:8px;">Resulting Join Operator</th>'
        '<th style="text-align:right; padding:8px;">Total Cost</th>'
        '<th style="text-align:right; padding:8px;">Ratio</th>'
        '<th style="text-align:center; padding:8px;">Status</th>'
        '</tr></thead><tbody>'
    )

    rows_html: List[str] = []
    for rec in bundle.aqps:
        if rec.note:
            rows_html.append(
                f'<tr style="border-bottom:1px solid rgba(128,128,128,0.15);">'
                f'<td style="padding:6px 8px;"><code style="color:#EF4444">{rec.setting[7:]}</code></td>'
                f'<td style="padding:6px 8px;">N/A</td>'
                f'<td style="padding:6px 8px; text-align:right;">—</td>'
                f'<td style="padding:6px 8px; text-align:right;">—</td>'
                f'<td style="padding:6px 8px; text-align:center; font-size:0.78rem; opacity:0.7;">'
                f'{rec.note[:50]}</td></tr>'
            )
            continue

        top_join = annotation._find_primary_join_operator(rec.plan_json) or "N/A"
        ratio = rec.total_cost / baseline if baseline > 0 else float("inf")

        if ratio > 2.0:
            status = "Much worse"
        elif ratio > 1.05:
            status = "Worse"
        elif ratio < 0.95:
            status = "Better (!)"
        else:
            status = "Similar"

        rows_html.append(
            f'<tr style="border-bottom:1px solid rgba(128,128,128,0.15);">'
             f'<td style="padding:6px 8px;"><code style="color:#EF4444">{rec.setting[7:]}</code></td>'
            f'<td style="padding:6px 8px;">{top_join}</td>'
            f'<td style="padding:6px 8px; text-align:right;">{rec.total_cost:,.2f}</td>'
            f'<td style="padding:6px 8px; text-align:right;">{ratio:.2f}x</td>'
            f'<td style="padding:6px 8px; text-align:center;">{_status_pill(status)}</td>'
            f'</tr>'
        )

    table_html = header + "\n".join(rows_html) + "</tbody></table>"
    st.markdown(table_html, unsafe_allow_html=True)


### Tab 4 - AQP Tree Comparison
def _render_aqp_trees(bundle: preprocessing.PlanBundle) -> None:
    """Let the user pick an AQP and view its plan tree side-by-side with the QEP."""
    valid_aqps = [r for r in bundle.aqps if not r.note and r.plan_json.get("Plan")]
    if not valid_aqps:
        st.warning("No alternative plans were generated successfully.")
        return

    labels = [f"{r.setting[7:]}  (Cost: {r.total_cost:,.2f})" for r in valid_aqps]
    chosen = st.selectbox("Select a disabled setting to view AQP", labels)
    idx = labels.index(chosen)
    rec = valid_aqps[idx]

    baseline = bundle.qep_total_cost
    ratio = rec.total_cost / baseline if baseline > 0 else float("inf")

    c1, c2, c3 = st.columns(3)
    c1.metric("Disabled Setting", rec.setting[7:])
    c2.metric("AQP Cost", f"{rec.total_cost:,.2f}")
    c3.metric("Cost Ratio vs QEP", f"{ratio:.2f}x",
              delta=f"{(ratio - 1) * 100:+.1f}%",
              delta_color="inverse")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    col_qep, col_aqp = st.columns(2)

    with col_qep:
        st.markdown("##### QEP (Baseline)")
        _render_single_tree(bundle.qep_json)

    with col_aqp:
        st.markdown(f"##### AQP ({rec.setting[7:]} = off)")
        _render_single_tree(rec.plan_json)


def _render_single_tree(plan_json: Dict[str, Any]) -> None:
    """Render a single plan tree (Graphviz with text fallback)."""
    root = plan_json.get("Plan")
    if not root:
        st.info("No plan tree available.")
        return

    try:
        import graphviz
        dot = graphviz.Digraph(
            format="svg",
            graph_attr={"rankdir": "TB", "bgcolor": "transparent",
                        "nodesep": "0.5", "ranksep": "0.7", "pad": "0.2"},
            node_attr={"shape": "box", "style": "rounded,filled",
                       "fontname": "Helvetica", "fontsize": "9",
                       "fontcolor": "white", "margin": "0.15,0.08",
                       "penwidth": "0"},
            edge_attr={"color": "#94A3B8", "arrowsize": "0.7",
                       "penwidth": "1.3"},
        )
        _add_graphviz_nodes(dot, root, node_id=[0])
        st.graphviz_chart(dot, width="stretch")
    except Exception:
        st.code(preprocessing.format_plan_tree(plan_json), language=None)


### Tab 5 — Custom AQP
PLANNER_SETTINGS_GROUPED = {
    "Scan Methods": [
        ("enable_seqscan", "Sequential Scan"),
        ("enable_indexscan", "Index Scan"),
        ("enable_indexonlyscan", "Index Only Scan"),
        ("enable_bitmapscan", "Bitmap Scan"),
        ("enable_tidscan", "TID Scan"),
    ],
    "Join Methods": [
        ("enable_nestloop", "Nested Loop Join"),
        ("enable_hashjoin", "Hash Join"),
        ("enable_mergejoin", "Merge Join"),
    ],
    "Other Operations": [
        ("enable_sort", "Sort"),
        ("enable_material", "Materialize"),
        ("enable_hashagg", "Hash Aggregate"),
        ("enable_gathermerge", "Gather Merge"),
    ],
}

ALL_SETTINGS = [s for group in PLANNER_SETTINGS_GROUPED.values() for s, _ in group]
SCAN_SETTINGS = {s for s, _ in PLANNER_SETTINGS_GROUPED["Scan Methods"]}
JOIN_SETTINGS = {s for s, _ in PLANNER_SETTINGS_GROUPED["Join Methods"]}


def _render_custom_aqp(config: Dict[str, str], query: str,
                       baseline_cost: float, qep_json: Dict[str, Any]) -> None:

    st.markdown(
        "Toggle **on** the methods you want PostgreSQL to consider then click **Generate Custom AQP**.\n\n"
        "PostgreSQL requires at least 1 scan method and 1 join method to product a valid plan."
    )

    if "custom_aqp_inited" not in st.session_state:
        for setting in ALL_SETTINGS:
            st.session_state[f"custom_aqp_{setting}"] = False
        st.session_state["custom_aqp_inited"] = True

    # clicking on checkbox causes the tabs to switch to the first tab
    with st.form("custom_aqp_form"):
        cols = st.columns(len(PLANNER_SETTINGS_GROUPED))
        for col, (group_name, settings) in zip(cols, PLANNER_SETTINGS_GROUPED.items()):
            with col:
                st.markdown(f"**{group_name}**")
                for setting, label in settings:
                    st.checkbox(label, key=f"custom_aqp_{setting}")

        submitted = st.form_submit_button(
            "Generate Custom AQP",
            type="primary"
        )

    # get enabled settings
    enabled_settings = [
        s for s in ALL_SETTINGS if st.session_state.get(f"custom_aqp_{s}")
    ]
    enabled_scans = [s for s in enabled_settings if s in SCAN_SETTINGS]
    enabled_joins = [s for s in enabled_settings if s in JOIN_SETTINGS]

    if enabled_settings:
        st.markdown(
            "Enabled: " + ", ".join(f"`{s[7:]}`" for s in enabled_settings)
        )
    else:
        st.caption("All methods disabled.")

    if not enabled_scans:
        st.warning(
            "Choose at least 1 scan method."
        )
    if not enabled_joins:
        st.warning(
            "Choose at least 1 join method."
        )

    if submitted:
        if not query.strip():
            st.warning("Enter a query and click Run Annotation.")
            return
        if not enabled_scans or not enabled_joins:
            st.error(
                "Cannot generate plan."
            )
            return

    custom_plan = st.session_state.get("custom_aqp_plan")
    custom_enabled = st.session_state.get("custom_aqp_enabled", [])
    if custom_plan is None:
        return

    custom_cost = preprocessing.extract_total_cost(custom_plan)
    ratio = custom_cost / baseline_cost if baseline_cost > 0 else float("inf")

    st.divider()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("QEP Baseline Cost", f"{baseline_cost:,.2f}")
    c2.metric("Custom AQP Cost", f"{custom_cost:,.2f}")
    c3.metric("Cost Ratio", f"{ratio:.2f}x",
              delta=f"{(ratio - 1) * 100:+.1f}%",
              delta_color="inverse")
    c4.metric("Methods Enabled", f"{len(custom_enabled)} / {len(ALL_SETTINGS)}")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # sub tabs: tree comparison, text, and JSON
    sub_vis, sub_txt, sub_json = st.tabs(["Visual Tree", "Text Tree", "Raw JSON"])

    with sub_vis:
        col_qep, col_custom = st.columns(2)
        with col_qep:
            st.markdown("##### QEP (Baseline)")
            _render_single_tree(qep_json)
        with col_custom:
            enabled_label = ", ".join(s[7:] for s in custom_enabled) or "none"
            st.markdown(f"##### Custom AQP (Enabled: {enabled_label})")
            _render_single_tree(custom_plan)

    with sub_txt:
        st.code(preprocessing.format_plan_tree(custom_plan), language=None)

    with sub_json:
        st.json(custom_plan)



### MAIN
def main() -> None:
    st.markdown(
        "<br/>"
        "<h2 style='margin-bottom:0'>SC3020 Project 2</h2>"
        "<p style='opacity:0.6; margin-top:0'>Query Plan-Based SQL Annotation</p>",
        unsafe_allow_html=True,
    )

    config = _render_sidebar()

    if "sql_area" not in st.session_state:
        st.session_state["sql_area"] = (
            "select *\nfrom customer C, orders O\nwhere C.c_custkey = O.o_custkey;"
        )

    query = st.text_area(
        "Enter your SQL query",
        height=150,
        key="sql_area",
        help="Paste an SQL query or pick one from the sidebar.",
    )

    col1, col2, _ = st.columns([1, 1, 5])
    with col1:
        run_clicked = st.button("Run Annotation", type="primary")
    with col2:
        if st.button("Clear Results"):
            st.session_state.pop("result", None)
            st.rerun()

    if run_clicked:
        if not query.strip():
            st.warning("Please enter a SQL query first.")
            return
        with st.spinner("Connecting to PostgreSQL and generating annotations..."):
            try:
                result = _run(config, query)
                st.session_state["result"] = result
            except Exception as exc:
                st.error(f"Error: {exc}")
                return

    result = st.session_state.get("result")
    if result is None:
        st.info("Enter a query above and click **Run Annotation** to see results.")
        return

    st.divider()

    tab_ann, tab_tree, tab_aqp, tab_aqp_trees, tab_custom = st.tabs([
        "Annotated Query",
        "QEP Tree",
        "AQP Comparison Table",
        "AQP Comparison Trees",
        "Custom AQP Config",
    ])

    with tab_ann:
        _render_annotated_query(result.structured)
    with tab_tree:
        _render_qep_tree(result.raw_qep, result.qep_tree)
    with tab_aqp:
        _render_aqp_table(result.bundle)
    with tab_aqp_trees:
        _render_aqp_trees(result.bundle)
    with tab_custom:
        _render_custom_aqp(config, query, result.bundle.qep_total_cost,
                           result.raw_qep)

main()