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

"""Bootstrap companion runtime from a generation artifact."""

from __future__ import annotations

import json
from pathlib import Path

from companion.models.generation import GenerationArtifact
from companion.models.manifest import CompanionManifest
from companion.models.profile import CompanionProfile


def bootstrap_from_artifact(
  profile: CompanionProfile, artifact: GenerationArtifact
) -> dict:
  manifest_path = Path(artifact.manifest_path)
  seeds: list[dict] = []
  if manifest_path.is_file():
    manifest = CompanionManifest.model_validate(
      json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    seeds = [s.model_dump() for s in manifest.memory_seeds]
  return {
    "character_name": profile.resolved_memory_name(),
    "persona": profile.system_prompt,
    "memory_seeds": seeds,
    "package_path": artifact.package_path,
  }
