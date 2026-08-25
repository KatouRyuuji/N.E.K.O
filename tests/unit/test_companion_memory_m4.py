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

"""Phase 5 M4 tests: corpus → fact seeds, persona refine, card versioning.

All LLM calls are mocked (scripted replies); fact-layer writes go through a
fake FactStore double so no real memory files are touched.
"""

import copy
import json

import pytest

import companion.ai.persona_versions as pv_mod
import companion.ai.refine as refine_mod
from companion.ai.bootstrap import FACT_SEED_IMPORT_FORMAT, seed_fact_layer
from companion.ai.persona import CompanionPersonaBridge
from companion.generator import pipeline as pipeline_mod
from companion.generator import voice_mapping as voice_mapping_mod
from companion.generator.pipeline import retry_generation, run_pipeline_sync
from companion.generator.tasks import TaskStatus, get_task_store
from companion.models.generation import GenerationInput, GenerationStage
from companion.models.manifest import CompanionManifest, FactSeed
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

_FACT_SEED_REPLY = json.dumps({
  "facts": [
    {"entity": "master", "content": "主人喜欢在深夜写代码。",
     "importance": 7, "confidence": 0.95},
    # importance clamped to 10
    {"entity": "neko", "content": "小柚害怕打雷。",
     "importance": 15, "confidence": 0.9},
    # low confidence → dropped
    {"entity": "relationship", "content": "推测他们可能是同学。",
     "importance": 5, "confidence": 0.4},
    # missing entity/importance → defaults
    {"entity": "", "content": "两人经常一起看电影。", "confidence": 0.85},
    "not-a-dict",
    {"entity": "master", "content": "   ", "confidence": 0.99},
  ],
}, ensure_ascii=False)


class FakeFactStore:
  """Records `_apersist_new_facts` calls; optionally drops entries (dedup)."""

  def __init__(self, added_indices=None):
    self.calls = []
    self._added_indices = added_indices

  async def _apersist_new_facts(self, lanlan_name, extracted):
    self.calls.append({"name": lanlan_name, "extracted": list(extracted)})
    added = []
    for i, fact in enumerate(extracted):
      if self._added_indices is not None and i not in self._added_indices:
        continue
      added.append({"id": f"fact_{i}", "text": fact["text"]})
    return added


class FakeConfigManager:
  """In-memory stand-in for ConfigManager.aload/asave_characters."""

  def __init__(self, characters=None):
    self.characters = characters if characters is not None else {}
    self.saved = None

  async def aload_characters(self):
    return copy.deepcopy(self.characters)

  async def asave_characters(self, data):
    self.saved = data
    self.characters = copy.deepcopy(data)


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


def _read_manifest(task) -> CompanionManifest:
  raw = json.loads(
    open(task.artifact.manifest_path, encoding="utf-8").read()
  )
  return CompanionManifest.model_validate(raw)


# ---------------------------------------------------------------------------
# Pipeline: extract_fact_seeds stage
# ---------------------------------------------------------------------------


def test_fact_seed_stage_off_by_default(tmp_path, monkeypatch):
  monkeypatch.setattr(pipeline_mod, "_default_output_root", lambda: tmp_path / "out")
  # Only two scripted replies: a third LLM call (fact seeds) would raise.
  fake_llm = _FakeLLM([_ANALYSIS_REPLY, _PERSONA_REPLY])
  _patch_scripted_llm(monkeypatch, fake_llm)

  task = get_task_store().create(
    GenerationInput(companion_name="小柚", corpus_text="温柔的猫娘语料")
  )
  run_pipeline_sync(task)

  assert task.status == TaskStatus.COMPLETED
  assert GenerationStage.EXTRACT_FACT_SEEDS in task.stages_completed
  assert task.stage_results["fact_seeds"] == []
  assert _read_manifest(task).fact_seeds == []
  assert not fake_llm.replies  # analyze + persona consumed, nothing more


