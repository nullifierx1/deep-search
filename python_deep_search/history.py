from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path


class SearchHistory:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS search_jobs (
                    id TEXT PRIMARY KEY, created_at REAL NOT NULL, status TEXT NOT NULL, snapshot TEXT NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS search_jobs_created ON search_jobs(created_at DESC, id DESC)")
            unfinished = db.execute(
                "SELECT snapshot FROM search_jobs WHERE status IN ('running', 'cancelling')"
            ).fetchall()
            for (encoded,) in unfinished:
                snapshot = json.loads(encoded)
                snapshot["status"] = "interrupted"
                for progress in snapshot["site_progress"].values():
                    if progress["stage"] != "finished":
                        progress.update(stage="finished", reason="interrupted")
                snapshot["finished_sites"] = snapshot["total_sites"]
                self._write(db, snapshot)

    @staticmethod
    def _write(db: sqlite3.Connection, snapshot: dict) -> None:
        db.execute("""
            INSERT INTO search_jobs (id, created_at, status, snapshot) VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET status = excluded.status, snapshot = excluded.snapshot
        """, (snapshot["id"], snapshot["created_at"], snapshot["status"], json.dumps(snapshot, ensure_ascii=False)))

    def save(self, snapshot: dict) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            self._write(db, snapshot)

    def get(self, job_id: str) -> dict | None:
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT snapshot FROM search_jobs WHERE id = ?", (job_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, limit: int, offset: int) -> list[dict]:
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute(
                "SELECT snapshot FROM search_jobs ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        snapshots = [json.loads(row[0]) for row in rows]
        return [{key: snapshot[key] for key in (
            "id", "status", "created_at", "request", "total_sites", "finished_sites",
        )} for snapshot in snapshots]
