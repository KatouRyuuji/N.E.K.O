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

"""Phase 4 (HA) tests: persistent task store, stage retry, background mode."""

import json
import time

import pytest

from companion.generator import pipeline as pipeline_mod
from companion.generator import voice_mapping as voice_mapping_mod
from companion.generator.pipeline import retry_generation, run_pipeline_sync
from companion.generator.tasks import (
  GenerationTask,
  GenerationTaskStore,
  TaskStatus,
  get_task_store,
)
from companion.models.generation import GenerationInput, GenerationStage
from companion.models.profile import VoiceConfig


class _FakeLLMResponse:
  def __init__(self, content: str):
    self.content = content


class _FakeLLM:
  """Scripted LLM double: returns queued replies, records prompts."""

  def __init__(self, replies):
    self.replies = list(replies)
    self.prompts = []

  def invoke(self, messages, **overrides):
    self.prompts.append(messages)
    if not self.replies:
      raise RuntimeError("no scripted reply left")
    return _FakeLLMResponse(self.replies.pop(0))


_ANALYSIS_REPLY = json.dumps({
  "detected_traits": ["温柔"],
  "speaking_style": "软软的口语",
  "relationship_hints": [],
  "summary": "温柔的猫娘。",
}, ensure_ascii=False)

_PERSONA_REPLY = json.dumps({
  "system_prompt": "你是小柚，一只温柔的猫娘。",
  "memory_seeds": [{"entity": "neko", "content": "小柚是定制猫娘。"}],
}, ensure_ascii=False)


class _FlakyVoiceMapping:
  """Fails until ``fail`` is cleared — simulates a broken pipeline stage."""

  def __init__(self):
    self.fail = True
    self.calls = 0

  def __call__(self, reference_audio_paths, **kwargs):
    self.calls += 1
    if self.fail:
      raise RuntimeError("voice mapping backend down")
    return VoiceConfig(provider="test", voice_id="v1")


def _use_heuristic(monkeypatch, tmp_path):
  monkeypatch.setattr(pipeline_mod, "_default_output_root", lambda: tmp_path / "out")
  monkeypatch.setattr(pipeline_mod, "_resolve_generator_api_config", lambda: None)


# ---------------------------------------------------------------------------
# SQLite persistence
# ---------------------------------------------------------------------------


def test_store_roundtrip_across_instances(tmp_path):
  db = tmp_path / "tasks.db"
  store = GenerationTaskStore(db)
  task = store.create(GenerationInput(companion_name="小柚", corpus_text="语料"))
  task.status = TaskStatus.FAILED
  task.error = "boom"
  task.attempts = 3
  task.stages_completed = [GenerationStage.INGEST, GenerationStage.ANALYZE_CORPUS]
  task.stage_results = {"analysis": {"detected_traits": ["温柔"]}}
  store.update(task)
  store.close()

  # A brand-new store instance (≈ process restart) sees the same task.
  reopened = GenerationTaskStore(db)
  loaded = reopened.get(task.id)
  assert loaded is not None
  assert loaded.status == TaskStatus.FAILED
  assert loaded.error == "boom"
  assert loaded.attempts == 3
  assert loaded.input.companion_name == "小柚"
  assert loaded.stages_completed == [
    GenerationStage.INGEST, GenerationStage.ANALYZE_CORPUS,
  ]
  assert loaded.stage_results["analysis"]["detected_traits"] == ["温柔"]
  reopened.close()


def test_store_persists_completed_artifact_across_restart(tmp_path, monkeypatch):
  _use_heuristic(monkeypatch, tmp_path)
  db = tmp_path / "tasks.db"
  store = GenerationTaskStore(db)
  monkeypatch.setattr(pipeline_mod, "get_task_store", lambda: store)

  task = store.create(GenerationInput(companion_name="小柚", corpus_text="温柔"))
  artifact = run_pipeline_sync(task, output_root=tmp_path / "out")
  store.close()

  reopened = GenerationTaskStore(db)
  loaded = reopened.get(task.id)
  assert loaded.status == TaskStatus.COMPLETED
  assert loaded.artifact is not None
  assert loaded.artifact.manifest_path == artifact.manifest_path
  assert loaded.artifact.profile.name == "小柚"
  reopened.close()


def test_store_get_returns_fresh_copies(tmp_path):
  store = GenerationTaskStore(tmp_path / "tasks.db")
  task = store.create(GenerationInput(companion_name="小柚"))
  copy = store.get(task.id)
  copy.error = "mutated locally"
  # Not persisted until update() — SQLite stays the source of truth.
  assert store.get(task.id).error is None
  store.close()


