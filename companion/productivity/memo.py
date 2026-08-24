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

"""Memo / notes service."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Memo:
  id: str
  content: str
  created_at: str = field(
    default_factory=lambda: datetime.now(timezone.utc).isoformat()
  )


class MemoService:
  def __init__(self) -> None:
    self._memos: dict[str, Memo] = {}

  def create(self, content: str) -> Memo:
    memo = Memo(id=str(uuid.uuid4()), content=content)
    self._memos[memo.id] = memo
    return memo

  def list_memos(self) -> list[Memo]:
    return sorted(self._memos.values(), key=lambda m: m.created_at, reverse=True)

  def delete(self, memo_id: str) -> bool:
    return self._memos.pop(memo_id, None) is not None
