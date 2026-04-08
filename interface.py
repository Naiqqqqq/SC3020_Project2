"""Tkinter GUI for SQL query annotation project."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict


class QueryAnnotationApp(tk.Tk):
    def __init__(self, run_pipeline_fn: Callable[[Dict[str, str], str], Any]) -> None:
        super().__init__()
        self.title("SC3020 Project 2 - Plan-Based SQL Annotation")
        self.geometry("1250x780")

        self.run_pipeline_fn = run_pipeline_fn

        self._build_connection_panel()
        self._build_main_panels()
        self._build_status_bar()

    def _build_connection_panel(self) -> None:
        frame = ttk.LabelFrame(self, text="PostgreSQL Connection")
        frame.pack(fill=tk.X, padx=10, pady=8)

        self.host_var = tk.StringVar(value="localhost")
        self.port_var = tk.StringVar(value="5432")
        self.db_var = tk.StringVar(value="postgres")
        self.user_var = tk.StringVar(value="postgres")
        self.password_var = tk.StringVar(value="")

        fields = [
            ("Host", self.host_var),
            ("Port", self.port_var),
            ("Database", self.db_var),
            ("User", self.user_var),
            ("Password", self.password_var),
        ]

        for idx, (label, var) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=0, column=idx * 2, padx=6, pady=6, sticky="w")
            show = "*" if label == "Password" else None
            entry = ttk.Entry(frame, textvariable=var, width=16, show=show)
            entry.grid(row=0, column=idx * 2 + 1, padx=6, pady=6, sticky="we")

        for col in range(len(fields) * 2):
            frame.grid_columnconfigure(col, weight=1)

    def _build_main_panels(self) -> None:
        wrapper = ttk.Frame(self)
        wrapper.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        top_frame = ttk.LabelFrame(wrapper, text="Query Panel")
        top_frame.pack(fill=tk.BOTH, expand=True)

        self.query_text = tk.Text(top_frame, wrap=tk.WORD, font=("Consolas", 11), height=10)
        self.query_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.query_text.insert(
            "1.0",
            "select *\nfrom customer C, orders O\nwhere C.c_custkey = O.o_custkey;",
        )

        button_row = ttk.Frame(top_frame)
        button_row.pack(fill=tk.X, padx=8, pady=(0, 8))

        ttk.Button(button_row, text="Load SQL File", command=self._load_query_file).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(button_row, text="Run Annotation", command=self._run_annotation).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(button_row, text="Clear Output", command=self._clear_output).pack(side=tk.LEFT)

        result_frame = ttk.LabelFrame(wrapper, text="Results")
        result_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        self.tabs = ttk.Notebook(result_frame)
        self.tabs.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.annotated_text = self._create_text_tab("Annotated Query")
        self.qep_text = self._create_text_tab("QEP Tree")
        self.aqp_text = self._create_text_tab("AQP Summary")

    def _build_status_bar(self) -> None:
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self, textvariable=self.status_var, anchor="w")
        status_bar.pack(fill=tk.X, padx=10, pady=(0, 6))

    def _create_text_tab(self, title: str) -> tk.Text:
        frame = ttk.Frame(self.tabs)
        self.tabs.add(frame, text=title)

        text = tk.Text(frame, wrap=tk.WORD, font=("Consolas", 10))
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)

        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        return text

    def _load_query_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Select SQL File",
            filetypes=[("SQL files", "*.sql"), ("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as sql_file:
                content = sql_file.read()
        except OSError as exc:
            messagebox.showerror("Read Error", f"Could not read file.\n\n{exc}")
            return

        self.query_text.delete("1.0", tk.END)
        self.query_text.insert("1.0", content)
        self.status_var.set(f"Loaded query from {file_path}")

    def _clear_output(self) -> None:
        for text_widget in (self.annotated_text, self.qep_text, self.aqp_text):
            text_widget.delete("1.0", tk.END)
        self.status_var.set("Output cleared")

    def _collect_connection_config(self) -> Dict[str, str]:
        return {
            "host": self.host_var.get().strip(),
            "port": self.port_var.get().strip(),
            "dbname": self.db_var.get().strip(),
            "user": self.user_var.get().strip(),
            "password": self.password_var.get(),
        }

    def _run_annotation(self) -> None:
        query = self.query_text.get("1.0", tk.END).strip()
        if not query:
            messagebox.showwarning("Missing Query", "Please enter a SQL query first.")
            return

        config = self._collect_connection_config()

        try:
            self.status_var.set("Running EXPLAIN and generating annotations...")
            self.update_idletasks()
            result = self.run_pipeline_fn(config, query)
        except Exception as exc:
            # Avoid showing stale results from a previous successful run.
            for text_widget in (self.annotated_text, self.qep_text, self.aqp_text):
                text_widget.delete("1.0", tk.END)
            messagebox.showerror("Execution Error", str(exc))
            self.status_var.set("Execution failed")
            return

        self.annotated_text.delete("1.0", tk.END)
        self.annotated_text.insert("1.0", result.annotated_query)

        self.qep_text.delete("1.0", tk.END)
        self.qep_text.insert("1.0", result.qep_tree)

        self.aqp_text.delete("1.0", tk.END)
        self.aqp_text.insert("1.0", result.aqp_summary)

        self.status_var.set("Done - annotation generated")


def launch_app(run_pipeline_fn: Callable[[Dict[str, str], str], Any]) -> None:
    app = QueryAnnotationApp(run_pipeline_fn)
    app.mainloop()