def test_fact_seed_stage_extracts_high_confidence_facts(tmp_path, monkeypatch):
  monkeypatch.setattr(pipeline_mod, "_default_output_root", lambda: tmp_path / "out")
  fake_llm = _FakeLLM([_ANALYSIS_REPLY, _PERSONA_REPLY, _FACT_SEED_REPLY])
  _patch_scripted_llm(monkeypatch, fake_llm)

  task = get_task_store().create(
    GenerationInput(
      companion_name="小柚", corpus_text="温柔的猫娘语料",
      extract_fact_seeds=True,
    )
  )
  run_pipeline_sync(task)

  assert task.status == TaskStatus.COMPLETED
  seeds = _read_manifest(task).fact_seeds
  assert [s.content for s in seeds] == [
    "主人喜欢在深夜写代码。", "小柚害怕打雷。", "两人经常一起看电影。",
  ]
  assert seeds[0].entity == "master" and seeds[0].importance == 7
  assert seeds[1].importance == 10  # clamped from 15
  assert seeds[2].entity == "master" and seeds[2].importance == 6  # defaults
  assert all(s.confidence >= 0.8 for s in seeds)
  # Stage checkpoint mirrors the manifest content.
  assert [s["content"] for s in task.stage_results["fact_seeds"]] == [
    s.content for s in seeds
  ]


def test_fact_seed_stage_degrades_to_empty_on_llm_garbage(tmp_path, monkeypatch):
  monkeypatch.setattr(pipeline_mod, "_default_output_root", lambda: tmp_path / "out")
  fake_llm = _FakeLLM([_ANALYSIS_REPLY, _PERSONA_REPLY, "not json at all"])
  _patch_scripted_llm(monkeypatch, fake_llm)

  task = get_task_store().create(
    GenerationInput(
      companion_name="小柚", corpus_text="温柔的猫娘语料",
      extract_fact_seeds=True,
    )
  )
  run_pipeline_sync(task)

  assert task.status == TaskStatus.COMPLETED
  assert _read_manifest(task).fact_seeds == []


def test_fact_seed_stage_without_llm_route_yields_empty(tmp_path, monkeypatch):
  monkeypatch.setattr(pipeline_mod, "_default_output_root", lambda: tmp_path / "out")
  monkeypatch.setattr(pipeline_mod, "_resolve_generator_api_config", lambda: None)

  task = get_task_store().create(
    GenerationInput(
      companion_name="小柚", corpus_text="温柔的猫娘语料",
      extract_fact_seeds=True,
    )
  )
  run_pipeline_sync(task)

  # No LLM → heuristic persona, but NO fabricated facts.
  assert task.status == TaskStatus.COMPLETED
  assert _read_manifest(task).fact_seeds == []


def test_retry_keeps_fact_seed_checkpoint_without_reprobing_llm(tmp_path, monkeypatch):
  monkeypatch.setattr(pipeline_mod, "_default_output_root", lambda: tmp_path / "out")
  fake_llm = _FakeLLM([_ANALYSIS_REPLY, _PERSONA_REPLY, _FACT_SEED_REPLY])
  _patch_scripted_llm(monkeypatch, fake_llm)

  class _FlakyVoiceMapping:
    def __init__(self):
      self.fail = True

    def __call__(self, reference_audio_paths, **kwargs):
      if self.fail:
        raise RuntimeError("voice mapping backend down")
      return VoiceConfig(provider="test", voice_id="v1")

  flaky = _FlakyVoiceMapping()
  monkeypatch.setattr(voice_mapping_mod, "map_reference_audio_to_voice", flaky)

  task = get_task_store().create(
    GenerationInput(
      companion_name="小柚", corpus_text="温柔的猫娘语料",
      extract_fact_seeds=True,
    )
  )
  with pytest.raises(RuntimeError, match="voice mapping backend down"):
    run_pipeline_sync(task)
  assert GenerationStage.EXTRACT_FACT_SEEDS in task.stages_completed

  def _must_not_resolve():
    raise AssertionError("resumed task must not probe an LLM route again")

  monkeypatch.setattr(pipeline_mod, "_resolve_generator_api_config", _must_not_resolve)
  flaky.fail = False
  retry_generation(task)

  assert task.status == TaskStatus.COMPLETED
  assert [s.content for s in _read_manifest(task).fact_seeds] == [
    "主人喜欢在深夜写代码。", "小柚害怕打雷。", "两人经常一起看电影。",
  ]


