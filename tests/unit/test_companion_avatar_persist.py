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

"""Unit tests for avatar-registry persistence (Phase 5 M2).

Covers the SQLite store, the write-through PersistentAvatarRegistry
(restart = new instance on the same db), safe package deletion, and the
API flow: import → reset store (restart simulation) → list still returns
the avatar and its resources; DELETE removes it durably.

The autouse ``_isolate_companion_avatar_registry`` fixture (conftest)
points ``NEKO_COMPANION_AVATAR_DB_PATH`` at ``tmp_path`` and pins the
managed packages root (``NEKO_COMPANION_PACKAGES_ROOT``) to ``tmp_path``.
"""

import json
import shutil
import tempfile
import threading
from pathlib import Path

import pytest

from companion.avatar.profile import AvatarProfile
from companion.avatar.store import (
  AvatarRegistryStore,
  PackagePathError,
  PersistentAvatarRegistry,
  remove_package_dir,
  reset_avatar_registry,
)
from companion.models.manifest import CompanionManifest
from companion.models.profile import AvatarKind, CompanionProfile


def _profile(pid: str, **kwargs) -> AvatarProfile:
  defaults = dict(kind=AvatarKind.LIVE2D, resource_id=f"model-{pid}")
  defaults.update(kwargs)
  return AvatarProfile(id=pid, **defaults)


def _make_package(base_dir, name="小柚", profile_id="companion-1"):
  """Create a minimal `.neko-companion` package directory."""
  pkg = Path(base_dir) / f"pkg_{profile_id}"
  manifest = CompanionManifest(
    profile=CompanionProfile(
      id=profile_id,
      name=name,
      display_name=name,
      avatar_kind="live2d",
    ),
  )
  mdir = pkg / "avatar" / "live2d" / "hiyori"
  mdir.mkdir(parents=True)
  (pkg / "manifest.json").write_text(
    json.dumps(manifest.to_package_dict(), ensure_ascii=False), encoding="utf-8"
  )
  (mdir / "hiyori.model3.json").write_text(
    json.dumps({"Version": 3, "FileReferences": {"Textures": []}}),
    encoding="utf-8",
  )
  return pkg


# ---------------------------------------------------------------------------
# store
# ---------------------------------------------------------------------------


def test_store_roundtrip_profiles_and_active():
  store = AvatarRegistryStore(":memory:")
  store.upsert_profile(_profile("c1", display_name="柚子"))
  store.upsert_profile(
    _profile("c2", effects={"decorations": {"particles": True}})
  )
  store.set_active_id("c2")

  profiles = {p.id: p for p in store.load_profiles()}
  assert set(profiles) == {"c1", "c2"}
  assert profiles["c1"].display_name == "柚子"
  assert profiles["c1"].kind == AvatarKind.LIVE2D
  assert profiles["c2"].effects["decorations"] == {"particles": True}
  assert store.get_active_id() == "c2"
  store.close()


def test_store_upsert_overwrites_existing_payload():
  store = AvatarRegistryStore(":memory:")
  store.upsert_profile(_profile("c1"))
  store.upsert_profile(_profile("c1", display_name="renamed"))
  profiles = store.load_profiles()
  assert len(profiles) == 1
  assert profiles[0].display_name == "renamed"
  store.close()


def test_store_delete_profile():
  store = AvatarRegistryStore(":memory:")
  store.upsert_profile(_profile("c1"))
  assert store.delete_profile("c1") is True
  assert store.delete_profile("c1") is False
  assert store.load_profiles() == []
  store.close()


# ---------------------------------------------------------------------------
# persistent registry: restart = new instance on the same db path
# ---------------------------------------------------------------------------


def test_registry_restores_profiles_and_active_after_restart(tmp_path):
  db = tmp_path / "avatars.db"
  registry = PersistentAvatarRegistry(AvatarRegistryStore(db))
  registry.register(_profile("c1"))
  registry.register(_profile("c2"))
  registry.set_active("c2")
  registry.close()

  reloaded = PersistentAvatarRegistry(AvatarRegistryStore(db))
  assert {p.id for p in reloaded.list_profiles()} == {"c1", "c2"}
  assert reloaded.active() is not None
  assert reloaded.active().id == "c2"
  reloaded.close()


