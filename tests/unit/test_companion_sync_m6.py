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

"""Unit tests for Phase 5 M6: sync manifest + idempotent memory delta."""

import copy
import json
import os

import pytest

import companion.sync.service as sync_service
from companion.sync.service import (
  CONFLICT_STRATEGY,
  EXCHANGE_UNIT,
  PROTOCOL_VERSION,
  UnknownCompanionError,
  build_sync_manifest,
  fact_cursor,
  memory_delta,
)

NAME = "小柚"


class FakeSyncConfigManager:
  """Duck-typed stand-in: load_characters() + memory_dir."""

  def __init__(self, characters, memory_dir):
    self.characters = characters
    self.memory_dir = str(memory_dir)

  def load_characters(self):
    return copy.deepcopy(self.characters)


def _fact(n: int, created_at: str, **overrides) -> dict:
  base = {
    "id": f"fact_20260825_{n:08d}",
    "text": f"事实 {n}",
    "entity": "master",
    "importance": 5,
    "source": "conversation",
    "created_at": created_at,
    # Device-local pipeline state / derived caches that must NOT sync:
    "absorbed": False,
    "signal_processed": False,
    "embedding": [0.1] * 8,
    "token_count": 12,
  }
  base.update(overrides)
  return base


def _default_facts() -> list[dict]:
  return [
    _fact(1, "2026-08-25T10:00:00.000001"),
    _fact(2, "2026-08-25T10:00:00.000001"),  # same instant — id tie-break
    _fact(3, "2026-08-25T11:30:00.500000"),
  ]


def _persona() -> dict:
  return {
    "neko": {
      "facts": [
        {
          "id": "card_001",
          "text": "小柚是温柔的猫娘。",
          "source": "character_card",
          "source_id": None,
          "protected": True,
          "token_count": 9,
          "embedding": [0.2] * 8,
        }
      ]
    },
    "master": {
      "facts": [
        {
          "id": "manual_20260825_0001",
          "text": "主人喜欢抹茶拿铁。",
          "source": "manual",
          "source_id": None,
          "protected": False,
        }
      ]
    },
  }


def _write_store(memory_dir, name=NAME, facts=None, persona=None):
  char_dir = os.path.join(str(memory_dir), name)
  os.makedirs(char_dir, exist_ok=True)
  if facts is not None:
    with open(os.path.join(char_dir, "facts.json"), "w", encoding="utf-8") as f:
      json.dump(facts, f, ensure_ascii=False)
  if persona is not None:
    with open(os.path.join(char_dir, "persona.json"), "w", encoding="utf-8") as f:
      json.dump(persona, f, ensure_ascii=False)


def _manager(tmp_path, facts=None, persona=None, characters=None):
  memory_dir = tmp_path / "memory"
  memory_dir.mkdir(exist_ok=True)
  if facts is not None or persona is not None:
    _write_store(memory_dir, facts=facts, persona=persona)
  characters = characters if characters is not None else {"猫娘": {NAME: {"昵称": NAME}}}
  return FakeSyncConfigManager(characters, memory_dir)


# ---------------------------------------------------------------------------
# GET /sync/manifest — shape
# ---------------------------------------------------------------------------


def test_manifest_protocol_block_and_exchange_unit(tmp_path):
  cm = _manager(tmp_path, facts=_default_facts(), persona=_persona())
  snapshot = build_sync_manifest(config_manager=cm)

  assert snapshot["protocol"] == {
    "version": PROTOCOL_VERSION,
    "exchange_unit": EXCHANGE_UNIT,
    "conflict_strategy": CONFLICT_STRATEGY,
  }
  assert EXCHANGE_UNIT == ".neko-companion"
  assert CONFLICT_STRATEGY == "desktop-authoritative"
  assert snapshot["generated_at"]

  (entry,) = snapshot["companions"]
  assert entry["name"] == NAME
  # The manifest field is the `.neko-companion` manifest.json shape.
  manifest = entry["manifest"]
  assert manifest["version"] == "1.0"
  assert manifest["profile"]["name"] == NAME
  assert manifest["profile"]["memory_character_name"] == NAME
  # Live memory travels through the delta endpoint, never as seeds.
  assert manifest["memory_seeds"] == []