# ---------------------------------------------------------------------------
# seed_fact_layer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_fact_layer_writes_through_fact_pipeline():
  store = FakeFactStore()
  seeds = [
    FactSeed(entity="master", content="主人喜欢在深夜写代码。",
             importance=7, confidence=0.95),
    FactSeed(entity="neko", content="小柚害怕打雷。", importance=10,
             confidence=0.9),
    FactSeed(entity="master", content="   "),  # skipped
  ]
  result = await seed_fact_layer("小柚", seeds, fact_store=store)

  assert result["facts_total"] == 3
  assert result["facts_added"] == 2
  assert result["facts_skipped"] == 1
  assert result["fact_ids"] == ["fact_0", "fact_1"]
  (call,) = store.calls
  assert call["name"] == "小柚"
  first = call["extracted"][0]
  assert first["text"] == "主人喜欢在深夜写代码。"
  assert first["entity"] == "master"
  assert first["importance"] == 7
  assert first["_external_import"]["format"] == FACT_SEED_IMPORT_FORMAT
  assert first["_external_import"]["confidence"] == 0.95


@pytest.mark.asyncio
async def test_seed_fact_layer_counts_deduped_as_skipped():
  store = FakeFactStore(added_indices={0})  # second entry deduped away
  seeds = [
    FactSeed(content="事实A。"),
    FactSeed(content="事实A。"),
  ]
  result = await seed_fact_layer("小柚", seeds, fact_store=store)
  assert result["facts_added"] == 1
  assert result["facts_skipped"] == 1


@pytest.mark.asyncio
async def test_seed_fact_layer_empty_seeds_never_touch_store():
  store = FakeFactStore()
  result = await seed_fact_layer("小柚", [], fact_store=store)
  assert result["facts_added"] == 0
  assert store.calls == []


# ---------------------------------------------------------------------------
# POST /api/companion/import — fact seeds keyed by the FINAL card key
# ---------------------------------------------------------------------------


def _write_package(tmp_path, fact_seeds=None):
  from companion.models.manifest import MemorySeed
  from companion.models.profile import CompanionProfile

  pkg = tmp_path / "pkg"
  pkg.mkdir(parents=True, exist_ok=True)
  manifest = CompanionManifest(
    profile=CompanionProfile(
      id="companion-1", name="小柚", display_name="小柚",
      system_prompt="你是小柚，一只温柔的猫娘。",
    ),
    memory_seeds=[MemorySeed(entity="neko", content="小柚是定制猫娘。")],
    fact_seeds=fact_seeds or [],
  )
  (pkg / "manifest.json").write_text(
    json.dumps(manifest.to_package_dict(), ensure_ascii=False), encoding="utf-8"
  )
  return pkg


class FakePersonaManager:
  FACT_ADDED = "added"

  def __init__(self):
    self.calls = []

  async def aadd_fact(self, name, text, entity="master", source="manual",
                      source_id=None):
    self.calls.append({"name": name, "entity": entity, "text": text})
    return self.FACT_ADDED


@pytest.fixture()
def import_client(monkeypatch):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient

  import companion.ai.bootstrap as bootstrap_mod
  import companion.ai.persona as persona_mod
  import companion.api.routes as routes
  from companion.avatar.registry import AvatarRegistry

  persona_manager = FakePersonaManager()
  fact_store = FakeFactStore()
  config_manager = FakeConfigManager({"猫娘": {"小柚": {}}})

  monkeypatch.setattr(
    bootstrap_mod, "_resolve_persona_manager", lambda: persona_manager
  )
  monkeypatch.setattr(bootstrap_mod, "_resolve_fact_store", lambda: fact_store)

  real_register = persona_mod.register_character_card

  async def _register_with_fake_config(profile, config_manager_arg=None):
    return await real_register(profile, config_manager=config_manager)

  monkeypatch.setattr(
    persona_mod, "register_character_card", _register_with_fake_config
  )

  async def _no_reload(*, reason):
    return False

  monkeypatch.setattr(routes, "_notify_memory_server_reload_safe", _no_reload)
  monkeypatch.setattr(routes, "_avatar_registry", AvatarRegistry())

  app = FastAPI()
  app.include_router(routes.router)
  client = TestClient(app)
  client.fake_persona_manager = persona_manager
  client.fake_fact_store = fact_store
  client.fake_config_manager = config_manager
  return client


