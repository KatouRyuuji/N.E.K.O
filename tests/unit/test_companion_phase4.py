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

"""Phase 4: workshop, dialogue session (integration tests)."""

import pytest

from companion.generator import pipeline as pipeline_mod
from companion.generator.pipeline import retry_generation, run_pipeline_sync
from companion.generator.tasks import TaskStatus, get_task_store
from companion.models.generation import GenerationInput
from companion.models.profile import CompanionProfile
from companion.ai.facade import CompanionAI
from companion.workshop.export import build_workshop_listing, export_workshop_bundle


def test_task_store_survives_reopen(tmp_path, monkeypatch):
  from companion.generator import tasks as tasks_mod

  db = tmp_path / "persist.db"
  monkeypatch.setenv(tasks_mod.ENV_TASKS_DB_PATH, str(db))
  tasks_mod.reset_task_store()
  created = get_task_store().create(GenerationInput(companion_name="持久化"))
  created.status = TaskStatus.FAILED
  created.error = "boom"
  get_task_store().update(created)

  tasks_mod.reset_task_store()
  again = get_task_store().get(created.id)
  assert again is not None
  assert again.status == TaskStatus.FAILED
  assert again.error == "boom"


def test_retry_generation_after_failure(tmp_path, monkeypatch):
  monkeypatch.setattr(pipeline_mod, "_default_output_root", lambda: tmp_path)
  monkeypatch.setattr(pipeline_mod, "_resolve_generator_api_config", lambda: None)

  task = get_task_store().create(
    GenerationInput(companion_name="重试猫", corpus_text="猫娘"),
  )
  task.status = TaskStatus.FAILED
  task.error = "stage error"
  get_task_store().update(task)

  retried = retry_generation(task)
  assert retried.attempts >= 2
  assert retried.status == TaskStatus.COMPLETED


def test_dialogue_session_connect_info():
  profile = CompanionProfile(
    id="c1", name="小柚", display_name="小柚", memory_character_name="小柚",
  )
  ai = CompanionAI(profile)
  text = ai.chat.connect_info()
  voice = ai.realtime.connect_info()
  assert text["websocket_path"] == "/ws/小柚"
  assert voice["protocol"] == "neko-realtime-v1"
  assert text["memory_character"] == "小柚"


def test_workshop_listing_requires_completed_task(tmp_path, monkeypatch):
  monkeypatch.setattr(pipeline_mod, "_default_output_root", lambda: tmp_path)
  monkeypatch.setattr(pipeline_mod, "_resolve_generator_api_config", lambda: None)
  task = get_task_store().create(GenerationInput(companion_name="工坊", corpus_text="猫娘"))
  run_pipeline_sync(task, output_root=tmp_path)
  listing = build_workshop_listing(task)
  assert listing["name"] == "工坊"
  dest = export_workshop_bundle(task, output_root=tmp_path / "shop")
  assert (dest / "workshop.json").is_file()


def test_api_retry_and_dialogue(tmp_path, monkeypatch):
  fastapi = pytest.importorskip("fastapi")
  from fastapi.testclient import TestClient
  import companion.api.routes as routes

  monkeypatch.setattr(pipeline_mod, "_default_output_root", lambda: tmp_path)
  monkeypatch.setattr(pipeline_mod, "_resolve_generator_api_config", lambda: None)
  monkeypatch.setattr(routes, "_productivity", None)
  app = fastapi.FastAPI()
  app.include_router(routes.router)
  client = TestClient(app)

  res = client.post(
    "/api/companion/dialogue/session",
    json={"companion_name": "小柚", "locale": "zh-CN"},
  )
  assert res.status_code == 200
  body = res.json()
  assert body["text_chat"]["websocket_path"] == "/ws/小柚"

  task = get_task_store().create(GenerationInput(companion_name="失败", corpus_text="猫娘语料"))
  task.status = TaskStatus.FAILED
  task.error = "x"
  get_task_store().update(task)
  res = client.post(f"/api/companion/generate/{task.id}/retry")
  assert res.status_code == 200
  assert res.json()["status"] == "completed"