def test_store_list_tasks_order_and_limit(tmp_path):
  store = GenerationTaskStore(tmp_path / "tasks.db")
  ids = [store.create(GenerationInput(companion_name=f"c{i}")).id for i in range(5)]
  listed = store.list_tasks(limit=3)
  assert len(listed) == 3
  assert {t.id for t in listed} <= set(ids)
  everything = store.list_tasks(limit=100)
  assert {t.id for t in everything} == set(ids)
  # Newest first (created_at DESC; sub-second ties broken by id DESC).
  timestamps = [t.created_at for t in everything]
  assert timestamps == sorted(timestamps, reverse=True)
  store.close()


def test_public_dict_reports_attempts(tmp_path):
  store = GenerationTaskStore(":memory:")
  task = store.create(GenerationInput(companion_name="小柚"))
  payload = task.to_public_dict()
  assert payload["attempts"] == 1
  assert payload["status"] == "pending"
  store.close()


# ---------------------------------------------------------------------------
# Retry: resume from the failing stage, keep LLM stage checkpoints
# ---------------------------------------------------------------------------


def _patch_scripted_llm(monkeypatch, fake_llm):
  monkeypatch.setattr(
    pipeline_mod, "_resolve_generator_api_config",
    lambda: {
      "model": "fake-summary-model",
      "base_url": "https://example.invalid/v1",
      "api_key": "k",
      "provider_type": None,
      "is_ollama": False,
    },
  )
  monkeypatch.setattr(pipeline_mod, "create_chat_llm", lambda *a, **kw: fake_llm)


def test_retry_resumes_from_failed_stage_without_rerunning_llm(tmp_path, monkeypatch):
  monkeypatch.setattr(pipeline_mod, "_default_output_root", lambda: tmp_path / "out")
  fake_llm = _FakeLLM([_ANALYSIS_REPLY, _PERSONA_REPLY])
  _patch_scripted_llm(monkeypatch, fake_llm)
  flaky = _FlakyVoiceMapping()
  monkeypatch.setattr(voice_mapping_mod, "map_reference_audio_to_voice", flaky)

  store = get_task_store()
  task = store.create(GenerationInput(companion_name="小柚", corpus_text="温柔"))
  with pytest.raises(RuntimeError, match="voice mapping backend down"):
    run_pipeline_sync(task, output_root=tmp_path / "out")

  failed = store.get(task.id)
  assert failed.status == TaskStatus.FAILED
  assert "voice mapping backend down" in failed.error
  # LLM stages completed and checkpointed before the failure.
  assert GenerationStage.EXTRACT_PERSONA in failed.stages_completed
  assert GenerationStage.CONFIGURE_VOICE not in failed.stages_completed
  assert failed.stage_results["analysis"]["analysis_source"] == "llm"
  assert len(fake_llm.prompts) == 2

  # Fix the stage; an LLM route resolution on retry would be a bug.
  flaky.fail = False

  def _must_not_resolve():
    raise AssertionError("LLM route must not be re-resolved on resume")

  monkeypatch.setattr(pipeline_mod, "_resolve_generator_api_config", _must_not_resolve)

  retried = retry_generation(failed)
  assert retried.status == TaskStatus.COMPLETED
  assert retried.attempts == 2
  assert retried.error is None
  assert flaky.calls == 2  # once per attempt — earlier stages were skipped
  assert len(fake_llm.prompts) == 2  # no extra LLM calls on resume

  # Checkpointed LLM outputs made it into the final artifact.
  assert retried.artifact.profile.system_prompt == "你是小柚，一只温柔的猫娘。"
  assert retried.artifact.analysis_summary["analysis_source"] == "llm"
  assert retried.artifact.analysis_summary["llm"]["model"] == "fake-summary-model"
  assert retried.artifact.profile.voice.provider == "test"

  persisted = store.get(task.id)
  assert persisted.status == TaskStatus.COMPLETED
  assert persisted.attempts == 2


