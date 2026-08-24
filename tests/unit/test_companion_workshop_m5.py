# -*- coding: utf-8 -*-
# Copyright 2025-2026 Project N.E.K.O. Team

"""Phase 5 M5 workshop catalog enrichment."""

import json
from pathlib import Path

import pytest

from companion.generator import pipeline as pipeline_mod
from companion.generator.tasks import get_task_store
from companion.models.generation import GenerationInput
from companion.workshop.export import (
  build_workshop_listing,
  export_workshop_bundle,
  find_workshop_entry,
  scan_workshop_catalog,
)


def test_workshop_listing_includes_tags_and_summary(tmp_path, monkeypatch):
  monkeypatch.setattr(pipeline_mod, "_default_output_root", lambda: tmp_path)
  monkeypatch.setattr(pipeline_mod, "_resolve_generator_api_config", lambda: None)
  task = get_task_store().create(
    GenerationInput(companion_name="工坊猫", corpus_text="温柔的猫娘")
  )
  pipeline_mod.run_pipeline_sync(task, output_root=tmp_path)
  listing = build_workshop_listing(task)
  assert "generated" in listing["tags"]
  assert listing["companion_id"]


def test_catalog_scan_and_entry(tmp_path, monkeypatch):
  monkeypatch.setattr(pipeline_mod, "_default_output_root", lambda: tmp_path)
  monkeypatch.setattr(pipeline_mod, "_resolve_generator_api_config", lambda: None)
  task = get_task_store().create(GenerationInput(companion_name="上架", corpus_text="猫娘"))
  pipeline_mod.run_pipeline_sync(task, output_root=tmp_path)
  dest = export_workshop_bundle(task, output_root=tmp_path / "shop")
  entries = scan_workshop_catalog(tmp_path / "shop")
  assert len(entries) == 1
  assert entries[0]["catalog_id"] == dest.name
  found = find_workshop_entry(tmp_path / "shop", dest.name)
  assert found is not None
  assert found["task_id"] == task.id


def test_api_workshop_entry_and_asset(tmp_path, monkeypatch):
  fastapi = pytest.importorskip("fastapi")
  from fastapi.testclient import TestClient
  import companion.api.routes as routes

  shop = tmp_path / "shop"
  shop.mkdir()
  cat_dir = shop / "cid_abc12345"
  cat_dir.mkdir()
  (cat_dir / "workshop.json").write_text(
    json.dumps({"catalog_id": "cid_abc12345", "display_name": "测试"}),
    encoding="utf-8",
  )
  (cat_dir / "cover.png").write_bytes(b"png")

  monkeypatch.setattr(routes, "_workshop_export_root", lambda: shop)
  monkeypatch.setattr(routes, "_productivity", None)
  app = fastapi.FastAPI()
  app.include_router(routes.router)
  client = TestClient(app)

  res = client.get("/api/companion/workshop/entry/cid_abc12345")
  assert res.status_code == 200
  res = client.get("/api/companion/workshop/asset/cid_abc12345/cover.png")
  assert res.status_code == 200
