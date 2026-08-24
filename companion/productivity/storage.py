# -*- coding: utf-8 -*-
# Copyright 2025-2026 Project N.E.K.O. Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""SQLite persistence for companion productivity data (Phase 2).

Stores todos and memos in a single SQLite database so they survive
restarts. The store is thread-safe: FastAPI may serve requests from
multiple worker threads, so every operation goes through one shared
connection guarded by a lock (the workload is tiny, contention is not
a concern).
"""

from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS todos (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  done INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memos (
  id TEXT PRIMARY KEY,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""

ENV_DB_PATH = "NEKO_COMPANION_DB_PATH"


def _utcnow() -> str:
  return datetime.now(timezone.utc).isoformat()


def default_db_path() -> Path:
  """Resolve the productivity database location.

  Priority:
  1. ``NEKO_COMPANION_DB_PATH`` environment variable (tests / overrides).
  2. The user runtime data root managed by :mod:`utils.config_manager`.
  3. Project-local ``memory/store`` as a last resort.
  """
  env_path = os.environ.get(ENV_DB_PATH, "").strip()
  if env_path:
    return Path(env_path)
  try:
    from utils.config_manager import get_config_manager

    root = Path(get_config_manager().app_docs_dir)
    return root / "companion" / "productivity.db"
  except Exception:
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "memory" / "store" / "companion_productivity.db"


class ProductivityStorage:
  """Thread-safe SQLite store for todos and memos.

  Pass ``":memory:"`` as ``db_path`` for an ephemeral store (tests).
  """

  def __init__(self, db_path: str | Path | None = None) -> None:
    if db_path is None:
      db_path = default_db_path()
    self._db_path = str(db_path)
    if self._db_path != ":memory:":
      Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
    self._lock = threading.Lock()
    self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
    self._conn.row_factory = sqlite3.Row
    with self._lock, self._conn:
      self._conn.executescript(_SCHEMA)

  @property
  def db_path(self) -> str:
    return self._db_path

  def close(self) -> None:
    with self._lock:
      self._conn.close()

  # ---------------------------------------------------------------- todos

  def create_todo(self, title: str) -> dict[str, Any]:
    now = _utcnow()
    row = {
      "id": str(uuid.uuid4()),
      "title": title,
      "done": False,
      "created_at": now,
      "updated_at": now,
    }
    with self._lock, self._conn:
      self._conn.execute(
        "INSERT INTO todos (id, title, done, created_at, updated_at)"
        " VALUES (?, ?, 0, ?, ?)",
        (row["id"], title, now, now),
      )
    return row

  def list_todos(self) -> list[dict[str, Any]]:
    with self._lock:
      rows = self._conn.execute(
        "SELECT id, title, done, created_at, updated_at FROM todos"
        " ORDER BY created_at ASC, id ASC"
      ).fetchall()
    return [self._todo_row(r) for r in rows]

  def get_todo(self, todo_id: str) -> dict[str, Any] | None:
    with self._lock:
      row = self._conn.execute(
        "SELECT id, title, done, created_at, updated_at FROM todos WHERE id = ?",
        (todo_id,),
      ).fetchone()
    return self._todo_row(row) if row else None

  def set_todo_done(self, todo_id: str, done: bool) -> dict[str, Any] | None:
    with self._lock, self._conn:
      cur = self._conn.execute(
        "UPDATE todos SET done = ?, updated_at = ? WHERE id = ?",
        (1 if done else 0, _utcnow(), todo_id),
      )
      if cur.rowcount == 0:
        return None
    return self.get_todo(todo_id)

  def update_todo_title(self, todo_id: str, title: str) -> dict[str, Any] | None:
    with self._lock, self._conn:
      cur = self._conn.execute(
        "UPDATE todos SET title = ?, updated_at = ? WHERE id = ?",
        (title, _utcnow(), todo_id),
      )
      if cur.rowcount == 0:
        return None
    return self.get_todo(todo_id)

  def delete_todo(self, todo_id: str) -> bool:
    with self._lock, self._conn:
      cur = self._conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
      return cur.rowcount > 0

  @staticmethod
  def _todo_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
      "id": row["id"],
      "title": row["title"],
      "done": bool(row["done"]),
      "created_at": row["created_at"],
      "updated_at": row["updated_at"],
    }

  # ---------------------------------------------------------------- memos

  def create_memo(self, content: str) -> dict[str, Any]:
    row = {
      "id": str(uuid.uuid4()),
      "content": content,
      "created_at": _utcnow(),
    }
    with self._lock, self._conn:
      self._conn.execute(
        "INSERT INTO memos (id, content, created_at) VALUES (?, ?, ?)",
        (row["id"], content, row["created_at"]),
      )
    return row

  def list_memos(self) -> list[dict[str, Any]]:
    with self._lock:
      rows = self._conn.execute(
        "SELECT id, content, created_at FROM memos"
        " ORDER BY created_at DESC, id DESC"
      ).fetchall()
    return [dict(r) for r in rows]

  def delete_memo(self, memo_id: str) -> bool:
    with self._lock, self._conn:
      cur = self._conn.execute("DELETE FROM memos WHERE id = ?", (memo_id,))
      return cur.rowcount > 0
