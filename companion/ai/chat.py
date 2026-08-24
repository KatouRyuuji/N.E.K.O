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

"""Text chat facade over the main websocket channel (Phase 4).

How text dialogue actually flows in N.E.K.O. (research notes):

- ``main_routers/websocket_router.py`` exposes one websocket per character
  at ``/ws/{lanlan_name}``. A text conversation is a session opened with
  ``{"action": "start_session", "input_type": "text"}`` followed by
  ``{"action": "stream_data", "input_type": "text", "data": ...}`` frames,
  and closed with ``{"action": "end_session"}``.
- ``frontend/react-neko-chat`` (built as ``neko-chat-window.iife.js``, the
  single shared chat UI) speaks exactly this protocol through
  ``static/app/app-buttons.js`` / ``app-websocket.js`` — a companion driven
  through this facade appears in the same chat window.
- The text model is resolved from the ``conversation`` provider tier via
  ``config_manager.get_model_api_config('conversation')``; per neko-guide
  the model is never hardcoded here.

The bridge does **not** open sockets itself — it exposes the routing
(character name, websocket URL), the provider tier, and ready-to-send
protocol frames, so callers (HTTP metadata endpoint, future companion
runtimes, tests) stay decoupled from the live server.
"""

from __future__ import annotations

from companion.ai import runtime
from companion.models.profile import CompanionProfile


class CompanionChatBridge:
  """Callable facade: character routing + provider tier + WS text frames."""

  tier = "conversation"
  input_type = "text"

  def __init__(self, profile: CompanionProfile) -> None:
    self.profile = profile

  @property
  def character_name(self) -> str:
    return self.profile.resolved_memory_name()

  def session_character(self) -> str:
    return self.character_name

  def websocket_url(self) -> str:
    return f"/ws/{self.character_name}"

  def provider_config(self, config_manager=None) -> dict:
    """Sanitized ``conversation``-tier config (never exposes api_key)."""
    return runtime.sanitize_api_config(
      runtime.tier_api_config(self.tier, config_manager), self.tier
    )

  def start_session_message(self, new_session: bool = True) -> dict:
    return {
      "action": "start_session",
      "input_type": self.input_type,
      "new_session": new_session,
    }

  def text_message(self, text: str, request_id: str = "") -> dict:
    frame = {
      "action": "stream_data",
      "input_type": self.input_type,
      "data": text,
    }
    if request_id:
      frame["request_id"] = request_id
    return frame

  def end_session_message(self) -> dict:
    return {"action": "end_session"}

  def session_metadata(self, config_manager=None) -> dict:
    return {
      "character_name": self.character_name,
      "channel": "websocket",
      "websocket_url": self.websocket_url(),
      "input_type": self.input_type,
      "provider": self.provider_config(config_manager),
      "protocol": {
        "start_session": self.start_session_message(),
        "end_session": self.end_session_message(),
      },
    }