def test_manifest_memory_cursor_and_counts(tmp_path):
  facts = _default_facts()
  cm = _manager(tmp_path, facts=facts, persona=_persona())
  (entry,) = build_sync_manifest(config_manager=cm)["companions"]

  memory = entry["memory"]
  assert memory["fact_count"] == 3
  # Cursor points at the chronologically last fact.
  assert memory["fact_cursor"] == fact_cursor(facts[2])
  assert memory["fact_cursor"] == "2026-08-25T11:30:00.500000|fact_20260825_00000003"
  assert memory["persona_digest"].startswith("sha256:")
  assert memory["persona_entry_count"] == 2


def test_manifest_without_memory_files_or_characters(tmp_path):
  # Registered card but no memory dir yet — empty cursor, digest still stable.
  cm = _manager(tmp_path)
  (entry,) = build_sync_manifest(config_manager=cm)["companions"]
  assert entry["memory"]["fact_count"] == 0
  assert entry["memory"]["fact_cursor"] == ""

  empty = FakeSyncConfigManager({}, tmp_path / "memory")
  assert build_sync_manifest(config_manager=empty)["companions"] == []


# ---------------------------------------------------------------------------
# GET /sync/memory/{name} — cursor semantics + idempotency
# ---------------------------------------------------------------------------


def test_delta_full_bootstrap_is_sorted_and_cursored(tmp_path):
  facts = _default_facts()
  cm = _manager(tmp_path, facts=list(reversed(facts)))  # on-disk order shuffled
  delta = memory_delta(NAME, since="", config_manager=cm)

  assert delta["count"] == 3
  assert delta["has_more"] is False
  assert [f["id"] for f in delta["facts"]] == [
    "fact_20260825_00000001",
    "fact_20260825_00000002",
    "fact_20260825_00000003",
  ]
  assert delta["next_cursor"] == fact_cursor(facts[2])


def test_delta_same_since_is_idempotent(tmp_path):
  cm = _manager(tmp_path, facts=_default_facts(), persona=_persona())

  first = memory_delta(NAME, since="", config_manager=cm)
  second = memory_delta(NAME, since="", config_manager=cm)
  assert first == second

  mid_cursor = first["facts"][0]["created_at"] + "|" + first["facts"][0]["id"]
  a = memory_delta(NAME, since=mid_cursor, config_manager=cm)
  b = memory_delta(NAME, since=mid_cursor, config_manager=cm)
  assert a == b
  assert [f["id"] for f in a["facts"]] == [
    "fact_20260825_00000002",
    "fact_20260825_00000003",
  ]


def test_delta_drain_returns_empty_page_and_echoes_cursor(tmp_path):
  cm = _manager(tmp_path, facts=_default_facts())
  full = memory_delta(NAME, since="", config_manager=cm)

  drained = memory_delta(NAME, since=full["next_cursor"], config_manager=cm)
  assert drained["count"] == 0
  assert drained["facts"] == []
  assert drained["has_more"] is False
  # Cursor is echoed back unchanged — repeated polling never drifts.
  assert drained["next_cursor"] == full["next_cursor"]
  again = memory_delta(NAME, since=drained["next_cursor"], config_manager=cm)
  assert again == drained


def test_delta_only_ships_facts_after_cursor(tmp_path):
  facts = _default_facts()
  cm = _manager(tmp_path, facts=facts)
  cursor = memory_delta(NAME, since="", config_manager=cm)["next_cursor"]

  # A new fact lands on the desktop instance.
  new_fact = _fact(4, "2026-08-25T12:00:00.000000", text="新增事实")
  _write_store(cm.memory_dir, facts=facts + [new_fact])

  delta = memory_delta(NAME, since=cursor, config_manager=cm)
  assert [f["id"] for f in delta["facts"]] == ["fact_20260825_00000004"]
  assert delta["next_cursor"] == fact_cursor(new_fact)


