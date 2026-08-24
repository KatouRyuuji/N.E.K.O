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
from typing import Any

from companion.models.generation import GenerationArtifact, GenerationInput, GenerationStage


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
  created_at: str = field(
    default_factory=lambda: datetime.now(timezone.utc).isoformat()
  )
  updated_at: str = field(
    default_factory=lambda: datetime.now(timezone.utc).isoformat()
  )

  def to_public_dict(self) -> dict[str, Any]:
    return {
      "id": self.id,
      "status": self.status.value,
      "current_stage": self.current_stage.value if self.current_stage else None,
      "stages_completed": [s.value for s in self.stages_completed],
      "error": self.error,
      "created_at": self.created_at,
      "updated_at": self.updated_at,
      "has_artifact": self.artifact is not None,
    }


class GenerationTaskStore:
  """In-memory task store (Phase 1). Phase 4 will add persistence."""

  def __init__(self) -> None:
    self._tasks: dict[str, GenerationTask] = {}
    self._lock = threading.Lock()

  def create(self, gen_input: GenerationInput) -> GenerationTask:
    task_id = str(uuid.uuid4())
    task = GenerationTask(
      id=task_id,
      status=TaskStatus.PENDING,
      input=gen_input,
    )
    with self._lock:
      self._tasks[task_id] = task
    return task

  def get(self, task_id: str) -> GenerationTask | None:
    with self._lock:
      return self._tasks.get(task_id)

  def update(self, task: GenerationTask) -> None:
    task.updated_at = datetime.now(timezone.utc).isoformat()
    with self._lock:
      self._tasks[task.id] = task

  def list_tasks(self, limit: int = 50) -> list[GenerationTask]:
    with self._lock:
      tasks = list(self._tasks.values())
    tasks.sort(key=lambda t: t.created_at, reverse=True)
    return tasks[:limit]


_task_store = GenerationTaskStore()


def get_task_store() -> GenerationTaskStore:
  return _task_store
