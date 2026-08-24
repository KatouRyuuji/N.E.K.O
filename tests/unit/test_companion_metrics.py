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

"""Phase 5 M3 companion metrics."""

from pathlib import Path

import pytest

from companion.generator.tasks import TaskStatus, get_task_store
from companion.metrics.summary import collect_companion_metrics
from companion.models.generation import GenerationInput


def test_collect_metrics_empty(tmp_path):
  from companion.generator import tasks as tasks_mod

  tasks_mod.reset_task_store(tmp_path / "tasks.db")
  metrics = collect_companion_metrics(
    task_store=get_task_store(),
    workshop_root=tmp_path / "shop",
    todo_count=2,
    memo_count=1,
    avatar_profile_count=0,
  )
  assert metrics["generation"]["tasks_sampled"] == 0
  assert metrics["productivity"]["todos"] == 2
  assert metrics["workshop"]["published_entries"] == 0


def test_collect_metrics_llm_route_counts(tmp_path):
  from companion.generator import tasks as tasks_mod
  from companion.generator.tasks import GenerationTask

  tasks_mod.reset_task_store(tmp_path / "tasks.db")
  store = get_task_store()
  t1 = store.create(GenerationInput(companion_name="a"))
  t1.status = TaskStatus.COMPLETED
  t1.stage_results = {"llm_meta": {"provider": "ollama"}, "stage_timings_ms": {"ingest": 5}}
  store.update(t1)
  t2 = store.create(GenerationInput(companion_name="b"))
  t2.status = TaskStatus.FAILED
  store.update(t2)

  metrics = collect_companion_metrics(
    task_store=store,
    workshop_root=tmp_path,
    todo_count=0,
    memo_count=0,
    avatar_profile_count=1,
  )
  assert metrics["generation"]["completed"] == 1
  assert metrics["generation"]["failed"] == 1
  assert metrics["generation"]["llm_route_counts"].get("ollama") == 1
  assert metrics["avatar"]["profiles"] == 1


def test_api_metrics_endpoint(tmp_path, monkeypatch):
  fastapi = pytest.importorskip("fastapi")
  from fastapi.testclient import TestClient
  import companion.api.routes as routes

  monkeypatch.setattr(routes, "_productivity", None)
  app = fastapi.FastAPI()
  app.include_router(routes.router)
  client = TestClient(app)
  res = client.get("/api/companion/metrics")
  assert res.status_code == 200
  body = res.json()
  assert "generation" in body and "workshop" in body
