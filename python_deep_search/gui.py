from __future__ import annotations

import logging
import re
import threading
import time as _time
import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox, ttk

from . import cache
from .browser import open_browser_tab
from .config import DEFAULT_SITES_PATH, load_sites_config
from .models import SearchRequest, SiteResult
from .output import save_results_json
from .search_engine import deep_search, filter_candidates, setup_logging

_FONT = ("Segoe UI", 10)
_FONT_BOLD = ("Segoe UI", 10, "bold")
_FONT_TITLE = ("Segoe UI", 16, "bold")
_FONT_SMALL = ("Segoe UI", 9)
_FONT_MONO = ("Consolas", 10)

_BG = "#f6f7f9"
_PANEL = "#ffffff"
_FG = "#1f2937"
_MUTED = "#6b7280"
_ACCENT = "#2563eb"
_SUCCESS = "#15803d"
_DANGER = "#b91c1c"
_WARN = "#b45309"
_BORDER = "#d7dce3"
_LOG_BG = "#111827"
_LOG_FG = "#d1d5db"
_OPTIONAL_BOOTSTRAP_THEME = "flatly"


class DeepSearchApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Deep Search")
        self.geometry("1240x820")
        self.minsize(980, 640)
        self.tk.call("tk", "scaling", self._screen_scaling())
        self.configure(bg=_BG)

        self._setup_styles()
        self._init_state()

        self._log_queue: Queue = Queue()
        setup_logging(verbose=False, gui_queue=self._log_queue)

        self._build_ui()
        self._poll_log_queue()
        self._load_cached_logs()

    def _init_state(self) -> None:
        last_sites = cache.get_setting("last_sites", DEFAULT_SITES_PATH)
        if not Path(last_sites).exists():
            last_sites = DEFAULT_SITES_PATH

        self.sites_path = tk.StringVar(value=last_sites)
        self.query_var = tk.StringVar()
        self.regex_var = tk.StringVar()
        self.max_results_var = tk.IntVar(value=10)
        self.max_links_var = tk.IntVar(value=100)
        self.timeout_var = tk.IntVar(value=15)
        self.workers_var = tk.IntVar(value=6)
        self.follow_var = tk.BooleanVar(value=True)
        self.follow_limit_var = tk.IntVar(value=5)
        self.playwright_var = tk.BooleanVar(value=True)
        self.verbose_var = tk.BooleanVar(value=False)
        self.cache_var = tk.BooleanVar(value=True)
        self.browser_var = tk.StringVar(value=cache.get_setting("last_browser", ""))
        self.view_var = tk.StringVar(value="all")
        self.status_var = tk.StringVar(value="Ready")
        self.summary_var = tk.StringVar(value="No search yet")

        self.latest_results: dict[str, SiteResult] = {}
        self.latest_candidates: dict[str, SiteResult] = {}
        self._rendered_results: dict[str, SiteResult] = {}
        self._url_tag_count = 0
        self._running = False
        self.log_panel_visible = False

    def _setup_styles(self) -> None:
        style = ttk.Style()
        try:
            import ttkbootstrap  # noqa: F401

            style.theme_use(_OPTIONAL_BOOTSTRAP_THEME)
        except Exception:
            style.theme_use("clam")
        style.configure(".", font=_FONT, background=_BG, foreground=_FG)
        style.configure("TFrame", background=_BG)
        style.configure("Panel.TFrame", background=_PANEL)
        style.configure("TLabel", background=_BG, foreground=_FG, font=_FONT)
        style.configure("Panel.TLabel", background=_PANEL, foreground=_FG, font=_FONT)
        style.configure("Muted.TLabel", background=_BG, foreground=_MUTED, font=_FONT_SMALL)
        style.configure("Title.TLabel", background=_BG, foreground=_FG, font=_FONT_TITLE)
        style.configure("TButton", font=_FONT, padding=(10, 6))
        style.configure("Accent.TButton", background=_ACCENT, foreground="white")
        style.map("Accent.TButton", background=[("active", "#1d4ed8"), ("disabled", "#9ca3af")])
        style.configure("TEntry", fieldbackground=_PANEL, bordercolor=_BORDER, lightcolor=_BORDER, darkcolor=_BORDER)
        style.configure("TSpinbox", fieldbackground=_PANEL, bordercolor=_BORDER)
        style.configure("TCheckbutton", background=_PANEL, foreground=_FG)
        style.configure("TRadiobutton", background=_PANEL, foreground=_FG)
        style.configure("TProgressbar", troughcolor="#e5e7eb", background=_ACCENT)
        style.configure("Treeview", font=_FONT, rowheight=28, background=_PANEL, fieldbackground=_PANEL)
        style.configure("Treeview.Heading", font=_FONT_BOLD, background="#eef2f7", foreground=_FG)

    def _screen_scaling(self) -> float:
        width = self.winfo_screenwidth()
        if width <= 1400:
            return 1.15
        if width >= 2200:
            return 1.0
        return 1.08

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=0, minsize=330)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        self._build_header()
        self._build_controls()
        self._build_workspace()
        self._build_status_bar()

    def _build_header(self) -> None:
        header = ttk.Frame(self, padding=(18, 14, 18, 8))
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="Deep Search", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.summary_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w")

        self.progress = ttk.Progressbar(header, mode="indeterminate", length=160)
        self.progress.grid(row=0, column=1, rowspan=2, sticky="e", padx=(16, 0))

    def _build_controls(self) -> None:
        panel = ttk.Frame(self, style="Panel.TFrame", padding=14)
        panel.grid(row=1, column=0, sticky="nsew", padx=(16, 8), pady=(0, 12))
        panel.columnconfigure(0, weight=1)

        ttk.Label(panel, text="Search", style="Panel.TLabel", font=_FONT_BOLD).grid(row=0, column=0, sticky="w")

        ttk.Label(panel, text="Query", style="Panel.TLabel").grid(row=1, column=0, sticky="w", pady=(14, 4))
        ttk.Entry(panel, textvariable=self.query_var).grid(row=2, column=0, sticky="ew")

        ttk.Label(panel, text="Regex", style="Panel.TLabel").grid(row=3, column=0, sticky="w", pady=(12, 4))
        ttk.Entry(panel, textvariable=self.regex_var).grid(row=4, column=0, sticky="ew")

        ttk.Label(panel, text="Sites JSON", style="Panel.TLabel").grid(row=5, column=0, sticky="w", pady=(12, 4))
        sites_row = ttk.Frame(panel, style="Panel.TFrame")
        sites_row.grid(row=6, column=0, sticky="ew")
        sites_row.columnconfigure(0, weight=1)
        ttk.Entry(sites_row, textvariable=self.sites_path).grid(row=0, column=0, sticky="ew")
        ttk.Button(sites_row, text="...", width=4, command=self._pick_sites_file).grid(row=0, column=1, padx=(6, 0))

        ttk.Label(panel, text="Browser", style="Panel.TLabel").grid(row=7, column=0, sticky="w", pady=(12, 4))
        ttk.Entry(panel, textvariable=self.browser_var).grid(row=8, column=0, sticky="ew")

        limits = ttk.Frame(panel, style="Panel.TFrame")
        limits.grid(row=9, column=0, sticky="ew", pady=(16, 0))
        for col in range(2):
            limits.columnconfigure(col, weight=1)

        self._spinbox(limits, "Results", self.max_results_var, 1, 100, 0, 0)
        self._spinbox(limits, "Links", self.max_links_var, 1, 500, 0, 1)
        self._spinbox(limits, "Timeout", self.timeout_var, 3, 120, 2, 0)
        self._spinbox(limits, "Workers", self.workers_var, 1, 32, 2, 1)
        self._spinbox(limits, "Follow limit", self.follow_limit_var, 1, 50, 4, 0)

        flags = ttk.Frame(panel, style="Panel.TFrame")
        flags.grid(row=10, column=0, sticky="ew", pady=(16, 0))
        ttk.Checkbutton(flags, text="Follow links", variable=self.follow_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(flags, text="Use Playwright", variable=self.playwright_var).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Checkbutton(flags, text="Use cache", variable=self.cache_var).grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Checkbutton(flags, text="Verbose logs", variable=self.verbose_var).grid(row=3, column=0, sticky="w", pady=(4, 0))

        actions = ttk.Frame(panel, style="Panel.TFrame")
        actions.grid(row=11, column=0, sticky="ew", pady=(18, 0))
        actions.columnconfigure(0, weight=1)
        self.search_button = ttk.Button(actions, text="Search", style="Accent.TButton", command=self._start_search)
        self.search_button.grid(row=0, column=0, sticky="ew")

        ttk.Separator(panel).grid(row=12, column=0, sticky="ew", pady=18)
        ttk.Label(panel, text="View", style="Panel.TLabel", font=_FONT_BOLD).grid(row=13, column=0, sticky="w")
        ttk.Radiobutton(panel, text="All sites", variable=self.view_var, value="all", command=self._refresh_view).grid(
            row=14, column=0, sticky="w", pady=(8, 0)
        )
        ttk.Radiobutton(panel, text="Candidates only", variable=self.view_var, value="candidates", command=self._refresh_view).grid(
            row=15, column=0, sticky="w", pady=(4, 0)
        )

        bulk = ttk.Frame(panel, style="Panel.TFrame")
        bulk.grid(row=16, column=0, sticky="ew", pady=(16, 0))
        bulk.columnconfigure(0, weight=1)
        bulk.columnconfigure(1, weight=1)
        ttk.Button(bulk, text="Open links", command=self._open_visible_links).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(bulk, text="Save JSON", command=self._save_json).grid(row=0, column=1, sticky="ew", padx=(4, 0))

    def _spinbox(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.IntVar,
        from_: int,
        to: int,
        row: int,
        column: int,
    ) -> None:
        ttk.Label(parent, text=label, style="Panel.TLabel").grid(row=row, column=column, sticky="w", padx=(0, 8), pady=(0, 4))
        ttk.Spinbox(parent, from_=from_, to=to, textvariable=variable, width=8).grid(
            row=row + 1, column=column, sticky="ew", padx=(0, 8), pady=(0, 10)
        )

    def _build_workspace(self) -> None:
        workspace = ttk.Frame(self)
        workspace.grid(row=1, column=1, sticky="nsew", padx=(8, 16), pady=(0, 12))
        workspace.columnconfigure(0, weight=1)
        workspace.rowconfigure(0, weight=1)

        self.main_pane = ttk.PanedWindow(workspace, orient=tk.VERTICAL)
        self.main_pane.grid(row=0, column=0, sticky="nsew")

        results_panel = ttk.Frame(self.main_pane, style="Panel.TFrame", padding=10)
        results_panel.columnconfigure(0, weight=1)
        results_panel.rowconfigure(1, weight=1)
        self.main_pane.add(results_panel, weight=3)

        toolbar = ttk.Frame(results_panel, style="Panel.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        toolbar.columnconfigure(0, weight=1)
        ttk.Label(toolbar, text="Results", style="Panel.TLabel", font=_FONT_BOLD).grid(row=0, column=0, sticky="w")
        ttk.Button(toolbar, text="Open selected", command=self._open_selected_links).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(toolbar, text="Logs", command=self._toggle_log_panel).grid(row=0, column=2, padx=(8, 0))

        columns = ("status", "site", "search", "links", "followed", "time")
        self.results_tree = ttk.Treeview(results_panel, columns=columns, show="headings", selectmode="browse")
        self.results_tree.heading("status", text="")
        self.results_tree.heading("site", text="Site")
        self.results_tree.heading("search", text="Search URL")
        self.results_tree.heading("links", text="Search links")
        self.results_tree.heading("followed", text="Followed")
        self.results_tree.heading("time", text="Time")
        self.results_tree.column("status", width=42, minwidth=36, stretch=False, anchor=tk.CENTER)
        self.results_tree.column("site", width=180, minwidth=120, stretch=False)
        self.results_tree.column("search", width=420, minwidth=220, stretch=True)
        self.results_tree.column("links", width=104, minwidth=86, stretch=False, anchor=tk.E)
        self.results_tree.column("followed", width=82, minwidth=70, stretch=False, anchor=tk.E)
        self.results_tree.column("time", width=78, minwidth=64, stretch=False, anchor=tk.E)
        self.results_tree.tag_configure("found", foreground=_SUCCESS)
        self.results_tree.tag_configure("empty", foreground=_MUTED)
        self.results_tree.tag_configure("error", foreground=_DANGER)
        self.results_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.results_tree.grid(row=1, column=0, sticky="nsew")

        tree_scroll = ttk.Scrollbar(results_panel, orient=tk.VERTICAL, command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.grid(row=1, column=1, sticky="ns")

        detail_panel = ttk.Frame(self.main_pane, style="Panel.TFrame", padding=10)
        detail_panel.columnconfigure(0, weight=1)
        detail_panel.rowconfigure(1, weight=1)
        self.main_pane.add(detail_panel, weight=2)

        ttk.Label(detail_panel, text="Details", style="Panel.TLabel", font=_FONT_BOLD).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.text = tk.Text(
            detail_panel,
            wrap=tk.WORD,
            cursor="arrow",
            font=_FONT_MONO,
            bg=_PANEL,
            fg=_FG,
            relief="solid",
            borderwidth=1,
            padx=12,
            pady=10,
            selectbackground=_ACCENT,
            selectforeground="white",
        )
        detail_scroll = ttk.Scrollbar(detail_panel, orient=tk.VERTICAL, command=self.text.yview)
        self.text.configure(yscrollcommand=detail_scroll.set)
        self.text.grid(row=1, column=0, sticky="nsew")
        detail_scroll.grid(row=1, column=1, sticky="ns")

        self.text.tag_configure("url", foreground=_ACCENT, underline=True)
        self.text.tag_bind("url", "<Enter>", lambda _e: self.text.configure(cursor="hand2"))
        self.text.tag_bind("url", "<Leave>", lambda _e: self.text.configure(cursor="arrow"))
        self.text.tag_configure("header", font=_FONT_BOLD, foreground=_ACCENT)
        self.text.tag_configure("muted", foreground=_MUTED)
        self.text.tag_configure("match", foreground=_SUCCESS)
        self.text.tag_configure("error", foreground=_DANGER)

        self._build_log_panel(workspace)

    def _build_log_panel(self, parent: ttk.Frame) -> None:
        self.log_frame = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        self.log_frame.columnconfigure(0, weight=1)
        self.log_frame.rowconfigure(1, weight=1)

        log_toolbar = ttk.Frame(self.log_frame, style="Panel.TFrame")
        log_toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        log_toolbar.columnconfigure(0, weight=1)
        ttk.Label(log_toolbar, text="Logs", style="Panel.TLabel", font=_FONT_BOLD).grid(row=0, column=0, sticky="w")
        ttk.Button(log_toolbar, text="Clear", command=self._clear_log).grid(row=0, column=1)

        self.log_text = tk.Text(
            self.log_frame,
            height=9,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=_FONT_MONO,
            bg=_LOG_BG,
            fg=_LOG_FG,
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=8,
        )
        self.log_scroll = ttk.Scrollbar(self.log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=self.log_scroll.set)
        self.log_text.grid(row=1, column=0, sticky="nsew")
        self.log_scroll.grid(row=1, column=1, sticky="ns")

        self.log_text.tag_configure("ERRO", foreground="#fecaca")
        self.log_text.tag_configure("WARN", foreground="#fed7aa")
        self.log_text.tag_configure("INFO", foreground="#bbf7d0")
        self.log_text.tag_configure("DEBU", foreground="#93c5fd")

    def _build_status_bar(self) -> None:
        bar = ttk.Frame(self, padding=(16, 0, 16, 12))
        bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        bar.columnconfigure(0, weight=1)
        ttk.Label(bar, textvariable=self.status_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")

    def _toggle_log_panel(self) -> None:
        if self.log_panel_visible:
            self.log_frame.grid_forget()
            self.log_panel_visible = False
        else:
            self.log_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
            self.log_panel_visible = True

    def _clear_log(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _poll_log_queue(self) -> None:
        while True:
            try:
                record: logging.LogRecord = self._log_queue.get_nowait()
                self._append_log(record)
            except Empty:
                break
        self.after(250, self._poll_log_queue)

    def _append_log(self, record: logging.LogRecord) -> None:
        self._append_log_line(record.levelname[:4], record.getMessage())

    def _append_log_line(self, level: str, msg: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{level}] {msg}\n", (level,))
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _load_cached_logs(self) -> None:
        for entry in cache.get_cached_logs():
            self._append_log_line(str(entry.get("level", "INFO")), str(entry.get("msg", "")))

    def _pick_sites_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose sites JSON",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.sites_path.set(path)
            cache.set_setting("last_sites", path)

    def _start_search(self) -> None:
        if self._running:
            return

        query = self.query_var.get().strip()
        if not query:
            messagebox.showerror("Search error", "Enter a search query.")
            return

        regex_pattern = self.regex_var.get().strip()
        if regex_pattern:
            try:
                re.compile(regex_pattern)
            except re.error as e:
                messagebox.showerror("Regex error", str(e))
                return

        sites_path = self.sites_path.get().strip()
        if not Path(sites_path).exists():
            messagebox.showerror("Sites JSON not found", sites_path)
            return

        cache.set_setting("last_sites", sites_path)
        cache.set_setting("last_browser", self.browser_var.get().strip())
        setup_logging(verbose=self.verbose_var.get(), gui_queue=self._log_queue)

        req = SearchRequest(
            query=query,
            regex_pattern=regex_pattern,
            max_results=max(1, self.max_results_var.get()),
            max_links=max(1, self.max_links_var.get()),
            timeout_sec=max(3, self.timeout_var.get()),
            follow_links=self.follow_var.get(),
            follow_limit=max(1, self.follow_limit_var.get()),
            use_playwright=self.playwright_var.get(),
            verbose=self.verbose_var.get(),
        )
        max_workers = max(1, self.workers_var.get())
        use_cache = self.cache_var.get()

        self._set_running(True)
        self._clear_results()
        self.status_var.set("Search is running...")
        self.summary_var.set("Working")

        thread = threading.Thread(
            target=self._search_worker,
            args=(sites_path, req, max_workers, use_cache),
            daemon=True,
        )
        thread.start()

    def _set_running(self, running: bool) -> None:
        self._running = running
        self.search_button.configure(state=tk.DISABLED if running else tk.NORMAL)
        if running:
            self.progress.start(12)
        else:
            self.progress.stop()

    def _clear_results(self) -> None:
        self.latest_results = {}
        self.latest_candidates = {}
        self._rendered_results = {}
        self._url_tag_count = 0
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        self.text.delete("1.0", tk.END)

    def _search_worker(self, sites_path: str, req: SearchRequest, max_workers: int, use_cache: bool) -> None:
        try:
            sites = load_sites_config(sites_path)

            def progress(msg: str) -> None:
                self.after(0, self._on_progress, msg)

            results = deep_search(
                sites=sites,
                req=req,
                max_workers=max_workers,
                progress_callback=progress,
                use_cache=use_cache,
            )
            self.after(0, self._finish_search, results)
        except Exception as e:
            self.after(0, self._on_error, str(e))

    def _on_progress(self, msg: str) -> None:
        self.status_var.set(msg)

    def _finish_search(self, results: dict[str, SiteResult]) -> None:
        self._set_running(False)
        self.latest_results = results
        self.latest_candidates = filter_candidates(results)
        self._refresh_view()

    def _refresh_view(self) -> None:
        results = self.latest_candidates if self.view_var.get() == "candidates" else self.latest_results
        self._render_results(results)

    def _render_results(self, results: dict[str, SiteResult]) -> None:
        self._rendered_results = {
            site: data
            for site, data in results.items()
            if data.urls
        }
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

        for site, data in self._rendered_results.items():
            if data.error:
                marker = "ERR"
                tag = "error"
            elif data.urls:
                marker = "OK"
                tag = "found"
            else:
                marker = "-"
                tag = "empty"

            self.results_tree.insert(
                "",
                tk.END,
                iid=site,
                values=(
                    marker,
                    site,
                    self._short_search_url(data.search_url),
                    len(data.urls),
                    len(data.followed),
                    f"{data.elapsed_sec:.2f}s",
                ),
                tags=(tag,),
            )

        total_urls = sum(len(r.urls) for r in self.latest_results.values())
        self.summary_var.set(
            f"Search pages: {len(self._rendered_results)}/{len(self.latest_results)}    Search links: {total_urls}"
            if self.latest_results else "No search yet"
        )
        self.status_var.set("Ready" if self.latest_results else "No results")

        first = next(iter(self._rendered_results), None)
        if first:
            self.results_tree.selection_set(first)
            self.results_tree.focus(first)
            self._show_site_details(first)
        else:
            self.text.delete("1.0", tk.END)
            self._append("No search-level links in this view.\n", "muted")

    def _short_search_url(self, search_url: str) -> str:
        if not search_url:
            return "-"
        first_url = search_url.split(" | ", 1)[0]
        return first_url if len(first_url) <= 90 else first_url[:87] + "..."

    def _on_tree_select(self, _event) -> None:
        selected = self.results_tree.selection()
        if selected:
            self._show_site_details(selected[0])

    def _show_site_details(self, site: str) -> None:
        data = self._rendered_results.get(site)
        if data is None:
            return

        self.text.delete("1.0", tk.END)
        self._url_tag_count = 0

        self._append(f"{data.site_name}\n", "header")
        self._append(f"Base: {data.base_url}\n", "muted")
        self._append("Search: ", "muted")
        if data.search_url:
            for index, url in enumerate(data.search_url.split(" | "), 1):
                if index > 1:
                    self._append(" | ", "muted")
                self._append_url(url)
            self._append("\n")
        else:
            self._append("-\n", "muted")

        status = "found" if data.urls else "empty"
        if data.error:
            status = "error"
        self._append(f"Status: {status}    HTTP: {data.status_code or '-'}    Time: {data.elapsed_sec:.2f}s\n\n")

        if data.error:
            self._append(f"{data.error}\n", "error")
            return

        self._append(f"Search results ({len(data.urls)})\n", "header")
        if data.urls:
            for index, url in enumerate(data.urls, 1):
                self._append(f"{index}. ", "muted")
                self._append_url(url)
                self._append("\n")
        else:
            self._append("No links.\n", "muted")

        self._append(f"\nFollowed pages ({len(data.followed)})\n", "header")
        if data.followed:
            for index, followed in enumerate(data.followed, 1):
                self._append(f"{index}. ", "muted")
                self._append_url(followed.source_url)
                self._append("\n")
                if followed.error:
                    self._append(f"   {followed.error}\n", "error")
                if followed.matches:
                    for match in followed.matches:
                        self._append(f"   match [{match.score}] {match.text}\n", "match")
                if followed.urls:
                    for url in followed.urls:
                        self._append("   link: ", "muted")
                        self._append_url(url)
                        self._append("\n")
                if not followed.matches and not followed.urls and not followed.error:
                    self._append("   No extracted details.\n", "muted")
        else:
            self._append("No followed pages.\n", "muted")

    def _append(self, message: str, *tags: str) -> None:
        self.text.insert(tk.END, message, tags if tags else ())
        self.text.see(tk.END)

    def _append_url(self, url: str) -> None:
        start = self.text.index("end-1c")
        self.text.insert(tk.END, url)
        end = self.text.index("end-1c")
        tag = f"url-{self._url_tag_count}"
        self._url_tag_count += 1
        self.text.tag_add("url", start, end)
        self.text.tag_add(tag, start, end)
        self.text.tag_bind(tag, "<Button-1>", lambda _event, target=url: self._open_single_url(target))

    def _open_single_url(self, url: str) -> None:
        ok, error = open_browser_tab(url, self.browser_var.get())
        if not ok:
            messagebox.showerror("Browser error", f"Could not open link:\n{url}\n\n{error}")

    def _on_error(self, error_text: str) -> None:
        self._set_running(False)
        self.status_var.set("Error")
        self.summary_var.set("Search failed")
        messagebox.showerror("Search error", error_text)

    def _save_json(self) -> None:
        if not self.latest_results:
            messagebox.showwarning("No data", "Run a search first.")
            return

        path = filedialog.asksaveasfilename(
            title="Save results",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile="search_results.json",
        )
        if not path:
            return

        saved = save_results_json(self.latest_results, path)
        messagebox.showinfo("Saved", f"Results saved:\n{saved}")

    def _open_visible_links(self) -> None:
        self._open_links(self._rendered_results)

    def _open_all_links(self) -> None:
        self._open_links(self.latest_results)

    def _open_candidate_links(self) -> None:
        self._open_links(self.latest_candidates)

    def _open_selected_links(self) -> None:
        selected = self.results_tree.selection()
        if not selected:
            messagebox.showinfo("No selection", "Select a site first.")
            return
        data = self._rendered_results.get(selected[0])
        self._open_link_list(self._site_output_links(data) if data else [])

    def _open_links(self, results: dict[str, SiteResult]) -> None:
        urls = list(dict.fromkeys(url for data in results.values() for url in self._site_output_links(data)))
        self._open_link_list(urls)

    def _site_output_links(self, data: SiteResult) -> list[str]:
        urls = list(data.urls)
        for followed in data.followed:
            urls.append(followed.source_url)
            urls.extend(followed.urls)
        return urls

    def _open_link_list(self, urls: list[str]) -> None:
        if not urls:
            messagebox.showinfo("No links", "No links to open.")
            return

        if len(urls) > 10 and not messagebox.askyesno("Open links", f"Open {len(urls)} tabs in your browser?"):
            return

        self.status_var.set(f"Opening links: 0/{len(urls)}")
        browser_name = self.browser_var.get().strip()
        cache.set_setting("last_browser", browser_name)
        threading.Thread(target=self._open_links_worker, args=(urls, browser_name), daemon=True).start()

    def _open_links_worker(self, urls: list[str], browser_name: str = "") -> None:
        failed = 0
        for index, url in enumerate(urls, 1):
            ok, _error = open_browser_tab(url, browser_name)
            if not ok:
                failed += 1
            self.after(0, self.status_var.set, f"Opening links: {index}/{len(urls)}")
            _time.sleep(0.3)
        opened = len(urls) - failed
        if failed:
            self.after(0, self.status_var.set, f"Opened links: {opened}, failed: {failed}")
        else:
            self.after(0, self.status_var.set, f"Opened links: {opened}")


def run_gui() -> None:
    app = DeepSearchApp()
    app.mainloop()
