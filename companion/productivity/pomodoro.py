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

"""Pomodoro timer service."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class PomodoroPhase(str, Enum):
  IDLE = "idle"
  WORK = "work"
  BREAK = "break"


@dataclass
class PomodoroState:
  phase: PomodoroPhase = PomodoroPhase.IDLE
  work_minutes: int = 25
  break_minutes: int = 5
  started_at: str | None = None
  completed_cycles: int = 0


class PomodoroService:
  def __init__(self) -> None:
    self._state = PomodoroState()

  def start_work(self) -> PomodoroState:
    self._state.phase = PomodoroPhase.WORK
    self._state.started_at = datetime.now(timezone.utc).isoformat()
    return self._state

  def start_break(self) -> PomodoroState:
    self._state.phase = PomodoroPhase.BREAK
    self._state.started_at = datetime.now(timezone.utc).isoformat()
    return self._state

  def stop(self) -> PomodoroState:
    if self._state.phase == PomodoroPhase.WORK:
      self._state.completed_cycles += 1
    self._state.phase = PomodoroPhase.IDLE
    self._state.started_at = None
    return self._state

  def snapshot(self) -> dict:
    return {
      "phase": self._state.phase.value,
      "work_minutes": self._state.work_minutes,
      "break_minutes": self._state.break_minutes,
      "started_at": self._state.started_at,
      "completed_cycles": self._state.completed_cycles,
    }
