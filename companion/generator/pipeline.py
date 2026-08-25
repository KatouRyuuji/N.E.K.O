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

Phase 4 (HA): every completed stage checkpoints its outputs into
``task.stage_results`` (persisted by the SQLite task store), so
``retry_generation`` resumes a failed task from the failing stage — already
completed LLM stages are not re-run. ``start_generation_background`` runs
the same pipeline on a daemon thread for long tasks; callers poll
``GET /generate/{task_id}`` for status.
"""

from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from companion.generator.tasks import GenerationTask, TaskStatus, get_task_store
from companion.models.generation import GenerationArtifact, GenerationInput, GenerationStage
from companion.models.manifest import CompanionManifest, FactSeed, MemorySeed
from companion.models.profile import AvatarKind, CompanionProfile, VoiceConfig
from config import (
  COMPANION_ANALYSIS_CONTEXT_MAX_TOKENS,
  COMPANION_CORPUS_MAX_TOKENS,
  COMPANION_FACT_SEED_MAX_SEEDS,
  COMPANION_FACT_SEED_MIN_CONFIDENCE,
  COMPANION_GENERATOR_LLM_TIMEOUT_SECONDS,
  COMPANION_PROMPT_SEED_MAX_TOKENS,
  LLM_OUTPUT_GUARD_MAX_TOKENS,
)
from config.prompts.prompts_companion import (
  COMPANION_CORPUS_ANALYSIS_PROMPT,
  COMPANION_FACT_SEED_PROMPT,
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
  GenerationStage.EXTRACT_FACT_SEEDS,
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


def _extract_fact_seeds_llm(gen_input: GenerationInput, llm: Any) -> list[FactSeed]:
  """LLM-backed corpus → fact-seed extraction (Phase 5 M4, opt-in stage).

  Returns only the seeds whose self-reported confidence clears
  ``COMPANION_FACT_SEED_MIN_CONFIDENCE``. Facts are ground truth for the
  memory fact layer, so there is deliberately **no heuristic fallback**:
  when the LLM is unreachable or replies garbage the stage yields an empty
  list instead of fabricating "facts" — the generation task never fails
  because of this stage.
  """
  text = (gen_input.corpus_text or "").strip()
  if not text:
    return []
  # Same HEAD+TAIL budget rationale as the analyze_corpus stage.
  _half = COMPANION_CORPUS_MAX_TOKENS // 2
  prompt = _loc(
    COMPANION_FACT_SEED_PROMPT, _resolve_prompt_lang(gen_input.locale)
  ) % (
    gen_input.companion_name,
    truncate_head_tail_tokens(text, _half, _half),
  )
  try:
    resp = llm.invoke([{"role": "user", "content": prompt}])
    data = _parse_llm_json(resp.content)
  except Exception:
    logger.warning("Companion generator: fact seed LLM call failed", exc_info=True)
    return []
  if not isinstance(data, dict) or not isinstance(data.get("facts"), list):
    return []
  seeds: list[FactSeed] = []
  for raw in data["facts"]:
    if not isinstance(raw, dict):
      continue
    content = str(raw.get("content", "") or "").strip()
    if not content:
      continue
    try:
      confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
      confidence = 0.0
    if confidence < COMPANION_FACT_SEED_MIN_CONFIDENCE:
      continue
    try:
      importance = int(raw.get("importance", 6))
    except (TypeError, ValueError):
      importance = 6
    entity = str(raw.get("entity", "") or "").strip() or "master"
    seeds.append(
      FactSeed(
        entity=entity,
        content=content,
        importance=max(1, min(importance, 10)),
        confidence=max(0.0, min(confidence, 1.0)),
      )
    )
  return seeds[:COMPANION_FACT_SEED_MAX_SEEDS]


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


# ── package stage helpers ──────────────────────────────────────────────────


def _bundle_live2d_package(source_path: str, package_dir: Path) -> str | None:
  """Copy a user-provided Live2D package into ``avatar/live2d/``.

  Makes the generated `.neko-companion` package self-contained so the
  one-click import (``POST /generate/{task_id}/import``) can register the
  avatar without referencing the original upload location. Best-effort: an
  unusable source path degrades to a metadata-only package instead of
  failing the whole generation task.

  Returns the manifest ``resource_paths["live2d"]`` hint, or None when
  nothing was bundled.
  """
  from companion.avatar.loader import AvatarPackageError, discover_live2d_entry

  try:
    entry = discover_live2d_entry(source_path)
  except AvatarPackageError:
    logger.warning(
      "Companion generator: no Live2D model in package path %r, skipping bundle",
      source_path,
    )
    return None
  model_dir = entry.parent
  dest = package_dir / "avatar" / "live2d" / model_dir.name
  try:
    shutil.copytree(model_dir, dest, dirs_exist_ok=True)
  except OSError:
    logger.warning(
      "Companion generator: failed to copy Live2D model from %s", model_dir,
      exc_info=True,
    )
    return None
  return "avatar/live2d"


# ── pipeline ───────────────────────────────────────────────────────────────


def _restore_checkpoints(task: GenerationTask) -> dict[str, Any]:
  """Rehydrate stage outputs persisted by a previous (failed) attempt."""
  results = task.stage_results or {}
  state: dict[str, Any] = {
    "analysis": dict(results.get("analysis") or {}),
    "system_prompt": str(results.get("system_prompt") or ""),
    "memory_seeds": [
      MemorySeed.model_validate(s) for s in results.get("memory_seeds") or []
    ],
    "fact_seeds": [
      FactSeed.model_validate(s) for s in results.get("fact_seeds") or []
    ],
    "avatar_kind": (
      AvatarKind(results["avatar_kind"]) if results.get("avatar_kind")
      else AvatarKind.LIVE2D
    ),
    "avatar_id": str(results.get("avatar_id") or ""),
    "voice": (
      VoiceConfig.model_validate(results["voice"]) if results.get("voice")
      else VoiceConfig()
    ),
  }
  if results.get("llm_meta"):
    state["llm_meta"] = dict(results["llm_meta"])
  return state


def run_pipeline_sync(task: GenerationTask, output_root: Path | None = None) -> GenerationArtifact:
  """Run all pipeline stages synchronously, resuming from checkpoints.

  Stages already in ``task.stages_completed`` are skipped and their outputs
  restored from ``task.stage_results`` — this is what makes a retry of a
  failed task resume from the failing stage.

  Blocking by design (LLM + disk IO): async callers must offload with
  ``asyncio.to_thread`` (see ``companion/api/routes.py``).
  """
  store = get_task_store()
  gen_input = task.input
  out_root = output_root or _default_output_root()

  completed = set(task.stages_completed)
  state = _restore_checkpoints(task)
  analysis: dict[str, Any] = state["analysis"]
  system_prompt: str = state["system_prompt"]
  memory_seeds: list[MemorySeed] = state["memory_seeds"]
  fact_seeds: list[FactSeed] = state["fact_seeds"]
  avatar_kind: AvatarKind = state["avatar_kind"]
  avatar_id: str = state["avatar_id"]
  voice: VoiceConfig = state["voice"]
  llm_meta: dict[str, Any] = state.get("llm_meta") or {
    "provider": "heuristic", "model": None,
  }
  llm: Any = None

  # Only resolve an LLM route when an LLM stage still has to run — a resumed
  # task whose analyze/persona stages already checkpointed must not probe
  # the network (config tier / local Ollama) again.
  needs_llm = (
    GenerationStage.ANALYZE_CORPUS not in completed
    or GenerationStage.EXTRACT_PERSONA not in completed
    or (
      gen_input.extract_fact_seeds
      and GenerationStage.EXTRACT_FACT_SEEDS not in completed
    )
  )
  if needs_llm:
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
  task.error = None
  store.update(task)

  try:
    for stage in _PIPELINE_STAGES:
      if stage in completed:
        logger.info(
          "Companion generator resume: skipping stage=%s task=%s",
          stage.value, task.id,
        )
        continue
      task.current_stage = stage
      store.update(task)
      stage_t0 = time.perf_counter()
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
        task.stage_results["analysis"] = analysis
        task.stage_results["llm_meta"] = llm_meta

      elif stage == GenerationStage.EXTRACT_PERSONA:
        persona = _extract_persona_llm(gen_input, analysis, llm) if llm else None
        if persona is None:
          if llm is not None:
            llm_meta = dict(llm_meta, degraded=True)
          system_prompt, memory_seeds = _extract_persona_fallback(gen_input, analysis)
        else:
          system_prompt, memory_seeds = persona
        task.stage_results["system_prompt"] = system_prompt
        task.stage_results["memory_seeds"] = [
          s.model_dump(mode="json") for s in memory_seeds
        ]
        task.stage_results["llm_meta"] = llm_meta

      elif stage == GenerationStage.EXTRACT_FACT_SEEDS:
        # Opt-in (Phase 5 M4): default OFF — the stage checkpoints an empty
        # list so a resumed task never re-enters it.
        if gen_input.extract_fact_seeds and llm is not None:
          fact_seeds = _extract_fact_seeds_llm(gen_input, llm)
        else:
          fact_seeds = []
        task.stage_results["fact_seeds"] = [
          s.model_dump(mode="json") for s in fact_seeds
        ]

      elif stage == GenerationStage.CONFIGURE_AVATAR:
        avatar_kind = AvatarKind.LIVE2D
        avatar_id = gen_input.live2d_model_id or ""
        task.stage_results["avatar_kind"] = avatar_kind.value
        task.stage_results["avatar_id"] = avatar_id

      elif stage == GenerationStage.CONFIGURE_VOICE:
        from companion.generator.voice_mapping import map_reference_audio_to_voice

        voice = map_reference_audio_to_voice(list(gen_input.reference_audio))
        task.stage_results["voice"] = voice.model_dump(mode="json")

      elif stage == GenerationStage.INIT_MEMORY:
        if not memory_seeds:
          memory_seeds = _default_memory_seeds(gen_input)
          task.stage_results["memory_seeds"] = [
            s.model_dump(mode="json") for s in memory_seeds
          ]

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
        package_dir = out_root / f"{gen_input.companion_name}_{task.id[:8]}"
        package_dir.mkdir(parents=True, exist_ok=True)
        resource_paths = {
          "reference_images": ",".join(gen_input.reference_images),
          "reference_video": ",".join(gen_input.reference_video),
        }
        if gen_input.live2d_package_path:
          live2d_hint = _bundle_live2d_package(
            gen_input.live2d_package_path, package_dir
          )
          if live2d_hint:
            resource_paths["live2d"] = live2d_hint
        manifest = CompanionManifest(
          profile=profile,
          memory_seeds=memory_seeds,
          fact_seeds=fact_seeds,
          resource_paths=resource_paths,
          generator_metadata={"analysis": analysis, "llm": llm_meta},
        )
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
        timings = task.stage_results.setdefault("stage_timings_ms", {})
        timings[stage.value] = int((time.perf_counter() - stage_t0) * 1000)
        task.stages_completed.append(stage)
        task.status = TaskStatus.COMPLETED
        task.current_stage = None
        store.update(task)
        return artifact

      # Persist the checkpoint the moment the stage completes: a later crash
      # must find stages_completed/stage_results consistent for the retry.
      timings = task.stage_results.setdefault("stage_timings_ms", {})
      timings[stage.value] = int((time.perf_counter() - stage_t0) * 1000)
      task.stages_completed.append(stage)
      store.update(task)

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


# ── Phase 4: retry + background execution ──────────────────────────────────


_background_lock = threading.Lock()
_background_task_ids: set[str] = set()


def is_generation_running(task_id: str) -> bool:
  """True while a background thread is executing this task's pipeline."""
  with _background_lock:
    return task_id in _background_task_ids