def test_api_import_seeds_fact_layer_under_final_card_key(tmp_path, import_client):
  pkg = _write_package(
    tmp_path,
    fact_seeds=[
      FactSeed(entity="master", content="主人喜欢在深夜写代码。",
               importance=7, confidence=0.95),
    ],
  )
  res = import_client.post(
    "/api/companion/import", json={"package_path": str(pkg)}
  )
  assert res.status_code == 201
  body = res.json()

  # "小柚" already exists → conflict rename; fact seeds must follow the
  # FINAL card key just like persona seeds do.
  assert body["character_name"] == "小柚(1)"
  assert body["memory"]["fact_layer"]["facts_added"] == 1
  (call,) = import_client.fake_fact_store.calls
  assert call["name"] == "小柚(1)"
  assert all(
    c["name"] == "小柚(1)" for c in import_client.fake_persona_manager.calls
  )


def test_api_import_without_fact_seeds_skips_fact_layer(tmp_path, import_client):
  pkg = _write_package(tmp_path)
  res = import_client.post(
    "/api/companion/import", json={"package_path": str(pkg)}
  )
  assert res.status_code == 201
  assert "fact_layer" not in res.json()["memory"]
  assert import_client.fake_fact_store.calls == []


# ---------------------------------------------------------------------------
# refine_persona_card (LLM mocked)
# ---------------------------------------------------------------------------


_OLD_PROMPT = "你是小柚，一只温柔的猫娘。"
_NEW_PROMPT = "你是小柚，一只温柔但偶尔傲娇的猫娘。"
_REFINE_REPLY = json.dumps(
  {"system_prompt": _NEW_PROMPT, "change_summary": "加入偶尔傲娇的性格侧面。"},
  ensure_ascii=False,
)


def _patch_refine_llm(monkeypatch, fake_llm):
  monkeypatch.setattr(
    refine_mod, "_resolve_refine_api_config",
    lambda: {
      "model": "fake-correction-model",
      "base_url": "https://example.invalid/v1",
      "api_key": "k",
      "provider_type": None,
    },
  )
  monkeypatch.setattr(refine_mod, "create_chat_llm", lambda *a, **kw: fake_llm)


def test_refine_persona_card_returns_diff_proposal(monkeypatch):
  fake_llm = _FakeLLM([_REFINE_REPLY])
  _patch_refine_llm(monkeypatch, fake_llm)

  proposal = refine_mod.refine_persona_card(
    "小柚", _OLD_PROMPT, "希望她偶尔傲娇一点", locale="zh-CN"
  )
  assert proposal["proposed_system_prompt"] == _NEW_PROMPT
  assert proposal["changed"] is True
  assert any(line.startswith("-") for line in proposal["diff"])
  assert any(line.startswith("+") for line in proposal["diff"])
  assert proposal["llm"] == {"tier": "correction", "model": "fake-correction-model"}
  # The single prompt sent to the LLM carries both the card and the feedback.
  (messages,) = fake_llm.prompts
  sent = messages[0]["content"]
  assert _OLD_PROMPT in sent
  assert "希望她偶尔傲娇一点" in sent


def test_refine_persona_card_rejects_empty_llm_output(monkeypatch):
  _patch_refine_llm(monkeypatch, _FakeLLM([json.dumps({"system_prompt": ""})]))
  with pytest.raises(refine_mod.PersonaRefineFailed):
    refine_mod.refine_persona_card("小柚", _OLD_PROMPT, "反馈")


def test_refine_tier_unconfigured_raises_unavailable(monkeypatch):
  class _NoTierConfigManager:
    def get_model_api_config(self, tier):
      raise KeyError(tier)

  monkeypatch.setattr(
    refine_mod, "get_config_manager", lambda: _NoTierConfigManager()
  )
  with pytest.raises(refine_mod.PersonaRefineUnavailable):
    refine_mod._resolve_refine_api_config()


# ---------------------------------------------------------------------------
# persona version chain
# ---------------------------------------------------------------------------


