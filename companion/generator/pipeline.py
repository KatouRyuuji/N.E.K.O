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

"""Companion generator pipeline — multi-stage long-running analysis."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from companion.generator.tasks import GenerationTask, TaskStatus, get_task_store
from companion.models.generation import GenerationArtifact, GenerationInput, GenerationStage
from companion.models.manifest import CompanionManifest, MemorySeed
from companion.models.profile import AvatarKind, CompanionProfile, VoiceConfig
from utils.logger_config import get_module_logger

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


def _default_output_root() -> Path:
  from utils.config_manager import get_config_manager

  root = Path(get_config_manager().docs_dir) / "N.E.K.O" / "companions" / "generated"
  root.mkdir(parents=True, exist_ok=True)
  return root


def _analyze_corpus_mock(gen_input: GenerationInput) -> dict[str, Any]:
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
  }


def _extract_persona_mock(
  gen_input: GenerationInput, analysis: dict[str, Any]
) -> tuple[str, list[MemorySeed]]:
  base_prompt = gen_input.system_prompt or ""
  traits = analysis.get("detected_traits", [])
  trait_hint = "、".join(traits) if traits else "友善"
  if not base_prompt:
    base_prompt = (
      f"你是{gen_input.companion_name}，性格{trait_hint}。"
      "你会记住与主人的互动，用自然口语陪伴对方。"
    )
  seeds = [
    MemorySeed(
      entity="neko",
      content=f"{gen_input.companion_name} 是由用户定制的专属虚拟伴侣。",
    ),
    MemorySeed(
      entity="relationship",
      content="主人正在与我建立长期的陪伴关系。",
    ),
  ]
  return base_prompt, seeds


def run_pipeline_sync(task: GenerationTask, output_root: Path | None = None) -> GenerationArtifact:
  """Run all pipeline stages synchronously (Phase 1)."""
  store = get_task_store()
  gen_input = task.input
  out_root = output_root or _default_output_root()
  analysis: dict[str, Any] = {}

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
        analysis = _analyze_corpus_mock(gen_input)

      elif stage == GenerationStage.EXTRACT_PERSONA:
        system_prompt, _seeds = _extract_persona_mock(gen_input, analysis)

      elif stage == GenerationStage.CONFIGURE_AVATAR:
        avatar_kind = AvatarKind.LIVE2D if (
          gen_input.live2d_model_id or gen_input.live2d_package_path
        ) else AvatarKind.LIVE2D
        avatar_id = gen_input.live2d_model_id or ""

      elif stage == GenerationStage.CONFIGURE_VOICE:
        voice = VoiceConfig(
          reference_audio_paths=list(gen_input.reference_audio),
        )

      elif stage == GenerationStage.INIT_MEMORY:
        _system_prompt, memory_seeds = _extract_persona_mock(gen_input, analysis)

      elif stage == GenerationStage.PACKAGE:
        profile_id = str(uuid.uuid4())
        system_prompt, memory_seeds = _extract_persona_mock(gen_input, analysis)
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
          generator_metadata={"analysis": analysis},
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
          analysis_summary=analysis,
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
