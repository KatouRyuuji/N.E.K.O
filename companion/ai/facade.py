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

"""Unified Companion AI entry point."""

from __future__ import annotations

from companion.ai.bootstrap import bootstrap_from_artifact
from companion.ai.chat import CompanionChatBridge
from companion.ai.memory_bridge import CompanionMemoryBridge
from companion.ai.open_source import resolve_open_source_provider, to_api_config
from companion.ai.persona import CompanionPersonaBridge
from companion.ai.realtime_voice import CompanionRealtimeVoiceBridge
from companion.ai.tts_bridge import CompanionTTSBridge
from companion.models.generation import GenerationArtifact
from companion.models.profile import CompanionProfile


class CompanionAI:
  """Thin facade over N.E.K.O. brain, memory, and TTS subsystems."""

  def __init__(self, profile: CompanionProfile) -> None:
    self.profile = profile
    self.memory = CompanionMemoryBridge(profile)
    self.persona = CompanionPersonaBridge(profile)
    self.chat = CompanionChatBridge(profile)
    self.realtime = CompanionRealtimeVoiceBridge(profile)
    self.tts = CompanionTTSBridge(profile)

  def bootstrap_from_generation(self, artifact: GenerationArtifact) -> dict:
    return bootstrap_from_artifact(self.profile, artifact)

  def open_source_config(self) -> dict | None:
    provider = resolve_open_source_provider()
    if provider is None:
      return None
    return to_api_config(provider)
