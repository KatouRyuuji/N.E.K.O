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

"""Map reference audio files to companion voice configuration."""

from __future__ import annotations

from pathlib import Path

from companion.models.profile import VoiceConfig


def map_reference_audio_to_voice(
  reference_audio_paths: list[str],
  *,
  provider: str = "",
  voice_id: str = "",
) -> VoiceConfig:
  """Derive a VoiceConfig from uploaded reference audio paths."""
  valid_paths = [p for p in reference_audio_paths if p and Path(p).is_file()]
  resolved_provider = provider
  resolved_voice_id = voice_id
  if valid_paths and not resolved_provider:
    resolved_provider = "reference_clone"
  if valid_paths and not resolved_voice_id:
    resolved_voice_id = Path(valid_paths[0]).stem
  return VoiceConfig(
    provider=resolved_provider,
    voice_id=resolved_voice_id,
    reference_audio_paths=valid_paths,
    extra={"mapping": "reference_audio"},
  )
