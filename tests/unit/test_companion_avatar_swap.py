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

"""Unit tests for avatar hot-swap: package loader + avatar API (Phase 2)."""

import json

import pytest

from companion.avatar.loader import (
  AvatarPackageError,
  load_avatar_from_package,
  load_manifest,
  resolve_live2d_model,
  slugify_model_name,
)
from companion.avatar.registry import AvatarRegistry
from companion.models.manifest import CompanionManifest
from companion.models.profile import AvatarKind, CompanionProfile


def _make_package(
  tmp_path,
  name="小柚",
  profile_id="companion-1",
  model_dir="avatar/live2d/hiyori",
  model_file="hiyori.model3.json",
  resource_paths=None,
  avatar_kind="live2d",
):
  """Create a minimal `.neko-companion` package directory."""
  pkg = tmp_path / f"pkg_{profile_id}"
  manifest = CompanionManifest(
    profile=CompanionProfile(
      id=profile_id,
      name=name,
      display_name=name,
      avatar_kind=avatar_kind,
    ),
    resource_paths=resource_paths or {},
  )
  pkg.mkdir(parents=True)
  (pkg / "manifest.json").write_text(
    json.dumps(manifest.to_package_dict(), ensure_ascii=False), encoding="utf-8"
  )
  if model_dir is not None:
    mdir = pkg / model_dir
    mdir.mkdir(parents=True)
    (mdir / model_file).write_text(
      json.dumps({"Version": 3, "FileReferences": {"Textures": []}}),
      encoding="utf-8",
    )
  return pkg


# ---------------------------------------------------------------------------
# slug derivation
# ---------------------------------------------------------------------------


def test_slugify_ascii_names():
  assert slugify_model_name("Hiyori Free") == "hiyori-free"
  assert slugify_model_name("yui-origin") == "yui-origin"
  assert slugify_model_name("  Mixed__Case 42 ") == "mixed-case-42"


def test_slugify_non_ascii_is_deterministic():
  slug_a = slugify_model_name("小柚")
  slug_b = slugify_model_name("小柚")
  assert slug_a == slug_b
  assert slug_a.startswith("model-")
  assert slug_a != slugify_model_name("小梅")


# ---------------------------------------------------------------------------
# loader
# ---------------------------------------------------------------------------


def test_load_manifest_roundtrip(tmp_path):
  pkg = _make_package(tmp_path)
  manifest = load_manifest(pkg)
  assert manifest.profile.name == "小柚"


def test_load_manifest_missing(tmp_path):
  with pytest.raises(AvatarPackageError, match="manifest.json not found"):
    load_manifest(tmp_path)


def test_load_manifest_invalid_json(tmp_path):
  (tmp_path / "manifest.json").write_text("{not json", encoding="utf-8")
  with pytest.raises(AvatarPackageError, match="unreadable"):
    load_manifest(tmp_path)


def test_resolve_live2d_model_default_layout(tmp_path):
  pkg = _make_package(tmp_path)
  model = resolve_live2d_model(pkg)
  assert model.slug == "hiyori"
  assert model.name == "hiyori"
  assert model.relative_entry == "avatar/live2d/hiyori/hiyori.model3.json"


def test_resolve_live2d_model_manifest_hint_wins(tmp_path):
  pkg = _make_package(
    tmp_path,
    model_dir="custom/models",
    model_file="rin.model3.json",
    resource_paths={"live2d": "custom/models"},
  )
  # also drop a decoy model in a conventional dir; hint must win
  decoy = pkg / "avatar" / "live2d"
  decoy.mkdir(parents=True)
  (decoy / "decoy.model3.json").write_text("{}", encoding="utf-8")

  manifest = load_manifest(pkg)
  model = resolve_live2d_model(pkg, manifest)
  assert model.slug == "rin"


def test_resolve_live2d_model_hint_cannot_escape_package(tmp_path):
  outside = tmp_path / "outside"
  outside.mkdir()
  (outside / "evil.model3.json").write_text("{}", encoding="utf-8")
  pkg = _make_package(
    tmp_path,
    model_dir=None,
    resource_paths={"live2d": "../outside"},
  )
  manifest = load_manifest(pkg)
  with pytest.raises(AvatarPackageError, match="no Live2D model"):
    resolve_live2d_model(pkg, manifest)


