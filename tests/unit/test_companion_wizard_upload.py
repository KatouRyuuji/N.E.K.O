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

"""Phase 3 tests: multimodal wizard upload endpoint + end-to-end import."""

import json
from pathlib import Path

import pytest

from companion.generator import pipeline as pipeline_mod
from companion.generator import uploads as uploads_mod
from companion.generator.pipeline import run_pipeline_sync
from companion.generator.tasks import get_task_store
from companion.generator.uploads import sanitize_filename
from companion.models.generation import GenerationInput

_STATIC_WIZARD = Path(__file__).resolve().parents[2] / "static" / "companion" / "wizard"


def _make_live2d_source(tmp_path, model_name="hiyori"):
  """A bare Live2D model directory (what a user would point the wizard at)."""
  src = tmp_path / "l2d_source" / model_name
  src.mkdir(parents=True)
  (src / f"{model_name}.model3.json").write_text(
    json.dumps({"Version": 3, "FileReferences": {"Textures": ["tex.png"]}}),
    encoding="utf-8",
  )
  (src / "tex.png").write_bytes(b"\x89PNG fake")
  return src


@pytest.fixture()
def client(tmp_path, monkeypatch):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient

  import companion.api.routes as routes
  from companion.avatar.registry import AvatarRegistry

  out_root = tmp_path / "generated"
  out_root.mkdir()
  upload_root = tmp_path / "uploads"
  upload_root.mkdir()
  monkeypatch.setattr(pipeline_mod, "_default_output_root", lambda: out_root)
  # Deterministic heuristic path — no LLM route in unit tests.
  monkeypatch.setattr(pipeline_mod, "_resolve_generator_api_config", lambda: None)
  monkeypatch.setattr(uploads_mod, "default_upload_root", lambda: upload_root)
  monkeypatch.setattr(routes, "_avatar_registry", AvatarRegistry())

  app = FastAPI()
  app.include_router(routes.router)
  test_client = TestClient(app)
  test_client.upload_root = upload_root
  test_client.out_root = out_root
  return test_client


# ---------------------------------------------------------------------------
# filename sanitization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
  ("chat.txt", "chat.txt"),
  ("../../etc/passwd", "passwd"),
  ("..\\..\\win\\evil.txt", "evil.txt"),
  ("空 格 与*号?.md", "空_格_与_号_.md"),
  ("...", "file"),
  ("", "file"),
  (None, "file"),
])
def test_sanitize_filename(raw, expected):
  assert sanitize_filename(raw) == expected


# ---------------------------------------------------------------------------
# POST /api/companion/generate/upload
# ---------------------------------------------------------------------------


def test_upload_endpoint_saves_files_and_merges_corpus(client):
  res = client.post(
    "/api/companion/generate/upload",
    data={
      "companion_name": "小柚",
      "locale": "zh-CN",
      "corpus_text": "内联语料：温柔的猫娘。",
      "system_prompt": "你是小柚。",
    },
    files=[
      ("corpus_files", ("chat.txt", "文件语料：喜欢陪主人学习。".encode("utf-8"), "text/plain")),
      ("corpus_files", ("notes.bin", b"\x00\x01binary", "application/octet-stream")),
      ("reference_images", ("ref.png", b"\x89PNG fake", "image/png")),
      ("reference_audio", ("voice.wav", b"RIFF fake", "audio/wav")),
      ("reference_video", ("dance.mp4", b"\x00mp4 fake", "video/mp4")),
    ],
  )
  assert res.status_code == 201
  body = res.json()
  assert body["status"] == "completed"
  assert body["uploads"]["corpus_files"] == 2
  assert body["uploads"]["reference_images"] == 1
  assert body["uploads"]["reference_audio"] == 1
  assert body["uploads"]["reference_video"] == 1

  session_dir = Path(body["uploads"]["session_dir"])
  assert session_dir.is_relative_to(client.upload_root)
  assert (session_dir / "corpus" / "00_chat.txt").is_file()
  assert (session_dir / "images" / "00_ref.png").read_bytes() == b"\x89PNG fake"

  task = get_task_store().get(body["id"])
  # Inline text and decodable corpus files are merged; binary is path-only.
  assert "内联语料" in task.input.corpus_text
  assert "文件语料" in task.input.corpus_text
  assert "binary" not in task.input.corpus_text
  assert len(task.input.corpus_files) == 2
  assert task.input.reference_audio[0].endswith("00_voice.wav")


def test_upload_endpoint_form_only(client):
  res = client.post(
    "/api/companion/generate/upload",
    data={"companion_name": "API测试", "corpus_text": "活泼的猫娘"},
  )
  assert res.status_code == 201
  body = res.json()
  assert body["status"] == "completed"
  assert body["uploads"]["corpus_files"] == 0

  task = get_task_store().get(body["id"])
  assert task.input.corpus_text == "活泼的猫娘"
  assert task.input.live2d_package_path is None


def test_upload_endpoint_traversal_filename_stays_in_session(client):
  res = client.post(
    "/api/companion/generate/upload",
    data={"companion_name": "小柚"},
    files=[("corpus_files", ("../../evil.txt", b"pwn", "text/plain"))],
  )
  assert res.status_code == 201
  saved = get_task_store().get(res.json()["id"]).input.corpus_files[0]
  saved_path = Path(saved)
  assert saved_path.name == "00_evil.txt"
  assert saved_path.is_relative_to(client.upload_root)
  assert not (client.upload_root.parent / "evil.txt").exists()


