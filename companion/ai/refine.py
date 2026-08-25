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

"""Persona refine — one LLM round over an existing character card (Phase 5 M4).

``refine_persona_card`` takes the card's current system prompt plus free-form
user feedback, asks the ``correction`` tier for a minimal revision, and
returns a **proposal** (old/new prompt + unified diff). Nothing is written
here: the API layer only persists after the user confirms the diff
(``POST /api/companion/persona/{name}/refine/apply``), snapshotting the
previous card version first (see ``companion/ai/persona_versions.py``).

Tier semantics follow neko-guide: persona correction work rides the
``correction`` tier; when the tier is not configured the API rejects instead
of silently falling back to another model — unlike the offline generator
wizard, refine edits a live persona and must not degrade to heuristics.

Blocking by design (sync LLM call): async callers must offload with
``asyncio.to_thread``.
"""

from __future__ import annotations

import difflib

from config import (
  COMPANION_GENERATOR_LLM_TIMEOUT_SECONDS,
  COMPANION_PROMPT_SEED_MAX_TOKENS,
  COMPANION_REFINE_FEEDBACK_MAX_TOKENS,
  LLM_OUTPUT_GUARD_MAX_TOKENS,
)
from config.prompts.prompts_companion import COMPANION_PERSONA_REFINE_PROMPT, _loc
from utils.config_manager import get_config_manager
from utils.file_utils import robust_json_loads
from utils.llm_client import create_chat_llm
from utils.logger_config import get_module_logger
from utils.tokenize import truncate_to_tokens

logger = get_module_logger(__name__)

REFINE_TIER = "correction"

_PROMPT_LANGS = {"zh", "en", "ja", "ko", "ru"}


class PersonaRefineUnavailable(RuntimeError):
  """The ``correction`` tier is not configured / not reachable."""


class PersonaRefineFailed(RuntimeError):
  """The LLM round completed but produced no usable revision."""


def _resolve_prompt_lang(locale: str) -> str:
  base = (locale or "").replace("_", "-").split("-")[0].lower()
  return base if base in _PROMPT_LANGS else "en"


def _resolve_refine_api_config() -> dict:
  """Resolve the correction tier route; raise when unconfigured (no fallback)."""
  try:
    api_config = get_config_manager().get_model_api_config(REFINE_TIER)
  except Exception as exc:
    raise PersonaRefineUnavailable(f"correction tier unavailable: {exc}") from exc
  if not api_config or not api_config.get("model") or not api_config.get("base_url"):
    raise PersonaRefineUnavailable("correction tier is not configured")
  return api_config


def _create_refine_llm(api_config: dict):
  # No `temperature=`: provider default (neko-guide 辅助 LLM 调用约定).
  return create_chat_llm(
    api_config["model"], api_config["base_url"], api_config["api_key"],
    max_retries=1,
    timeout=COMPANION_GENERATOR_LLM_TIMEOUT_SECONDS,
    max_completion_tokens=LLM_OUTPUT_GUARD_MAX_TOKENS,  # full revised prompt, no tight task budget
    provider_type=api_config.get("provider_type"),
  )


def _parse_llm_json(text: str | None):
  cleaned = (text or "").strip()
  if cleaned.startswith("```"):
    cleaned = cleaned.replace("```json", "").replace("```", "").strip()
  return robust_json_loads(cleaned)


def build_prompt_diff(current: str, proposed: str) -> list[str]:
  """Line-level unified diff between the current and proposed prompts."""
  return list(
    difflib.unified_diff(
      current.splitlines(),
      proposed.splitlines(),
      fromfile="current",
      tofile="proposed",
      lineterm="",
    )
  )


def refine_persona_card(
  name: str,
  current_system_prompt: str,
  feedback: str,
  locale: str = "zh-CN",
) -> dict:
  """One correction-tier LLM round: current prompt + feedback → diff proposal.

  Returns ``{name, current_system_prompt, proposed_system_prompt, diff,
  change_summary, llm}``. Raises :class:`PersonaRefineUnavailable` when the
  tier is unconfigured and :class:`PersonaRefineFailed` when the LLM reply
  is unusable — callers map these to 503 / 502.
  """
  api_config = _resolve_refine_api_config()
  llm = _create_refine_llm(api_config)

  prompt = _loc(COMPANION_PERSONA_REFINE_PROMPT, _resolve_prompt_lang(locale)) % (
    name,
    truncate_to_tokens(current_system_prompt or "", COMPANION_PROMPT_SEED_MAX_TOKENS),
    truncate_to_tokens(feedback or "", COMPANION_REFINE_FEEDBACK_MAX_TOKENS),
  )
  try:
    resp = llm.invoke([{"role": "user", "content": prompt}])
    data = _parse_llm_json(resp.content)
  except Exception as exc:
    logger.warning("Companion persona refine: LLM call failed", exc_info=True)
    raise PersonaRefineFailed(f"refine LLM call failed: {exc}") from exc
  if not isinstance(data, dict):
    raise PersonaRefineFailed("refine LLM returned non-object payload")
  proposed = str(data.get("system_prompt", "") or "").strip()
  if not proposed:
    raise PersonaRefineFailed("refine LLM returned an empty system_prompt")

  return {
    "name": name,
    "current_system_prompt": current_system_prompt,
    "proposed_system_prompt": proposed,
    "changed": proposed != (current_system_prompt or ""),
    "diff": build_prompt_diff(current_system_prompt or "", proposed),
    "change_summary": str(data.get("change_summary", "") or ""),
    "llm": {"tier": REFINE_TIER, "model": api_config["model"]},
  }


__all__ = [
  "REFINE_TIER",
  "PersonaRefineFailed",
  "PersonaRefineUnavailable",
  "build_prompt_diff",
  "refine_persona_card",
]
