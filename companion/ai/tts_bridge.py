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

"""TTS bridge over utils.tts."""

from __future__ import annotations

from companion.models.profile import CompanionProfile


class CompanionTTSBridge:
  def __init__(self, profile: CompanionProfile) -> None:
    self.profile = profile

  def voice_config(self) -> dict:
    voice = self.profile.voice
    return {
      "provider": voice.provider,
      "voice_id": voice.voice_id,
      "reference_audio_paths": list(voice.reference_audio_paths),
    }

  def preview_payload(self, text: str = "你好，我是你的专属虚拟伴侣。") -> dict:
    """Return TTS preview request payload (execution deferred to runtime TTS worker)."""
    cfg = self.voice_config()
    return {
      "text": text,
      "provider": cfg["provider"] or "default",
      "voice_id": cfg["voice_id"],
      "reference_audio_paths": cfg["reference_audio_paths"],
      "status": "ready" if cfg["reference_audio_paths"] or cfg["voice_id"] else "unconfigured",
    }