def test_upload_endpoint_rejects_oversized_file(client, monkeypatch):
  monkeypatch.setattr(uploads_mod, "COMPANION_UPLOAD_MAX_FILE_BYTES", 8)
  res = client.post(
    "/api/companion/generate/upload",
    data={"companion_name": "小柚"},
    files=[("reference_video", ("big.mp4", b"0123456789", "video/mp4"))],
  )
  assert res.status_code == 413
  assert "big.mp4" in res.json()["detail"]


def test_upload_endpoint_rejects_too_many_files(client, monkeypatch):
  monkeypatch.setattr(uploads_mod, "COMPANION_UPLOAD_MAX_FILES_PER_FIELD", 1)
  res = client.post(
    "/api/companion/generate/upload",
    data={"companion_name": "小柚"},
    files=[
      ("corpus_files", ("a.txt", b"a", "text/plain")),
      ("corpus_files", ("b.txt", b"b", "text/plain")),
    ],
  )
  assert res.status_code == 413
  assert "corpus" in res.json()["detail"]


def test_upload_endpoint_requires_name(client):
  res = client.post("/api/companion/generate/upload", data={"corpus_text": "x"})
  assert res.status_code == 422


# ---------------------------------------------------------------------------
# Live2D bundling in the PACKAGE stage
# ---------------------------------------------------------------------------


def test_pipeline_bundles_live2d_package(tmp_path, monkeypatch):
  monkeypatch.setattr(pipeline_mod, "_resolve_generator_api_config", lambda: None)
  src = _make_live2d_source(tmp_path)

  task = get_task_store().create(GenerationInput(
    companion_name="小柚",
    corpus_text="温柔的猫娘",
    live2d_package_path=str(src),
  ))
  artifact = run_pipeline_sync(task, output_root=tmp_path / "out")

  package_dir = Path(artifact.package_path)
  bundled_entry = package_dir / "avatar" / "live2d" / "hiyori" / "hiyori.model3.json"
  assert bundled_entry.is_file()
  assert (package_dir / "avatar" / "live2d" / "hiyori" / "tex.png").is_file()
  manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
  assert manifest["resource_paths"]["live2d"] == "avatar/live2d"


def test_pipeline_skips_bundle_for_bad_package_path(tmp_path, monkeypatch):
  monkeypatch.setattr(pipeline_mod, "_resolve_generator_api_config", lambda: None)
  task = get_task_store().create(GenerationInput(
    companion_name="小柚",
    live2d_package_path=str(tmp_path / "does_not_exist"),
  ))
  artifact = run_pipeline_sync(task, output_root=tmp_path / "out")

  # A bad path degrades to a metadata-only package instead of failing.
  assert task.status.value == "completed"
  manifest = json.loads(
    (Path(artifact.package_path) / "manifest.json").read_text(encoding="utf-8")
  )
  assert "live2d" not in manifest["resource_paths"]


# ---------------------------------------------------------------------------
# POST /api/companion/generate/{task_id}/import — end-to-end
# ---------------------------------------------------------------------------


def test_generate_then_import_end_to_end(client, tmp_path):
  src = _make_live2d_source(tmp_path)
  created = client.post(
    "/api/companion/generate/upload",
    data={
      "companion_name": "小柚",
      "corpus_text": "温柔的猫娘",
      "live2d_package_path": str(src),
    },
    files=[("reference_images", ("ref.png", b"\x89PNG fake", "image/png"))],
  )
  assert created.status_code == 201
  task_id = created.json()["id"]

  imported = client.post(f"/api/companion/generate/{task_id}/import")
  assert imported.status_code == 201
  body = imported.json()
  assert body["imported"] is True
  assert body["avatar"]["slug"] == "hiyori"
  assert body["avatar"]["entry_url"].endswith("hiyori.model3.json")

  # The imported avatar is registered and active in the hot-swap registry.
  listing = client.get("/api/companion/avatar/list").json()
  assert listing["active_id"] == body["avatar"]["id"]
  assert listing["profiles"][0]["slug"] == "hiyori"

  # Its Live2D resources are servable from the bundled package copy.
  entry = client.get(body["avatar"]["entry_url"])
  assert entry.status_code == 200
  assert entry.json()["Version"] == 3


def test_import_unknown_task_404(client):
  res = client.post("/api/companion/generate/no-such-task/import")
  assert res.status_code == 404


def test_import_pending_task_409(client):
  task = get_task_store().create(GenerationInput(companion_name="等待中"))
  res = client.post(f"/api/companion/generate/{task.id}/import")
  assert res.status_code == 409


def test_import_without_live2d_422(client):
  created = client.post(
    "/api/companion/generate/upload",
    data={"companion_name": "无形象", "corpus_text": "语料"},
  )
  assert created.status_code == 201
  res = client.post(f"/api/companion/generate/{created.json()['id']}/import")
  assert res.status_code == 422
  assert "no Live2D model" in res.json()["detail"]


# ---------------------------------------------------------------------------
# wizard static contracts
# ---------------------------------------------------------------------------


def test_wizard_static_contracts():
  html = (_STATIC_WIZARD / "index.html").read_text(encoding="utf-8")
  js = (_STATIC_WIZARD / "wizard.js").read_text(encoding="utf-8")

  # The page defers logic to the external script and exposes the key controls.
  assert "/static/companion/wizard/wizard.js" in html
  for element_id in (
    "gen-form", "submit-btn", "import-btn", "manifest-btn",
    "file-corpus", "file-images", "file-audio", "file-video",
    "live2d-path", "stage-list",
  ):
    assert f'id="{element_id}"' in html, element_id

  # The script drives the multipart upload + one-click import endpoints.
  assert "generate/upload" in js
  assert "/import" in js
  for field in (
    "companion_name", "corpus_files",
    "reference_images", "reference_audio", "reference_video",
    "live2d_package_path",
  ):
    assert field in js, field
