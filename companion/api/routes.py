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

"""Companion Platform API routes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from companion.generator.pipeline import start_generation
from companion.generator.tasks import TaskStatus, get_task_store
from companion.models.generation import GenerationInput
from companion.productivity.service import ProductivityService
from companion.avatar.registry import AvatarRegistry

router = APIRouter(prefix="/api/companion", tags=["companion"])
_productivity = ProductivityService()
_avatar_registry = AvatarRegistry()


@router.get("/health")
async def companion_health():
  return {"status": "ok", "module": "companion-platform", "version": "0.1.0"}


@router.get("/platform")
async def companion_platform_info():
  return {
    "name": "N.E.K.O. Companion Platform",
    "version": "0.1.0",
    "features": [
      "long_term_memory",
      "persona",
      "tts",
      "realtime_voice",
      "text_chat",
      "productivity",
      "effects",
      "live2d",
      "avatar_swap",
      "companion_generator",
    ],
  }


@router.post("/generate")
async def create_generation_task(body: GenerationInput):
  # LLM + disk IO inside the sync pipeline: offload so the shared event loop
  # (main/memory/agent subsystems) is never blocked by a generation task.
  task = await asyncio.to_thread(start_generation, body)
  return JSONResponse(
    status_code=201,
    content=task.to_public_dict(),
  )


@router.get("/generate")
async def list_generation_tasks(limit: int = 50):
  store = get_task_store()
  tasks = store.list_tasks(limit=limit)
  return {"tasks": [t.to_public_dict() for t in tasks]}


@router.get("/generate/{task_id}")
async def get_generation_task(task_id: str):
  store = get_task_store()
  task = store.get(task_id)
  if task is None:
    raise HTTPException(status_code=404, detail="task not found")
  payload = task.to_public_dict()
  if task.artifact is not None:
    payload["artifact"] = task.artifact.model_dump(mode="json")
  return payload


@router.get("/generate/{task_id}/manifest")
async def download_manifest(task_id: str):
  store = get_task_store()
  task = store.get(task_id)
  if task is None:
    raise HTTPException(status_code=404, detail="task not found")
  if task.status != TaskStatus.COMPLETED or task.artifact is None:
    raise HTTPException(status_code=409, detail="task not completed")
  manifest_path = Path(task.artifact.manifest_path)
  if not manifest_path.is_file():
    raise HTTPException(status_code=404, detail="manifest not found")
  return json.loads(manifest_path.read_text(encoding="utf-8"))


@router.get("/productivity/status")
async def productivity_status():
  return {
    "pomodoro": _productivity.pomodoro.snapshot(),
    "todos": [
      {"id": t.id, "title": t.title, "done": t.done}
      for t in _productivity.todo.list_items()
    ],
    "memos": [
      {"id": m.id, "content": m.content, "created_at": m.created_at}
      for m in _productivity.memo.list_memos()
    ],
    "media": {
      "playing": _productivity.media.snapshot().playing,
      "title": _productivity.media.snapshot().title,
    },
  }


@router.post("/productivity/pomodoro/start")
async def pomodoro_start(phase: str = "work"):
  if phase == "break":
    _productivity.pomodoro.start_break()
  else:
    _productivity.pomodoro.start_work()
  return _productivity.on_pomodoro_event(f"pomodoro.{phase}.start")


@router.post("/productivity/pomodoro/stop")
async def pomodoro_stop():
  _productivity.pomodoro.stop()
  return _productivity.on_pomodoro_event("pomodoro.stop")


@router.post("/productivity/todos")
async def create_todo(title: str):
  item = _productivity.todo.create(title)
  return {"id": item.id, "title": item.title, "done": item.done}


@router.post("/productivity/memos")
async def create_memo(content: str):
  memo = _productivity.memo.create(content)
  return {"id": memo.id, "content": memo.content, "created_at": memo.created_at}


@router.get("/avatar/list")
async def list_avatars():
  profiles = _avatar_registry.list_profiles()
  active = _avatar_registry.active()
  return {
    "active_id": active.id if active else None,
    "profiles": [
      {
        "id": p.id,
        "kind": p.kind.value,
        "resource_id": p.resource_id,
        "display_name": p.display_name,
      }
      for p in profiles
    ],
  }


@router.post("/avatar/active")
async def set_active_avatar(profile_id: str):
  profile = _avatar_registry.set_active(profile_id)
  if profile is None:
    raise HTTPException(status_code=404, detail="avatar profile not found")
  return {
    "id": profile.id,
    "kind": profile.kind.value,
    "resource_id": profile.resource_id,
  }
