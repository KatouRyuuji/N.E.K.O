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

"""SQLite persistence for the avatar registry (Phase 5 M2).

The Phase 2 :class:`~companion.avatar.registry.AvatarRegistry` was a pure
in-memory object: every imported avatar (and its Phase 3 effects
decorations) vanished on restart. This module mirrors the
``GenerationTaskStore`` pattern from :mod:`companion.generator.tasks`:

- profiles are serialized as one JSON payload row each in SQLite
  (``avatar_profiles``), the active selection lives in a small key/value
  table (``avatar_registry_state``);
- :class:`PersistentAvatarRegistry` restores everything at construction
  and writes registrations / active switches / deletions through;
- a lazy module singleton (:func:`get_avatar_registry`) is what the API
  routes use, so importing the routes never touches the user data dir.

Safe package deletion for ``DELETE /api/companion/avatar/{profile_id}``
also lives here (:func:`remove_package_dir`): only directories inside the
managed companions data root that look like real packages may be removed.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from companion.avatar.profile import AvatarProfile
from companion.avatar.registry import AvatarRegistry
from companion.models.profile import AvatarKind

ENV_AVATAR_DB_PATH = "NEKO_COMPANION_AVATAR_DB_PATH"
# Overrides the only root DELETE …?delete_package=true may remove package
# directories from (tests / relocated data dirs).
ENV_PACKAGES_ROOT = "NEKO_COMPANION_PACKAGES_ROOT"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS avatar_profiles (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS avatar_registry_state (
  key TEXT PRIMARY KEY,
  value TEXT
);
"""

_ACTIVE_KEY = "active_id"


def _utcnow() -> str:
  return datetime.now(timezone.utc).isoformat()


def default_avatar_db_path() -> Path:
  """Resolve the avatar-registry database location.

  Priority:
  1. ``NEKO_COMPANION_AVATAR_DB_PATH`` environment variable (tests / overrides).
  2. The user runtime data root managed by :mod:`utils.config_manager`.
  3. Project-local ``memory/store`` as a last resort.
  """
  env_path = os.environ.get(ENV_AVATAR_DB_PATH, "").strip()
  if env_path:
    return Path(env_path)
  try:
    from utils.config_manager import get_config_manager

    root = Path(get_config_manager().app_docs_dir)
    return root / "companion" / "avatar_registry.db"
  except Exception:
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "memory" / "store" / "companion_avatar_registry.db"


def profile_to_storage_dict(profile: AvatarProfile) -> dict[str, Any]:
  return {
    "id": profile.id,
    "kind": profile.kind.value,
    "resource_id": profile.resource_id,
    "display_name": profile.display_name,
    "effects": profile.effects,
  }


def profile_from_storage_dict(data: dict[str, Any]) -> AvatarProfile:
  return AvatarProfile(
    id=data["id"],
    kind=AvatarKind(data["kind"]),
    resource_id=data["resource_id"],
    display_name=data.get("display_name", ""),
    effects=dict(data.get("effects") or {}),
  )


class AvatarRegistryStore:
  """Thread-safe SQLite store for avatar profiles + the active selection.

  Pass ``":memory:"`` as ``db_path`` for an ephemeral store (tests).
  """

  def __init__(self, db_path: str | Path | None = None) -> None:
    if db_path is None:
      db_path = default_avatar_db_path()
    self._db_path = str(db_path)
    if self._db_path != ":memory:":
      Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
    self._lock = threading.Lock()
    self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
    self._conn.row_factory = sqlite3.Row
    with self._lock, self._conn:
      self._conn.executescript(_SCHEMA)

  @property
  def db_path(self) -> str:
    return self._db_path

  def close(self) -> None:
    with self._lock:
      self._conn.close()

  def upsert_profile(self, profile: AvatarProfile) -> None:
    now = _utcnow()
    payload = json.dumps(profile_to_storage_dict(profile), ensure_ascii=False)
    with self._lock, self._conn:
      self._conn.execute(
        "INSERT INTO avatar_profiles (id, created_at, updated_at, payload)"
        " VALUES (?, ?, ?, ?)"
        " ON CONFLICT(id) DO UPDATE SET"
        " updated_at = excluded.updated_at, payload = excluded.payload",
        (profile.id, now, now, payload),
      )

  def delete_profile(self, profile_id: str) -> bool:
    with self._lock, self._conn:
      cur = self._conn.execute(
        "DELETE FROM avatar_profiles WHERE id = ?", (profile_id,)
      )
      return cur.rowcount > 0

  def load_profiles(self) -> list[AvatarProfile]:
    """All persisted profiles, oldest registration first."""
    with self._lock:
      rows = self._conn.execute(
        "SELECT payload FROM avatar_profiles ORDER BY created_at ASC, id ASC"
      ).fetchall()
    return [profile_from_storage_dict(json.loads(r["payload"])) for r in rows]

  def get_active_id(self) -> str | None:
    with self._lock:
      row = self._conn.execute(
        "SELECT value FROM avatar_registry_state WHERE key = ?", (_ACTIVE_KEY,)
      ).fetchone()
    return row["value"] if row and row["value"] else None

  def set_active_id(self, profile_id: str | None) -> None:
    with self._lock, self._conn:
      self._conn.execute(
        "INSERT INTO avatar_registry_state (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (_ACTIVE_KEY, profile_id),
      )


