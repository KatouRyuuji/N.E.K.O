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

"""Open-source AI provider detection and routing (Ollama first).

Lightweight, env-driven counterpart of ``companion/generator/open_source.py``
(no ``config``/logger imports so it stays import-cheap for the API layer).
Backs ``GET /api/companion/ai/open-source``; the generator pipeline uses the
richer generator-side module instead.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx

DEFAULT_OLLAMA_BASE = "http://127.0.0.1:11434"
OLLAMA_OPENAI_COMPAT = "/v1"


@dataclass(frozen=True)
class OpenSourceProvider:
  name: str
  base_url: str
  model: str
  api_key: str = "ollama"
  available: bool = False
  metadata: dict[str, Any] | None = None


def ollama_base_url() -> str:
  return os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_BASE).rstrip("/")


def ollama_openai_base_url() -> str:
  base = ollama_base_url()
  if base.endswith(OLLAMA_OPENAI_COMPAT):
    return base
  return urljoin(base + "/", OLLAMA_OPENAI_COMPAT.lstrip("/"))


def probe_ollama(timeout: float = 2.0) -> OpenSourceProvider:
  """Probe the local Ollama daemon via ``GET {OLLAMA_HOST}/api/tags``.

  Blocking (sync httpx) — callers on the event loop must offload, e.g. with
  ``asyncio.to_thread``. The preferred model comes from
  ``COMPANION_OLLAMA_MODEL`` (default ``llama3``); if it is not among the
  installed models, the first listed model is used instead. Any HTTP/parse
  error yields an ``available=False`` provider rather than raising.
  """
  base = ollama_base_url()
  model = os.environ.get("COMPANION_OLLAMA_MODEL", "llama3")
  provider = OpenSourceProvider(
    name="ollama",
    base_url=ollama_openai_base_url(),
    model=model,
  )
  try:
    with httpx.Client(timeout=timeout, trust_env=False) as client:
      resp = client.get(f"{base}/api/tags")
      if resp.status_code != 200:
        return provider
      data = resp.json()
      models = [m.get("name", "") for m in data.get("models", [])]
      if models and model not in models:
        model = models[0]
      return OpenSourceProvider(
        name="ollama",
        base_url=ollama_openai_base_url(),
        model=model,
        available=True,
        metadata={"models": models},
      )
  except (httpx.HTTPError, OSError, ValueError):
    return provider


def resolve_open_source_provider() -> OpenSourceProvider | None:
  """Return the first available open-source provider, or None."""
  ollama = probe_ollama()
  if ollama.available:
    return ollama
  return None


def to_api_config(provider: OpenSourceProvider) -> dict[str, str]:
  return {
    "model": provider.model,
    "base_url": provider.base_url,
    "api_key": provider.api_key,
    "provider": provider.name,
  }
