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

"""Generation task store and state machine.

Phase 4 (HA): tasks are persisted in SQLite so they survive restarts, and
each task carries per-stage checkpoints (``stage_results``) so a failed
task can be retried from the failing stage instead of from scratch.

The store keeps SQLite as the single source of truth: every ``get`` reads
a fresh row, so API handlers and background pipeline threads never share
mutable task objects.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from companion.models.generation import GenerationArtifact, GenerationInput, GenerationStage

ENV_TASKS_DB_PATH = "NEKO_COMPANION_TASKS_DB_PATH"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS generation_tasks (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_generation_tasks_created
  ON generation_tasks (created_at DESC);
"""


def _utcnow() -> str:
  return datetime.now(timezone.utc).isoformat()


def default_tasks_db_path() -> Path:
  """Resolve the generation-task database location.

  Priority:
  1. ``NEKO_COMPANION_TASKS_DB_PATH`` environment variable (tests / overrides).
  2. The user runtime data root managed by :mod:`utils.config_manager`.
  3. Project-local ``memory/store`` as a last resort.
  """
  env_path = os.environ.get(ENV_TASKS_DB_PATH, "").strip()
  if env_path:
    return Path(env_path)
  try:
    from utils.config_manager import get_config_manager

    root = Path(get_config_manager().app_docs_dir)
    return root / "companion" / "generation_tasks.db"
  except Exception:
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "memory" / "store" / "companion_generation_tasks.db"


class TaskStatus(str, Enum):
  PENDING = "pending"
  RUNNING = "running"
  COMPLETED = "completed"
  FAILED = "failed"


@dataclass
class GenerationTask:
  id: str
  status: TaskStatus
  input: GenerationInput
  current_stage: GenerationStage | None = None
  stages_completed: list[GenerationStage] = field(default_factory=list)
  artifact: GenerationArtifact | None = None
  error: str | None = None
  attempts: int = 1
  # Per-stage checkpoints (analysis dict, persona prompt, voice config, …)
  # so a retry resumes from the failing stage. JSON-serializable only.
  stage_results: dict[str, Any] = field(default_factory=dict)
  created_at: str = field(default_factory=_utcnow)
  updated_at: str = field(default_factory=_utcnow)

  def to_public_dict(self) -> dict[str, Any]:
    return {
      "id": self.id,
      "status": self.status.value,
      "current_stage": self.current_stage.value if self.current_stage else None,
      "stages_completed": [s.value for s in self.stages_completed],
      "error": self.error,
      "attempts": self.attempts,
      "created_at": self.created_at,
      "updated_at": self.updated_at,
      "has_artifact": self.artifact is not None,
    }

  # ------------------------------------------------------------ persistence

  def to_storage_dict(self) -> dict[str, Any]:
    return {
      "id": self.id,
      "status": self.status.value,
      "input": self.input.model_dump(mode="json"),
      "current_stage": self.current_stage.value if self.current_stage else None,
      "stages_completed": [s.value for s in self.stages_completed],
      "artifact": self.artifact.model_dump(mode="json") if self.artifact else None,
      "error": self.error,
      "attempts": self.attempts,
      "stage_results": self.stage_results,
      "created_at": self.created_at,
      "updated_at": self.updated_at,
    }

  @classmethod
  def from_storage_dict(cls, data: dict[str, Any]) -> "GenerationTask":
    artifact = data.get("artifact")
    current_stage = data.get("current_stage")
    return cls(
      id=data["id"],
      status=TaskStatus(data["status"]),
      input=GenerationInput.model_validate(data["input"]),
      current_stage=GenerationStage(current_stage) if current_stage else None,
      stages_completed=[GenerationStage(s) for s in data.get("stages_completed", [])],
      artifact=GenerationArtifact.model_validate(artifact) if artifact else None,
      error=data.get("error"),
      attempts=int(data.get("attempts", 1)),
      stage_results=dict(data.get("stage_results") or {}),
      created_at=data["created_at"],
      updated_at=data["updated_at"],
    )


class GenerationTaskStore:
  """Thread-safe SQLite-backed task store (Phase 4).

  Rows hold the full task serialized as JSON next to the columns used for
  lookups/ordering. Pass ``":memory:"`` as ``db_path`` for an ephemeral
  store (tests).
  """

  def __init__(self, db_path: str | Path | None = None) -> None:
    if db_path is None:
      db_path = default_tasks_db_path()
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

  def create(self, gen_input: GenerationInput) -> GenerationTask:
    task = GenerationTask(
      id=str(uuid.uuid4()),
      status=TaskStatus.PENDING,
      input=gen_input,
    )
    payload = json.dumps(task.to_storage_dict(), ensure_ascii=False)
    with self._lock, self._conn:
      self._conn.execute(
        "INSERT INTO generation_tasks (id, status, created_at, updated_at, payload)"
        " VALUES (?, ?, ?, ?, ?)",
        (task.id, task.status.value, task.created_at, task.updated_at, payload),
      )
    return task

  def get(self, task_id: str) -> GenerationTask | None:
    with self._lock:
      row = self._conn.execute(
        "SELECT payload FROM generation_tasks WHERE id = ?", (task_id,)
      ).fetchone()
    if row is None:
      return None
    return GenerationTask.from_storage_dict(json.loads(row["payload"]))

  def update(self, task: GenerationTask) -> None:
    task.updated_at = _utcnow()
    payload = json.dumps(task.to_storage_dict(), ensure_ascii=False)
    with self._lock, self._conn:
      self._conn.execute(
        "UPDATE generation_tasks SET status = ?, updated_at = ?, payload = ?"
        " WHERE id = ?",
        (task.status.value, task.updated_at, payload, task.id),
      )

  def list_tasks(self, limit: int = 50) -> list[GenerationTask]:
    with self._lock:
      rows = self._conn.execute(
        "SELECT payload FROM generation_tasks"
        " ORDER BY created_at DESC, id DESC LIMIT ?",
        (max(0, int(limit)),),
      ).fetchall()
    return [GenerationTask.from_storage_dict(json.loads(r["payload"])) for r in rows]


_task_store: GenerationTaskStore | None = None
_store_lock = threading.Lock()


def get_task_store() -> GenerationTaskStore:
  """Shared task store, created lazily on the default database path."""
  global _task_store
  with _store_lock:
    if _task_store is None:
      _task_store = GenerationTaskStore()
    return _task_store


def reset_task_store(db_path: str | Path | None = None) -> None:
  """Close and drop the shared store (tests / path reconfiguration).

  With ``db_path`` the next singleton is created eagerly on that path;
  without it, the next :func:`get_task_store` call re-resolves the default.
  """
  global _task_store
  with _store_lock:
    if _task_store is not None:
      try:
        _task_store.close()
      except Exception:
        pass
    _task_store = GenerationTaskStore(db_path) if db_path is not None else None
