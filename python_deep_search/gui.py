from __future__ import annotations

import logging
import re
import threading
import time as _time
import tkinter as tk
import webbrowser
from queue import Queue, Empty
from tkinter import filedialog, messagebox, ttk

from .config import load_sites_config
from .models import SearchRequest
from .output import save_results_json
from .search_engine import deep_search, filter_candidates, setup_logging

_FONT = ("Segoe UI", 10)
_FONT_BOLD = ("Segoe UI", 10, "bold")
_FONT_TITLE = ("Segoe UI", 14, "bold")
_FONT_MONO = ("Consolas", 10)

_BG = "#f0f2f5"
_FG = "#1a1a2e"
_ACCENT = "#2563eb"
_ACCENT_HOVER = "#1d4ed8"
_SUCCESS = "#16a34a"
_DANGER = "#dc2626"
_WARN = "#ea580c"
_BORDER = "#d4d4d8"
_SURFACE = "#ffffff"


class DeepSearchApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Deep Search")
        self.geometry("1100x780")
        self.minsize(960, 600)
        self.configure(bg=_BG)

        self._setup_styles()

        self.sites_path = tk.StringVar(value="python_deep_search/sites.json")
        self.query_var = tk.StringVar()
        self.regex_var = tk.StringVar(value=r"\b\w+\b")
        self.max_results_var = tk.IntVar(value=10)
        self.timeout_var = tk.IntVar(value=15)
        self.workers_var = tk.IntVar(value=6)
        self.follow_var = tk.BooleanVar(value=True)
        self.follow_limit_var = tk.IntVar(value=5)
        self.playwright_var = tk.BooleanVar(value=True)
        self.show_log_var = tk.BooleanVar(value=False)

        self.latest_results: dict = {}
        self.latest_candidates: dict = {}

        self._log_queue: Queue = Queue()
        setup_logging(verbose=False, gui_queue=self._log_queue)

        self._build_ui()
        self._poll_log_queue()

    def _setup_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", font=_FONT, background=_BG, foreground=_FG)
        style.configure("TFrame", background=_BG)
        style.configure("TLabel", background=_BG, font=_FONT)
        style.configure("TButton", font=_FONT, padding=(10, 5))
        style.configure("Accent.TButton", background=_ACCENT, foreground="white")
        style.map("Accent.TButton", background=[("active", _ACCENT_HOVER)])
        style.configure("TLabelframe", background=_BG, font=_FONT_BOLD, borderwidth=1, relief="solid")
        style.configure("TLabelframe.Label", background=_BG, font=_FONT_BOLD)
        style.configure("TEntry", fieldbackground=_SURFACE, borderwidth=1, relief="solid")
        style.configure("TSpinbox", fieldbackground=_SURFACE)
        style.configure("TCheckbutton", background=_BG)
        style.configure("TProgressbar", troughcolor=_BORDER, background=_ACCENT)

    def _build_ui(self) -> None:
        hdr = tk.Frame(self, bg=_ACCENT, height=48)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(
            hdr, text="Deep Search", font=_FONT_TITLE, fg="white", bg=_ACCENT,
        ).pack(side=tk.LEFT, padx=16, pady=10)

        main = ttk.Frame(self)
        main.pack(fill=tk.BOTH, expand=True, padx=12, pady=(12, 0))

        self._build_search_panel(main)
        self._build_result_area(main)
        self._build_status_bar(main)

        self.log_panel_visible = False
        self._build_log_panel(main)

    def _build_search_panel(self, parent: ttk.Frame) -> None:
        top = ttk.LabelFrame(parent, text=" Параметры поиска ", padding=12)
        top.pack(fill=tk.X)

        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="JSON сайтов:").grid(row=0, column=0, sticky="e", padx=(0, 8))
        site_frame = ttk.Frame(top)
        site_frame.grid(row=0, column=1, columnspan=2, sticky="ew")
        ttk.Entry(site_frame, textvariable=self.sites_path).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(site_frame, text="…", width=3, command=self._pick_sites_file).pack(side=tk.LEFT, padx=(4, 0))

        ttk.Label(top, text="Запрос:").grid(row=1, column=0, sticky="e", padx=(0, 8), pady=(10, 0))
        ttk.Entry(top, textvariable=self.query_var).grid(row=1, column=1, columnspan=2, sticky="ew", pady=(10, 0))

        ttk.Label(top, text="Regex:").grid(row=2, column=0, sticky="e", padx=(0, 8), pady=(8, 0))
        ttk.Entry(top, textvariable=self.regex_var).grid(row=2, column=1, columnspan=2, sticky="ew", pady=(8, 0))

        opt = ttk.Frame(top)
        opt.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 0))

        ttk.Label(opt, text="Результатов:").pack(side=tk.LEFT)
        ttk.Spinbox(opt, from_=1, to=100, textvariable=self.max_results_var, width=5).pack(side=tk.LEFT, padx=(4, 16))

        ttk.Label(opt, text="Timeout:").pack(side=tk.LEFT)
        ttk.Spinbox(opt, from_=3, to=120, textvariable=self.timeout_var, width=5).pack(side=tk.LEFT, padx=(4, 16))

        ttk.Label(opt, text="Workers:").pack(side=tk.LEFT)
        ttk.Spinbox(opt, from_=1, to=32, textvariable=self.workers_var, width=5).pack(side=tk.LEFT, padx=(4, 0))

        ttk.Button(opt, text="▶  Поиск", style="Accent.TButton", command=self._start_search).pack(side=tk.RIGHT)

        opt2 = ttk.Frame(top)
        opt2.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0))

        ttk.Checkbutton(opt2, text="Обходить ссылки", variable=self.follow_var).pack(side=tk.LEFT)
        ttk.Label(opt2, text="до").pack(side=tk.LEFT, padx=(4, 4))
        ttk.Spinbox(opt2, from_=1, to=20, textvariable=self.follow_limit_var, width=4).pack(side=tk.LEFT)
        ttk.Checkbutton(opt2, text="Playwright", variable=self.playwright_var).pack(side=tk.LEFT, padx=(16, 0))

    def _build_result_area(self, parent: ttk.Frame) -> None:
        self.pane = ttk.PanedWindow(parent, orient=tk.VERTICAL)
        self.pane.pack(fill=tk.BOTH, expand=True, pady=(10, 4))

        result_frame = ttk.Frame(self.pane)
        self.pane.add(result_frame, weight=3)

        self.text = tk.Text(
            result_frame, wrap=tk.WORD, cursor="arrow",
            font=_FONT_MONO, bg=_SURFACE, fg=_FG,
            relief="flat", borderwidth=0, padx=12, pady=8,
            selectbackground=_ACCENT, selectforeground="white",
        )
        scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.text.yview)
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.text.tag_configure("url", foreground=_ACCENT, underline=True)
        self.text.tag_bind("url", "<Button-1>", self._on_url_click)
        self.text.tag_bind("url", "<Enter>", lambda _e: self.text.configure(cursor="hand2"))
        self.text.tag_bind("url", "<Leave>", lambda _e: self.text.configure(cursor="arrow"))
        self.text.tag_configure("header", font=_FONT_BOLD, foreground=_ACCENT)
        self.text.tag_configure("match", foreground=_SUCCESS)
        self.text.tag_configure("error", foreground=_DANGER)

    def _build_status_bar(self, parent: ttk.Frame) -> None:
        bar = ttk.Frame(parent)
        bar.pack(fill=tk.X, pady=(0, 6))

        self.status_var = tk.StringVar(value="Готов")
        self.status_label = ttk.Label(bar, textvariable=self.status_var)
        self.status_label.pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=120)
        self.progress.pack(side=tk.LEFT, padx=(12, 0))

        ttk.Button(bar, text="Логи", width=5, command=self._toggle_log_panel).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(bar, text="↗ Все ссылки", command=self._open_all_links).pack(side=tk.RIGHT, padx=4)
        ttk.Button(bar, text="↗ Кандидаты", command=self._open_candidate_links).pack(side=tk.RIGHT)
        ttk.Button(bar, text="Кандидаты", command=self._show_candidates).pack(side=tk.RIGHT, padx=4)
        ttk.Button(bar, text="Все", command=self._show_all).pack(side=tk.RIGHT)
        ttk.Button(bar, text="💾 JSON", command=self._save_json).pack(side=tk.RIGHT, padx=(0, 12))

    def _build_log_panel(self, parent: ttk.Frame) -> None:
        self.log_frame = ttk.LabelFrame(parent, text=" Логи ", padding=4)

        log_toolbar = ttk.Frame(self.log_frame)
        log_toolbar.pack(fill=tk.X)
        ttk.Button(log_toolbar, text="Очистить", command=self._clear_log).pack(side=tk.RIGHT)

        self.log_text = tk.Text(
            self.log_frame, height=8, wrap=tk.WORD, state=tk.DISABLED,
            font=_FONT_MONO, bg="#1e1e2e", fg="#cdd6f4",
            relief="flat", borderwidth=0, padx=10, pady=6,
        )
        self.log_scroll = ttk.Scrollbar(self.log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=self.log_scroll.set)

        self.log_text.tag_configure("ERRO", foreground="#f38ba8")
        self.log_text.tag_configure("WARN", foreground="#fab387")
        self.log_text.tag_configure("INFO", foreground="#a6e3a1")
        self.log_text.tag_configure("DEBU", foreground="#6c7086")

    def _toggle_log_panel(self) -> None:
        if self.log_panel_visible:
            self.log_frame.pack_forget()
            self.log_text.pack_forget()
            self.log_scroll.pack_forget()
            self.log_panel_visible = False
        else:
            self.log_frame.pack(fill=tk.BOTH, before=self.status_label.master)
            self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=(4, 0))
            self.log_scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=(4, 0))
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
        level = record.levelname[:4]
        msg = record.getMessage()
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{level}] {msg}\n", (level,))
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _pick_sites_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите JSON", filetypes=[("JSON", "*.json"), ("All", "*.*")]
        )
        if path:
            self.sites_path.set(path)

    def _append(self, message: str, *tags: str) -> None:
        self.text.insert(tk.END, message, tags if tags else ())
        self.text.see(tk.END)

    def _on_url_click(self, event: tk.Event) -> None:
        index = self.text.index(f"@{event.x},{event.y}")
        for tag in self.text.tag_names(index):
            if tag == "url":
                url = self.text.get(f"{index} linestart", f"{index} lineend").strip()
                if url.startswith("http"):
                    webbrowser.open(url)
                return

    def _start_search(self) -> None:
        query = self.query_var.get().strip()
        if not query:
            messagebox.showerror("Ошибка", "Введите поисковый запрос")
            return

        regex_pattern = self.regex_var.get().strip()
        try:
            re.compile(regex_pattern)
        except re.error as e:
            messagebox.showerror("Ошибка regex", str(e))
            return

        self.text.delete("1.0", tk.END)
        self.status_var.set("Поиск выполняется…")
        self.progress.start(12)

        thread = threading.Thread(
            target=self._search_worker, args=(query, regex_pattern), daemon=True
        )
        thread.start()

    def _search_worker(self, query: str, regex_pattern: str) -> None:
        try:
            sites = load_sites_config(self.sites_path.get())
            req = SearchRequest(
                query=query,
                regex_pattern=regex_pattern,
                max_results=max(1, int(self.max_results_var.get())),
                timeout_sec=max(3, int(self.timeout_var.get())),
                follow_links=self.follow_var.get(),
                follow_limit=max(1, int(self.follow_limit_var.get())),
                use_playwright=self.playwright_var.get(),
            )

            def progress(msg: str) -> None:
                self.after(0, self._append, f"  [ok] {msg}\n")

            results = deep_search(
                sites=sites,
                req=req,
                max_workers=max(1, int(self.workers_var.get())),
                progress_callback=progress,
            )

            candidates = filter_candidates(results)
            self.latest_results = results
            self.latest_candidates = candidates

            self.after(0, self._render_results, results, candidates)
        except Exception as e:
            self.after(0, self._on_error, str(e))

    def _render_results(self, results: dict, candidates: dict) -> None:
        self.progress.stop()
        total_urls = sum(len(r.urls) for r in results.values())
        self.status_var.set(
            f"Готово — кандидатов: {len(candidates)}/{len(results)}, ссылок: {total_urls}"
        )

        for site, data in results.items():
            self._append("\n")
            self.text.insert(tk.END, "─" * 90 + "\n")

            status_icon = "✓" if data.found else "✗"
            status_color = "match" if data.found else "error"
            self.text.insert(tk.END, f"  {status_icon}  ", (status_color,))
            self.text.insert(tk.END, site.upper(), ("header",))
            self._append(f"  | {data.elapsed_sec:.2f}s  |  status={data.status_code}")

            if data.error:
                self._append(f"  Ошибка: {data.error}", "error")
                continue

            if not data.found:
                self._append("  Ничего не найдено")
                continue

            if data.matches:
                self._append(f"  Совпадений: {len(data.matches)}")
                for i, m in enumerate(data.matches[:5], 1):
                    self._append(f"    {i}. {m.text}")

            if data.urls:
                self._append(f"  Ссылки ({len(data.urls)}):")
                for i, u in enumerate(data.urls, 1):
                    self._append(f"    {i}. ", )
                    self._append_url(u)
                    self._append("")

    def _append_url(self, url: str) -> None:
        start = self.text.index("end-1c")
        self.text.insert(tk.END, url)
        end = self.text.index("end-1c")
        self.text.tag_add("url", start, end)

    def _on_error(self, error_text: str) -> None:
        self.progress.stop()
        self.status_var.set("Ошибка")
        messagebox.showerror("Ошибка", error_text)

    def _save_json(self) -> None:
        if not self.latest_results:
            messagebox.showwarning("Нет данных", "Сначала выполните поиск")
            return

        path = filedialog.asksaveasfilename(
            title="Сохранить результаты",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile="search_results.json",
        )
        if not path:
            return

        saved = save_results_json(self.latest_results, path)
        messagebox.showinfo("Сохранено", f"Результаты сохранены:\n{saved}")

    def _show_candidates(self) -> None:
        self.text.delete("1.0", tk.END)
        if not self.latest_candidates:
            self._append("Кандидатов нет")
            return
        self._render_results(self.latest_candidates, self.latest_candidates)

    def _show_all(self) -> None:
        self.text.delete("1.0", tk.END)
        if not self.latest_results:
            self._append("Результатов нет")
            return
        self._render_results(self.latest_results, self.latest_candidates)

    def _open_all_links(self) -> None:
        self._open_links(self.latest_results)

    def _open_candidate_links(self) -> None:
        self._open_links(self.latest_candidates)

    def _open_links(self, results: dict) -> None:
        if not results:
            messagebox.showwarning("Нет данных", "Сначала выполните поиск")
            return

        opened = 0
        for _site, data in results.items():
            if not data.urls:
                continue
            for url in data.urls:
                webbrowser.open(url)
                opened += 1
                _time.sleep(0.3)

        if opened == 0:
            messagebox.showinfo("Нет ссылок", "Ссылок для открытия не найдено")
        else:
            self.status_var.set(f"Открыто ссылок: {opened}")


def run_gui() -> None:
    app = DeepSearchApp()
    app.mainloop()
