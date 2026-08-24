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

"""Memo / notes service backed by SQLite persistence (Phase 2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from companion.productivity.storage import ProductivityStorage


@dataclass
class Memo:
  id: str
  content: str
  created_at: str = ""


def _to_memo(row: dict[str, Any]) -> Memo:
  return Memo(id=row["id"], content=row["content"], created_at=row["created_at"])


class MemoService:
  def __init__(self, storage: ProductivityStorage | None = None) -> None:
    self._storage = storage if storage is not None else ProductivityStorage(":memory:")

  def create(self, content: str) -> Memo:
    return _to_memo(self._storage.create_memo(content))

  def list_memos(self) -> list[Memo]:
    return [_to_memo(row) for row in self._storage.list_memos()]

  def delete(self, memo_id: str) -> bool:
    return self._storage.delete_memo(memo_id)
