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

"""Shared runtime resolution for the dialogue facades (chat / realtime voice).

Both bridges need the same three things from the running N.E.K.O. process:

1. the global config manager (provider tiers via ``get_model_api_config``),
2. the live per-character session managers (``main_routers.shared_state``),
3. a sanitized public projection of one tier's API config.

Centralized here so ``chat.py`` and ``realtime_voice.py`` stay structurally
symmetric without duplicating the lazy-import fallbacks. All imports are
lazy and best-effort: the companion package must stay importable without
the main server booted (unit tests, standalone tools).
"""

from __future__ import annotations


def resolve_runtime_config_manager():
  """Best-effort global config manager; ``None`` when unavailable."""
  try:
    from utils.config_manager import get_config_manager
  except Exception:
    return None
  try:
    return get_config_manager()
  except Exception:
    return None


def live_session_snapshot(character_name: str) -> dict | None:
  """Read-only view of the live websocket session for one character.

  Returns ``None`` when the main server shared state is not initialized
  (unit tests, standalone tools) — callers degrade to metadata-only mode.
  Otherwise returns ``registered`` (character known to the running server,
  same check ``websocket_router`` performs on connect) and ``connected``
  (a frontend websocket is currently attached to the session manager).
  """
  try:
    from main_routers.shared_state import get_session_manager
    manager_view = get_session_manager()
  except Exception:
    return None
  if character_name not in manager_view:
    return {"registered": False, "connected": False}
  mgr = manager_view[character_name]
  return {
    "registered": True,
    "connected": getattr(mgr, "websocket", None) is not None,
    "input_mode": getattr(mgr, "input_mode", "") or "",
  }


def sanitize_api_config(api_config: dict | None, tier: str) -> dict:
  """Public projection of one provider tier config.

  Never exposes ``api_key`` — only whether one is configured. Safe to
  return from HTTP endpoints and to log.
  """
  cfg = api_config or {}
  return {
    "tier": tier,
    "model": cfg.get("model", "") or "",
    "base_url": cfg.get("base_url", "") or "",
    "is_custom": bool(cfg.get("is_custom", False)),
    "has_api_key": bool(cfg.get("api_key")),
  }


def tier_api_config(tier: str, config_manager=None) -> dict | None:
  """Raw tier config from the (given or global) config manager.

  Returns ``None`` when no config manager is reachable or the tier lookup
  fails — the tier being unconfigured is a normal state, not an error.
  """
  cm = config_manager if config_manager is not None else resolve_runtime_config_manager()
  if cm is None:
    return None
  try:
    return cm.get_model_api_config(tier)
  except Exception:
    return None
