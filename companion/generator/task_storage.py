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

"""SQLite persistence for companion generator tasks (Phase 4)."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

from companion.generator.tasks import GenerationTask, TaskStatus
from companion.models.generation import GenerationArtifact, GenerationInput, GenerationStage

ENV_TASK_DB_PATH = "NEKO_COMPANION_TASK_DB_PATH"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS generation_tasks (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  input_json TEXT NOT NULL,
  current_stage TEXT,
  stages_completed_json TEXT NOT NULL,
  artifact_json TEXT,
  error TEXT,
  retry_count INTEGER NOT NULL DEFAULT 0,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


def default_task_db_path() -> Path:
  env_path = os.environ.get(ENV_TASK_DB_PATH, "").strip()
  if env_path:
    return Path(env_path)
  try:
    from utils.config_manager import get_config_manager

    root = Path(get_config_manager().app_docs_dir)
    return root / "companion" / "generator_tasks.db"
  except Exception:
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "memory" / "store" / "companion_generator_tasks.db"


def _stage_list_to_json(stages: list[GenerationStage]) -> str:
  return json.dumps([s.value for s in stages], ensure_ascii=False)


def _stage_list_from_json(raw: str) -> list[GenerationStage]:
  values = json.loads(raw or "[]")
  return [GenerationStage(v) for v in values]


def task_to_row(task: GenerationTask) -> dict[str, Any]:
  artifact_json = None
  if task.artifact is not None:
    artifact_json = task.artifact.model_dump_json()
  return {
    "id": task.id,
    "status": task.status.value,
    "input_json": task.input.model_dump_json(),
    "current_stage": task.current_stage.value if task.current_stage else None,
    "stages_completed_json": _stage_list_to_json(task.stages_completed),
    "artifact_json": artifact_json,
    "error": task.error,
    "retry_count": task.retry_count,
    "attempt_count": task.attempt_count,
    "created_at": task.created_at,
    "updated_at": task.updated_at,
  }


def row_to_task(row: sqlite3.Row) -> GenerationTask:
  artifact = None
  if row["artifact_json"]:
    artifact = GenerationArtifact.model_validate_json(row["artifact_json"])
  current = row["current_stage"]
  return GenerationTask(
    id=row["id"],
    status=TaskStatus(row["status"]),
    input=GenerationInput.model_validate_json(row["input_json"]),
    current_stage=GenerationStage(current) if current else None,
    stages_completed=_stage_list_from_json(row["stages_completed_json"]),
    artifact=artifact,
    error=row["error"],
    retry_count=int(row["retry_count"]),
    attempt_count=int(row["attempt_count"]),
    created_at=row["created_at"],
    updated_at=row["updated_at"],
  )


class TaskSQLiteStorage:
  """Thread-safe SQLite backing store for :class:`GenerationTaskStore`."""

  def __init__(self, db_path: Path | str) -> None:
    self._db_path = str(db_path)
    self._lock = threading.Lock()
    self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
    self._conn.row_factory = sqlite3.Row
    with self._lock:
      self._conn.executescript(_SCHEMA)
      self._conn.commit()

  def close(self) -> None:
    with self._lock:
      self._conn.close()

  def upsert(self, task: GenerationTask) -> None:
    row = task_to_row(task)
    with self._lock:
      self._conn.execute(
        """
        INSERT INTO generation_tasks (
          id, status, input_json, current_stage, stages_completed_json,
          artifact_json, error, retry_count, attempt_count, created_at, updated_at
        ) VALUES (
          :id, :status, :input_json, :current_stage, :stages_completed_json,
          :artifact_json, :error, :retry_count, :attempt_count, :created_at, :updated_at
        )
        ON CONFLICT(id) DO UPDATE SET
          status=excluded.status,
          input_json=excluded.input_json,
          current_stage=excluded.current_stage,
          stages_completed_json=excluded.stages_completed_json,
          artifact_json=excluded.artifact_json,
          error=excluded.error,
          retry_count=excluded.retry_count,
          attempt_count=excluded.attempt_count,
          updated_at=excluded.updated_at
        """,
        row,
      )
      self._conn.commit()

  def get(self, task_id: str) -> GenerationTask | None:
    with self._lock:
      cur = self._conn.execute(
        "SELECT * FROM generation_tasks WHERE id = ?", (task_id,)
      )
      row = cur.fetchone()
    return row_to_task(row) if row else None

  def list_all(self) -> list[GenerationTask]:
    with self._lock:
      cur = self._conn.execute("SELECT * FROM generation_tasks")
      rows = cur.fetchall()
    return [row_to_task(r) for r in rows]
