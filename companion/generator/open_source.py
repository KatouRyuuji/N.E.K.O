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

"""Open-source / local LLM detection for the companion generator (Ollama).

Detection heuristics mirror ``brain/openfang_adapter._detect_provider_info``
so the two subsystems agree on what counts as an Ollama endpoint. The probe
talks to Ollama's native ``/api/tags`` endpoint; the resolved config points at
its OpenAI-compatible ``/v1`` facade so it can feed straight into
``utils.llm_client.create_chat_llm``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

from config import COMPANION_OLLAMA_DETECT_TIMEOUT_SECONDS
from utils.logger_config import get_module_logger

logger = get_module_logger(__name__)

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_DEFAULT_PORT = 11434

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


@dataclass
class OllamaStatus:
  """Result of a local Ollama probe."""

  available: bool
  base_url: str
  models: list[str] = field(default_factory=list)
  error: str | None = None


def _is_local_host(host: str) -> bool:
  if host in _LOOPBACK_HOSTS:
    return True
  # RFC1918 private ranges: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
  return (
    host.startswith("10.")
    or host.startswith("192.168.")
    or any(host.startswith(f"172.{i}.") for i in range(16, 32))
  )


def is_ollama_endpoint(base_url: str, model: str = "") -> bool:
  """Heuristically decide whether ``base_url``/``model`` points at Ollama.

  Signals (same as ``brain/openfang_adapter``):
    1. default port 11434 on any host,
    2. URL path containing ``/ollama`` (reverse-proxy setups),
    3. loopback/LAN address combined with "ollama" in the model name.
  """
  if not base_url:
    return False
  try:
    parts = urlsplit(base_url if "//" in base_url else f"//{base_url}")
  except ValueError:
    return False
  host = (parts.hostname or "").lower()
  port = parts.port
  path = (parts.path or "").lower()
  model_lower = (model or "").lower()

  if port == OLLAMA_DEFAULT_PORT:
    return True
  if "/ollama" in path:
    return True
  return _is_local_host(host) and "ollama" in model_lower


def detect_ollama(
  base_url: str = DEFAULT_OLLAMA_BASE_URL,
  timeout: float = COMPANION_OLLAMA_DETECT_TIMEOUT_SECONDS,
) -> OllamaStatus:
  """Probe a local Ollama daemon via ``GET /api/tags``.

  Sync HTTP is fine here: the companion generator pipeline (Phase 1) runs
  synchronously and API routes offload it with ``asyncio.to_thread``.
  """
  base = base_url.rstrip("/")
  try:
    resp = httpx.get(f"{base}/api/tags", timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
  except Exception as exc:
    return OllamaStatus(available=False, base_url=base, error=str(exc))
  models = [
    m.get("name", "")
    for m in payload.get("models", [])
    if isinstance(m, dict) and m.get("name")
  ]
  return OllamaStatus(available=True, base_url=base, models=models)


def _pick_chat_model(models: list[str]) -> str | None:
  """Pick the first model that looks like a chat model (skip embedders)."""
  for name in models:
    if "embed" in name.lower():
      continue
    return name
  return None


def resolve_ollama_api_config(
  base_url: str = DEFAULT_OLLAMA_BASE_URL,
) -> dict | None:
  """Return a ``get_model_api_config``-shaped dict for a local Ollama, or None.

  The returned ``base_url`` targets Ollama's OpenAI-compatible ``/v1`` facade;
  ``api_key`` is the conventional placeholder (Ollama ignores it but the
  OpenAI SDK requires a non-empty key).
  """
  status = detect_ollama(base_url)
  if not status.available:
    return None
  model = _pick_chat_model(status.models)
  if not model:
    logger.info("Ollama detected at %s but no chat model installed", status.base_url)
    return None
  return {
    "model": model,
    "base_url": f"{status.base_url}/v1",
    "api_key": "ollama",
    "provider_type": None,
    "is_ollama": True,
  }
