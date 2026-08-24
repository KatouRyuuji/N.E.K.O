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

"""Avatar registry (SQLite-persisted), package loader, Live2D bridge, effects."""

from companion.avatar.loader import (
  AvatarPackageError,
  Live2DModelRef,
  load_avatar_from_package,
  resolve_live2d_model,
  slugify_model_name,
)
from companion.avatar.registry import AvatarRegistry
from companion.avatar.store import (
  AvatarRegistryStore,
  PackagePathError,
  PersistentAvatarRegistry,
  get_avatar_registry,
  remove_package_dir,
  reset_avatar_registry,
)

__all__ = [
  "AvatarRegistry",
  "AvatarRegistryStore",
  "AvatarPackageError",
  "Live2DModelRef",
  "PackagePathError",
  "PersistentAvatarRegistry",
  "get_avatar_registry",
  "load_avatar_from_package",
  "remove_package_dir",
  "reset_avatar_registry",
  "resolve_live2d_model",
  "slugify_model_name",
]
