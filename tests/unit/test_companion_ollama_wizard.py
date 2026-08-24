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

"""Phase 5 M1 tests: Ollama one-click setup wizard.

Covers the tier-config write helpers (``companion/ai/open_source.py``),
``POST /api/companion/ai/open-source/config`` (config persistence + probe
failure paths, httpx and config writes both mocked), and the fixed
``GET /api/companion/ai/open-source`` unavailable path.
"""

import json
from pathlib import Path

import httpx
import pytest

import companion.ai.open_source as ai_open_source
from companion.ai.open_source import (
  DEFAULT_OLLAMA_CONFIG_TIERS,
  OLLAMA_CONFIG_TIER_PREFIXES,
  apply_ollama_tier_config,
  build_ollama_tier_patch,
  normalize_ollama_openai_base_url,
)
from companion.generator import open_source as gen_open_source

_STATIC_OLLAMA = Path(__file__).resolve().parents[2] / "static" / "companion" / "ollama"
_LOCALES_DIR = Path(__file__).resolve().parents[2] / "static" / "locales"
_ALL_LOCALES = ("en", "ja", "ko", "zh-CN", "zh-TW", "ru", "es", "pt")

_TAGS_PAYLOAD = {"models": [{"name": "qwen3:8b"}, {"name": "llama3.1:8b"}]}


class _FakeConfigManager:
  """Records core_config.json reads/writes without touching disk."""

  def __init__(self, existing=None):
    self.existing = existing if existing is not None else {}
    self.saved = None

  def load_json_config(self, filename, default=None):
    assert filename == "core_config.json"
    return self.existing

  def save_json_config(self, filename, data):
    assert filename == "core_config.json"
    self.saved = data


class _FakeTagsResponse:
  def __init__(self, payload, status_code=200):
    self._payload = payload
    self.status_code = status_code

  def raise_for_status(self):
    if self.status_code != 200:
      raise httpx.HTTPError(f"status {self.status_code}")

  def json(self):
    return self._payload


@pytest.fixture()
def client():
  from fastapi import FastAPI
  from fastapi.testclient import TestClient

  import companion.api.routes as routes

  app = FastAPI()
  app.include_router(routes.router)
  return TestClient(app)


@pytest.fixture()
def fake_cm(monkeypatch):
  """Route the endpoint's config writes into an in-memory recorder."""
  import utils.config_manager as cm_mod

  cm = _FakeConfigManager()
  monkeypatch.setattr(cm_mod, "get_config_manager", lambda: cm)
  return cm


def _mock_daemon(monkeypatch, payload=_TAGS_PAYLOAD):
  """Local Ollama daemon replies to GET /api/tags with ``payload``."""
  monkeypatch.setattr(
    gen_open_source.httpx, "get",
    lambda url, timeout: _FakeTagsResponse(payload),
  )


def _mock_daemon_down(monkeypatch):
  def _raise(url, timeout):
    raise ConnectionError("connection refused")

  monkeypatch.setattr(gen_open_source.httpx, "get", _raise)


# ---------------------------------------------------------------------------
# tier patch helpers
# ---------------------------------------------------------------------------


def test_normalize_openai_base_url():
  assert (
    normalize_ollama_openai_base_url("http://127.0.0.1:11434")
    == "http://127.0.0.1:11434/v1"
  )
  # Already-normalized URLs must not grow a second /v1.
  assert (
    normalize_ollama_openai_base_url("http://127.0.0.1:11434/v1")
    == "http://127.0.0.1:11434/v1"
  )
  assert normalize_ollama_openai_base_url("") == "http://127.0.0.1:11434/v1"


def test_build_tier_patch_default_targets_summary():
  patch = build_ollama_tier_patch("qwen3:8b", "http://127.0.0.1:11434")
  assert DEFAULT_OLLAMA_CONFIG_TIERS == ("summary",)
  assert patch == {
    "enableCustomApi": True,
    "summaryModelProvider": "custom",
    "summaryModelUrl": "http://127.0.0.1:11434/v1",
    "summaryModelId": "qwen3:8b",
    "summaryModelApiKey": "ollama",
  }


def test_build_tier_patch_multiple_tiers():
  patch = build_ollama_tier_patch(
    "llama3.1:8b", "http://127.0.0.1:11434", ["summary", "conversation"]
  )
  for prefix in ("summary", "conversation"):
    assert patch[f"{prefix}ModelProvider"] == "custom"
    assert patch[f"{prefix}ModelId"] == "llama3.1:8b"
    assert patch[f"{prefix}ModelUrl"] == "http://127.0.0.1:11434/v1"
    assert patch[f"{prefix}ModelApiKey"] == "ollama"


