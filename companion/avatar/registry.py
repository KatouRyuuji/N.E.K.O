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

"""Hot-swappable avatar registry."""

from __future__ import annotations

from companion.avatar.profile import AvatarProfile
from companion.models.profile import AvatarKind


class AvatarRegistry:
  def __init__(self) -> None:
    self._active_id: str | None = None
    self._profiles: dict[str, AvatarProfile] = {}

  def register(self, profile: AvatarProfile) -> None:
    self._profiles[profile.id] = profile
    if self._active_id is None:
      self._active_id = profile.id

  def list_profiles(self) -> list[AvatarProfile]:
    return list(self._profiles.values())

  def set_active(self, profile_id: str) -> AvatarProfile | None:
    if profile_id not in self._profiles:
      return None
    self._active_id = profile_id
    return self._profiles[profile_id]

  def active(self) -> AvatarProfile | None:
    if self._active_id is None:
      return None
    return self._profiles.get(self._active_id)

  def from_companion_profile(
    self, companion_id: str, kind: AvatarKind, resource_id: str
  ) -> AvatarProfile:
    profile = AvatarProfile(
      id=companion_id,
      kind=kind,
      resource_id=resource_id,
    )
    self.register(profile)
    return profile
