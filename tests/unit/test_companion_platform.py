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

from companion.generator import open_source as open_source_mod
from companion.generator import pipeline as pipeline_mod
from companion.generator.pipeline import run_pipeline_sync, start_generation
from companion.generator.tasks import TaskStatus, get_task_store
from companion.models.generation import GenerationInput
from companion.models.manifest import CompanionManifest


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
    reply = self.replies.pop(0)
    if isinstance(reply, Exception):
      raise reply
    return _FakeLLMResponse(reply)


class _FakeConfigManager:
  def __init__(self, summary_config):
    self._summary_config = summary_config

  def get_model_api_config(self, tier):
    assert tier == "summary"
    if isinstance(self._summary_config, Exception):
      raise self._summary_config
    return dict(self._summary_config)


_SUMMARY_CONFIG = {
  "model": "fake-summary-model",
  "base_url": "https://example.invalid/v1",
  "api_key": "fake-key",
  "provider_type": None,
}

_ANALYSIS_REPLY = json.dumps({
  "detected_traits": ["温柔", "黏人"],
  "speaking_style": "软软的口语，句尾带喵",
  "relationship_hints": ["与主人是久别重逢的青梅竹马"],
  "summary": "语料展示了一只温柔黏人的猫娘日常。",
}, ensure_ascii=False)

_PERSONA_REPLY = json.dumps({
  "system_prompt": "你是小柚，一只温柔黏人的猫娘，说话软软的、句尾带喵。",
  "memory_seeds": [
    {"entity": "neko", "content": "小柚是主人定制的猫娘伴侣。"},
    {"entity": "relationship", "content": "小柚和主人是青梅竹马。"},
  ],
}, ensure_ascii=False)


def _patch_llm(monkeypatch, fake_llm, summary_config=None):
  """Wire the pipeline to a fake summary-tier config + scripted LLM."""
  captured = {}

  def _fake_create_chat_llm(model, base_url, api_key, **kwargs):
    captured["model"] = model
    captured["base_url"] = base_url
    captured["kwargs"] = kwargs
    return fake_llm

  monkeypatch.setattr(
    pipeline_mod, "get_config_manager",
    lambda: _FakeConfigManager(summary_config or _SUMMARY_CONFIG),
  )
  monkeypatch.setattr(pipeline_mod, "create_chat_llm", _fake_create_chat_llm)
  return captured


def test_generation_input_defaults():
  inp = GenerationInput(companion_name="测试猫娘")
  assert inp.locale == "zh-CN"
  assert inp.corpus_files == []


def test_pipeline_produces_manifest(tmp_path, monkeypatch):
  monkeypatch.setattr(
    "companion.generator.pipeline._default_output_root",
    lambda: tmp_path,
  )
  # Force the deterministic heuristic path — no LLM route in unit tests.
  monkeypatch.setattr(pipeline_mod, "_resolve_generator_api_config", lambda: None)
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
  monkeypatch.setattr(pipeline_mod, "_resolve_generator_api_config", lambda: None)
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


# ── Phase 2: real-LLM pipeline (mocked) ─────────────────────────────────────


def test_pipeline_uses_summary_tier_llm(tmp_path, monkeypatch):
  fake_llm = _FakeLLM([_ANALYSIS_REPLY, _PERSONA_REPLY])
  captured = _patch_llm(monkeypatch, fake_llm)

  gen_input = GenerationInput(
    companion_name="小柚",
    corpus_text="温柔黏人的猫娘，句尾带喵，和主人是青梅竹马。",
  )
  store = get_task_store()
  task = store.create(gen_input)
  artifact = run_pipeline_sync(task, output_root=tmp_path)

  assert task.status == TaskStatus.COMPLETED
  # Route taken from the summary tier, not hardcoded.
  assert captured["model"] == "fake-summary-model"
  assert captured["base_url"] == "https://example.invalid/v1"
  # neko-guide: no temperature; budget + timeout are mandatory.
  assert "temperature" not in captured["kwargs"]
  assert captured["kwargs"]["timeout"] > 0
  assert captured["kwargs"]["max_completion_tokens"] > 0

  # Both stages consumed a scripted reply.
  assert len(fake_llm.prompts) == 2
  assert artifact.profile.system_prompt == (
    "你是小柚，一只温柔黏人的猫娘，说话软软的、句尾带喵。"
  )
  assert artifact.analysis_summary["analysis_source"] == "llm"
  assert artifact.analysis_summary["detected_traits"] == ["温柔", "黏人"]
  assert artifact.analysis_summary["llm"] == {
    "provider": "summary", "model": "fake-summary-model",
  }

  manifest = CompanionManifest.model_validate(
    json.loads(Path(artifact.manifest_path).read_text(encoding="utf-8"))
  )
  assert [s.entity for s in manifest.memory_seeds] == ["neko", "relationship"]
  assert manifest.generator_metadata["llm"]["model"] == "fake-summary-model"


def test_pipeline_llm_reply_with_code_fences(tmp_path, monkeypatch):
  fenced = f"```json\n{_ANALYSIS_REPLY}\n```"
  fake_llm = _FakeLLM([fenced, f"```json\n{_PERSONA_REPLY}\n```"])
  _patch_llm(monkeypatch, fake_llm)

  task = get_task_store().create(
    GenerationInput(companion_name="小柚", corpus_text="猫娘语料")
  )
  artifact = run_pipeline_sync(task, output_root=tmp_path)
  assert artifact.analysis_summary["analysis_source"] == "llm"
  assert artifact.profile.system_prompt.startswith("你是小柚")


