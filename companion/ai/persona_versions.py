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

"""Character-card version chain (Phase 5 M4).

Before a companion write path (refine apply / rollback) replaces a
characters.json card, the previous card body is snapshotted into a per
character backup file::

    <docs_dir>/N.E.K.O/companions/persona_versions/<card_key>.json

    {"name": "<card_key>", "versions": [
        {"version": 1, "saved_at": "...", "reason": "refine_apply",
         "card": {...full card body...}},
        ...
    ]}

The chain is capped at ``COMPANION_PERSONA_VERSION_MAX_SNAPSHOTS`` (oldest
dropped first). The card body includes the ``_reserved`` section, so a
rollback restores system_prompt / voice_id / avatar binding together with
the user-visible fields — and because the card **key** never changes, the
memory files keyed by the character name (persona.json / facts.json) stay
consistent with the restored card.

All functions are synchronous file IO: async callers (API routes) must
offload with ``asyncio.to_thread``. Card keys are only ever taken from
characters.json (validated by ``validate_character_name`` at registration),
so they are safe as file names; callers must verify card existence before
touching the chain.

Everything is written through ``atomic_write_json`` so a crash mid-write
never truncates the chain.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from config import COMPANION_PERSONA_VERSION_MAX_SNAPSHOTS
from utils.file_utils import atomic_write_json
from utils.logger_config import get_module_logger

logger = get_module_logger(__name__)


def _default_root() -> Path:
  from utils.config_manager import get_config_manager

  root = (
    Path(get_config_manager().docs_dir)
    / "N.E.K.O" / "companions" / "persona_versions"
  )
  root.mkdir(parents=True, exist_ok=True)
  return root


def _chain_path(name: str, root: Path | None = None) -> Path:
  return (root or _default_root()) / f"{name}.json"


def _load_chain(name: str, root: Path | None = None) -> dict:
  path = _chain_path(name, root)
  if not path.is_file():
    return {"name": name, "versions": []}
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
  except (OSError, ValueError):
    logger.warning("Persona version chain unreadable for %r, starting fresh", name)
    return {"name": name, "versions": []}
  if not isinstance(data, dict) or not isinstance(data.get("versions"), list):
    return {"name": name, "versions": []}
  return data


def snapshot_card(
  name: str, card: dict, *, reason: str = "update", root: Path | None = None
) -> dict:
  """Append the current card body to the version chain; return the entry meta."""
  chain = _load_chain(name, root)
  versions = chain["versions"]
  next_version = (versions[-1]["version"] + 1) if versions else 1
  entry = {
    "version": next_version,
    "saved_at": datetime.now().isoformat(),
    "reason": reason,
    "card": card,
  }
  versions.append(entry)
  if len(versions) > COMPANION_PERSONA_VERSION_MAX_SNAPSHOTS:
    del versions[: len(versions) - COMPANION_PERSONA_VERSION_MAX_SNAPSHOTS]
  atomic_write_json(str(_chain_path(name, root)), chain, ensure_ascii=False, indent=2)
  return {"version": entry["version"], "saved_at": entry["saved_at"], "reason": reason}


def list_versions(name: str, root: Path | None = None) -> list[dict]:
  """Version metadata (no card bodies), oldest first."""
  return [
    {
      "version": v.get("version"),
      "saved_at": v.get("saved_at"),
      "reason": v.get("reason"),
    }
    for v in _load_chain(name, root)["versions"]
  ]


def get_version(name: str, version: int, root: Path | None = None) -> dict | None:
  """Full snapshot entry (including the card body) for one version."""
  for v in _load_chain(name, root)["versions"]:
    if v.get("version") == version:
      return v
  return None


def latest_version(name: str, root: Path | None = None) -> dict | None:
  versions = _load_chain(name, root)["versions"]
  return versions[-1] if versions else None


__all__ = [
  "get_version",
  "latest_version",
  "list_versions",
  "snapshot_card",
]