def test_delta_plain_timestamp_since_is_at_least_once(tmp_path):
  cm = _manager(tmp_path, facts=_default_facts())
  # Plain ISO timestamp == (ts, ""): facts stamped exactly at that instant
  # are re-sent (at-least-once), later ones always included.
  delta = memory_delta(
    NAME, since="2026-08-25T10:00:00.000001", config_manager=cm
  )
  assert [f["id"] for f in delta["facts"]] == [
    "fact_20260825_00000001",
    "fact_20260825_00000002",
    "fact_20260825_00000003",
  ]
  later = memory_delta(NAME, since="2026-08-25T11:00:00", config_manager=cm)
  assert [f["id"] for f in later["facts"]] == ["fact_20260825_00000003"]


def test_delta_pagination_never_skips_or_repeats(tmp_path):
  facts = [
    _fact(n, f"2026-08-25T10:00:00.{n:06d}") for n in range(1, 8)
  ]
  cm = _manager(tmp_path, facts=facts)

  seen: list[str] = []
  cursor = ""
  pages = 0
  while True:
    page = memory_delta(NAME, since=cursor, limit=3, config_manager=cm)
    seen.extend(f["id"] for f in page["facts"])
    pages += 1
    if not page["has_more"]:
      break
    cursor = page["next_cursor"]

  assert pages == 3
  assert seen == [f["id"] for f in facts]
  assert len(set(seen)) == len(seen)


def test_delta_ships_portable_fields_only(tmp_path):
  cm = _manager(tmp_path, facts=_default_facts(), persona=_persona())
  delta = memory_delta(NAME, since="", include_persona=True, config_manager=cm)

  for fact in delta["facts"]:
    assert "embedding" not in fact
    assert "token_count" not in fact
    assert "absorbed" not in fact
    assert "signal_processed" not in fact
    assert fact["created_at"]
  for entries in delta["persona"]["entities"].values():
    for entry in entries:
      assert "embedding" not in entry
      assert "token_count" not in entry


def test_delta_unknown_companion_raises(tmp_path):
  cm = _manager(tmp_path, facts=_default_facts())
  with pytest.raises(UnknownCompanionError):
    memory_delta("不存在的猫娘", since="", config_manager=cm)


def test_delta_limit_is_clamped(tmp_path):
  cm = _manager(tmp_path, facts=_default_facts())
  delta = memory_delta(NAME, since="", limit=0, config_manager=cm)
  assert delta["count"] == 1  # clamped up to 1
  assert delta["has_more"] is True


# ---------------------------------------------------------------------------
# persona snapshot digest
# ---------------------------------------------------------------------------


def test_persona_digest_ignores_volatile_fields_and_order(tmp_path):
  cm_a = _manager(tmp_path / "a", facts=[], persona=_persona())
  digest_a = memory_delta(NAME, since="", config_manager=cm_a)["persona"]["digest"]

  # Same content, different entry order + mutated device-local caches.
  shuffled = _persona()
  shuffled["neko"]["facts"][0]["token_count"] = 999
  shuffled["neko"]["facts"][0]["embedding"] = None
  reordered = {"master": shuffled["master"], "neko": shuffled["neko"]}
  cm_b = _manager(tmp_path / "b", facts=[], persona=reordered)
  digest_b = memory_delta(NAME, since="", config_manager=cm_b)["persona"]["digest"]
  assert digest_a == digest_b

  # Content change flips the digest.
  changed = _persona()
  changed["master"]["facts"][0]["text"] = "主人换口味了。"
  cm_c = _manager(tmp_path / "c", facts=[], persona=changed)
  digest_c = memory_delta(NAME, since="", config_manager=cm_c)["persona"]["digest"]
  assert digest_c != digest_a


def test_delta_include_persona_returns_portable_snapshot(tmp_path):
  cm = _manager(tmp_path, facts=[], persona=_persona())
  slim = memory_delta(NAME, since="", config_manager=cm)
  assert "entities" not in slim["persona"]

  full = memory_delta(NAME, since="", include_persona=True, config_manager=cm)
  entities = full["persona"]["entities"]
  assert set(entities) == {"neko", "master"}
  assert entities["neko"][0]["protected"] is True
  assert full["persona"]["entry_count"] == 2