def test_resolve_live2d_model_none_found(tmp_path):
  pkg = _make_package(tmp_path, model_dir=None)
  with pytest.raises(AvatarPackageError, match="no Live2D model"):
    resolve_live2d_model(pkg)


def test_load_avatar_from_package_registers_and_activates(tmp_path):
  registry = AvatarRegistry()
  pkg = _make_package(tmp_path)
  profile = load_avatar_from_package(pkg, registry)

  assert registry.active() is profile
  assert profile.kind == AvatarKind.LIVE2D
  assert profile.resource_id == "hiyori"
  live2d = profile.effects["live2d"]
  assert live2d["slug"] == "hiyori"
  assert live2d["relative_entry"] == "avatar/live2d/hiyori/hiyori.model3.json"
  assert live2d["package_dir"] == str(pkg.resolve())


def test_load_avatar_from_package_without_activation(tmp_path):
  registry = AvatarRegistry()
  first = load_avatar_from_package(
    _make_package(tmp_path, profile_id="c1"), registry
  )
  second = load_avatar_from_package(
    _make_package(tmp_path, profile_id="c2"), registry, activate=False
  )
  assert registry.active() is first
  assert {p.id for p in registry.list_profiles()} == {"c1", "c2"}
  assert second.id == "c2"


def test_load_avatar_rejects_non_live2d_kind(tmp_path):
  registry = AvatarRegistry()
  pkg = _make_package(tmp_path, avatar_kind="vrm")
  with pytest.raises(AvatarPackageError, match="unsupported avatar kind"):
    load_avatar_from_package(pkg, registry)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(monkeypatch):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient

  import companion.api.routes as routes

  monkeypatch.setattr(routes, "_avatar_registry", AvatarRegistry())
  app = FastAPI()
  app.include_router(routes.router)
  return TestClient(app)


def test_api_load_package_and_list(tmp_path, client):
  pkg = _make_package(tmp_path)
  res = client.post(
    "/api/companion/avatar/load-package",
    json={"package_path": str(pkg)},
  )
  assert res.status_code == 201
  body = res.json()
  assert body["slug"] == "hiyori"
  assert body["entry_url"].endswith("avatar/live2d/hiyori/hiyori.model3.json")

  listing = client.get("/api/companion/avatar/list").json()
  assert listing["active_id"] == "companion-1"
  assert listing["profiles"][0]["entry_url"] == body["entry_url"]

  active = client.get("/api/companion/avatar/active").json()
  assert active["active"]["slug"] == "hiyori"


def test_api_load_package_invalid(tmp_path, client):
  res = client.post(
    "/api/companion/avatar/load-package",
    json={"package_path": str(tmp_path / "nope")},
  )
  assert res.status_code == 422


def test_api_set_active_switches_between_packages(tmp_path, client):
  for pid in ("c1", "c2"):
    client.post(
      "/api/companion/avatar/load-package",
      json={
        "package_path": str(_make_package(tmp_path, profile_id=pid)),
        "activate": pid == "c1",
      },
    )
  res = client.post("/api/companion/avatar/active", params={"profile_id": "c2"})
  assert res.status_code == 200
  assert client.get("/api/companion/avatar/active").json()["active"]["id"] == "c2"

  missing = client.post(
    "/api/companion/avatar/active", params={"profile_id": "ghost"}
  )
  assert missing.status_code == 404


def test_api_resource_serving_and_traversal_guard(tmp_path, client):
  pkg = _make_package(tmp_path)
  secret = tmp_path / "secret.txt"
  secret.write_text("top secret", encoding="utf-8")

  created = client.post(
    "/api/companion/avatar/load-package", json={"package_path": str(pkg)}
  ).json()

  ok = client.get(created["entry_url"])
  assert ok.status_code == 200
  assert ok.json()["Version"] == 3

  traversal = client.get(
    "/api/companion/avatar/companion-1/resource/%2E%2E/secret.txt"
  )
  assert traversal.status_code in (403, 404)

  missing = client.get(
    "/api/companion/avatar/companion-1/resource/avatar/live2d/hiyori/nope.png"
  )
  assert missing.status_code == 404

  unknown_profile = client.get(
    "/api/companion/avatar/ghost/resource/manifest.json"
  )
  assert unknown_profile.status_code == 404