def test_retry_survives_store_reopen(tmp_path, monkeypatch):
  """Checkpoints written by attempt 1 drive a resume in a 'new process'."""
  monkeypatch.setattr(pipeline_mod, "_default_output_root", lambda: tmp_path / "out")
  db = tmp_path / "tasks.db"
  store = GenerationTaskStore(db)
  monkeypatch.setattr(pipeline_mod, "get_task_store", lambda: store)
  monkeypatch.setattr(pipeline_mod, "_resolve_generator_api_config", lambda: None)
  flaky = _FlakyVoiceMapping()
  monkeypatch.setattr(voice_mapping_mod, "map_reference_audio_to_voice", flaky)

  task = store.create(GenerationInput(companion_name="小柚", corpus_text="温柔"))
  with pytest.raises(RuntimeError):
    run_pipeline_sync(task, output_root=tmp_path / "out")
  store.close()

  reopened = GenerationTaskStore(db)
  monkeypatch.setattr(pipeline_mod, "get_task_store", lambda: reopened)
  flaky.fail = False
  retried = retry_generation(reopened.get(task.id))
  assert retried.status == TaskStatus.COMPLETED
  assert retried.attempts == 2
  reopened.close()


# ---------------------------------------------------------------------------
# API: retry endpoint + background mode
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path, monkeypatch):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient

  import companion.api.routes as routes

  _use_heuristic(monkeypatch, tmp_path)
  app = FastAPI()
  app.include_router(routes.router)
  return TestClient(app)


def _poll_until_done(client, task_id, timeout=15.0):
  deadline = time.monotonic() + timeout
  while time.monotonic() < deadline:
    body = client.get(f"/api/companion/generate/{task_id}").json()
    if body["status"] in ("completed", "failed"):
      return body
    time.sleep(0.05)
  raise AssertionError(f"task {task_id} did not finish within {timeout}s")


def test_retry_unknown_task_404(client):
  res = client.post("/api/companion/generate/no-such-task/retry")
  assert res.status_code == 404


def test_retry_non_failed_task_409(client):
  created = client.post(
    "/api/companion/generate", json={"companion_name": "小柚", "corpus_text": "温柔"}
  )
  assert created.status_code == 201
  assert created.json()["status"] == "completed"
  res = client.post(f"/api/companion/generate/{created.json()['id']}/retry")
  assert res.status_code == 409
  assert "completed" in res.json()["detail"]


def test_retry_failed_task_via_api(client, monkeypatch):
  flaky = _FlakyVoiceMapping()
  monkeypatch.setattr(voice_mapping_mod, "map_reference_audio_to_voice", flaky)

  created = client.post(
    "/api/companion/generate", json={"companion_name": "小柚", "corpus_text": "温柔"}
  )
  assert created.status_code == 201
  body = created.json()
  assert body["status"] == "failed"
  assert "voice mapping backend down" in body["error"]

  flaky.fail = False
  retried = client.post(f"/api/companion/generate/{body['id']}/retry")
  assert retried.status_code == 200
  retried_body = retried.json()
  assert retried_body["status"] == "completed"
  assert retried_body["attempts"] == 2

  detail = client.get(f"/api/companion/generate/{body['id']}").json()
  assert detail["status"] == "completed"
  assert detail["artifact"]["profile"]["name"] == "小柚"


def test_generate_background_returns_202_then_completes(client):
  res = client.post(
    "/api/companion/generate?background=true",
    json={"companion_name": "小柚", "corpus_text": "温柔"},
  )
  assert res.status_code == 202
  body = res.json()
  assert body["status"] in ("pending", "running")
  assert body["has_artifact"] is False

  done = _poll_until_done(client, body["id"])
  assert done["status"] == "completed"
  assert done["artifact"]["profile"]["name"] == "小柚"


def test_upload_background_returns_202_then_completes(client, tmp_path, monkeypatch):
  from companion.generator import uploads as uploads_mod

  upload_root = tmp_path / "uploads"
  upload_root.mkdir()
  monkeypatch.setattr(uploads_mod, "default_upload_root", lambda: upload_root)

  res = client.post(
    "/api/companion/generate/upload?background=true",
    data={"companion_name": "小柚", "corpus_text": "温柔"},
  )
  assert res.status_code == 202
  body = res.json()
  assert body["status"] in ("pending", "running")
  assert body["uploads"]["corpus_files"] == 0

  done = _poll_until_done(client, body["id"])
  assert done["status"] == "completed"


def test_retry_background_returns_202_then_completes(client, monkeypatch):
  flaky = _FlakyVoiceMapping()
  monkeypatch.setattr(voice_mapping_mod, "map_reference_audio_to_voice", flaky)

  created = client.post(
    "/api/companion/generate", json={"companion_name": "小柚", "corpus_text": "温柔"}
  )
  assert created.json()["status"] == "failed"

  flaky.fail = False
  res = client.post(
    f"/api/companion/generate/{created.json()['id']}/retry?background=true"
  )
  assert res.status_code == 202
  assert res.json()["attempts"] == 2

  done = _poll_until_done(client, created.json()["id"])
  assert done["status"] == "completed"