def test_pipeline_falls_back_when_llm_fails(tmp_path, monkeypatch):
  fake_llm = _FakeLLM([RuntimeError("boom"), RuntimeError("boom")])
  _patch_llm(monkeypatch, fake_llm)

  gen_input = GenerationInput(
    companion_name="小柚",
    corpus_text="温柔的猫娘。",
    system_prompt="你是小柚。",
  )
  task = get_task_store().create(gen_input)
  artifact = run_pipeline_sync(task, output_root=tmp_path)

  # LLM errors must degrade to the heuristic path, never fail the task.
  assert task.status == TaskStatus.COMPLETED
  assert artifact.analysis_summary["analysis_source"] == "heuristic"
  assert artifact.analysis_summary["llm"]["degraded"] is True
  assert artifact.profile.system_prompt == "你是小柚。"
  assert artifact.analysis_summary["detected_traits"] == ["gentle"]


def test_pipeline_heuristic_when_no_route_at_all(tmp_path, monkeypatch):
  monkeypatch.setattr(
    pipeline_mod, "get_config_manager",
    lambda: _FakeConfigManager(RuntimeError("tier not configured")),
  )
  monkeypatch.setattr(open_source_mod, "resolve_ollama_api_config", lambda *a, **kw: None)

  task = get_task_store().create(
    GenerationInput(companion_name="小柚", corpus_text="活泼的猫娘")
  )
  artifact = run_pipeline_sync(task, output_root=tmp_path)
  assert task.status == TaskStatus.COMPLETED
  assert artifact.analysis_summary["llm"]["provider"] == "heuristic"
  assert artifact.analysis_summary["analysis_source"] == "heuristic"


def test_pipeline_ollama_fallback_route(tmp_path, monkeypatch):
  fake_llm = _FakeLLM([_ANALYSIS_REPLY, _PERSONA_REPLY])
  captured = {}

  def _fake_create_chat_llm(model, base_url, api_key, **kwargs):
    captured["model"] = model
    captured["base_url"] = base_url
    return fake_llm

  monkeypatch.setattr(
    pipeline_mod, "get_config_manager",
    lambda: _FakeConfigManager({"model": "", "base_url": "", "api_key": ""}),
  )
  monkeypatch.setattr(
    open_source_mod, "resolve_ollama_api_config",
    lambda *a, **kw: {
      "model": "qwen3:8b",
      "base_url": "http://127.0.0.1:11434/v1",
      "api_key": "ollama",
      "provider_type": None,
      "is_ollama": True,
    },
  )
  monkeypatch.setattr(pipeline_mod, "create_chat_llm", _fake_create_chat_llm)

  task = get_task_store().create(
    GenerationInput(companion_name="小柚", corpus_text="猫娘语料")
  )
  artifact = run_pipeline_sync(task, output_root=tmp_path)
  assert captured["model"] == "qwen3:8b"
  assert captured["base_url"] == "http://127.0.0.1:11434/v1"
  assert artifact.analysis_summary["llm"] == {
    "provider": "ollama", "model": "qwen3:8b",
  }


# ── Phase 2: open_source (Ollama detection) ─────────────────────────────────


# NB: parameter deliberately named endpoint_url — "base_url" collides with the
# pytest-base-url plugin's session-scoped fixture.
@pytest.mark.parametrize("endpoint_url,model,expected", [
  ("http://127.0.0.1:11434", "", True),               # default port
  ("http://192.168.1.5:11434/v1", "", True),          # default port on LAN
  ("https://my.proxy.example/ollama/v1", "", True),   # reverse-proxy path
  ("http://localhost:8000/v1", "ollama/qwen3", True), # local + model hint
  ("https://api.openai.com/v1", "gpt-4.1-mini", False),
  ("http://localhost:8000/v1", "qwen3", False),       # local but no hint
  ("", "", False),
])
def test_is_ollama_endpoint(endpoint_url, model, expected):
  assert open_source_mod.is_ollama_endpoint(endpoint_url, model) is expected


class _FakeTagsResponse:
  def __init__(self, payload):
    self._payload = payload

  def raise_for_status(self):
    return None

  def json(self):
    return self._payload


def test_detect_ollama_available(monkeypatch):
  payload = {"models": [{"name": "qwen3:8b"}, {"name": "nomic-embed-text"}]}
  monkeypatch.setattr(
    open_source_mod.httpx, "get",
    lambda url, timeout: _FakeTagsResponse(payload),
  )
  status = open_source_mod.detect_ollama()
  assert status.available is True
  assert status.models == ["qwen3:8b", "nomic-embed-text"]


def test_detect_ollama_unreachable(monkeypatch):
  def _raise(url, timeout):
    raise ConnectionError("refused")

  monkeypatch.setattr(open_source_mod.httpx, "get", _raise)
  status = open_source_mod.detect_ollama()
  assert status.available is False
  assert status.error


def test_resolve_ollama_api_config_skips_embedders(monkeypatch):
  payload = {"models": [{"name": "nomic-embed-text"}, {"name": "llama3.1:8b"}]}
  monkeypatch.setattr(
    open_source_mod.httpx, "get",
    lambda url, timeout: _FakeTagsResponse(payload),
  )
  config = open_source_mod.resolve_ollama_api_config()
  assert config["model"] == "llama3.1:8b"
  assert config["base_url"] == "http://127.0.0.1:11434/v1"
  assert config["is_ollama"] is True


def test_resolve_ollama_api_config_none_when_only_embedders(monkeypatch):
  payload = {"models": [{"name": "nomic-embed-text"}]}
  monkeypatch.setattr(
    open_source_mod.httpx, "get",
    lambda url, timeout: _FakeTagsResponse(payload),
  )
  assert open_source_mod.resolve_ollama_api_config() is None
