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

"""Todo list backed by SQLite persistence (Phase 2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from companion.productivity.storage import ProductivityStorage


@dataclass
class TodoItem:
  id: str
  title: str
  done: bool = False
  created_at: str = ""
  updated_at: str = ""
  metadata: dict[str, Any] = field(default_factory=dict)


def _to_item(row: dict[str, Any]) -> TodoItem:
  return TodoItem(
    id=row["id"],
    title=row["title"],
    done=row["done"],
    created_at=row.get("created_at", ""),
    updated_at=row.get("updated_at", ""),
  )


class TodoService:
  def __init__(self, storage: ProductivityStorage | None = None) -> None:
    self._storage = storage if storage is not None else ProductivityStorage(":memory:")

  def create(self, title: str) -> TodoItem:
    return _to_item(self._storage.create_todo(title))

  def list_items(self) -> list[TodoItem]:
    return [_to_item(row) for row in self._storage.list_todos()]

  def get(self, item_id: str) -> TodoItem | None:
    row = self._storage.get_todo(item_id)
    return _to_item(row) if row else None

  def toggle(self, item_id: str, done: bool) -> TodoItem | None:
    row = self._storage.set_todo_done(item_id, done)
    return _to_item(row) if row else None

  def rename(self, item_id: str, title: str) -> TodoItem | None:
    row = self._storage.update_todo_title(item_id, title)
    return _to_item(row) if row else None

  def delete(self, item_id: str) -> bool:
    return self._storage.delete_todo(item_id)
