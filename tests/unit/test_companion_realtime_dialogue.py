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

"""Unit tests for the Phase 4 realtime dialogue facades + session endpoint.

Everything is mocked — no real websocket, no live config files, no LLM.
"""

import json

import pytest

from companion.ai import runtime as runtime_mod
from companion.ai.chat import CompanionChatBridge
from companion.ai.realtime_voice import CompanionRealtimeVoiceBridge
from companion.models.profile import CompanionProfile


def _profile(name="小柚", memory_name=""):
  return CompanionProfile(
    id="c1", name=name, display_name=name, memory_character_name=memory_name
  )


class _FakeConfigManager:
  """Scripted config manager double: tier configs + core config."""

  def __init__(self, tiers=None, core_config=None):
    self.tiers = tiers or {}
    self.core_config = core_config or {}
    self.requested_tiers = []

  def get_model_api_config(self, tier):
    self.requested_tiers.append(tier)
    value = self.tiers.get(tier)
    if isinstance(value, Exception):
      raise value
    if value is None:
      raise ValueError(f"Unknown model_type: {tier}")
    return dict(value)

  def get_core_config(self):
    return dict(self.core_config)


_CHAT_TIER = {
  "model": "fake-conversation-model",
  "base_url": "https://example.invalid/v1",
  "api_key": "sk-top-secret",
  "is_custom": True,
}

_REALTIME_TIER = {
  "model": "fake-realtime-model",
  "base_url": "wss://example.invalid/realtime",
  "api_key": "sk-realtime-secret",
  "api_type": "qwen",
}


# ── chat bridge ──────────────────────────────────────────────────────────────


def test_chat_bridge_routes_by_resolved_memory_name():
  bridge = CompanionChatBridge(_profile(memory_name="小柚(1)"))
  assert bridge.character_name == "小柚(1)"
  assert bridge.session_character() == "小柚(1)"  # legacy API preserved
  assert bridge.websocket_url() == "/ws/小柚(1)"


def test_chat_bridge_protocol_frames_match_websocket_router():
  bridge = CompanionChatBridge(_profile())
  assert bridge.start_session_message() == {
    "action": "start_session", "input_type": "text", "new_session": True,
  }
  assert bridge.text_message("你好") == {
    "action": "stream_data", "input_type": "text", "data": "你好",
  }
  assert bridge.text_message("你好", request_id="req-1")["request_id"] == "req-1"
  assert bridge.end_session_message() == {"action": "end_session"}


def test_chat_provider_config_uses_conversation_tier_and_hides_api_key():
  cm = _FakeConfigManager(tiers={"conversation": _CHAT_TIER})
  bridge = CompanionChatBridge(_profile())
  cfg = bridge.provider_config(cm)
  assert cm.requested_tiers == ["conversation"]
  assert cfg == {
    "tier": "conversation",
    "model": "fake-conversation-model",
    "base_url": "https://example.invalid/v1",
    "is_custom": True,
    "has_api_key": True,
  }
  assert "sk-top-secret" not in json.dumps(cfg)


def test_chat_provider_config_degrades_when_tier_unconfigured():
  cm = _FakeConfigManager(tiers={"conversation": RuntimeError("tier missing")})
  cfg = CompanionChatBridge(_profile()).provider_config(cm)
  assert cfg["model"] == ""
  assert cfg["has_api_key"] is False


# ── realtime voice bridge ────────────────────────────────────────────────────


def test_realtime_bridge_protocol_frames():
  bridge = CompanionRealtimeVoiceBridge(_profile())
  assert bridge.websocket_channel() == "websocket"  # legacy API preserved
  assert bridge.websocket_url() == "/ws/小柚"
  assert bridge.start_session_message() == {
    "action": "start_session", "input_type": "audio", "new_session": True,
  }
  assert bridge.audio_chunk_message([1, 2, 3]) == {
    "action": "stream_data", "input_type": "audio", "data": [1, 2, 3],
  }
  assert bridge.end_session_message() == {"action": "end_session"}


def test_realtime_api_type_comes_from_realtime_tier():
  cm = _FakeConfigManager(tiers={"realtime": _REALTIME_TIER})
  cfg = CompanionRealtimeVoiceBridge(_profile()).provider_config(cm)
  assert cm.requested_tiers == ["realtime"]
  assert cfg["tier"] == "realtime"
  assert cfg["api_type"] == "qwen"
  assert cfg["has_api_key"] is True
  assert "sk-realtime-secret" not in json.dumps(cfg)


