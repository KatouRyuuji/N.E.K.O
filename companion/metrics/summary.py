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

"""Aggregate companion metrics from SQLite tasks, workshop catalog, productivity."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from companion.generator.tasks import GenerationTask, GenerationTaskStore, TaskStatus


def _llm_route_key(task: GenerationTask) -> str:
  llm = (task.stage_results or {}).get("llm_meta") or {}
  if not isinstance(llm, dict):
    llm = {}
  provider = str(llm.get("provider") or "unknown")
  if llm.get("degraded"):
    return "degraded"
  return provider


def _task_duration_ms(task: GenerationTask) -> int | None:
  timings = (task.stage_results or {}).get("stage_timings_ms") or {}
  if not isinstance(timings, dict) or not timings:
    return None
  return int(sum(int(v) for v in timings.values()))


def collect_companion_metrics(
  *,
  task_store: GenerationTaskStore,
  workshop_root: Path,
  todo_count: int,
  memo_count: int,
  avatar_profile_count: int,
  limit: int = 500,
) -> dict[str, Any]:
  tasks = task_store.list_tasks(limit=limit)
  total = len(tasks)
  completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
  failed = sum(1 for t in tasks if t.status == TaskStatus.FAILED)
  running = sum(1 for t in tasks if t.status == TaskStatus.RUNNING)

  route_counts: dict[str, int] = {}
  durations: list[int] = []
  for task in tasks:
    if task.status == TaskStatus.COMPLETED:
      route_counts[_llm_route_key(task)] = route_counts.get(_llm_route_key(task), 0) + 1
    dur = _task_duration_ms(task)
    if dur is not None:
      durations.append(dur)

  workshop_entries = 0
  if workshop_root.is_dir():
    workshop_entries = sum(
      1 for child in workshop_root.iterdir()
      if child.is_dir() and (child / "workshop.json").is_file()
    )

  finished = completed + failed
  success_rate = (completed / finished) if finished else None
  avg_duration_ms = (sum(durations) / len(durations)) if durations else None

  return {
    "generation": {
      "tasks_sampled": total,
      "completed": completed,
      "failed": failed,
      "running": running,
      "success_rate": success_rate,
      "avg_duration_ms": avg_duration_ms,
      "llm_route_counts": route_counts,
    },
    "workshop": {"published_entries": workshop_entries},
    "productivity": {"todos": todo_count, "memos": memo_count},
    "avatar": {"profiles": avatar_profile_count},
  }
