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

"""Memory bridge to N.E.K.O. memory service."""

from __future__ import annotations

from companion.models.profile import CompanionProfile


class CompanionMemoryBridge:
  def __init__(self, profile: CompanionProfile) -> None:
    self.profile = profile

  @property
  def character_name(self) -> str:
    return self.profile.resolved_memory_name()

  def new_dialog_path(self) -> str:
    return f"/new_dialog/{self.character_name}"
