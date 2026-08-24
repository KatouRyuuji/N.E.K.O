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

"""Realtime voice facade over the main websocket channel (Phase 4).

How realtime voice actually flows in N.E.K.O. (research notes):

- The same per-character websocket ``/ws/{lanlan_name}``
  (``main_routers/websocket_router.py``) carries voice: the session is
  opened with ``{"action": "start_session", "input_type": "audio"}`` and
  mic frames arrive as ``{"action": "stream_data", "input_type": "audio",
  "data": [...]}`` (``static/app/app-audio-capture.js``). The backend
  session manager (``main_logic/core``) forwards them to the realtime
  provider client (``main_logic/omni_realtime_client``).
- The provider is resolved from the ``realtime`` tier via
  ``config_manager.get_model_api_config('realtime')``; the effective
  ``api_type`` mirrors ``main_logic/core/lifecycle.py``:
  ``realtime_config['api_type'] or core_config['CORE_API_TYPE']``.

Like the chat bridge, this facade never opens sockets — it exposes the
routing, the provider tier, and ready-to-send protocol frames.
"""

from __future__ import annotations

from companion.ai import runtime
from companion.models.profile import CompanionProfile


def _resolved_character(profile: CompanionProfile, override: str | None) -> str:
  if override and override.strip():
    return override.strip()
  return profile.resolved_memory_name()


class CompanionRealtimeVoiceBridge:
  """Callable facade: character routing + provider tier + WS audio frames."""

  tier = "realtime"
  input_type = "audio"

  def __init__(self, profile: CompanionProfile) -> None:
    self.profile = profile

  @property
  def character_name(self) -> str:
    return self.profile.resolved_memory_name()

  def websocket_channel(self) -> str:
    return "websocket"

  def websocket_url(self) -> str:
    return f"/ws/{self.character_name}"

  def connect_info(self, *, character_name: str | None = None) -> dict[str, str]:
    name = _resolved_character(self.profile, character_name)
    return {
      "character_name": name,
      "locale": self.profile.locale,
      "transport": self.websocket_channel(),
      "websocket_path": f"/ws/{name}",
      "protocol": "neko-realtime-v1",
    }

  def provider_config(self, config_manager=None) -> dict:
    """Sanitized ``realtime``-tier config (never exposes api_key).

    Adds ``api_type`` on top of the common projection, resolved the same
    way ``main_logic/core/lifecycle.py`` derives ``core_api_type``: the
    realtime tier's own ``api_type`` wins, else ``CORE_API_TYPE``.
    """
    cm = (
      config_manager
      if config_manager is not None
      else runtime.resolve_runtime_config_manager()
    )
    api_config = runtime.tier_api_config(self.tier, cm)
    cfg = runtime.sanitize_api_config(api_config, self.tier)
    api_type = (api_config or {}).get("api_type", "") or ""
    if not api_type and cm is not None:
      try:
        api_type = cm.get_core_config().get("CORE_API_TYPE", "") or ""
      except Exception:
        api_type = ""
    cfg["api_type"] = api_type
    return cfg

  def start_session_message(self, new_session: bool = True) -> dict:
    return {
      "action": "start_session",
      "input_type": self.input_type,
      "new_session": new_session,
    }

  def audio_chunk_message(self, samples: list) -> dict:
    return {
      "action": "stream_data",
      "input_type": self.input_type,
      "data": samples,
    }

  def end_session_message(self) -> dict:
    return {"action": "end_session"}

  def session_metadata(self, config_manager=None) -> dict:
    return {
      "character_name": self.character_name,
      "channel": self.websocket_channel(),
      "websocket_url": self.websocket_url(),
      "input_type": self.input_type,
      "provider": self.provider_config(config_manager),
      "protocol": {
        "start_session": self.start_session_message(),
        "end_session": self.end_session_message(),
      },
    }