def test_registry_persists_effects_decorations(tmp_path):
  db = tmp_path / "avatars.db"
  registry = PersistentAvatarRegistry(AvatarRegistryStore(db))
  profile = _profile("c1")
  registry.register(profile)
  profile.effects["decorations"] = {"particles": True, "border": "sakura"}
  registry.save_profile(profile)
  registry.close()

  reloaded = PersistentAvatarRegistry(AvatarRegistryStore(db))
  restored = reloaded.get("c1")
  assert restored is not None
  assert restored.effects["decorations"] == {
    "particles": True,
    "border": "sakura",
  }
  reloaded.close()


def test_registry_unregister_persists_and_repairs_active(tmp_path):
  db = tmp_path / "avatars.db"
  registry = PersistentAvatarRegistry(AvatarRegistryStore(db))
  registry.register(_profile("c1"))
  registry.register(_profile("c2"))
  registry.set_active("c1")

  removed = registry.unregister("c1")
  assert removed is not None and removed.id == "c1"
  assert registry.unregister("ghost") is None
  assert registry.active().id == "c2"
  registry.close()

  reloaded = PersistentAvatarRegistry(AvatarRegistryStore(db))
  assert {p.id for p in reloaded.list_profiles()} == {"c2"}
  assert reloaded.active().id == "c2"
  reloaded.close()


def test_registry_repairs_stored_active_pointing_at_missing_profile(tmp_path):
  db = tmp_path / "avatars.db"
  store = AvatarRegistryStore(db)
  store.upsert_profile(_profile("c1"))
  store.set_active_id("ghost")
  store.close()

  reloaded = PersistentAvatarRegistry(AvatarRegistryStore(db))
  assert reloaded.active().id == "c1"
  assert reloaded.store.get_active_id() == "c1"
  reloaded.close()


def test_registry_concurrent_registration_survives_reload(tmp_path):
  db = tmp_path / "avatars.db"
  registry = PersistentAvatarRegistry(AvatarRegistryStore(db))

  def _register(i: int) -> None:
    registry.register(_profile(f"c{i}"))

  threads = [threading.Thread(target=_register, args=(i,)) for i in range(16)]
  for t in threads:
    t.start()
  for t in threads:
    t.join()
  registry.close()

  reloaded = PersistentAvatarRegistry(AvatarRegistryStore(db))
  ids = {p.id for p in reloaded.list_profiles()}
  assert ids == {f"c{i}" for i in range(16)}
  assert reloaded.active().id in ids
  reloaded.close()


# ---------------------------------------------------------------------------
# safe package deletion
# ---------------------------------------------------------------------------


def test_remove_package_dir_inside_root(tmp_path):
  pkg = _make_package(tmp_path)
  removed = remove_package_dir(pkg, allowed_root=tmp_path)
  assert removed == str(pkg.resolve())
  assert not pkg.exists()


def test_remove_package_dir_missing_is_idempotent(tmp_path):
  assert remove_package_dir(tmp_path / "gone", allowed_root=tmp_path) is None


def test_remove_package_dir_rejects_outside_root(tmp_path):
  inside_root = tmp_path / "root"
  inside_root.mkdir()
  outside_pkg = _make_package(tmp_path)  # sibling of root, not inside it
  with pytest.raises(PackagePathError, match="outside managed root"):
    remove_package_dir(outside_pkg, allowed_root=inside_root)
  assert outside_pkg.is_dir()


