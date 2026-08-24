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

"""Unit tests for Phase 3: memory seed bootstrap + character card import."""

import copy
import json

import pytest

from companion.ai.bootstrap import (
  SEED_SOURCE,
  bootstrap_from_artifact,
  load_manifest_from_artifact,
  seed_memory,
)
from companion.ai.persona import (
  CharacterCardError,
  CompanionPersonaBridge,
  register_character_card,
)
from companion.models.generation import GenerationArtifact
from companion.models.manifest import CompanionManifest, MemorySeed
from companion.models.profile import AvatarKind, CompanionProfile, VoiceConfig


class FakePersonaManager:
  """Records aadd_fact calls; replays scripted status codes."""

  FACT_ADDED = "added"

  def __init__(self, statuses=None):
    self.calls = []
    self._statuses = list(statuses or [])

  async def aadd_fact(self, name, text, entity="master", source="manual",
                      source_id=None):
    self.calls.append(
      {"name": name, "text": text, "entity": entity, "source": source}
    )
    return self._statuses.pop(0) if self._statuses else self.FACT_ADDED


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


def _profile(**overrides) -> CompanionProfile:
  base = dict(
    id="companion-1",
    name="小柚",
    display_name="小柚",
    system_prompt="你是小柚，一只温柔的猫娘。",
  )
  base.update(overrides)
  return CompanionProfile(**base)


def _seeds():
  return [
    MemorySeed(entity="neko", content="小柚是主人定制的猫娘伴侣。"),
    MemorySeed(entity="relationship", content="小柚和主人是青梅竹马。"),
  ]


def _write_package(tmp_path, profile=None, seeds=None, with_live2d=False):
  """Create a minimal `.neko-companion` package directory."""
  pkg = tmp_path / "pkg"
  pkg.mkdir(parents=True, exist_ok=True)
  manifest = CompanionManifest(
    profile=profile or _profile(),
    memory_seeds=seeds if seeds is not None else _seeds(),
  )
  (pkg / "manifest.json").write_text(
    json.dumps(manifest.to_package_dict(), ensure_ascii=False), encoding="utf-8"
  )
  if with_live2d:
    mdir = pkg / "avatar" / "live2d" / "hiyori"
    mdir.mkdir(parents=True)
    (mdir / "hiyori.model3.json").write_text(
      json.dumps({"Version": 3, "FileReferences": {"Textures": []}}),
      encoding="utf-8",
    )
  return pkg


# ---------------------------------------------------------------------------
# seed_memory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_memory_writes_via_persona_manager():
  manager = FakePersonaManager()
  result = await seed_memory("小柚", _seeds(), persona_manager=manager)

  assert result["seeds_total"] == 2
  assert result["seeds_added"] == 2
  assert result["seeds_skipped"] == 0
  assert [c["entity"] for c in manager.calls] == ["neko", "relationship"]
  assert all(c["name"] == "小柚" for c in manager.calls)
  assert all(c["source"] == SEED_SOURCE for c in manager.calls)


@pytest.mark.asyncio
async def test_seed_memory_entity_fallback_and_empty_skip():
  manager = FakePersonaManager()
  seeds = [
    MemorySeed(entity="unknown_section", content="奇怪实体归入 neko。"),
    MemorySeed(entity="master", content="   "),
  ]
  result = await seed_memory("小柚", seeds, persona_manager=manager)

  # Unknown entity falls back to the companion's own section.
  assert manager.calls == [
    {"name": "小柚", "text": "奇怪实体归入 neko。", "entity": "neko",
     "source": SEED_SOURCE},
  ]
  assert result["seeds_added"] == 1
  assert result["seeds_skipped"] == 1
  assert result["seed_results"][1]["status"] == "empty"


@pytest.mark.asyncio
async def test_seed_memory_counts_non_added_statuses_as_skipped():
  manager = FakePersonaManager(statuses=["added", "queued", "rejected_card"])
  seeds = _seeds() + [MemorySeed(entity="neko", content="与角色卡矛盾的种子。")]
  result = await seed_memory("小柚", seeds, persona_manager=manager)

  assert result["seeds_added"] == 1
  assert result["seeds_skipped"] == 2
  assert [r["status"] for r in result["seed_results"]] == [
    "added", "queued", "rejected_card",
  ]


