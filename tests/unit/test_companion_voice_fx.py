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

from pathlib import Path

from companion.generator.voice_mapping import map_reference_audio_to_voice
from companion.productivity.widget_hook import pomodoro_widget_event


def test_map_reference_audio_to_voice(tmp_path):
  audio = tmp_path / "ref.wav"
  audio.write_bytes(b"RIFF")
  voice = map_reference_audio_to_voice([str(audio)])
  assert voice.provider == "reference_clone"
  assert voice.voice_id == "ref"
  assert voice.reference_audio_paths == [str(audio)]


def test_pomodoro_widget_hook_suggests_enabled_on_work():
  payload = pomodoro_widget_event("pomodoro.work.start", "work")
  assert payload["suggest_enabled"] is True
  assert payload["widget_mode_api"] == "/api/widget-mode/enabled"


def test_tts_preview_payload():
  from companion.ai.tts_bridge import CompanionTTSBridge
  from companion.models.profile import CompanionProfile, VoiceConfig

  profile = CompanionProfile(
    id="p1",
    name="test",
    voice=VoiceConfig(provider="ref", voice_id="v1"),
  )
  payload = CompanionTTSBridge(profile).preview_payload()
  assert payload["status"] == "ready"
  assert payload["voice_id"] == "v1"
