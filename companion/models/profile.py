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

"""Companion profile — runtime configuration for a virtual companion."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AvatarKind(str, Enum):
    LIVE2D = "live2d"
    VRM = "vrm"
    MMD = "mmd"
    PNGTUBER = "pngtuber"
    DESKTOP_PET = "desktop_pet"


class VoiceConfig(BaseModel):
  provider: str = ""
  voice_id: str = ""
  reference_audio_paths: list[str] = Field(default_factory=list)
  extra: dict[str, Any] = Field(default_factory=dict)


class CompanionProfile(BaseModel):
  """Complete runtime configuration for one virtual companion."""

  id: str
  name: str
  display_name: str = ""
  locale: str = "zh-CN"
  system_prompt: str = ""
  avatar_kind: AvatarKind = AvatarKind.LIVE2D
  avatar_resource_id: str = ""
  avatar_extra: dict[str, Any] = Field(default_factory=dict)
  voice: VoiceConfig = Field(default_factory=VoiceConfig)
  memory_character_name: str = ""
  tags: list[str] = Field(default_factory=list)
  metadata: dict[str, Any] = Field(default_factory=dict)

  def resolved_memory_name(self) -> str:
    return self.memory_character_name or self.name
