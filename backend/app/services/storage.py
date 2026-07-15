import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, database_path: Path, seed_knowledge_path: Path) -> None:
        self.database_path = database_path
        self.seed_knowledge_path = seed_knowledge_path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        with self._lock:
            conn = self._connect()
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS profiles (
                    user_id TEXT PRIMARY KEY,
                    profile_json TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    article_title TEXT NOT NULL,
                    section_title TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    version_label TEXT,
                    revised_at TEXT,
                    author TEXT,
                    reviewer TEXT,
                    content_hash TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reports (
                    report_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    report_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    items_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS audit_logs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    action TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._seed_knowledge_if_empty(conn)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.database_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _seed_knowledge_if_empty(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT COUNT(*) AS count FROM knowledge_chunks").fetchone()
        if row["count"] > 0 or not self.seed_knowledge_path.exists():
            return
        chunks = json.loads(self.seed_knowledge_path.read_text(encoding="utf-8"))
        for chunk in chunks:
            conn.execute(
                """
                INSERT INTO knowledge_chunks (
                    chunk_id, article_title, section_title, source_url, category,
                    content, tags_json, version_label, revised_at, author, reviewer,
                    content_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk["chunk_id"],
                    chunk["article_title"],
                    chunk["section_title"],
                    chunk["source_url"],
                    chunk["category"],
                    chunk["content"],
                    json.dumps(chunk.get("tags", []), ensure_ascii=False),
                    chunk.get("version_label"),
                    chunk.get("revised_at"),
                    chunk.get("author"),
                    chunk.get("reviewer"),
                    chunk.get("content_hash"),
                    utc_now(),
                ),
            )

    def create_user(self, email: str, password_hash: str) -> dict[str, Any] | None:
        user_id = str(uuid.uuid4())
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO users (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                    (user_id, email, password_hash, utc_now()),
                )
            except sqlite3.IntegrityError:
                return None
            conn.commit()
        return self.get_user_by_id(user_id)

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        row = self._connect().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        row = self._connect().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def upsert_profile(self, user_id: str, profile: dict[str, Any], tags: list[str]) -> None:
        with self._lock:
            self._connect().execute(
                """
                INSERT INTO profiles (user_id, profile_json, tags_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    profile_json = excluded.profile_json,
                    tags_json = excluded.tags_json,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    json.dumps(profile, ensure_ascii=False),
                    json.dumps(tags, ensure_ascii=False),
                    utc_now(),
                ),
            )
            self._connect().commit()

    def get_profile(self, user_id: str) -> tuple[dict[str, Any] | None, list[str]]:
        row = self._connect().execute("SELECT * FROM profiles WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            return None, []
        return json.loads(row["profile_json"]), json.loads(row["tags_json"])

    def list_knowledge_chunks(self) -> list[dict[str, Any]]:
        rows = self._connect().execute("SELECT * FROM knowledge_chunks").fetchall()
        chunks: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["tags"] = json.loads(item.pop("tags_json"))
            chunks.append(item)
        return chunks

    def add_report(
        self,
        user_id: str,
        report_id: str,
        file_name: str,
        report_type: str,
        status: str,
        summary: str,
        items: list[dict[str, Any]],
    ) -> None:
        with self._lock:
            self._connect().execute(
                """
                INSERT INTO reports (
                    report_id, user_id, file_name, report_type, status,
                    summary, items_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    user_id,
                    file_name,
                    report_type,
                    status,
                    summary,
                    json.dumps(items, ensure_ascii=False),
                    utc_now(),
                ),
            )
            self._connect().commit()

    def get_report(self, user_id: str, report_id: str) -> dict[str, Any] | None:
        row = self._connect().execute(
            "SELECT * FROM reports WHERE user_id = ? AND report_id = ?",
            (user_id, report_id),
        ).fetchone()
        if row is None:
            return None
        report = dict(row)
        report["items"] = json.loads(report.pop("items_json"))
        return report

    def add_audit_log(self, user_id: str | None, action: str, detail: dict[str, Any]) -> None:
        with self._lock:
            self._connect().execute(
                "INSERT INTO audit_logs (id, user_id, action, detail_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), user_id, action, json.dumps(detail, ensure_ascii=False), utc_now()),
            )
            self._connect().commit()
