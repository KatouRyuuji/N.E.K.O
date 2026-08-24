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

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from companion.generator.pipeline import start_generation
from companion.generator.tasks import TaskStatus, get_task_store
from companion.models.generation import GenerationInput
from companion.productivity.service import ProductivityService
from companion.avatar.loader import AvatarPackageError, load_avatar_from_package
from companion.avatar.profile import AvatarProfile
from companion.avatar.registry import AvatarRegistry

router = APIRouter(prefix="/api/companion", tags=["companion"])
_productivity: ProductivityService | None = None
_avatar_registry = AvatarRegistry()


def _avatar_public_dict(profile: AvatarProfile) -> dict:
  """Serialize an avatar profile for the swap panel / Live2D bridge."""
  live2d = profile.effects.get("live2d") or {}
  entry_url = None
  if live2d.get("relative_entry"):
    entry_url = (
      f"/api/companion/avatar/{profile.id}/resource/{live2d['relative_entry']}"
    )
  return {
    "id": profile.id,
    "kind": profile.kind.value,
    "resource_id": profile.resource_id,
    "display_name": profile.display_name,
    "slug": live2d.get("slug") or profile.resource_id,
    "entry_url": entry_url,
  }


@router.get("/ai/open-source")
async def companion_open_source_status():
  from companion.ai.open_source import probe_ollama, resolve_open_source_provider

  provider = resolve_open_source_provider()
  if provider is None:
    return {"available": False, "providers": {"ollama": probe_ollama().model_dump()}}
  return {
    "available": True,
    "active": provider.name,
    "config": {
      "model": provider.model,
      "base_url": provider.base_url,
    },
  }


def get_productivity() -> ProductivityService:
  """Lazily build the shared productivity service.

  Deferred so importing this module never touches the user data directory;
  the SQLite database is only opened when a productivity endpoint is hit.
  """
  global _productivity
  if _productivity is None:
    _productivity = ProductivityService()
  return _productivity


class TodoCreate(BaseModel):
  title: str = Field(min_length=1, max_length=500)


class TodoPatch(BaseModel):
  done: bool | None = None
  title: str | None = Field(default=None, min_length=1, max_length=500)


class MemoCreate(BaseModel):
  content: str = Field(min_length=1, max_length=5000)


def _todo_dict(item) -> dict:
  return {
    "id": item.id,
    "title": item.title,
    "done": item.done,
    "created_at": item.created_at,
    "updated_at": item.updated_at,
  }


def _memo_dict(memo) -> dict:
  return {"id": memo.id, "content": memo.content, "created_at": memo.created_at}


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
  task = start_generation(body)
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
  prod = get_productivity()
  media = prod.media.snapshot()
  return {
    "pomodoro": prod.pomodoro.snapshot(),
    "todos": [_todo_dict(t) for t in prod.todo.list_items()],
    "memos": [_memo_dict(m) for m in prod.memo.list_memos()],
    "media": {"playing": media.playing, "title": media.title},
  }


@router.get("/productivity/music")
async def productivity_music_state():
  """Read-only snapshot of the music router runtime state."""
  return get_productivity().media.music_state()


@router.post("/productivity/pomodoro/start")
async def pomodoro_start(phase: str = "work"):
  prod = get_productivity()
  if phase == "break":
    prod.pomodoro.start_break()
  else:
    prod.pomodoro.start_work()
  event = prod.on_pomodoro_event(f"pomodoro.{phase}.start")
  event["pomodoro"] = prod.pomodoro.snapshot()
  return event


@router.post("/productivity/pomodoro/stop")
async def pomodoro_stop():
  prod = get_productivity()
  prod.pomodoro.stop()
  event = prod.on_pomodoro_event("pomodoro.stop")
  event["pomodoro"] = prod.pomodoro.snapshot()
  return event


@router.post("/productivity/todos", status_code=201)
async def create_todo(body: TodoCreate):
  return _todo_dict(get_productivity().todo.create(body.title.strip()))


