from __future__ import annotations

import re
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .config import load_sites_config
from .models import SearchRequest
from .output import save_results_json
from .search_engine import deep_search, filter_candidates


class DeepSearchApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Deep Search (Python)")
        self.geometry("1000x700")
        self.minsize(900, 600)

        self.sites_path = tk.StringVar(value="python_deep_search/sites.json")
        self.query_var = tk.StringVar()
        self.regex_var = tk.StringVar(value=r"\b\w+\b")
        self.max_results_var = tk.IntVar(value=10)
        self.timeout_var = tk.IntVar(value=15)
        self.workers_var = tk.IntVar(value=6)
        self.follow_var = tk.BooleanVar(value=True)
        self.follow_limit_var = tk.IntVar(value=5)
        self.playwright_var = tk.BooleanVar(value=True)

        self.latest_results = {}
        self.latest_candidates = {}

        self._build_ui()

    def _build_ui(self) -> None:
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        top = ttk.LabelFrame(frm, text="Параметры поиска", padding=10)
        top.pack(fill=tk.X)

        ttk.Label(top, text="JSON сайтов:").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.sites_path, width=70).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(top, text="Выбрать", command=self._pick_sites_file).grid(row=0, column=2)

        ttk.Label(top, text="Запрос:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(top, textvariable=self.query_var, width=70).grid(row=1, column=1, columnspan=2, sticky="ew", padx=6, pady=(8, 0))

        ttk.Label(top, text="Regex:").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(top, textvariable=self.regex_var, width=70).grid(row=2, column=1, columnspan=2, sticky="ew", padx=6, pady=(8, 0))

        opt = ttk.Frame(top)
        opt.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        ttk.Label(opt, text="Max results:").pack(side=tk.LEFT)
        ttk.Spinbox(opt, from_=1, to=100, textvariable=self.max_results_var, width=6).pack(side=tk.LEFT, padx=(6, 12))

        ttk.Label(opt, text="Timeout:").pack(side=tk.LEFT)
        ttk.Spinbox(opt, from_=3, to=120, textvariable=self.timeout_var, width=6).pack(side=tk.LEFT, padx=(6, 12))

        ttk.Label(opt, text="Workers:").pack(side=tk.LEFT)
        ttk.Spinbox(opt, from_=1, to=32, textvariable=self.workers_var, width=6).pack(side=tk.LEFT, padx=(6, 12))

        ttk.Button(opt, text="Запустить поиск", command=self._start_search).pack(side=tk.RIGHT)

        opt2 = ttk.Frame(top)
        opt2.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(6, 0))

        ttk.Checkbutton(opt2, text="Переходить по ссылкам", variable=self.follow_var).pack(side=tk.LEFT)
        ttk.Label(opt2, text="Лимит:").pack(side=tk.LEFT, padx=(2, 0))
        ttk.Spinbox(opt2, from_=1, to=20, textvariable=self.follow_limit_var, width=4).pack(side=tk.LEFT, padx=(2, 12))
        ttk.Checkbutton(opt2, text="Playwright (JS-сайты)", variable=self.playwright_var).pack(side=tk.LEFT)

        top.columnconfigure(1, weight=1)

        mid = ttk.Frame(frm)
        mid.pack(fill=tk.BOTH, expand=True, pady=10)

        self.status_var = tk.StringVar(value="Готово")
        ttk.Label(mid, textvariable=self.status_var).pack(anchor="w")

        self.progress = ttk.Progressbar(mid, mode="indeterminate")
        self.progress.pack(fill=tk.X, pady=(2, 8))

        self.text = tk.Text(mid, wrap=tk.WORD, cursor="arrow")
        self.text.pack(fill=tk.BOTH, expand=True)

        self.text.tag_configure("url", foreground="blue", underline=True)
        self.text.tag_bind("url", "<Button-1>", self._on_url_click)
        self.text.tag_bind("url", "<Enter>", lambda _e: self.text.configure(cursor="hand2"))
        self.text.tag_bind("url", "<Leave>", lambda _e: self.text.configure(cursor="arrow"))

        bottom = ttk.Frame(frm)
        bottom.pack(fill=tk.X)

        ttk.Button(bottom, text="Сохранить JSON", command=self._save_json).pack(side=tk.LEFT)
        ttk.Button(bottom, text="Показать только кандидатов", command=self._show_candidates).pack(side=tk.LEFT, padx=8)
        ttk.Button(bottom, text="Показать все", command=self._show_all).pack(side=tk.LEFT)
        ttk.Button(bottom, text="Открыть все ссылки", command=self._open_all_links).pack(side=tk.RIGHT, padx=4)
        ttk.Button(bottom, text="Открыть ссылки кандидатов", command=self._open_candidate_links).pack(side=tk.RIGHT)

    def _pick_sites_file(self) -> None:
        path = filedialog.askopenfilename(title="Выберите JSON", filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if path:
            self.sites_path.set(path)

    def _append(self, message: str) -> None:
        self.text.insert(tk.END, message + "\n")
        self.text.see(tk.END)

    def _append_url(self, url: str) -> None:
        start = self.text.index("end-1c")
        self.text.insert(tk.END, url)
        end = self.text.index("end-1c")
        self.text.tag_add("url", start, end)

    def _on_url_click(self, event: tk.Event) -> None:
        index = self.text.index(f"@{event.x},{event.y}")
        for tag in self.text.tag_names(index):
            if tag == "url":
                url = self.text.get(f"{index} linestart", f"{index} lineend")
                url = url.strip()
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
        self.status_var.set("Поиск выполняется...")
        self.progress.start(10)

        thread = threading.Thread(target=self._search_worker, args=(query, regex_pattern), daemon=True)
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
                self.after(0, self._append, f"[done] {msg}")

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
        self.status_var.set(f"Готово. Кандидатов: {len(candidates)} / {len(results)}")

        for site, data in results.items():
            self.text.tag_configure(site + "_bold", font=("TkDefaultFont", 10, "bold"))
            self._append("")
            self.text.insert(tk.END, "─" * 70 + "\n")
            self.text.insert(tk.END, f"  {site.upper()}  ", (site + "_bold",))
            self._append(f"| status={data.status_code} | {data.elapsed_sec:.2f}s")

            if data.error:
                self._append(f"  Ошибка: {data.error}")
                continue

            if not data.found:
                self._append("  Ничего не найдено")
                continue

            self._append(f"  Совпадений: {len(data.matches)}")
            for i, m in enumerate(data.matches[:5], 1):
                self._append(f"    {i}. {m.text}")

            if data.urls:
                self._append(f"  Ссылки ({len(data.urls)}):")
                for i, u in enumerate(data.urls, 1):
                    self.text.insert(tk.END, f"    {i}. ")
                    self._append_url(u)
                    self._append("")

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
        for site, data in results.items():
            if not data.urls:
                continue
            for url in data.urls[:3]:
                webbrowser.open(url)
                opened += 1

        if opened == 0:
            messagebox.showinfo("Нет ссылок", "Ссылок для открытия не найдено")
        else:
            self.status_var.set(f"Открыто ссылок: {opened}")


def run_gui() -> None:
    app = DeepSearchApp()
    app.mainloop()
