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

"""Unified productivity facade."""

from __future__ import annotations

from companion.productivity.media_monitor import MediaMonitor
from companion.productivity.memo import MemoService
from companion.productivity.pomodoro import PomodoroService
from companion.productivity.todo import TodoService


class ProductivityService:
  def __init__(self) -> None:
    self.pomodoro = PomodoroService()
    self.todo = TodoService()
    self.memo = MemoService()
    self.media = MediaMonitor()

  def on_pomodoro_event(self, event: str) -> dict:
    return {"event": event, "hook": "companion.persona.react"}
