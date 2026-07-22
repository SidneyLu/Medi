from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ApplicationRepository:
    """PostgreSQL repository for account, profile, chat, report, and audit data."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def initialize(self) -> None:
        schema_path = Path(__file__).resolve().parents[2] / "sql" / "application_schema.sql"
        with self._connect() as conn:
            conn.execute(schema_path.read_text(encoding="utf-8"))

    def create_user(self, email: str, password_hash: str) -> dict[str, Any] | None:
        user_id = str(uuid.uuid4())
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    INSERT INTO medi_users (id, email, password_hash, created_at)
                    VALUES (%s, %s, %s, %s)
                    RETURNING *
                    """,
                    (user_id, email, password_hash, utc_now()),
                ).fetchone()
        except psycopg.errors.UniqueViolation:
            return None
        return _row_to_user(row) if row else None

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM medi_users WHERE email = %s", (email,)).fetchone()
        return _row_to_user(row) if row else None

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM medi_users WHERE id = %s", (user_id,)).fetchone()
        return _row_to_user(row) if row else None

    def upsert_profile(self, user_id: str, profile: dict[str, Any], tags: list[str]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO medi_profiles (user_id, profile_json, tags_json, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    profile_json = EXCLUDED.profile_json,
                    tags_json = EXCLUDED.tags_json,
                    updated_at = EXCLUDED.updated_at
                """,
                (user_id, Json(profile), Json(tags), utc_now()),
            )

    def get_profile(self, user_id: str) -> tuple[dict[str, Any] | None, list[str]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM medi_profiles WHERE user_id = %s", (user_id,)).fetchone()
        if row is None:
            return None, []
        return _json_dict(row["profile_json"]), _json_list(row["tags_json"])

    def create_conversation(self, user_id: str) -> dict[str, Any]:
        now = utc_now()
        conversation = {
            "conversation_id": str(uuid.uuid4()),
            "user_id": user_id,
            "title": "New health chat",
            "preview": "",
            "messages": [],
            "updated_at": now,
            "created_at": now,
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO medi_conversations (
                    conversation_id, user_id, title, preview, messages_json, updated_at, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    conversation["conversation_id"],
                    user_id,
                    conversation["title"],
                    conversation["preview"],
                    Json(conversation["messages"]),
                    conversation["updated_at"],
                    conversation["created_at"],
                ),
            )
        return conversation

    def list_conversations(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM medi_conversations WHERE user_id = %s ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        return [_row_to_conversation(row) for row in rows]

    def get_conversation(self, user_id: str, conversation_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM medi_conversations WHERE user_id = %s AND conversation_id = %s",
                (user_id, conversation_id),
            ).fetchone()
        return _row_to_conversation(row) if row else None

    def update_conversation(self, user_id: str, conversation: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE medi_conversations
                SET title = %s, preview = %s, messages_json = %s, updated_at = %s
                WHERE user_id = %s AND conversation_id = %s
                """,
                (
                    conversation["title"],
                    conversation["preview"],
                    Json(conversation["messages"]),
                    conversation["updated_at"],
                    user_id,
                    conversation["conversation_id"],
                ),
            )

    def add_report(
        self,
        *,
        user_id: str,
        report_id: str,
        file_name: str,
        report_type: str,
        status: str,
        summary: str | None,
        profile_tags: list[str],
        items: list[dict[str, Any]],
        stored_file_name: str | None = None,
        raw_text: str | None = None,
        error_message: str | None = None,
    ) -> str:
        created_at = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO medi_reports (
                    report_id, user_id, file_name, stored_file_name, report_type, status,
                    summary, profile_tags_json, items_json, raw_text, error_message,
                    created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    report_id,
                    user_id,
                    file_name,
                    stored_file_name,
                    report_type,
                    status,
                    summary,
                    Json(profile_tags),
                    Json(items),
                    raw_text,
                    error_message,
                    created_at,
                    created_at,
                ),
            )
        return created_at

    def list_reports(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM medi_reports WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [_row_to_report(row) for row in rows]

    def get_report(self, user_id: str, report_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM medi_reports WHERE user_id = %s AND report_id = %s",
                (user_id, report_id),
            ).fetchone()
        return _row_to_report(row) if row else None

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
        with self._connect() as conn:
            row = conn.execute(
                """
                UPDATE medi_reports
                SET status = %s, summary = %s, items_json = %s, error_message = %s, updated_at = %s
                WHERE user_id = %s AND report_id = %s
                RETURNING *
                """,
                (
                    report["status"],
                    report["summary"],
                    Json(report["items"]),
                    report["error_message"],
                    utc_now(),
                    user_id,
                    report_id,
                ),
            ).fetchone()
        return _row_to_report(row) if row else None

    def delete_report(self, user_id: str, report_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM medi_reports WHERE user_id = %s AND report_id = %s",
                (user_id, report_id),
            )
        return bool(cursor.rowcount)

    def add_audit_log(self, user_id: str | None, action: str, detail: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO medi_audit_logs (id, user_id, action, detail_json, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (str(uuid.uuid4()), user_id, action, Json(detail), utc_now()),
            )


def _as_iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        loaded = json.loads(value)
        return loaded if isinstance(loaded, list) else []
    return []


def _row_to_user(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["id"] = str(item["id"])
    item["created_at"] = _as_iso(item["created_at"])
    return item


def _row_to_conversation(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["conversation_id"] = str(item["conversation_id"])
    item["user_id"] = str(item["user_id"])
    item["messages"] = _json_list(item.pop("messages_json"))
    item["updated_at"] = _as_iso(item["updated_at"])
    item["created_at"] = _as_iso(item["created_at"])
    return item


def _row_to_report(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["report_id"] = str(item["report_id"])
    item["user_id"] = str(item["user_id"])
    item["items"] = _json_list(item.pop("items_json"))
    item["profile_tags_used"] = _json_list(item.pop("profile_tags_json"))
    item["created_at"] = _as_iso(item["created_at"])
    item["updated_at"] = _as_iso(item["updated_at"])
    return item
