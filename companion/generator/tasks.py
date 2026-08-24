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

"""Async generation task store and state machine."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from companion.models.generation import GenerationArtifact, GenerationInput, GenerationStage


class TaskStatus(str, Enum):
  PENDING = "pending"
  RUNNING = "running"
  COMPLETED = "completed"
  FAILED = "failed"


DEFAULT_MAX_RETRIES = 3


@dataclass
class GenerationTask:
  id: str
  status: TaskStatus
  input: GenerationInput
  current_stage: GenerationStage | None = None
  stages_completed: list[GenerationStage] = field(default_factory=list)
  artifact: GenerationArtifact | None = None
  error: str | None = None
  retry_count: int = 0
  attempt_count: int = 0
  max_retries: int = DEFAULT_MAX_RETRIES
  created_at: str = field(
    default_factory=lambda: datetime.now(timezone.utc).isoformat()
  )
  updated_at: str = field(
    default_factory=lambda: datetime.now(timezone.utc).isoformat()
  )

  def can_retry(self) -> bool:
    return (
      self.status == TaskStatus.FAILED
      and self.retry_count < self.max_retries
    )

  def to_public_dict(self) -> dict[str, Any]:
    return {
      "id": self.id,
      "status": self.status.value,
      "current_stage": self.current_stage.value if self.current_stage else None,
      "stages_completed": [s.value for s in self.stages_completed],
      "error": self.error,
      "retry_count": self.retry_count,
      "attempt_count": self.attempt_count,
      "max_retries": self.max_retries,
      "retries_remaining": max(0, self.max_retries - self.retry_count),
      "created_at": self.created_at,
      "updated_at": self.updated_at,
      "has_artifact": self.artifact is not None,
    }


class GenerationTaskStore:
  """Task store with SQLite persistence (Phase 4)."""

  def __init__(self, db_path: Path | str | None = None) -> None:
    from companion.generator.task_storage import TaskSQLiteStorage, default_task_db_path

    path = Path(db_path) if db_path is not None else default_task_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    self._sqlite = TaskSQLiteStorage(path)
    self._tasks: dict[str, GenerationTask] = {}
    self._lock = threading.Lock()
    for task in self._sqlite.list_all():
      self._tasks[task.id] = task

  def create(self, gen_input: GenerationInput) -> GenerationTask:
    task_id = str(uuid.uuid4())
    task = GenerationTask(
      id=task_id,
      status=TaskStatus.PENDING,
      input=gen_input,
    )
    with self._lock:
      self._tasks[task_id] = task
    self._persist(task)
    return task

  def get(self, task_id: str) -> GenerationTask | None:
    with self._lock:
      task = self._tasks.get(task_id)
    if task is None:
      task = self._sqlite.get(task_id)
      if task is not None:
        with self._lock:
          self._tasks[task_id] = task
    return task

  def update(self, task: GenerationTask) -> None:
    task.updated_at = datetime.now(timezone.utc).isoformat()
    with self._lock:
      self._tasks[task.id] = task
    self._persist(task)

  def list_tasks(self, limit: int = 50) -> list[GenerationTask]:
    with self._lock:
      tasks = list(self._tasks.values())
    tasks.sort(key=lambda t: t.created_at, reverse=True)
    return tasks[:limit]

  def _persist(self, task: GenerationTask) -> None:
    self._sqlite.upsert(task)


_task_store: GenerationTaskStore | None = None


def get_task_store() -> GenerationTaskStore:
  global _task_store
  if _task_store is None:
    _task_store = GenerationTaskStore()
  return _task_store


def reset_task_store(db_path: Path | str | None = None) -> GenerationTaskStore:
  """Replace the process-wide store (unit tests / API fixtures)."""
  global _task_store
  _task_store = GenerationTaskStore(db_path=db_path)
  return _task_store
