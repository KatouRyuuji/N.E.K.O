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

"""Creative workshop helpers for published ``.neko-companion`` packages."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from companion.generator.tasks import GenerationTask, TaskStatus


def _utcnow() -> str:
  return datetime.now(timezone.utc).isoformat()


def build_workshop_listing(task: GenerationTask) -> dict[str, Any]:
  if task.status != TaskStatus.COMPLETED or task.artifact is None:
    raise ValueError("task has no publishable artifact")
  profile = task.artifact.profile
  return {
    "task_id": task.id,
    "companion_id": profile.id,
    "name": profile.name,
    "display_name": profile.display_name,
    "locale": profile.locale,
    "package_path": task.artifact.package_path,
    "published_at": _utcnow(),
    "tags": ["companion", "generated"],
    "generator": task.artifact.analysis_summary.get("llm", {}),
  }


def export_workshop_bundle(
  task: GenerationTask,
  *,
  output_root: Path,
) -> Path:
  """Copy a completed package into the workshop export directory."""
  listing = build_workshop_listing(task)
  dest = output_root / f"{listing['companion_id']}_{task.id[:8]}"
  src = Path(task.artifact.package_path)  # type: ignore[union-attr]
  if dest.exists():
    shutil.rmtree(dest)
  shutil.copytree(src, dest)
  (dest / "workshop.json").write_text(
    json.dumps(listing, ensure_ascii=False, indent=2),
    encoding="utf-8",
  )
  return dest


def scan_workshop_catalog(root: Path) -> list[dict[str, Any]]:
  if not root.is_dir():
    return []
  entries: list[dict[str, Any]] = []
  for child in sorted(root.iterdir()):
    if not child.is_dir():
      continue
    meta_path = child / "workshop.json"
    if not meta_path.is_file():
      continue
    try:
      entries.append(json.loads(meta_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
      continue
  entries.sort(key=lambda e: e.get("published_at", ""), reverse=True)
  return entries
