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

                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    preview TEXT NOT NULL,
                    messages_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS reports (
                    report_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    report_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT,
                    profile_tags_json TEXT NOT NULL,
                    items_json TEXT NOT NULL,
                    error_message TEXT,
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

    def create_conversation(self, user_id: str) -> dict[str, Any]:
        conversation = {
            "conversation_id": str(uuid.uuid4()),
            "user_id": user_id,
            "title": "New health chat",
            "preview": "",
            "messages": [],
            "updated_at": utc_now(),
            "created_at": utc_now(),
        }
        with self._lock:
            self._connect().execute(
                """
                INSERT INTO conversations (
                    conversation_id, user_id, title, preview, messages_json, updated_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation["conversation_id"],
                    user_id,
                    conversation["title"],
                    conversation["preview"],
                    json.dumps(conversation["messages"], ensure_ascii=False),
                    conversation["updated_at"],
                    conversation["created_at"],
                ),
            )
            self._connect().commit()
        return conversation

    def list_conversations(self, user_id: str) -> list[dict[str, Any]]:
        rows = self._connect().execute(
            "SELECT * FROM conversations WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
        return [self._row_to_conversation(row) for row in rows]

    def get_conversation(self, user_id: str, conversation_id: str) -> dict[str, Any] | None:
        row = self._connect().execute(
            "SELECT * FROM conversations WHERE user_id = ? AND conversation_id = ?",
            (user_id, conversation_id),
        ).fetchone()
        return self._row_to_conversation(row) if row else None

    def update_conversation(self, user_id: str, conversation: dict[str, Any]) -> None:
        with self._lock:
            self._connect().execute(
                """
                UPDATE conversations
                SET title = ?, preview = ?, messages_json = ?, updated_at = ?
                WHERE user_id = ? AND conversation_id = ?
                """,
                (
                    conversation["title"],
                    conversation["preview"],
                    json.dumps(conversation["messages"], ensure_ascii=False),
                    conversation["updated_at"],
                    user_id,
                    conversation["conversation_id"],
                ),
            )
            self._connect().commit()

    def _row_to_conversation(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["messages"] = json.loads(item.pop("messages_json"))
        return item

    def add_report(
        self,
        user_id: str,
        report_id: str,
        file_name: str,
        report_type: str,
        status: str,
        summary: str | None,
        profile_tags: list[str],
        items: list[dict[str, Any]],
        error_message: str | None = None,
    ) -> str:
        created_at = utc_now()
        with self._lock:
            self._connect().execute(
                """
                INSERT INTO reports (
                    report_id, user_id, file_name, report_type, status, summary,
                    profile_tags_json, items_json, error_message, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    user_id,
                    file_name,
                    report_type,
                    status,
                    summary,
                    json.dumps(profile_tags, ensure_ascii=False),
                    json.dumps(items, ensure_ascii=False),
                    error_message,
                    created_at,
                ),
            )
            self._connect().commit()
        return created_at

    def list_reports(self, user_id: str) -> list[dict[str, Any]]:
        rows = self._connect().execute(
            "SELECT * FROM reports WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [self._row_to_report(row) for row in rows]

    def get_report(self, user_id: str, report_id: str) -> dict[str, Any] | None:
        row = self._connect().execute(
            "SELECT * FROM reports WHERE user_id = ? AND report_id = ?",
            (user_id, report_id),
        ).fetchone()
        return self._row_to_report(row) if row else None

    def update_report(
        self,
        user_id: str,
        report_id: str,
        *,
        status: str | None = None,
        summary: str | None = None,
        items: list[dict[str, Any]] | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any] | None:
        report = self.get_report(user_id, report_id)
        if report is None:
            return None
        report["status"] = status or report["status"]
        report["summary"] = summary if summary is not None else report.get("summary")
        report["items"] = items if items is not None else report["items"]
        report["error_message"] = error_message
        with self._lock:
            self._connect().execute(
                """
                UPDATE reports
                SET status = ?, summary = ?, items_json = ?, error_message = ?
                WHERE user_id = ? AND report_id = ?
                """,
                (
                    report["status"],
                    report["summary"],
                    json.dumps(report["items"], ensure_ascii=False),
                    report["error_message"],
                    user_id,
                    report_id,
                ),
            )
            self._connect().commit()
        return report

    def delete_report(self, user_id: str, report_id: str) -> bool:
        with self._lock:
            cursor = self._connect().execute(
                "DELETE FROM reports WHERE user_id = ? AND report_id = ?",
                (user_id, report_id),
            )
            self._connect().commit()
        return cursor.rowcount > 0

    def _row_to_report(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["items"] = json.loads(item.pop("items_json"))
        item["profile_tags_used"] = json.loads(item.pop("profile_tags_json"))
        return item

    def add_audit_log(self, user_id: str | None, action: str, detail: dict[str, Any]) -> None:
        with self._lock:
            self._connect().execute(
                "INSERT INTO audit_logs (id, user_id, action, detail_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), user_id, action, json.dumps(detail, ensure_ascii=False), utc_now()),
            )
            self._connect().commit()