# ---------------------------------------------------------------------------
# two desktop instances: manifest + delta round trip
# ---------------------------------------------------------------------------


def test_two_instance_roundtrip_converges(tmp_path):
  """Instance B rebuilds A's companion from sync payloads; re-exports agree."""
  from companion.ai.persona import CompanionPersonaBridge
  from companion.models.profile import CompanionProfile

  # Instance A: registered card + live memory.
  card = {"昵称": NAME, "_reserved": {"system_prompt": "你是小柚。"}}
  cm_a = _manager(
    tmp_path / "a",
    facts=_default_facts(),
    persona=_persona(),
    characters={"猫娘": {NAME: card}},
  )
  snapshot_a = build_sync_manifest(config_manager=cm_a)
  (entry_a,) = snapshot_a["companions"]
  delta_a = memory_delta(NAME, since="", include_persona=True, config_manager=cm_a)
  assert delta_a["has_more"] is False

  # Instance B: register the manifest profile as its own card, then land
  # the portable facts / persona snapshot as its local memory files.
  profile = CompanionProfile(**entry_a["manifest"]["profile"])
  card_b = CompanionPersonaBridge(profile).to_character_card()
  persona_b = {
    entity: {"facts": entries}
    for entity, entries in delta_a["persona"]["entities"].items()
  }
  cm_b = _manager(
    tmp_path / "b",
    facts=delta_a["facts"],
    persona=persona_b,
    characters={"猫娘": {NAME: card_b}},
  )

  # B's own sync view converges with A's: same cursor, same digest.
  (entry_b,) = build_sync_manifest(config_manager=cm_b)["companions"]
  assert entry_b["memory"]["fact_cursor"] == entry_a["memory"]["fact_cursor"]
  assert entry_b["memory"]["fact_count"] == entry_a["memory"]["fact_count"]
  assert entry_b["memory"]["persona_digest"] == entry_a["memory"]["persona_digest"]

  # And a delta fetched from B is fact-for-fact identical to A's.
  delta_b = memory_delta(NAME, since="", config_manager=cm_b)
  assert delta_b["facts"] == delta_a["facts"]
  # Draining B with A's cursor is an empty page — nothing left to move.
  drained = memory_delta(
    NAME, since=entry_a["memory"]["fact_cursor"], config_manager=cm_b
  )
  assert drained["count"] == 0


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


@pytest.fixture()
def sync_client(tmp_path, monkeypatch):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient

  import companion.api.routes as routes

  cm = _manager(tmp_path, facts=_default_facts(), persona=_persona())
  monkeypatch.setattr(sync_service, "_resolve_config_manager", lambda: cm)

  app = FastAPI()
  app.include_router(routes.router)
  return TestClient(app)


def test_api_sync_manifest(sync_client):
  res = sync_client.get("/api/companion/sync/manifest")
  assert res.status_code == 200
  body = res.json()
  assert body["protocol"]["conflict_strategy"] == "desktop-authoritative"
  assert body["companions"][0]["name"] == NAME


def test_api_sync_memory_delta_idempotent(sync_client):
  first = sync_client.get(f"/api/companion/sync/memory/{NAME}", params={"since": ""})
  assert first.status_code == 200
  again = sync_client.get(f"/api/companion/sync/memory/{NAME}", params={"since": ""})
  assert first.json() == again.json()

  cursor = first.json()["next_cursor"]
  drained = sync_client.get(
    f"/api/companion/sync/memory/{NAME}", params={"since": cursor}
  )
  assert drained.status_code == 200
  assert drained.json()["count"] == 0
  assert drained.json()["next_cursor"] == cursor


def test_api_sync_memory_unknown_404(sync_client):
  res = sync_client.get("/api/companion/sync/memory/幽灵角色")
  assert res.status_code == 404