def test_version_chain_appends_and_caps(tmp_path):
  from config import COMPANION_PERSONA_VERSION_MAX_SNAPSHOTS as CAP

  for i in range(CAP + 5):
    pv_mod.snapshot_card("小柚", {"昵称": f"v{i}"}, reason="test", root=tmp_path)

  versions = pv_mod.list_versions("小柚", root=tmp_path)
  assert len(versions) == CAP
  # Oldest dropped, numbering keeps growing monotonically.
  assert versions[0]["version"] == 6
  assert versions[-1]["version"] == CAP + 5
  latest = pv_mod.latest_version("小柚", root=tmp_path)
  assert latest["card"] == {"昵称": f"v{CAP + 4}"}
  assert pv_mod.get_version("小柚", 6, root=tmp_path)["card"] == {"昵称": "v5"}
  assert pv_mod.get_version("小柚", 1, root=tmp_path) is None


def test_version_chain_survives_corrupt_file(tmp_path):
  (tmp_path / "小柚.json").write_text("{corrupt", encoding="utf-8")
  assert pv_mod.list_versions("小柚", root=tmp_path) == []
  meta = pv_mod.snapshot_card("小柚", {"昵称": "v0"}, root=tmp_path)
  assert meta["version"] == 1


# ---------------------------------------------------------------------------
# API: /persona/{name}/refine + apply + versions + rollback
# ---------------------------------------------------------------------------


def _card(prompt=_OLD_PROMPT):
  return {"昵称": "小柚", "_reserved": {"system_prompt": prompt}}


@pytest.fixture()
def persona_client(monkeypatch, tmp_path):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient

  import companion.api.routes as routes

  config_manager = FakeConfigManager({"猫娘": {"小柚": _card()}})
  monkeypatch.setattr(routes, "_resolve_config_manager", lambda: config_manager)
  monkeypatch.setattr(pv_mod, "_default_root", lambda: tmp_path / "versions")
  (tmp_path / "versions").mkdir()

  async def _no_reload(*, reason):
    return True

  monkeypatch.setattr(routes, "_notify_memory_server_reload_safe", _no_reload)

  app = FastAPI()
  app.include_router(routes.router)
  client = TestClient(app)
  client.fake_config_manager = config_manager
  client.versions_root = tmp_path / "versions"
  return client


def test_api_refine_returns_diff_without_writing(persona_client, monkeypatch):
  _patch_refine_llm(monkeypatch, _FakeLLM([_REFINE_REPLY]))
  res = persona_client.post(
    "/api/companion/persona/小柚/refine",
    json={"feedback": "希望她偶尔傲娇一点"},
  )
  assert res.status_code == 200
  body = res.json()
  assert body["applied"] is False
  assert body["proposal"]["proposed_system_prompt"] == _NEW_PROMPT
  assert body["proposal"]["diff"]
  # Confirm-before-write: nothing persisted by the refine round itself.
  assert persona_client.fake_config_manager.saved is None
  assert pv_mod.list_versions("小柚", root=persona_client.versions_root) == []


def test_api_refine_unknown_character_404(persona_client, monkeypatch):
  _patch_refine_llm(monkeypatch, _FakeLLM([_REFINE_REPLY]))
  res = persona_client.post(
    "/api/companion/persona/不存在/refine", json={"feedback": "x"}
  )
  assert res.status_code == 404


def test_api_refine_tier_unavailable_503(persona_client, monkeypatch):
  def _unavailable():
    raise refine_mod.PersonaRefineUnavailable("correction tier is not configured")

  monkeypatch.setattr(refine_mod, "_resolve_refine_api_config", _unavailable)
  res = persona_client.post(
    "/api/companion/persona/小柚/refine", json={"feedback": "x"}
  )
  assert res.status_code == 503


def test_api_refine_llm_failure_502(persona_client, monkeypatch):
  class _BoomLLM:
    def invoke(self, messages, **overrides):
      raise RuntimeError("provider down")

  _patch_refine_llm(monkeypatch, _BoomLLM())
  res = persona_client.post(
    "/api/companion/persona/小柚/refine", json={"feedback": "x"}
  )
  assert res.status_code == 502


