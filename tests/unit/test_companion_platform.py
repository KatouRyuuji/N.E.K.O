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

"""Unit tests for companion platform models and generator pipeline."""

import json
from pathlib import Path

import pytest

from companion.generator.pipeline import run_pipeline_sync, start_generation
from companion.generator.tasks import TaskStatus, get_task_store
from companion.models.generation import GenerationInput
from companion.models.manifest import CompanionManifest


def test_generation_input_defaults():
  inp = GenerationInput(companion_name="测试猫娘")
  assert inp.locale == "zh-CN"
  assert inp.corpus_files == []


def test_pipeline_produces_manifest(tmp_path, monkeypatch):
  monkeypatch.setattr(
    "companion.generator.pipeline._default_output_root",
    lambda: tmp_path,
  )
  gen_input = GenerationInput(
    companion_name="小柚",
    corpus_text="温柔活泼的猫娘，喜欢陪主人学习。",
    system_prompt="你是小柚。",
    live2d_model_id="demo_model",
  )
  store = get_task_store()
  task = store.create(gen_input)
  artifact = run_pipeline_sync(task, output_root=tmp_path)

  assert task.status == TaskStatus.COMPLETED
  assert artifact.profile.name == "小柚"
  manifest_path = Path(artifact.manifest_path)
  assert manifest_path.is_file()
  data = json.loads(manifest_path.read_text(encoding="utf-8"))
  manifest = CompanionManifest.model_validate(data)
  assert manifest.profile.system_prompt
  assert len(manifest.memory_seeds) >= 1


def test_start_generation_api_flow(tmp_path, monkeypatch):
  monkeypatch.setattr(
    "companion.generator.pipeline._default_output_root",
    lambda: tmp_path,
  )
  task = start_generation(GenerationInput(companion_name="API测试"))
  assert task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
  if task.status == TaskStatus.COMPLETED:
    assert task.artifact is not None


def test_open_source_probe_unavailable():
  from companion.ai.open_source import probe_ollama, resolve_open_source_provider

  provider = probe_ollama(timeout=0.001)
  assert provider.name == "ollama"
  assert provider.available is False
  assert resolve_open_source_provider() is None


def test_productivity_and_avatar_modules():
  from companion.productivity.service import ProductivityService
  from companion.avatar.registry import AvatarRegistry
  from companion.models.profile import AvatarKind

  prod = ProductivityService(":memory:")
  prod.pomodoro.start_work()
  assert prod.pomodoro.snapshot()["phase"] == "work"
  todo = prod.todo.create("写文档")
  assert todo.title == "写文档"

  registry = AvatarRegistry()
  profile = registry.from_companion_profile("c1", AvatarKind.LIVE2D, "model_a")
  assert registry.active() is profile
  registry.from_companion_profile("c2", AvatarKind.LIVE2D, "model_b")
  assert registry.set_active("c2") is not None
