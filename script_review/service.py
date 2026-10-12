from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
import re
import sqlite3
from typing import Callable, Iterator
from uuid import uuid4
from zoneinfo import ZoneInfo


BRAND_TIMEZONE = ZoneInfo("America/Sao_Paulo")
PENDING_REVIEW = "pending_review"
CHANGES_REQUESTED = "changes_requested"
APPROVED = "approved"


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class ScriptReviewService:
    """Owns state transitions and persists each write in one SQLite transaction."""

    def __init__(
        self,
        database_path: str | Path,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def create_script(self, creator_id: object, content: object) -> dict[str, object]:
        creator = self._required_text(creator_id, "creator_id")
        script_content = self._required_content(content)
        script_id = str(uuid4())

        with self._write_transaction() as connection:
            now = self._now()
            timestamp = self._timestamp(now)
            connection.execute(
                """INSERT INTO scripts
                   (id, creator_id, state, current_version, created_at, updated_at)
                   VALUES (?, ?, ?, 1, ?, ?)""",
                (script_id, creator, PENDING_REVIEW, timestamp, timestamp),
            )
            connection.execute(
                """INSERT INTO script_versions (script_id, version, content, created_at)
                   VALUES (?, 1, ?, ?)""",
                (script_id, script_content, timestamp),
            )
            return self._load_script(connection, script_id, now)

    def get_script(self, script_id: str) -> dict[str, object]:
        with self._read_connection() as connection:
            now = self._now()
            return self._load_script(connection, script_id, now)

    def review_script(
        self,
        script_id: str,
        decision: object,
        reason: object = None,
        deadline_date: object = None,
    ) -> dict[str, object]:
        if decision not in (APPROVED, CHANGES_REQUESTED):
            raise ApiError(400, "invalid_decision", "decision must be approved or changes_requested")

        review_reason: str | None = None
        due_date: date | None = None
        if decision == CHANGES_REQUESTED:
            review_reason = self._required_text(reason, "reason")
            due_date = self._parse_date(deadline_date)

        due_value = due_date.isoformat() if due_date is not None else None
        next_state = APPROVED if decision == APPROVED else CHANGES_REQUESTED

        with self._write_transaction() as connection:
            script = self._script_row(connection, script_id)
            if script["state"] != PENDING_REVIEW:
                raise ApiError(409, "invalid_state", "Only a pending_review script can be reviewed")
            now = self._now()
            if due_date is not None and due_date < now.astimezone(BRAND_TIMEZONE).date():
                raise ApiError(400, "deadline_in_past", "deadline_date cannot be before today's date in America/Sao_Paulo")
            timestamp = self._timestamp(now)

            connection.execute(
                """INSERT INTO review_events
                   (script_id, version, decision, reason, deadline_date, reviewed_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (script_id, script["current_version"], decision, review_reason, due_value, timestamp),
            )
            connection.execute(
                """UPDATE scripts
                   SET state = ?, change_reason = ?, deadline_date = ?, approved_at = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    next_state,
                    review_reason if decision == CHANGES_REQUESTED else None,
                    due_value,
                    timestamp if decision == APPROVED else None,
                    timestamp,
                    script_id,
                ),
            )
            return self._load_script(connection, script_id, now)

    def create_version(self, script_id: str, content: object) -> dict[str, object]:
        script_content = self._required_content(content)

        with self._write_transaction() as connection:
            script = self._script_row(connection, script_id)
            if script["state"] != CHANGES_REQUESTED:
                raise ApiError(409, "invalid_state", "A new version requires an open change request")
            now = self._now()
            if now.astimezone(BRAND_TIMEZONE).date() > date.fromisoformat(script["deadline_date"]):
                raise ApiError(409, "deadline_expired", "The change request deadline has passed")

            timestamp = self._timestamp(now)
            version = script["current_version"] + 1
            connection.execute(
                """INSERT INTO script_versions (script_id, version, content, created_at)
                   VALUES (?, ?, ?, ?)""",
                (script_id, version, script_content, timestamp),
            )
            connection.execute(
                """UPDATE scripts
                   SET state = ?, current_version = ?, change_reason = NULL,
                       deadline_date = NULL, updated_at = ?
                   WHERE id = ?""",
                (PENDING_REVIEW, version, timestamp, script_id),
            )
            return self._load_script(connection, script_id, now)

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS scripts (
                    id TEXT PRIMARY KEY,
                    creator_id TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('pending_review', 'changes_requested', 'approved')),
                    current_version INTEGER NOT NULL CHECK (current_version > 0),
                    change_reason TEXT,
                    deadline_date TEXT,
                    approved_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (
                        (state = 'changes_requested' AND change_reason IS NOT NULL AND deadline_date IS NOT NULL)
                        OR (state != 'changes_requested' AND change_reason IS NULL AND deadline_date IS NULL)
                    ),
                    CHECK ((state = 'approved' AND approved_at IS NOT NULL) OR state != 'approved')
                );
                CREATE TABLE IF NOT EXISTS script_versions (
                    script_id TEXT NOT NULL REFERENCES scripts(id),
                    version INTEGER NOT NULL CHECK (version > 0),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (script_id, version)
                );
                CREATE TABLE IF NOT EXISTS review_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    script_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    decision TEXT NOT NULL CHECK (decision IN ('approved', 'changes_requested')),
                    reason TEXT,
                    deadline_date TEXT,
                    reviewed_at TEXT NOT NULL,
                    FOREIGN KEY (script_id, version) REFERENCES script_versions(script_id, version),
                    CHECK (
                        (decision = 'changes_requested' AND reason IS NOT NULL AND deadline_date IS NOT NULL)
                        OR (decision = 'approved' AND reason IS NULL AND deadline_date IS NULL)
                    )
                );
                CREATE INDEX IF NOT EXISTS review_events_script_idx
                    ON review_events (script_id, id);
                """
            )
        finally:
            connection.close()

    @contextmanager
    def _write_transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def _read_connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _script_row(self, connection: sqlite3.Connection, script_id: str) -> sqlite3.Row:
        self._validate_unicode(script_id, "script_id")
        row = connection.execute("SELECT * FROM scripts WHERE id = ?", (script_id,)).fetchone()
        if row is None:
            raise ApiError(404, "script_not_found", "Script not found")
        return row

    def _load_script(
        self,
        connection: sqlite3.Connection,
        script_id: str,
        now: datetime,
    ) -> dict[str, object]:
        script = self._script_row(connection, script_id)
        versions = connection.execute(
            """SELECT version, content, created_at FROM script_versions
               WHERE script_id = ? ORDER BY version""",
            (script_id,),
        ).fetchall()
        reviews = connection.execute(
            """SELECT version, decision, reason, deadline_date, reviewed_at FROM review_events
               WHERE script_id = ? ORDER BY id""",
            (script_id,),
        ).fetchall()
        version_states = {review["version"]: review["decision"] for review in reviews}

        change_request = None
        if script["state"] == CHANGES_REQUESTED:
            deadline = date.fromisoformat(script["deadline_date"])
            status = "open" if now.astimezone(BRAND_TIMEZONE).date() <= deadline else "expired"
            change_request = {
                "reason": script["change_reason"],
                "deadline_date": script["deadline_date"],
                "status": status,
            }

        return {
            "id": script["id"],
            "creator_id": script["creator_id"],
            "state": script["state"],
            "current_version": script["current_version"],
            "created_at": script["created_at"],
            "updated_at": script["updated_at"],
            "approved_at": script["approved_at"],
            "change_request": change_request,
            "versions": [
                dict(version, state=version_states.get(version["version"], PENDING_REVIEW))
                for version in versions
            ],
            "reviews": [dict(review) for review in reviews],
        }

    def _now(self) -> datetime:
        current = self.clock()
        if not isinstance(current, datetime) or current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("clock must return an aware datetime")
        return current

    @staticmethod
    def _timestamp(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

    @staticmethod
    def _required_text(value: object, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ApiError(400, "invalid_" + field, field + " must be a non-empty string")
        ScriptReviewService._validate_unicode(value, field)
        return value.strip()

    @staticmethod
    def _required_content(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ApiError(400, "invalid_content", "content must be a non-empty string")
        ScriptReviewService._validate_unicode(value, "content")
        return value

    @staticmethod
    def _validate_unicode(value: str, field: str) -> None:
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as error:
            raise ApiError(400, "invalid_" + field, field + " must contain valid Unicode") from error

    @staticmethod
    def _parse_date(value: object) -> date:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ApiError(400, "invalid_deadline_date", "deadline_date must use YYYY-MM-DD")
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise ApiError(400, "invalid_deadline_date", "deadline_date is not a calendar date") from error
