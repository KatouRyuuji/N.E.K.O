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


def _cover_relative_path(package_dir: Path) -> str | None:
  manifest_path = package_dir / "manifest.json"
  if not manifest_path.is_file():
    return None
  try:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError):
    return None
  paths = data.get("resource_paths") or {}
  images = str(paths.get("reference_images") or "").strip()
  if not images:
    return None
  first = images.split(",")[0].strip()
  if not first:
    return None
  candidate = Path(first)
  if candidate.is_file():
    try:
      return str(candidate.relative_to(package_dir))
    except ValueError:
      return None
  # Stored as path relative to package
  rel = package_dir / first
  if rel.is_file():
    return first
  return None


def build_workshop_listing(task: GenerationTask) -> dict[str, Any]:
  if task.status != TaskStatus.COMPLETED or task.artifact is None:
    raise ValueError("task has no publishable artifact")
  profile = task.artifact.profile
  package_dir = Path(task.artifact.package_path)
  analysis = task.artifact.analysis_summary or {}
  llm = analysis.get("llm") or {}
  summary = ""
  if isinstance(analysis, dict):
    summary = str(analysis.get("summary") or "")[:280]
  cover = _cover_relative_path(package_dir)
  tags = ["companion", "generated"]
  if llm.get("provider"):
    tags.append(str(llm["provider"]))
  return {
    "task_id": task.id,
    "companion_id": profile.id,
    "name": profile.name,
    "display_name": profile.display_name,
    "locale": profile.locale,
    "package_path": task.artifact.package_path,
    "published_at": _utcnow(),
    "tags": tags,
    "summary": summary,
    "cover_relative": cover,
    "generator": llm,
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
      meta = json.loads(meta_path.read_text(encoding="utf-8"))
      meta = dict(meta)
      meta["catalog_id"] = child.name
      meta["export_path"] = str(child)
      rel = meta.get("cover_relative")
      if rel and (child / rel).is_file():
        meta["cover_url"] = f"/api/companion/workshop/asset/{child.name}/{rel}"
      entries.append(meta)
    except (OSError, json.JSONDecodeError):
      continue
  entries.sort(key=lambda e: e.get("published_at", ""), reverse=True)
  return entries


def find_workshop_entry(root: Path, catalog_id: str) -> dict[str, Any] | None:
  for entry in scan_workshop_catalog(root):
    if entry.get("catalog_id") == catalog_id:
      return entry
  return None
