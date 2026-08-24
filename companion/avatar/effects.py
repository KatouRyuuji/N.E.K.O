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

"""Visual effects and decoration schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EffectConfig:
  particles: bool = False
  border: str = ""
  background: str = ""
  expression_rules: list[dict[str, Any]] = field(default_factory=list)

  def to_dict(self) -> dict[str, Any]:
    return {
      "particles": self.particles,
      "border": self.border,
      "background": self.background,
      "expression_rules": list(self.expression_rules),
    }
