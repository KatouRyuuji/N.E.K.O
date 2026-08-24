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

"""Companion generator pipeline — multi-stage long-running analysis.

Phase 2: the analyze_corpus and extract_persona stages call a real LLM
(``summary`` tier via ``config_manager.get_model_api_config``), with a local
Ollama fallback (``companion/generator/open_source.py``) when the tier is not
configured, and a deterministic heuristic fallback when no LLM is reachable
at all — the pipeline never hard-fails because of a missing/unreachable LLM.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from companion.generator.tasks import GenerationTask, TaskStatus, get_task_store
from companion.models.generation import GenerationArtifact, GenerationInput, GenerationStage
from companion.models.manifest import CompanionManifest, MemorySeed
from companion.models.profile import AvatarKind, CompanionProfile, VoiceConfig
from config import (
  COMPANION_ANALYSIS_CONTEXT_MAX_TOKENS,
  COMPANION_CORPUS_MAX_TOKENS,
  COMPANION_GENERATOR_LLM_TIMEOUT_SECONDS,
  COMPANION_PROMPT_SEED_MAX_TOKENS,
  LLM_OUTPUT_GUARD_MAX_TOKENS,
)
from config.prompts.prompts_companion import (
  COMPANION_CORPUS_ANALYSIS_PROMPT,
  COMPANION_PERSONA_EXTRACT_PROMPT,
  _loc,
)
from utils.config_manager import get_config_manager
from utils.file_utils import robust_json_loads
from utils.llm_client import create_chat_llm
from utils.logger_config import get_module_logger
from utils.tokenize import truncate_head_tail_tokens, truncate_to_tokens

logger = get_module_logger(__name__)

_PIPELINE_STAGES: tuple[GenerationStage, ...] = (
  GenerationStage.INGEST,
  GenerationStage.ANALYZE_CORPUS,
  GenerationStage.EXTRACT_PERSONA,
  GenerationStage.CONFIGURE_AVATAR,
  GenerationStage.CONFIGURE_VOICE,
  GenerationStage.INIT_MEMORY,
  GenerationStage.PACKAGE,
)

_PROMPT_LANGS = {"zh", "en", "ja", "ko", "ru"}


def _default_output_root() -> Path:
  root = Path(get_config_manager().docs_dir) / "N.E.K.O" / "companions" / "generated"
  root.mkdir(parents=True, exist_ok=True)
  return root


def _resolve_prompt_lang(locale: str) -> str:
  base = (locale or "").replace("_", "-").split("-")[0].lower()
  return base if base in _PROMPT_LANGS else "en"


# ── LLM resolution ─────────────────────────────────────────────────────────


def _resolve_generator_api_config() -> dict | None:
  """Resolve the LLM route for generation: summary tier, then local Ollama.

  The generator is an offline wizard, not a chat path: a missing tier should
  degrade to a local open-source model (and ultimately to the heuristic
  fallback) instead of failing the whole generation task.
  """
  try:
    api_config = get_config_manager().get_model_api_config('summary')
  except Exception:
    logger.warning("Companion generator: summary tier unavailable", exc_info=True)
    api_config = None
  if api_config and api_config.get('model') and api_config.get('base_url'):
    return dict(api_config, is_ollama=False)

  from companion.generator.open_source import resolve_ollama_api_config

  ollama_config = resolve_ollama_api_config()
  if ollama_config:
    logger.info(
      "Companion generator: summary tier not configured, using local Ollama model=%s",
      ollama_config['model'],
    )
  return ollama_config


def _create_generator_llm(api_config: dict):
  # No `temperature=`: provider default (neko-guide 辅助 LLM 调用约定).
  return create_chat_llm(
    api_config['model'], api_config['base_url'], api_config['api_key'],
    max_retries=1,
    timeout=COMPANION_GENERATOR_LLM_TIMEOUT_SECONDS,
    max_completion_tokens=LLM_OUTPUT_GUARD_MAX_TOKENS,  # variable-length JSON output, no tight task budget
    provider_type=api_config.get('provider_type'),
  )


def _parse_llm_json(text: str | None) -> Any:
  cleaned = (text or "").strip()
  if cleaned.startswith("```"):
    cleaned = cleaned.replace("```json", "").replace("```", "").strip()
  return robust_json_loads(cleaned)


# ── analyze_corpus stage ───────────────────────────────────────────────────


def _analyze_corpus_llm(gen_input: GenerationInput, llm: Any) -> dict[str, Any] | None:
  """LLM-backed corpus analysis. Returns None on any failure."""
  text = (gen_input.corpus_text or "").strip()
  if not text:
    return None
  # Input budget: HEAD+TAIL — persona notes usually open the corpus, the
  # freshest tone samples close it; a head-only cut would drop the latter.
  _half = COMPANION_CORPUS_MAX_TOKENS // 2
  prompt = _loc(
    COMPANION_CORPUS_ANALYSIS_PROMPT, _resolve_prompt_lang(gen_input.locale)
  ) % (
    gen_input.companion_name,
    truncate_head_tail_tokens(text, _half, _half),
  )
  try:
    resp = llm.invoke([{"role": "user", "content": prompt}])
    data = _parse_llm_json(resp.content)
  except Exception:
    logger.warning("Companion generator: corpus analysis LLM call failed", exc_info=True)
    return None
  if not isinstance(data, dict):
    return None
  traits = [str(t) for t in data.get("detected_traits", []) if str(t).strip()]
  return {
    "corpus_length": len(text),
    "file_count": len(gen_input.corpus_files),
    "detected_traits": traits,
    "speaking_style": str(data.get("speaking_style", "") or "casual"),
    "relationship_hints": [
      str(h) for h in data.get("relationship_hints", []) if str(h).strip()
    ],
    "summary": str(data.get("summary", "") or ""),
  }


def _analyze_corpus_fallback(gen_input: GenerationInput) -> dict[str, Any]:
  """Deterministic keyword heuristic — used when no LLM is reachable."""
  text = gen_input.corpus_text or ""
  traits: list[str] = []
  if "温柔" in text or "gentle" in text.lower():
    traits.append("gentle")
  if "活泼" in text or "cheerful" in text.lower():
    traits.append("cheerful")
  return {
    "corpus_length": len(text),
    "file_count": len(gen_input.corpus_files),
    "detected_traits": traits,
    "speaking_style": "casual" if len(text) < 500 else "expressive",
    "relationship_hints": [],
    "summary": "",
  }


# ── extract_persona stage ──────────────────────────────────────────────────


def _extract_persona_llm(
  gen_input: GenerationInput, analysis: dict[str, Any], llm: Any
) -> tuple[str, list[MemorySeed]] | None:
  """LLM-backed persona extraction. Returns None on any failure."""
  analysis_json = json.dumps(
    {
      k: analysis.get(k)
      for k in ("detected_traits", "speaking_style", "relationship_hints", "summary")
    },
    ensure_ascii=False,
  )
  prompt = _loc(
    COMPANION_PERSONA_EXTRACT_PROMPT, _resolve_prompt_lang(gen_input.locale)
  ) % (
    gen_input.companion_name,
    truncate_to_tokens(analysis_json, COMPANION_ANALYSIS_CONTEXT_MAX_TOKENS),
    truncate_to_tokens(gen_input.system_prompt or "", COMPANION_PROMPT_SEED_MAX_TOKENS),
    gen_input.companion_name,
  )
  try:
    resp = llm.invoke([{"role": "user", "content": prompt}])
    data = _parse_llm_json(resp.content)
  except Exception:
    logger.warning("Companion generator: persona extraction LLM call failed", exc_info=True)
    return None
  if not isinstance(data, dict):
    return None
  system_prompt = str(data.get("system_prompt", "") or "").strip()
  if not system_prompt:
    return None
  seeds: list[MemorySeed] = []
  for raw in data.get("memory_seeds", []):
    if not isinstance(raw, dict):
      continue
    entity = str(raw.get("entity", "") or "").strip()
    content = str(raw.get("content", "") or "").strip()
    if entity and content:
      seeds.append(MemorySeed(entity=entity, content=content))
  if not seeds:
    seeds = _default_memory_seeds(gen_input)
  return system_prompt, seeds[:5]


def _default_memory_seeds(gen_input: GenerationInput) -> list[MemorySeed]:
  return [
    MemorySeed(
      entity="neko",
      content=f"{gen_input.companion_name} 是由用户定制的专属虚拟伴侣。",
    ),
    MemorySeed(
      entity="relationship",
      content="主人正在与我建立长期的陪伴关系。",
    ),
  ]


def _extract_persona_fallback(
  gen_input: GenerationInput, analysis: dict[str, Any]
) -> tuple[str, list[MemorySeed]]:
  """Template fallback — used when no LLM is reachable."""
  base_prompt = gen_input.system_prompt or ""
  traits = analysis.get("detected_traits", [])
  trait_hint = "、".join(traits) if traits else "友善"
  if not base_prompt:
    base_prompt = (
      f"你是{gen_input.companion_name}，性格{trait_hint}。"
      "你会记住与主人的互动，用自然口语陪伴对方。"
    )
  return base_prompt, _default_memory_seeds(gen_input)


# ── pipeline ───────────────────────────────────────────────────────────────


def run_pipeline_sync(task: GenerationTask, output_root: Path | None = None) -> GenerationArtifact:
  """Run all pipeline stages synchronously.

  Blocking by design (LLM + disk IO): async callers must offload with
  ``asyncio.to_thread`` (see ``companion/api/routes.py``).
  """
  store = get_task_store()
  gen_input = task.input
  out_root = output_root or _default_output_root()

  analysis: dict[str, Any] = {}
  system_prompt = ""
  memory_seeds: list[MemorySeed] = []
  llm_meta: dict[str, Any] = {"provider": "heuristic", "model": None}
  llm: Any = None

  api_config = _resolve_generator_api_config()
  if api_config:
    try:
      llm = _create_generator_llm(api_config)
      llm_meta = {
        "provider": "ollama" if api_config.get("is_ollama") else "summary",
        "model": api_config["model"],
      }
    except Exception:
      logger.warning("Companion generator: LLM client construction failed", exc_info=True)
      llm = None

  task.status = TaskStatus.RUNNING
  store.update(task)

  try:
    for stage in _PIPELINE_STAGES:
      task.current_stage = stage
      store.update(task)
      logger.info("Companion generator stage=%s task=%s", stage.value, task.id)

      if stage == GenerationStage.INGEST:
        if not gen_input.companion_name.strip():
          raise ValueError("companion_name is required")

      elif stage == GenerationStage.ANALYZE_CORPUS:
        result = _analyze_corpus_llm(gen_input, llm) if llm else None
        if result is None:
          if llm is not None and (gen_input.corpus_text or "").strip():
            llm_meta = dict(llm_meta, degraded=True)
          analysis = _analyze_corpus_fallback(gen_input)
          analysis["analysis_source"] = "heuristic"
        else:
          analysis = result
          analysis["analysis_source"] = "llm"

      elif stage == GenerationStage.EXTRACT_PERSONA:
        persona = _extract_persona_llm(gen_input, analysis, llm) if llm else None
        if persona is None:
          if llm is not None:
            llm_meta = dict(llm_meta, degraded=True)
          system_prompt, memory_seeds = _extract_persona_fallback(gen_input, analysis)
        else:
          system_prompt, memory_seeds = persona

      elif stage == GenerationStage.CONFIGURE_AVATAR:
        avatar_kind = AvatarKind.LIVE2D
        avatar_id = gen_input.live2d_model_id or ""

      elif stage == GenerationStage.CONFIGURE_VOICE:
        voice = VoiceConfig(
          reference_audio_paths=list(gen_input.reference_audio),
        )

      elif stage == GenerationStage.INIT_MEMORY:
        if not memory_seeds:
          memory_seeds = _default_memory_seeds(gen_input)

      elif stage == GenerationStage.PACKAGE:
        profile_id = str(uuid.uuid4())
        profile = CompanionProfile(
          id=profile_id,
          name=gen_input.companion_name,
          display_name=gen_input.companion_name,
          locale=gen_input.locale,
          system_prompt=system_prompt,
          avatar_kind=avatar_kind,
          avatar_resource_id=avatar_id,
          voice=voice,
          memory_character_name=gen_input.companion_name,
          metadata={"generator_task_id": task.id},
        )
        manifest = CompanionManifest(
          profile=profile,
          memory_seeds=memory_seeds,
          resource_paths={
            "reference_images": ",".join(gen_input.reference_images),
            "reference_video": ",".join(gen_input.reference_video),
          },
          generator_metadata={"analysis": analysis, "llm": llm_meta},
        )
        package_dir = out_root / f"{gen_input.companion_name}_{task.id[:8]}"
        package_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = package_dir / "manifest.json"
        manifest_path.write_text(
          json.dumps(manifest.to_package_dict(), ensure_ascii=False, indent=2),
          encoding="utf-8",
        )
        artifact = GenerationArtifact(
          task_id=task.id,
          profile=profile,
          package_path=str(package_dir),
          manifest_path=str(manifest_path),
          stages_completed=list(task.stages_completed) + [stage],
          analysis_summary=dict(analysis, llm=llm_meta),
        )
        task.artifact = artifact
        task.stages_completed.append(stage)
        task.status = TaskStatus.COMPLETED
        task.current_stage = None
        store.update(task)
        return artifact

      task.stages_completed.append(stage)

    raise RuntimeError("pipeline ended without PACKAGE stage")

  except Exception as exc:
    logger.exception("Companion generator failed task=%s", task.id)
    task.status = TaskStatus.FAILED
    task.error = str(exc)
    task.current_stage = None
    store.update(task)
    raise


def start_generation(gen_input: GenerationInput) -> GenerationTask:
  store = get_task_store()
  task = store.create(gen_input)
  try:
    run_pipeline_sync(task)
  except Exception:
    pass
  return task
