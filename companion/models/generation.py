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

"""Generation input/output models for the companion generator pipeline."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from companion.models.profile import CompanionProfile


class GenerationStage(str, Enum):
  INGEST = "ingest"
  ANALYZE_CORPUS = "analyze_corpus"
  EXTRACT_PERSONA = "extract_persona"
  CONFIGURE_AVATAR = "configure_avatar"
  CONFIGURE_VOICE = "configure_voice"
  INIT_MEMORY = "init_memory"
  PACKAGE = "package"


class GenerationInput(BaseModel):
  companion_name: str
  locale: str = "zh-CN"
  corpus_text: str | None = None
  corpus_files: list[str] = Field(default_factory=list)
  system_prompt: str | None = None
  live2d_model_id: str | None = None
  live2d_package_path: str | None = None
  reference_images: list[str] = Field(default_factory=list)
  reference_audio: list[str] = Field(default_factory=list)
  reference_video: list[str] = Field(default_factory=list)
  extra: dict[str, Any] = Field(default_factory=dict)


class GenerationArtifact(BaseModel):
  task_id: str
  profile: CompanionProfile
  package_path: str = ""
  manifest_path: str = ""
  stages_completed: list[GenerationStage] = Field(default_factory=list)
  analysis_summary: dict[str, Any] = Field(default_factory=dict)
