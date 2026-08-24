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

"""`.neko-companion` package manifest specification."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from companion.models.profile import CompanionProfile


class ManifestVersion(str, Enum):
  V1 = "1.0"


class MemorySeed(BaseModel):
  entity: str
  content: str
  importance: str = "normal"


class CompanionManifest(BaseModel):
  """Portable companion package manifest (manifest.json)."""

  version: ManifestVersion = ManifestVersion.V1
  profile: CompanionProfile
  memory_seeds: list[MemorySeed] = Field(default_factory=list)
  resource_paths: dict[str, str] = Field(default_factory=dict)
  generator_metadata: dict[str, Any] = Field(default_factory=dict)

  def to_package_dict(self) -> dict[str, Any]:
    return self.model_dump(mode="json")
