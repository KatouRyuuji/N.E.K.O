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

"""Load Live2D avatars from `.neko-companion` packages.

A companion package is a directory produced by the generator pipeline
(Phase 1). Layout::

    <package_dir>/
      manifest.json                  # CompanionManifest
      avatar/live2d/<model>/         # optional bundled Live2D model
        <name>.model3.json           # Cubism 3/4 entry
        ...textures / motions / physics

The loader resolves the Live2D entry file for a package, derives a stable
model slug, and registers a hot-swappable :class:`AvatarProfile` in the
:class:`AvatarRegistry`.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from companion.avatar.profile import AvatarProfile
from companion.avatar.registry import AvatarRegistry
from companion.models.manifest import CompanionManifest
from companion.models.profile import AvatarKind

# Search locations for a bundled Live2D model, relative to the package root.
# `resource_paths["live2d"]` in the manifest takes precedence over these.
_DEFAULT_LIVE2D_DIRS: tuple[str, ...] = ("avatar/live2d", "live2d", "avatar", ".")

# Cubism 3/4 entry first, legacy Cubism 2 second.
_LIVE2D_ENTRY_PATTERNS: tuple[str, ...] = ("*.model3.json", "*.model.json")

_SLUG_INVALID_RE = re.compile(r"[^a-z0-9]+")


class AvatarPackageError(Exception):
  """Raised when a companion package cannot provide a loadable avatar."""


def slugify_model_name(name: str) -> str:
  """Derive a stable, URL-safe slug from a model or companion name."""
  normalized = unicodedata.normalize("NFKD", name)
  ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
  slug = _SLUG_INVALID_RE.sub("-", ascii_only.lower()).strip("-")
  if slug:
    return slug
  # Non-ASCII-only names (e.g. pure CJK) still need a deterministic slug.
  digest = "".join(f"{b:02x}" for b in name.encode("utf-8")[:6])
  return f"model-{digest}"


@dataclass(frozen=True)
class Live2DModelRef:
  """Resolved Live2D model inside a companion package."""

  slug: str
  name: str
  entry_path: str  # absolute filesystem path to the *.model3.json
  package_dir: str  # absolute filesystem path to the package root

  @property
  def relative_entry(self) -> str:
    """Entry path relative to the package root (URL-friendly)."""
    return Path(self.entry_path).relative_to(self.package_dir).as_posix()


def load_manifest(package_dir: str | Path) -> CompanionManifest:
  """Read and validate ``manifest.json`` from a package directory."""
  root = Path(package_dir)
  manifest_path = root / "manifest.json"
  if not manifest_path.is_file():
    raise AvatarPackageError(f"manifest.json not found in {root}")
  try:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError) as exc:
    raise AvatarPackageError(f"manifest.json unreadable: {exc}") from exc
  try:
    return CompanionManifest.model_validate(data)
  except Exception as exc:  # pydantic.ValidationError
    raise AvatarPackageError(f"manifest.json invalid: {exc}") from exc


def _candidate_dirs(root: Path, manifest: CompanionManifest | None) -> list[Path]:
  dirs: list[Path] = []
  if manifest is not None:
    hinted = manifest.resource_paths.get("live2d", "").strip()
    if hinted:
      hinted_path = (root / hinted).resolve()
      # Manifest paths are untrusted input: never escape the package root.
      if hinted_path.is_relative_to(root.resolve()):
        dirs.append(hinted_path)
  for rel in _DEFAULT_LIVE2D_DIRS:
    dirs.append((root / rel).resolve())
  return dirs


def discover_live2d_entry(
  package_dir: str | Path, manifest: CompanionManifest | None = None
) -> Path:
  """Locate the Live2D entry JSON inside a package.

  Searches the manifest-hinted directory first, then conventional
  locations. Raises :class:`AvatarPackageError` when nothing is found.
  """
  root = Path(package_dir).resolve()
  if not root.is_dir():
    raise AvatarPackageError(f"package directory not found: {root}")

  seen: set[Path] = set()
  for directory in _candidate_dirs(root, manifest):
    if directory in seen or not directory.is_dir():
      continue
    seen.add(directory)
    for pattern in _LIVE2D_ENTRY_PATTERNS:
      matches = sorted(directory.rglob(pattern))
      if matches:
        return matches[0]
  raise AvatarPackageError(f"no Live2D model (*.model3.json) found in {root}")


def resolve_live2d_model(
  package_dir: str | Path, manifest: CompanionManifest | None = None
) -> Live2DModelRef:
  """Resolve the bundled Live2D model of a package into a model ref."""
  root = Path(package_dir).resolve()
  entry = discover_live2d_entry(root, manifest)
  # "hiyori.model3.json" -> "hiyori"; "foo.model.json" -> "foo"
  name = entry.name
  for suffix in (".model3.json", ".model.json"):
    if name.endswith(suffix):
      name = name[: -len(suffix)]
      break
  return Live2DModelRef(
    slug=slugify_model_name(name),
    name=name,
    entry_path=str(entry),
    package_dir=str(root),
  )


def load_avatar_from_package(
  package_dir: str | Path, registry: AvatarRegistry, activate: bool = True
) -> AvatarProfile:
  """Load a companion package and register its avatar for hot swap.

  Returns the registered :class:`AvatarProfile`. The profile keeps enough
  metadata in ``effects`` for the frontend Live2D bridge to build a model
  URL and drive ``live2dManager.loadModel``.
  """
  manifest = load_manifest(package_dir)
  profile_cfg = manifest.profile

  if profile_cfg.avatar_kind != AvatarKind.LIVE2D:
    raise AvatarPackageError(
      f"unsupported avatar kind for hot swap: {profile_cfg.avatar_kind.value}"
    )

  model = resolve_live2d_model(package_dir, manifest)
  profile = AvatarProfile(
    id=profile_cfg.id,
    kind=AvatarKind.LIVE2D,
    resource_id=model.slug,
    display_name=profile_cfg.display_name or profile_cfg.name,
    effects={
      "live2d": {
        "slug": model.slug,
        "model_name": model.name,
        "entry_path": model.entry_path,
        "relative_entry": model.relative_entry,
        "package_dir": model.package_dir,
      },
      **profile_cfg.avatar_extra,
    },
  )
  registry.register(profile)
  if activate:
    registry.set_active(profile.id)
  return profile
