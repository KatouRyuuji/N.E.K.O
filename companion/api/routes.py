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
from pydantic import BaseModel

from companion.generator.pipeline import start_generation
from companion.generator.tasks import TaskStatus, get_task_store
from companion.models.generation import GenerationInput
from companion.productivity.service import ProductivityService
from companion.avatar.loader import AvatarPackageError, load_avatar_from_package
from companion.avatar.profile import AvatarProfile
from companion.avatar.registry import AvatarRegistry

router = APIRouter(prefix="/api/companion", tags=["companion"])
_productivity = ProductivityService()
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