class PersistentAvatarRegistry(AvatarRegistry):
  """Avatar registry with SQLite write-through persistence.

  Construction restores every persisted profile — including effects
  decorations — and the active selection, so imported avatars survive
  process restarts.
  """

  def __init__(self, store: AvatarRegistryStore | None = None) -> None:
    super().__init__()
    self._store = store if store is not None else AvatarRegistryStore()
    for profile in self._store.load_profiles():
      self._profiles[profile.id] = profile
    active_id = self._store.get_active_id()
    if active_id in self._profiles:
      self._active_id = active_id
    elif self._profiles:
      # Stored active id points at a vanished profile (partial write,
      # external db edit): fall back deterministically and repair the row.
      self._active_id = next(iter(self._profiles))
      self._store.set_active_id(self._active_id)

  @property
  def store(self) -> AvatarRegistryStore:
    return self._store

  def close(self) -> None:
    self._store.close()

  def register(self, profile: AvatarProfile) -> None:
    super().register(profile)
    self._store.upsert_profile(profile)
    self._store.set_active_id(self._active_id)

  def set_active(self, profile_id: str) -> AvatarProfile | None:
    profile = super().set_active(profile_id)
    if profile is not None:
      self._store.set_active_id(self._active_id)
    return profile

  def unregister(self, profile_id: str) -> AvatarProfile | None:
    removed = super().unregister(profile_id)
    if removed is not None:
      self._store.delete_profile(profile_id)
      self._store.set_active_id(self._active_id)
    return removed

  def save_profile(self, profile: AvatarProfile) -> None:
    super().save_profile(profile)
    self._store.upsert_profile(profile)


_registry: PersistentAvatarRegistry | None = None
_registry_lock = threading.Lock()


def get_avatar_registry() -> PersistentAvatarRegistry:
  """Shared persistent registry, created lazily on the default db path."""
  global _registry
  with _registry_lock:
    if _registry is None:
      _registry = PersistentAvatarRegistry()
    return _registry


def reset_avatar_registry(db_path: str | Path | None = None) -> None:
  """Close and drop the shared registry (tests / restart simulation).

  With ``db_path`` the next singleton is created eagerly on that path;
  without it, the next :func:`get_avatar_registry` call re-resolves the
  default.
  """
  global _registry
  with _registry_lock:
    if _registry is not None:
      try:
        _registry.close()
      except Exception:
        pass
    _registry = (
      PersistentAvatarRegistry(AvatarRegistryStore(db_path))
      if db_path is not None
      else None
    )


# --------------------------------------------------------------- package GC


class PackagePathError(Exception):
  """Raised when a package directory fails the safe-deletion rules."""


def default_packages_root() -> Path | None:
  """The only root package deletions are allowed under.

  ``NEKO_COMPANION_PACKAGES_ROOT`` wins (tests / overrides); otherwise the
  managed companions data dir (generated / uploads / workshop all live
  under it). ``None`` when neither is resolvable — deletion then refuses.
  """
  env_root = os.environ.get(ENV_PACKAGES_ROOT, "").strip()
  if env_root:
    return Path(env_root)
  try:
    from utils.config_manager import get_config_manager

    return Path(get_config_manager().docs_dir) / "N.E.K.O" / "companions"
  except Exception:
    return None


def remove_package_dir(
  package_dir: str | Path, allowed_root: Path | None = None
) -> str | None:
  """Delete one companion package directory, defensively.

  Safety rules — any violation raises :class:`PackagePathError`:

  - an allowed root must be resolvable (see :func:`default_packages_root`);
  - the target must resolve strictly inside that root (symlink / ``..``
    escapes are rejected, and never the root itself);
  - the target must look like a companion package (``manifest.json``).

  Returns the removed absolute path, or ``None`` when the directory is
  already gone (idempotent).
  """
  root = allowed_root if allowed_root is not None else default_packages_root()
  if root is None:
    raise PackagePathError("no managed companion package root is configured")
  root = root.resolve()
  target = Path(package_dir).resolve()
  if not target.is_dir():
    return None
  if target == root or not target.is_relative_to(root):
    raise PackagePathError(f"package path outside managed root: {target}")
  if not (target / "manifest.json").is_file():
    raise PackagePathError(
      f"not a companion package (manifest.json missing): {target}"
    )
  shutil.rmtree(target)
  return str(target)