@pytest.mark.parametrize("model,tiers", [
  ("", ["summary"]),          # empty model
  ("   ", ["summary"]),       # blank model
  ("qwen3:8b", ["realtime"]), # provider-specific tier not wizard-configurable
  ("qwen3:8b", ["nope"]),     # unknown tier
  ("qwen3:8b", []),           # no tiers
])
def test_build_tier_patch_rejects_bad_input(model, tiers):
  with pytest.raises(ValueError):
    build_ollama_tier_patch(model, "http://127.0.0.1:11434", tiers)


def test_apply_tier_config_merges_existing_fields():
  cm = _FakeConfigManager(existing={
    "coreApiKey": "keep-me",
    "summaryModelId": "old-model",
  })
  patch = apply_ollama_tier_config(
    "qwen3:8b", "http://127.0.0.1:11434", ["summary"], cm
  )
  assert cm.saved is not None
  # Unrelated fields survive the merge; the tier patch wins on conflicts.
  assert cm.saved["coreApiKey"] == "keep-me"
  assert cm.saved["summaryModelId"] == "qwen3:8b"
  assert cm.saved["enableCustomApi"] is True
  assert patch["summaryModelUrl"] == "http://127.0.0.1:11434/v1"


def test_apply_tier_config_survives_unreadable_existing_config():
  class _BrokenLoadConfigManager(_FakeConfigManager):
    def load_json_config(self, filename, default=None):
      raise OSError("disk on fire")

  cm = _BrokenLoadConfigManager()
  apply_ollama_tier_config("qwen3:8b", "http://127.0.0.1:11434", ["summary"], cm)
  assert cm.saved["summaryModelId"] == "qwen3:8b"


# ---------------------------------------------------------------------------
# POST /api/companion/ai/open-source/config
# ---------------------------------------------------------------------------


def test_config_endpoint_persists_selected_model(client, fake_cm, monkeypatch):
  _mock_daemon(monkeypatch)
  resp = client.post(
    "/api/companion/ai/open-source/config",
    json={"model": "qwen3:8b"},
  )
  assert resp.status_code == 200
  body = resp.json()
  assert body["saved"] is True
  assert body["provider"] == "ollama"
  assert body["tiers"] == ["summary"]
  assert body["config"]["model"] == "qwen3:8b"
  assert body["config"]["base_url"].endswith("/v1")
  assert fake_cm.saved["summaryModelId"] == "qwen3:8b"
  assert fake_cm.saved["summaryModelProvider"] == "custom"
  assert fake_cm.saved["enableCustomApi"] is True


def test_config_endpoint_accepts_multiple_tiers(client, fake_cm, monkeypatch):
  _mock_daemon(monkeypatch)
  resp = client.post(
    "/api/companion/ai/open-source/config",
    json={"model": "llama3.1:8b", "tiers": ["summary", "conversation"]},
  )
  assert resp.status_code == 200
  assert resp.json()["tiers"] == ["summary", "conversation"]
  assert fake_cm.saved["conversationModelId"] == "llama3.1:8b"
  assert fake_cm.saved["summaryModelId"] == "llama3.1:8b"


def test_config_endpoint_probe_failure_writes_nothing(client, fake_cm, monkeypatch):
  """Daemon unreachable → 502 and the config file is never touched."""
  _mock_daemon_down(monkeypatch)
  resp = client.post(
    "/api/companion/ai/open-source/config",
    json={"model": "qwen3:8b"},
  )
  assert resp.status_code == 502
  assert "unreachable" in resp.json()["detail"]
  assert fake_cm.saved is None


def test_config_endpoint_rejects_uninstalled_model(client, fake_cm, monkeypatch):
  _mock_daemon(monkeypatch)
  resp = client.post(
    "/api/companion/ai/open-source/config",
    json={"model": "not-pulled:1b"},
  )
  assert resp.status_code == 409
  assert "ollama pull not-pulled:1b" in resp.json()["detail"]
  assert fake_cm.saved is None


def test_config_endpoint_rejects_unsupported_tier(client, fake_cm, monkeypatch):
  _mock_daemon(monkeypatch)
  resp = client.post(
    "/api/companion/ai/open-source/config",
    json={"model": "qwen3:8b", "tiers": ["realtime"]},
  )
  assert resp.status_code == 422
  assert fake_cm.saved is None


