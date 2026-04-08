"""Main entry point for SC3020 Project 2.

Run without arguments to start GUI:
    python project.py

Optional CLI mode:
    python project.py --nogui --query "select * from customer"
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any, Dict

import annotation
import preprocessing
from interface import launch_app


@dataclass
class PipelineResult:
    annotated_query: str
    qep_tree: str
    aqp_summary: str
    raw_qep: Dict[str, Any]


def run_pipeline(config_dict: Dict[str, str], query: str) -> PipelineResult:
    normalized_query = preprocessing.ensure_single_statement(query)

    try:
        port = int(config_dict.get("port", "5432"))
    except ValueError as exc:
        raise ValueError("Port must be an integer.") from exc

    db_config = preprocessing.DBConfig(
        host=config_dict.get("host", "localhost"),
        port=port,
        dbname=config_dict.get("dbname", "postgres"),
        user=config_dict.get("user", "postgres"),
        password=config_dict.get("password", "postgres"),
    )

    conn = preprocessing.connect_postgres(db_config)
    try:
        bundle = preprocessing.get_qep_and_aqps(conn, normalized_query)
    finally:
        conn.close()

    annotation_result = annotation.generate_annotation(normalized_query, bundle)

    return PipelineResult(
        annotated_query=annotation_result["annotated_query"],
        qep_tree=preprocessing.format_plan_tree(bundle.qep_json),
        aqp_summary=annotation.format_aqp_summary(bundle),
        raw_qep=bundle.qep_json,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SC3020 Project 2 SQL annotation tool")

    parser.add_argument("--nogui", action="store_true", help="Run in command-line mode")
    parser.add_argument("--query", type=str, help="SQL query text for CLI mode")
    parser.add_argument("--query-file", type=str, help="Path to SQL file for CLI mode")
    parser.add_argument(
        "--query-index",
        type=int,
        help="1-based statement index to run from --query-file",
    )
    parser.add_argument(
        "--all-queries",
        action="store_true",
        help="Run all statements found in --query-file",
    )

    parser.add_argument("--host", type=str, default="localhost")
    parser.add_argument("--port", type=str, default="5432")
    parser.add_argument("--dbname", type=str, default="postgres")
    parser.add_argument("--user", type=str, default="postgres")
    parser.add_argument("--password", type=str, default="postgres")

    return parser


def _run_cli(args: argparse.Namespace) -> None:
    if args.query and args.query_file:
        raise ValueError("Use either --query or --query-file, not both.")

    if args.query_index is not None and args.query_index <= 0:
        raise ValueError("--query-index must be >= 1.")

    if args.query and (args.query_index is not None or args.all_queries):
        raise ValueError("--query-index/--all-queries are only valid with --query-file.")

    queries_to_run: list[str]
    if args.query:
        queries_to_run = [preprocessing.ensure_single_statement(args.query)]
    elif args.query_file:
        file_queries = preprocessing.load_queries_from_file(args.query_file)
        if not file_queries:
            raise ValueError(f"No SQL statements found in file: {args.query_file}")

        if args.all_queries:
            queries_to_run = file_queries
        elif args.query_index is not None:
            if args.query_index > len(file_queries):
                raise ValueError(
                    f"--query-index {args.query_index} out of range; file has {len(file_queries)} statement(s)."
                )
            queries_to_run = [file_queries[args.query_index - 1]]
        elif len(file_queries) == 1:
            queries_to_run = file_queries
        else:
            raise ValueError(
                "Multiple SQL statements found in file. Use --query-index N to run one "
                "statement or --all-queries to run all statements."
            )
    else:
        raise ValueError("Provide a query with --query or --query-file in --nogui mode.")

    config = {
        "host": args.host,
        "port": args.port,
        "dbname": args.dbname,
        "user": args.user,
        "password": args.password,
    }

    for idx, query_text in enumerate(queries_to_run, start=1):
        if len(queries_to_run) > 1:
            print(f"\n===== Statement {idx}/{len(queries_to_run)} =====\n")
            print(query_text)

        result = run_pipeline(config, query_text)
        print("\n===== Annotated Query =====\n")
        print(result.annotated_query)
        print("\n===== QEP Tree =====\n")
        print(result.qep_tree)
        print("\n===== AQP Summary =====\n")
        print(result.aqp_summary)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.nogui:
        _run_cli(args)
        return

    launch_app(run_pipeline)


if __name__ == "__main__":
    main()