def test_realtime_api_type_falls_back_to_core_api_type():
  # Mirrors main_logic/core/lifecycle.py: realtime tier api_type wins,
  # otherwise CORE_API_TYPE.
  tier = dict(_REALTIME_TIER, api_type="")
  cm = _FakeConfigManager(
    tiers={"realtime": tier}, core_config={"CORE_API_TYPE": "gemini"}
  )
  cfg = CompanionRealtimeVoiceBridge(_profile()).provider_config(cm)
  assert cfg["api_type"] == "gemini"


def test_realtime_provider_config_degrades_safely():
  cm = _FakeConfigManager(tiers={"realtime": RuntimeError("not configured")})
  cfg = CompanionRealtimeVoiceBridge(_profile()).provider_config(cm)
  assert cfg["model"] == ""
  assert cfg["api_type"] == ""


def test_dialogue_bridges_are_symmetric():
  """neko-guide symmetry rule: both channels expose the same facade surface."""
  cm = _FakeConfigManager(
    tiers={"conversation": _CHAT_TIER, "realtime": _REALTIME_TIER}
  )
  chat = CompanionChatBridge(_profile()).session_metadata(cm)
  voice = CompanionRealtimeVoiceBridge(_profile()).session_metadata(cm)
  assert set(chat.keys()) == set(voice.keys())
  assert set(chat["protocol"].keys()) == set(voice["protocol"].keys())
  assert chat["websocket_url"] == voice["websocket_url"]
  assert chat["input_type"] == "text"
  assert voice["input_type"] == "audio"


# ── runtime helpers ──────────────────────────────────────────────────────────


def test_live_session_snapshot_none_without_booted_server():
  # Unit test process never calls init_shared_state → metadata-only mode.
  assert runtime_mod.live_session_snapshot("任意角色") is None


def test_sanitize_api_config_handles_none():
  cfg = runtime_mod.sanitize_api_config(None, "conversation")
  assert cfg == {
    "tier": "conversation", "model": "", "base_url": "",
    "is_custom": False, "has_api_key": False,
  }


def test_tier_api_config_none_when_no_config_manager(monkeypatch):
  monkeypatch.setattr(runtime_mod, "resolve_runtime_config_manager", lambda: None)
  assert runtime_mod.tier_api_config("conversation") is None


# ── session metadata endpoint ────────────────────────────────────────────────


@pytest.fixture()
def session_client(monkeypatch):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient

  import companion.api.routes as routes

  cm = _FakeConfigManager(
    tiers={"conversation": _CHAT_TIER, "realtime": _REALTIME_TIER},
    core_config={"CORE_API_TYPE": "qwen"},
  )
  monkeypatch.setattr(runtime_mod, "resolve_runtime_config_manager", lambda: cm)

  app = FastAPI()
  app.include_router(routes.router)
  return TestClient(app)


def test_session_endpoint_metadata_only_mode(session_client, monkeypatch):
  monkeypatch.setattr(runtime_mod, "live_session_snapshot", lambda name: None)
  resp = session_client.get("/api/companion/session/小柚")
  assert resp.status_code == 200
  body = resp.json()
  assert body["character_name"] == "小柚"
  assert body["websocket_url"] == "/ws/小柚"
  assert body["runtime"] == {"available": False, "session": None}
  assert body["chat"]["provider"]["tier"] == "conversation"
  assert body["chat"]["provider"]["model"] == "fake-conversation-model"
  assert body["realtime_voice"]["provider"]["api_type"] == "qwen"
  assert body["chat"]["protocol"]["start_session"]["input_type"] == "text"
  assert body["realtime_voice"]["protocol"]["start_session"]["input_type"] == "audio"
  # Secrets must never leave the server.
  assert "sk-top-secret" not in resp.text
  assert "sk-realtime-secret" not in resp.text


def test_session_endpoint_404_for_unknown_character(session_client, monkeypatch):
  monkeypatch.setattr(
    runtime_mod, "live_session_snapshot",
    lambda name: {"registered": False, "connected": False},
  )
  resp = session_client.get("/api/companion/session/不存在的角色")
  assert resp.status_code == 404


def test_session_endpoint_live_session(session_client, monkeypatch):
  monkeypatch.setattr(
    runtime_mod, "live_session_snapshot",
    lambda name: {"registered": True, "connected": True, "input_mode": "text"},
  )
  resp = session_client.get("/api/companion/session/小柚")
  assert resp.status_code == 200
  body = resp.json()
  assert body["runtime"]["available"] is True
  assert body["runtime"]["session"]["connected"] is True
  assert body["runtime"]["session"]["input_mode"] == "text"