def test_api_apply_snapshots_previous_version_then_writes(persona_client):
  res = persona_client.post(
    "/api/companion/persona/小柚/refine/apply",
    json={"system_prompt": _NEW_PROMPT, "expected_system_prompt": _OLD_PROMPT},
  )
  assert res.status_code == 200
  body = res.json()
  assert body["applied"] is True
  assert body["previous_version"]["version"] == 1
  assert body["memory_server_reloaded"] is True

  saved = persona_client.fake_config_manager.saved["猫娘"]["小柚"]
  assert saved["_reserved"]["system_prompt"] == _NEW_PROMPT
  assert saved["昵称"] == "小柚"  # untouched fields preserved
  snapshot = pv_mod.get_version("小柚", 1, root=persona_client.versions_root)
  assert snapshot["reason"] == "refine_apply"
  assert snapshot["card"]["_reserved"]["system_prompt"] == _OLD_PROMPT


def test_api_apply_conflict_when_card_changed(persona_client):
  res = persona_client.post(
    "/api/companion/persona/小柚/refine/apply",
    json={"system_prompt": _NEW_PROMPT, "expected_system_prompt": "陈旧的提示词"},
  )
  assert res.status_code == 409
  assert persona_client.fake_config_manager.saved is None
  assert pv_mod.list_versions("小柚", root=persona_client.versions_root) == []


def test_api_versions_lists_metadata(persona_client):
  persona_client.post(
    "/api/companion/persona/小柚/refine/apply",
    json={"system_prompt": _NEW_PROMPT},
  )
  res = persona_client.get("/api/companion/persona/小柚/versions")
  assert res.status_code == 200
  body = res.json()
  assert body["name"] == "小柚"
  assert [v["version"] for v in body["versions"]] == [1]
  assert body["versions"][0]["reason"] == "refine_apply"
  assert "card" not in body["versions"][0]  # metadata only


def test_api_rollback_restores_card_and_memory_key(persona_client):
  apply_res = persona_client.post(
    "/api/companion/persona/小柚/refine/apply",
    json={"system_prompt": _NEW_PROMPT},
  )
  assert apply_res.status_code == 200

  res = persona_client.post("/api/companion/persona/小柚/rollback", json={})
  assert res.status_code == 200
  body = res.json()
  assert body["rolled_back"] is True
  assert body["restored_version"] == 1
  assert body["memory_character_name"] == "小柚"

  restored = persona_client.fake_config_manager.characters["猫娘"]["小柚"]
  assert restored["_reserved"]["system_prompt"] == _OLD_PROMPT
  # Card ↔ memory key consistency: the restored card still maps to the same
  # memory character name, so persona.json / facts.json keys stay valid.
  profile = CompanionPersonaBridge.from_character_card("小柚", restored).profile
  assert profile.resolved_memory_name() == "小柚"
  # The rollback itself is revertible: the pre-rollback card was snapshotted.
  versions = pv_mod.list_versions("小柚", root=persona_client.versions_root)
  assert [v["reason"] for v in versions] == ["refine_apply", "pre_rollback"]
  pre = pv_mod.get_version("小柚", 2, root=persona_client.versions_root)
  assert pre["card"]["_reserved"]["system_prompt"] == _NEW_PROMPT


def test_api_rollback_specific_version(persona_client):
  persona_client.post(
    "/api/companion/persona/小柚/refine/apply",
    json={"system_prompt": "第二版提示词"},
  )
  persona_client.post(
    "/api/companion/persona/小柚/refine/apply",
    json={"system_prompt": "第三版提示词"},
  )
  res = persona_client.post(
    "/api/companion/persona/小柚/rollback", json={"version": 1}
  )
  assert res.status_code == 200
  assert res.json()["restored_version"] == 1
  restored = persona_client.fake_config_manager.characters["猫娘"]["小柚"]
  assert restored["_reserved"]["system_prompt"] == _OLD_PROMPT


def test_api_rollback_without_snapshots_404(persona_client):
  res = persona_client.post("/api/companion/persona/小柚/rollback", json={})
  assert res.status_code == 404
  assert persona_client.fake_config_manager.saved is None


def test_api_rollback_unknown_character_404(persona_client):
  res = persona_client.post("/api/companion/persona/不存在/rollback", json={})
  assert res.status_code == 404