def test_remove_package_dir_rejects_root_itself(tmp_path):
  (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
  with pytest.raises(PackagePathError, match="outside managed root"):
    remove_package_dir(tmp_path, allowed_root=tmp_path)


def test_remove_package_dir_rejects_non_package(tmp_path):
  plain = tmp_path / "not-a-package"
  plain.mkdir()
  with pytest.raises(PackagePathError, match="manifest.json missing"):
    remove_package_dir(plain, allowed_root=tmp_path)
  assert plain.is_dir()


# ---------------------------------------------------------------------------
# API: import → restart simulation → list / resources / delete
# ---------------------------------------------------------------------------


def _make_client():
  from fastapi import FastAPI
  from fastapi.testclient import TestClient

  import companion.api.routes as routes

  # No _avatar_registry monkeypatch on purpose: routes must fall through to
  # the persisted singleton (db path isolated per-test via conftest env).
  app = FastAPI()
  app.include_router(routes.router)
  return TestClient(app)


def test_api_import_survives_restart(tmp_path):
  pkg = _make_package(tmp_path)
  client = _make_client()
  created = client.post(
    "/api/companion/avatar/load-package", json={"package_path": str(pkg)}
  )
  assert created.status_code == 201
  entry_url = created.json()["entry_url"]

  # Restart simulation: drop the singleton; a fresh app + first API access
  # must restore the registry from SQLite.
  reset_avatar_registry()
  client = _make_client()

  listing = client.get("/api/companion/avatar/list").json()
  assert listing["active_id"] == "companion-1"
  assert [p["id"] for p in listing["profiles"]] == ["companion-1"]
  assert listing["profiles"][0]["entry_url"] == entry_url

  resource = client.get(entry_url)
  assert resource.status_code == 200
  assert resource.json()["Version"] == 3


def test_api_effects_decorations_survive_restart(tmp_path):
  pkg = _make_package(tmp_path)
  client = _make_client()
  client.post(
    "/api/companion/avatar/load-package", json={"package_path": str(pkg)}
  )
  res = client.post(
    "/api/companion/avatar/effects",
    params={"profile_id": "companion-1", "particles": True, "border": "gold"},
  )
  assert res.status_code == 200

  reset_avatar_registry()
  client = _make_client()

  listing = client.get("/api/companion/avatar/list").json()
  decorations = listing["profiles"][0]["decorations"]
  assert decorations["particles"] is True
  assert decorations["border"] == "gold"


def test_api_delete_avatar_is_durable(tmp_path):
  client = _make_client()
  for pid in ("c1", "c2"):
    client.post(
      "/api/companion/avatar/load-package",
      json={"package_path": str(_make_package(tmp_path, profile_id=pid))},
    )

  res = client.delete("/api/companion/avatar/c2")
  assert res.status_code == 200
  body = res.json()
  assert body["deleted"] == "c2"
  assert body["active_id"] == "c1"
  assert body["package_removed"] is None

  reset_avatar_registry()
  client = _make_client()
  listing = client.get("/api/companion/avatar/list").json()
  assert [p["id"] for p in listing["profiles"]] == ["c1"]
  assert listing["active_id"] == "c1"


def test_api_delete_unknown_profile_404(tmp_path):
  client = _make_client()
  assert client.delete("/api/companion/avatar/ghost").status_code == 404


def test_api_delete_with_package_removal(tmp_path):
  # conftest pins NEKO_COMPANION_PACKAGES_ROOT to tmp_path, so this package
  # is inside the managed root and eligible for deletion.
  pkg = _make_package(tmp_path)
  client = _make_client()
  client.post(
    "/api/companion/avatar/load-package", json={"package_path": str(pkg)}
  )

  res = client.delete(
    "/api/companion/avatar/companion-1", params={"delete_package": "true"}
  )
  assert res.status_code == 200
  assert res.json()["package_removed"] == str(pkg.resolve())
  assert not pkg.exists()
  assert client.get("/api/companion/avatar/list").json()["profiles"] == []


def test_api_delete_package_outside_root_is_rejected(tmp_path):
  outside = Path(tempfile.mkdtemp(prefix="neko-avatar-outside-"))
  try:
    pkg = _make_package(outside)
    client = _make_client()
    client.post(
      "/api/companion/avatar/load-package", json={"package_path": str(pkg)}
    )

    res = client.delete(
      "/api/companion/avatar/companion-1", params={"delete_package": "true"}
    )
    assert res.status_code == 409
    # Refused deletions must leave both the package and the registry intact.
    assert pkg.is_dir()
    listing = client.get("/api/companion/avatar/list").json()
    assert [p["id"] for p in listing["profiles"]] == ["companion-1"]
  finally:
    shutil.rmtree(outside, ignore_errors=True)
