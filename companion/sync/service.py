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

"""Sync protocol services (Phase 5 M6) — read-only, desktop-authoritative.

Two blocking (worker-thread) building blocks behind the
``/api/companion/sync/*`` routes:

- :func:`build_sync_manifest` — a device-level snapshot listing every
  registered companion as a ``.neko-companion`` manifest (the protocol's
  exchange unit) plus its current memory cursor;
- :func:`memory_delta` — an idempotent, cursor-paginated incremental read
  of one companion's fact-layer memory, keyed by the fact store's existing
  time index (``created_at``) with the fact ``id`` as tie-breaker.

Everything here is a **read**: no file is created or mutated, so the
functions are safe to point at a live memory directory while the memory
subsystem is writing (facts.json writes are atomic-rename). Conflict
resolution is intentionally out of scope — the desktop instance that
serves these endpoints is authoritative (see SYNC_PROTOCOL.md §5).
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from typing import Any

PROTOCOL_VERSION = "1.0"
EXCHANGE_UNIT = ".neko-companion"
CONFLICT_STRATEGY = "desktop-authoritative"

# Composite cursor: "<created_at ISO>|<fact_id>". Neither component may
# contain "|": created_at is datetime.isoformat(), fact ids are
# "fact_<ts>_<hash8>" / "manual_..." shaped.
CURSOR_SEPARATOR = "|"

DEFAULT_PAGE_LIMIT = 500
MAX_PAGE_LIMIT = 2000

# Portable fact fields — device-independent content only. Derived caches
# (embedding, token_count, refine stamps) and local pipeline state are
# deliberately excluded: they are recomputed by the receiving instance.
_FACT_PORTABLE_FIELDS = (
  "id",
  "text",
  "entity",
  "importance",
  "source",
  "created_at",
  "event_when_raw",
  "event_start_at",
  "event_end_at",
)

# Portable persona-entry fields — same rationale as facts. Evidence
# counters and caches stay on the authoritative desktop.
_PERSONA_PORTABLE_FIELDS = ("id", "text", "source", "source_id", "protected")


class UnknownCompanionError(LookupError):
  """Requested character has no card in characters.json."""


def _resolve_config_manager():
  """Deferred so importing this module never touches the user data dir.

  Tests monkeypatch this hook with an object exposing ``load_characters()``
  and ``memory_dir``.
  """
  from utils.config_manager import get_config_manager

  return get_config_manager()


def _catgirl_cards(characters: dict) -> dict:
  cards = characters.get("猫娘") if isinstance(characters, dict) else None
  return cards if isinstance(cards, dict) else {}


def _read_json(path: str) -> Any:
  """Best-effort read-only JSON load; missing/corrupt file degrades to None."""
  if not os.path.isfile(path):
    return None
  try:
    with open(path, encoding="utf-8") as f:
      return json.load(f)
  except (json.JSONDecodeError, UnicodeDecodeError, OSError):
    return None


def _character_file(memory_dir, name: str, filename: str) -> str:
  """Join without creating directories (read-only — unlike ensure_character_dir)."""
  return os.path.join(str(memory_dir), name, filename)


def _load_fact_layer(memory_dir, name: str) -> list[dict]:
  data = _read_json(_character_file(memory_dir, name, "facts.json"))
  if not isinstance(data, list):
    return []
  return [f for f in data if isinstance(f, dict)]


def _load_persona_layer(memory_dir, name: str) -> dict:
  data = _read_json(_character_file(memory_dir, name, "persona.json"))
  return data if isinstance(data, dict) else {}


# ── cursor semantics ────────────────────────────────────────────────


def fact_sort_key(fact: dict) -> tuple[str, str]:
  """Stable time-index order: (created_at ISO, fact id).

  ``created_at`` is the fact store's time-index anchor (ISO strings sort
  chronologically); the id disambiguates same-instant facts so the cursor
  is a strict total order and pagination never skips or repeats rows.
  """
  return (str(fact.get("created_at") or ""), str(fact.get("id") or ""))


def fact_cursor(fact: dict) -> str:
  created_at, fact_id = fact_sort_key(fact)
  return f"{created_at}{CURSOR_SEPARATOR}{fact_id}"


def parse_cursor(since: str | None) -> tuple[str, str] | None:
  """Decode a ``since`` value into a comparable (created_at, id) tuple.

  Accepts either the opaque composite cursor returned in ``next_cursor``
  (exactly-once resume) or a plain ISO timestamp (at-least-once resume:
  facts stamped exactly at that instant are re-sent). Empty/None means a
  full bootstrap fetch.
  """
  if not since:
    return None
  if CURSOR_SEPARATOR in since:
    created_at, _, fact_id = since.partition(CURSOR_SEPARATOR)
    return (created_at, fact_id)
  return (since, "")


# ── portable views ──────────────────────────────────────────────────


def _portable_fact(fact: dict) -> dict:
  return {k: fact[k] for k in _FACT_PORTABLE_FIELDS if k in fact}


def _portable_persona(persona: dict) -> dict:
  """Entity sections reduced to portable entries, sorted by id.

  Sorting makes the digest independent of on-disk entry order, so two
  instances holding the same content agree on the digest.
  """
  portable: dict[str, list[dict]] = {}
  for entity, section in sorted(persona.items()):
    if not isinstance(section, dict):
      continue
    entries = []
    for entry in section.get("facts", []):
      if isinstance(entry, dict):
        entries.append({k: entry[k] for k in _PERSONA_PORTABLE_FIELDS if k in entry})
      else:
        entries.append({"id": "", "text": str(entry)})
    entries.sort(key=lambda e: (str(e.get("id") or ""), str(e.get("text") or "")))
    portable[entity] = entries
  return portable


def persona_digest(portable_persona: dict) -> str:
  canonical = json.dumps(
    portable_persona, sort_keys=True, ensure_ascii=False, separators=(",", ":")
  )
  return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _memory_summary(memory_dir, name: str) -> dict:
  facts = sorted(_load_fact_layer(memory_dir, name), key=fact_sort_key)
  portable = _portable_persona(_load_persona_layer(memory_dir, name))
  return {
    "fact_count": len(facts),
    "fact_cursor": fact_cursor(facts[-1]) if facts else "",
    "persona_digest": persona_digest(portable),
    "persona_entry_count": sum(len(v) for v in portable.values()),
  }


# ── public API ──────────────────────────────────────────────────────


def build_sync_manifest(config_manager=None) -> dict:
  """Device-level sync snapshot: one ``.neko-companion`` manifest per card.

  Each registered character card is rendered back into a
  :class:`CompanionManifest` via the persona bridge — the same shape a
  package ``manifest.json`` carries — so a peer can import the companion
  through the existing ``POST /api/companion/import`` path. Memory seeds
  stay empty on purpose: live memory travels through the delta endpoint,
  not through import-time seeds.
  """
  from companion.ai.persona import CompanionPersonaBridge
  from companion.models.manifest import CompanionManifest

  cm = config_manager if config_manager is not None else _resolve_config_manager()
  cards = _catgirl_cards(cm.load_characters())
  memory_dir = cm.memory_dir

  companions = []
  for name in sorted(cards):
    card = cards[name]
    if not isinstance(card, dict):
      continue
    bridge = CompanionPersonaBridge.from_character_card(name, card)
    manifest = CompanionManifest(profile=bridge.profile)
    companions.append(
      {
        "name": name,
        "manifest": manifest.to_package_dict(),
        "memory": _memory_summary(memory_dir, name),
      }
    )

  return {
    "protocol": {
      "version": PROTOCOL_VERSION,
      "exchange_unit": EXCHANGE_UNIT,
      "conflict_strategy": CONFLICT_STRATEGY,
    },
    "generated_at": datetime.now().isoformat(),
    "companions": companions,
  }


def memory_delta(
  name: str,
  since: str | None = "",
  limit: int = DEFAULT_PAGE_LIMIT,
  include_persona: bool = False,
  config_manager=None,
) -> dict:
  """Idempotent incremental read of one companion's fact-layer memory.

  Returns every fact strictly **after** the ``since`` cursor in
  (created_at, id) order, capped at ``limit`` rows (``has_more`` signals a
  truncated page). ``next_cursor`` always points at the last row shipped —
  or echoes the normalized request cursor when nothing new exists — so
  re-fetching with an unchanged store yields byte-identical responses and
  draining with ``next_cursor`` converges to an empty page.

  The persona layer has no per-entry timestamps, so it syncs as a
  digest-compared snapshot instead of a delta: ``persona.digest`` is always
  present, the full portable snapshot only with ``include_persona``.
  """
  cm = config_manager if config_manager is not None else _resolve_config_manager()
  cards = _catgirl_cards(cm.load_characters())
  if name not in cards:
    raise UnknownCompanionError(name)

  limit = max(1, min(int(limit), MAX_PAGE_LIMIT))
  cursor = parse_cursor(since)
  facts = sorted(_load_fact_layer(cm.memory_dir, name), key=fact_sort_key)
  if cursor is not None:
    facts = [f for f in facts if fact_sort_key(f) > cursor]

  page = facts[:limit]
  has_more = len(facts) > len(page)
  if page:
    next_cursor = fact_cursor(page[-1])
  elif cursor is not None:
    next_cursor = f"{cursor[0]}{CURSOR_SEPARATOR}{cursor[1]}" if cursor[1] else cursor[0]
  else:
    next_cursor = ""

  portable_persona = _portable_persona(_load_persona_layer(cm.memory_dir, name))
  result: dict[str, Any] = {
    "name": name,
    "since": since or "",
    "count": len(page),
    "has_more": has_more,
    "next_cursor": next_cursor,
    "facts": [_portable_fact(f) for f in page],
    "persona": {
      "digest": persona_digest(portable_persona),
      "entry_count": sum(len(v) for v in portable_persona.values()),
    },
  }
  if include_persona:
    result["persona"]["entities"] = portable_persona
  return result
