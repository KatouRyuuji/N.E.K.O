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

"""Bootstrap companion memory from a generation artifact.

Persona memory seeds are written through :class:`memory.persona.manager.
PersonaManager` — the canonical persona write path (contradiction check +
per-character lock + atomic ``persona.json`` write). No bespoke file format
is duplicated here.

Manager resolution honors the merged single-process architecture
(main/memory/agent share one FastAPI process): when the memory subsystem is
booted, its **live** ``PersonaManager`` instance is used so the server's
in-memory persona cache stays coherent with our writes; otherwise (unit
tests, standalone tooling, memory subsystem not yet initialized) a
standalone manager writes the same on-disk files, which the memory server
picks up on its next load / ``/reload``.
"""

from __future__ import annotations

import json
from pathlib import Path

from companion.models.generation import GenerationArtifact
from companion.models.manifest import CompanionManifest, MemorySeed
from companion.models.profile import CompanionProfile

# `source` recorded on every seeded persona entry, so seeds are
# distinguishable from conversation-derived facts in persona.json.
SEED_SOURCE = "companion_seed"

# PersonaManager entity sections (see memory/persona/manager.py docstring).
VALID_SEED_ENTITIES = frozenset({"master", "neko", "relationship"})
_DEFAULT_SEED_ENTITY = "neko"


def load_manifest_from_artifact(
  artifact: GenerationArtifact,
) -> CompanionManifest | None:
  """Load the package manifest referenced by a generation artifact.

  Returns ``None`` when the artifact has no manifest on disk (e.g. a failed
  generation); invalid manifest content raises so callers never silently
  seed nothing from a corrupt package.
  """
  manifest_path = Path(artifact.manifest_path)
  if not manifest_path.is_file():
    return None
  return CompanionManifest.model_validate(
    json.loads(manifest_path.read_text(encoding="utf-8"))
  )


def _resolve_persona_manager():
  """Return the persona manager to write seeds through.

  Prefer the live memory_server instance (same process, shared in-memory
  cache); fall back to a standalone ``PersonaManager`` over the same files.
  """
  try:
    from app.memory_server import runtime as memory_runtime

    manager = getattr(memory_runtime, "persona_manager", None)
    if manager is not None:
      return manager
  except Exception:
    # Memory subsystem not importable/booted in this context (tests,
    # standalone tools) — the standalone fallback below still writes the
    # canonical on-disk format.
    pass
  from memory.persona.manager import PersonaManager

  return PersonaManager()


async def seed_memory(
  character_name: str,
  seeds: list[MemorySeed],
  persona_manager=None,
) -> dict:
  """Write persona memory seeds for ``character_name`` into the memory service.

  Each seed becomes one persona entry via ``PersonaManager.aadd_fact``;
  unknown entities fall back to the companion's own section (``neko``).
  Returns a summary with per-seed outcomes (``added`` / ``queued`` /
  ``rejected_card`` / ``empty``).
  """
  manager = persona_manager if persona_manager is not None else _resolve_persona_manager()
  added_code = getattr(manager, "FACT_ADDED", "added")

  seed_results: list[dict] = []
  added = 0
  skipped = 0
  for seed in seeds:
    entity = seed.entity if seed.entity in VALID_SEED_ENTITIES else _DEFAULT_SEED_ENTITY
    content = seed.content.strip()
    if not content:
      skipped += 1
      seed_results.append({"entity": entity, "status": "empty"})
      continue
    status = await manager.aadd_fact(
      character_name, content, entity=entity, source=SEED_SOURCE
    )
    if status == added_code:
      added += 1
    else:
      skipped += 1
    seed_results.append({"entity": entity, "status": status})

  return {
    "character_name": character_name,
    "seeds_total": len(seeds),
    "seeds_added": added,
    "seeds_skipped": skipped,
    "seed_results": seed_results,
  }


async def bootstrap_from_artifact(
  profile: CompanionProfile,
  artifact: GenerationArtifact,
  persona_manager=None,
) -> dict:
  """Seed the memory service from a completed generation artifact."""
  manifest = load_manifest_from_artifact(artifact)
  seeds = list(manifest.memory_seeds) if manifest is not None else []
  result = await seed_memory(
    profile.resolved_memory_name(), seeds, persona_manager=persona_manager
  )
  result["persona"] = profile.system_prompt
  result["package_path"] = artifact.package_path
  return result
