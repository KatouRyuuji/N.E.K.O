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

"""Media playback monitor + read-only bridge to the music router.

``music_state`` exposes a read-only snapshot of ``main_routers.music_router``
runtime state (source whitelist, proxy cache usage, NetEase VIP resolver
availability). It never mutates the router and degrades gracefully when the
router or its dependencies are unavailable (e.g. slim test environments).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MediaStatus:
  playing: bool = False
  title: str = ""
  artist: str = ""
  source: str = "unknown"


class MediaMonitor:
  def snapshot(self) -> MediaStatus:
    return MediaStatus()

  def music_state(self) -> dict[str, Any]:
    """Read-only view of the music router runtime state."""
    try:
      from main_routers import music_router
    except Exception as exc:
      return {
        "available": False,
        "reason": f"music_router unavailable: {type(exc).__name__}",
      }

    cache = getattr(music_router, "MUSIC_PROXY_CACHE", None)
    cache_info: dict[str, Any] = {}
    if cache is not None:
      try:
        cache_info = {
          "entries": len(cache),
          "current_size": cache.currsize,
          "max_size": cache.maxsize,
          "ttl_seconds": cache.ttl,
        }
      except Exception:
        cache_info = {"entries": None}

    pyncm_available = getattr(music_router, "_PYNCM_AVAILABLE", None)
    domains: list[str] = []
    try:
      from utils.music_crawlers import MUSIC_SOURCE_DOMAINS

      domains = sorted(MUSIC_SOURCE_DOMAINS)
    except Exception:
      pass

    return {
      "available": True,
      "source_domains": domains,
      "proxy_cache": cache_info,
      # None = the lazy import has not been attempted yet.
      "netease_vip_resolver": pyncm_available,
    }
