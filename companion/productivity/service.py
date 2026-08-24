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

from pathlib import Path

from companion.productivity.media_monitor import MediaMonitor
from companion.productivity.memo import MemoService
from companion.productivity.pomodoro import PomodoroService
from companion.productivity.storage import ProductivityStorage
from companion.productivity.todo import TodoService
from companion.productivity.widget_hook import pomodoro_widget_event


class ProductivityService:
  def __init__(self, db_path: str | Path | None = None) -> None:
    self.storage = ProductivityStorage(db_path)
    self.pomodoro = PomodoroService()
    self.todo = TodoService(self.storage)
    self.memo = MemoService(self.storage)
    self.media = MediaMonitor()

  def close(self) -> None:
    self.storage.close()

  def on_pomodoro_event(self, event: str) -> dict:
    phase = self.pomodoro.snapshot().get("phase", "idle")
    widget = pomodoro_widget_event(event, phase)
    return {"event": event, "hook": "companion.persona.react", "widget": widget}
