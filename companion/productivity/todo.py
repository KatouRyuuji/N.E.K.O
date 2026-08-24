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

"""Todo list with in-memory store (Phase 1)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TodoItem:
  id: str
  title: str
  done: bool = False
  metadata: dict[str, Any] = field(default_factory=dict)


class TodoService:
  def __init__(self) -> None:
    self._items: dict[str, TodoItem] = {}

  def create(self, title: str) -> TodoItem:
    item = TodoItem(id=str(uuid.uuid4()), title=title)
    self._items[item.id] = item
    return item

  def list_items(self) -> list[TodoItem]:
    return list(self._items.values())

  def toggle(self, item_id: str, done: bool) -> TodoItem | None:
    item = self._items.get(item_id)
    if item is None:
      return None
    item.done = done
    return item

  def delete(self, item_id: str) -> bool:
    return self._items.pop(item_id, None) is not None
