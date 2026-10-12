"""SQLite access: one connection per thread, WAL mode, explicit transactions."""
from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._local = threading.local()
        self._all: list[sqlite3.Connection] = []
        self._lock = threading.Lock()

    def connect(self) -> sqlite3.Connection:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA busy_timeout = 10000")
            self._local.conn = conn
            self._local.depth = 0
            with self._lock:
                self._all.append(conn)
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Re-entrant: nested calls join the outer transaction."""
        conn = self.connect()
        depth = self._local.depth
        if depth == 0:
            conn.execute("BEGIN IMMEDIATE")
        self._local.depth = depth + 1
        try:
            yield conn
        except BaseException:
            self._local.depth = depth
            if depth == 0:
                conn.execute("ROLLBACK")
            raise
        else:
            self._local.depth = depth
            if depth == 0:
                conn.execute("COMMIT")

    def query(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        return self.connect().execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        return self.connect().execute(sql, params).fetchone()

    def scalar(self, sql: str, params: tuple | dict = ()) -> Any:
        row = self.connect().execute(sql, params).fetchone()
        return row[0] if row else None

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        return self.connect().execute(sql, params)

    def close(self) -> None:
        with self._lock:
            for conn in self._all:
                try:
                    conn.close()
                except sqlite3.ProgrammingError:
                    pass  # closed from its own thread already
            self._all.clear()
        self._local = threading.local()