def test_config_endpoint_rejects_empty_tiers(client, fake_cm, monkeypatch):
  _mock_daemon(monkeypatch)
  resp = client.post(
    "/api/companion/ai/open-source/config",
    json={"model": "qwen3:8b", "tiers": ["  "]},
  )
  assert resp.status_code == 422
  assert fake_cm.saved is None


# ---------------------------------------------------------------------------
# GET /api/companion/ai/open-source (probe status for the wizard page)
# ---------------------------------------------------------------------------


class _FakeProbeClient:
  """Stand-in for ``httpx.Client`` inside ``companion.ai.open_source``."""

  def __init__(self, payload=None, error=None):
    self._payload = payload
    self._error = error

  def __enter__(self):
    return self

  def __exit__(self, *exc_info):
    return False

  def get(self, url):
    if self._error is not None:
      raise self._error
    return _FakeTagsResponse(self._payload)


def test_status_endpoint_reports_models_when_available(client, monkeypatch):
  monkeypatch.setattr(
    ai_open_source.httpx, "Client",
    lambda **kwargs: _FakeProbeClient(payload=_TAGS_PAYLOAD),
  )
  resp = client.get("/api/companion/ai/open-source")
  assert resp.status_code == 200
  body = resp.json()
  assert body["available"] is True
  assert body["active"] == "ollama"
  assert body["models"] == ["qwen3:8b", "llama3.1:8b"]
  assert body["config"]["model"] in body["models"]
  assert body["config"]["base_url"].endswith("/v1")


def test_status_endpoint_unavailable_path_serializes(client, monkeypatch):
  """Probe failure must yield a JSON status, not a serialization crash.

  Regression guard: the route used to call ``.model_dump()`` on the
  ``OpenSourceProvider`` dataclass, which 500'd on exactly the path the
  wizard needs to render install hints.
  """
  monkeypatch.setattr(
    ai_open_source.httpx, "Client",
    lambda **kwargs: _FakeProbeClient(error=httpx.ConnectError("refused")),
  )
  resp = client.get("/api/companion/ai/open-source")
  assert resp.status_code == 200
  body = resp.json()
  assert body["available"] is False
  probed = body["providers"]["ollama"]
  assert probed["available"] is False
  assert probed["name"] == "ollama"
  assert probed["base_url"]


# ---------------------------------------------------------------------------
# static wizard page + i18n contracts
# ---------------------------------------------------------------------------


def test_ollama_page_static_contracts():
  html = (_STATIC_OLLAMA / "index.html").read_text(encoding="utf-8")
  js = (_STATIC_OLLAMA / "ollama.js").read_text(encoding="utf-8")
  # The page wires up the shared companion i18n loader and the probe/config
  # endpoints without trailing slashes (neko-guide hard rule).
  assert "/static/companion/i18n.js" in html
  assert "/api/companion/ai/open-source/config" in js
  assert "/api/companion/ai/open-source/'" not in js
  assert "'/api/companion'" in js
  # Probe status, model picker, and per-OS install hints are all present.
  for element_id in (
    "probe-state", "model-select", "apply-btn", "recheck-btn",
    "os-macos", "os-windows", "os-linux",
  ):
    assert f'id="{element_id}"' in html, element_id


@pytest.mark.parametrize("locale", _ALL_LOCALES)
def test_ollama_i18n_keys_in_all_locales(locale):
  data = json.loads(
    (_LOCALES_DIR / f"{locale}.json").read_text(encoding="utf-8")
  )
  block = data["companion"]["ollama"]
  expected = {
    "title", "subtitle", "wizardLink", "backToWizard", "probeTitle",
    "statusChecking", "statusAvailable", "statusUnavailable", "recheck",
    "baseUrlLabel", "modelCountLabel", "configTitle", "noModels",
    "modelLabel", "tiersLabel", "tierSummary", "tierConversation",
    "apply", "applying", "applied", "applyFailed", "installTitle",
    "installIntro", "pullHint",
  }
  assert set(block) == expected
  assert all(isinstance(v, str) and v for v in block.values())


def test_tier_prefix_map_matches_core_config_vocabulary():
  """Tiers exposed by the wizard must map onto real core_config prefixes."""
  assert set(OLLAMA_CONFIG_TIER_PREFIXES) == {
    "conversation", "summary", "correction", "emotion", "vision", "agent",
  }
  # omni/tts are deliberately excluded: their routing carries provider
  # semantics (api_type / voices) a local Ollama cannot serve.
  assert "realtime" not in OLLAMA_CONFIG_TIER_PREFIXES
  assert "tts_default" not in OLLAMA_CONFIG_TIER_PREFIXES