# ---------------------------------------------------------------------------
# bootstrap_from_artifact
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_from_artifact_seeds_resolved_memory_name(tmp_path):
  pkg = _write_package(tmp_path)
  profile = _profile(memory_character_name="记忆小柚")
  artifact = GenerationArtifact(
    task_id="t1",
    profile=profile,
    package_path=str(pkg),
    manifest_path=str(pkg / "manifest.json"),
  )
  manager = FakePersonaManager()
  result = await bootstrap_from_artifact(profile, artifact, persona_manager=manager)

  assert result["character_name"] == "记忆小柚"
  assert result["seeds_added"] == 2
  assert result["persona"] == profile.system_prompt
  assert result["package_path"] == str(pkg)
  assert all(c["name"] == "记忆小柚" for c in manager.calls)


@pytest.mark.asyncio
async def test_bootstrap_from_artifact_without_manifest_writes_nothing(tmp_path):
  profile = _profile()
  artifact = GenerationArtifact(
    task_id="t2",
    profile=profile,
    manifest_path=str(tmp_path / "missing" / "manifest.json"),
  )
  manager = FakePersonaManager()
  result = await bootstrap_from_artifact(profile, artifact, persona_manager=manager)

  assert result["seeds_total"] == 0
  assert manager.calls == []


def test_load_manifest_from_artifact_invalid_content_raises(tmp_path):
  bad = tmp_path / "manifest.json"
  bad.write_text("{\"version\": \"1.0\"}", encoding="utf-8")  # profile missing
  artifact = GenerationArtifact(
    task_id="t3", profile=_profile(), manifest_path=str(bad)
  )
  with pytest.raises(Exception):
    load_manifest_from_artifact(artifact)


# ---------------------------------------------------------------------------
# persona bridge: CompanionProfile <-> character card
# ---------------------------------------------------------------------------


def test_to_character_card_writes_reserved_fields():
  profile = _profile(
    avatar_resource_id="hiyori",
    voice=VoiceConfig(provider="free", voice_id="cute-girl-1"),
    metadata={"card_fields": {"性别": "女", "爱好": "陪主人学习"}},
  )
  card = CompanionPersonaBridge(profile).to_character_card()

  assert card["昵称"] == "小柚"
  assert card["性别"] == "女"
  assert card["爱好"] == "陪主人学习"
  reserved = card["_reserved"]
  assert reserved["system_prompt"] == profile.system_prompt
  assert reserved["voice_id"] == "cute-girl-1"
  assert reserved["avatar"]["model_type"] == "live2d"
  assert reserved["avatar"]["live2d"]["model_path"] == "hiyori"


def test_character_card_round_trip():
  original = _profile(
    avatar_resource_id="hiyori",
    voice=VoiceConfig(voice_id="v1"),
    metadata={"card_fields": {"性别": "女"}},
  )
  card = CompanionPersonaBridge(original).to_character_card()
  bridge = CompanionPersonaBridge.from_character_card("小柚", card)
  restored = bridge.profile

  assert restored.name == "小柚"
  assert restored.display_name == "小柚"
  assert restored.system_prompt == original.system_prompt
  assert restored.avatar_kind == AvatarKind.LIVE2D
  assert restored.avatar_resource_id == "hiyori"
  assert restored.voice.voice_id == "v1"
  assert restored.memory_character_name == "小柚"
  assert restored.metadata["card_fields"] == {"性别": "女"}
  # And back again: card body must be identical (bidirectional mapping).
  assert CompanionPersonaBridge(restored).to_character_card() == card


def test_from_character_card_reads_legacy_flat_fields():
  legacy_card = {
    "昵称": "兰兰",
    "system_prompt": "旧版扁平提示词",
    "voice_id": "legacy-voice",
    "model_type": "live2d",
    "live2d": "mao_pro",
  }
  profile = CompanionPersonaBridge.from_character_card("兰兰", legacy_card).profile

  assert profile.system_prompt == "旧版扁平提示词"
  assert profile.voice.voice_id == "legacy-voice"
  assert profile.avatar_kind == AvatarKind.LIVE2D
  assert profile.avatar_resource_id == "mao_pro"