@router.get("/productivity/todos")
async def list_todos():
  return {"todos": [_todo_dict(t) for t in get_productivity().todo.list_items()]}


@router.patch("/productivity/todos/{todo_id}")
async def patch_todo(todo_id: str, body: TodoPatch):
  prod = get_productivity()
  item = None
  if body.title is not None:
    item = prod.todo.rename(todo_id, body.title.strip())
    if item is None:
      raise HTTPException(status_code=404, detail="todo not found")
  if body.done is not None:
    item = prod.todo.toggle(todo_id, body.done)
  if item is None:
    item = prod.todo.get(todo_id)
  if item is None:
    raise HTTPException(status_code=404, detail="todo not found")
  return _todo_dict(item)


@router.delete("/productivity/todos/{todo_id}")
async def delete_todo(todo_id: str):
  if not get_productivity().todo.delete(todo_id):
    raise HTTPException(status_code=404, detail="todo not found")
  return {"deleted": todo_id}


@router.post("/productivity/memos", status_code=201)
async def create_memo(body: MemoCreate):
  return _memo_dict(get_productivity().memo.create(body.content.strip()))


@router.get("/productivity/memos")
async def list_memos():
  return {"memos": [_memo_dict(m) for m in get_productivity().memo.list_memos()]}


@router.delete("/productivity/memos/{memo_id}")
async def delete_memo(memo_id: str):
  if not get_productivity().memo.delete(memo_id):
    raise HTTPException(status_code=404, detail="memo not found")
  return {"deleted": memo_id}


@router.get("/avatar/list")
async def list_avatars():
  profiles = _avatar_registry.list_profiles()
  active = _avatar_registry.active()
  return {
    "active_id": active.id if active else None,
    "profiles": [_avatar_public_dict(p) for p in profiles],
  }


@router.get("/avatar/active")
async def get_active_avatar():
  active = _avatar_registry.active()
  if active is None:
    return {"active": None}
  return {"active": _avatar_public_dict(active)}


@router.post("/avatar/active")
async def set_active_avatar(profile_id: str):
  profile = _avatar_registry.set_active(profile_id)
  if profile is None:
    raise HTTPException(status_code=404, detail="avatar profile not found")
  return _avatar_public_dict(profile)


class LoadPackageRequest(BaseModel):
  package_path: str
  activate: bool = True


@router.post("/avatar/load-package")
async def load_avatar_package(body: LoadPackageRequest):
  """Load a `.neko-companion` package directory and register its Live2D avatar."""
  try:
    profile = load_avatar_from_package(
      body.package_path, _avatar_registry, activate=body.activate
    )
  except AvatarPackageError as exc:
    raise HTTPException(status_code=422, detail=str(exc))
  return JSONResponse(status_code=201, content=_avatar_public_dict(profile))


@router.get("/avatar/{profile_id}/resource/{resource_path:path}")
async def get_avatar_resource(profile_id: str, resource_path: str):
  """Serve Live2D model files (entry JSON, textures, motions) from a package.

  pixi-live2d-display resolves textures relative to the entry URL, so the
  whole package subtree must be reachable through this endpoint.
  """
  profile = next(
    (p for p in _avatar_registry.list_profiles() if p.id == profile_id), None
  )
  if profile is None:
    raise HTTPException(status_code=404, detail="avatar profile not found")
  live2d = profile.effects.get("live2d") or {}
  package_dir = live2d.get("package_dir")
  if not package_dir:
    raise HTTPException(status_code=404, detail="avatar has no package resources")
  root = Path(package_dir).resolve()
  target = (root / resource_path).resolve()
  if not target.is_relative_to(root):
    raise HTTPException(status_code=403, detail="path escapes package directory")
  if not target.is_file():
    raise HTTPException(status_code=404, detail="resource not found")
  return FileResponse(target)
