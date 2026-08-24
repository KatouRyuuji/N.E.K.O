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

"""Pomodoro ↔ widget-mode (always-on-top) integration hook."""

from __future__ import annotations


def pomodoro_widget_event(event: str, pomodoro_phase: str) -> dict:
  """Build a widget-mode hint payload for pomodoro lifecycle events.

  Consumers may call ``POST /api/widget-mode/enabled`` when ``suggest_enabled``
  is true. This module does not mutate widget state directly.
  """
  suggest_enabled = event in ("pomodoro.work.start", "pomodoro.break.start")
  return {
    "event": event,
    "pomodoro_phase": pomodoro_phase,
    "suggest_enabled": suggest_enabled,
    "widget_mode_api": "/api/widget-mode/enabled",
  }