def test_from_character_card_ignores_structured_voice_object():
  card = {"_reserved": {"voice_id": {"source": "clone", "ref": "abc"}}}
  profile = CompanionPersonaBridge.from_character_card("小柚", card).profile
  assert profile.voice.voice_id == ""


# ---------------------------------------------------------------------------
# register_character_card
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_character_card_saves_new_card():
  manager = FakeConfigManager()
  key = await register_character_card(_profile(), config_manager=manager)

  assert key == "小柚"
  saved_card = manager.saved["猫娘"]["小柚"]
  assert saved_card["_reserved"]["system_prompt"] == _profile().system_prompt


@pytest.mark.asyncio
async def test_register_character_card_resolves_name_conflict():
  manager = FakeConfigManager({"猫娘": {"小柚": {}, "小柚(1)": {}}})
  key = await register_character_card(_profile(), config_manager=manager)

  assert key == "小柚(2)"
  assert "小柚(2)" in manager.saved["猫娘"]


@pytest.mark.asyncio
async def test_register_character_card_rejects_invalid_name():
  with pytest.raises(CharacterCardError):
    await register_character_card(
      _profile(name="bad/name"), config_manager=FakeConfigManager()
    )


# ---------------------------------------------------------------------------
# POST /api/companion/import
# ---------------------------------------------------------------------------


@pytest.fixture()
def import_client(monkeypatch):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient

  import companion.ai.bootstrap as bootstrap_mod
  import companion.ai.persona as persona_mod
  import companion.api.routes as routes
  from companion.avatar.registry import AvatarRegistry

  persona_manager = FakePersonaManager()
  config_manager = FakeConfigManager({"猫娘": {"小柚": {}}})

  monkeypatch.setattr(
    bootstrap_mod, "_resolve_persona_manager", lambda: persona_manager
  )

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
  client.fake_config_manager = config_manager
  return client


def test_api_import_full_package(tmp_path, import_client):
  pkg = _write_package(tmp_path, with_live2d=True)
  res = import_client.post(
    "/api/companion/import", json={"package_path": str(pkg)}
  )
  assert res.status_code == 201
  body = res.json()

  # "小柚" already exists in the fake config -> conflict rename, and the
  # memory seeds must be keyed by the FINAL card key.
  assert body["character_name"] == "小柚(1)"
  assert body["memory"]["seeds_added"] == 2
  assert all(
    c["name"] == "小柚(1)" for c in import_client.fake_persona_manager.calls
  )
  assert "小柚(1)" in import_client.fake_config_manager.saved["猫娘"]
  assert body["avatar"]["slug"] == "hiyori"
  assert body["memory_server_reloaded"] is False


def test_api_import_without_character_registration(tmp_path, import_client):
  pkg = _write_package(tmp_path)
  res = import_client.post(
    "/api/companion/import",
    json={
      "package_path": str(pkg),
      "register_character": False,
      "load_avatar": False,
    },
  )
  assert res.status_code == 201
  body = res.json()
  assert body["character_name"] is None
  assert body["avatar"] is None
  # Memory keyed by the profile's own resolved name.
  assert all(
    c["name"] == "小柚" for c in import_client.fake_persona_manager.calls
  )
  assert import_client.fake_config_manager.saved is None


def test_api_import_package_without_avatar_still_seeds(tmp_path, import_client):
  pkg = _write_package(tmp_path, with_live2d=False)
  res = import_client.post(
    "/api/companion/import", json={"package_path": str(pkg)}
  )
  assert res.status_code == 201
  body = res.json()
  assert body["memory"]["seeds_added"] == 2
  assert body["avatar"] is None
  assert "no Live2D model" in body["avatar_error"]


def test_api_import_invalid_package(tmp_path, import_client):
  res = import_client.post(
    "/api/companion/import", json={"package_path": str(tmp_path / "nope")}
  )
  assert res.status_code == 422
  assert not import_client.fake_persona_manager.calls