def _spawn_pipeline_thread(task: GenerationTask) -> threading.Thread:
  def _run() -> None:
    try:
      run_pipeline_sync(task)
    except Exception:
      # run_pipeline_sync already persisted FAILED + error on the task.
      pass
    finally:
      with _background_lock:
        _background_task_ids.discard(task.id)

  with _background_lock:
    _background_task_ids.add(task.id)
  thread = threading.Thread(
    target=_run, name=f"companion-gen-{task.id[:8]}", daemon=True
  )
  thread.start()
  return thread


def start_generation_background(gen_input: GenerationInput) -> GenerationTask:
  """Create a task and run the pipeline on a daemon thread.

  Returns immediately with the task in ``pending``/``running`` state;
  callers poll ``GET /generate/{task_id}`` until completed/failed.
  """
  task = get_task_store().create(gen_input)
  _spawn_pipeline_thread(task)
  return task


def retry_generation(task: GenerationTask, *, background: bool = False) -> GenerationTask:
  """Re-run a failed task, resuming from its persisted stage checkpoints.

  The caller (API layer) is responsible for only passing FAILED tasks.
  """
  task.attempts += 1
  task.error = None
  task.status = TaskStatus.PENDING
  get_task_store().update(task)
  if background:
    _spawn_pipeline_thread(task)
    return task
  try:
    run_pipeline_sync(task)
  except Exception:
    pass
  return task
