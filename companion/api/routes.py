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

"""Companion Platform API routes (``/api/companion``, no trailing slashes).

Route groups, all mounted through ``main_routers/companion_router``:

- generation: ``/generate`` (+ ``/upload``, ``/{task_id}``, ``/retry``,
  ``/manifest``, ``/import``) — SQLite-persisted tasks, stage-checkpoint
  retry, optional ``?background=true`` async mode (Phase 4 HA);
- dialogue: ``/session/{character_name}`` and ``/dialogue/session`` —
  text + realtime-voice facade metadata (Phase 4);
- package import: ``/import`` — character card + memory seeds + avatar;
- workshop: ``/workshop/catalog`` and ``/workshop/publish/{task_id}``;
- avatar hot swap and effects: ``/avatar/*`` — SQLite-persisted registry
  restored on first access, ``DELETE /avatar/{profile_id}`` with safe
  package-path deletion (Phase 5 M2);
- productivity: ``/productivity/*`` (pomodoro / todos / memos / media);
- open-source probe: ``/ai/open-source``; one-click Ollama tier config
  (Phase 5 M1): ``/ai/open-source/config``; TTS preview: ``/tts/preview``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from companion.generator.pipeline import (
  retry_generation,
  start_generation,
  start_generation_background,
)
from companion.generator.tasks import TaskStatus, get_task_store
from companion.generator.uploads import UploadError, save_generation_uploads
from companion.models.generation import GenerationInput
from companion.models.profile import CompanionProfile
from companion.ai.facade import CompanionAI
from companion.productivity.service import ProductivityService
from companion.avatar.loader import AvatarPackageError, load_avatar_from_package
from companion.avatar.profile import AvatarProfile
from companion.avatar.registry import AvatarRegistry

router = APIRouter(prefix="/api/companion", tags=["companion"])
_productivity: ProductivityService | None = None
# Test override hook: when set (monkeypatch) it wins over the persisted
# singleton — see _get_avatar_registry().
_avatar_registry: AvatarRegistry | None = None


def _get_avatar_registry() -> AvatarRegistry:
  """Lazily resolve the avatar registry backing the ``/avatar/*`` routes.

  Production path: the SQLite-persisted singleton from
  :mod:`companion.avatar.store`, so avatars imported before a restart are
  restored on first API access (registry, active selection, effects).
  Deferred import keeps this module importable without touching the user
  data directory; tests may monkeypatch ``_avatar_registry`` with a plain
  in-memory :class:`AvatarRegistry` instead.
  """
  if _avatar_registry is not None:
    return _avatar_registry
  from companion.avatar.store import get_avatar_registry

  return get_avatar_registry()


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
    "decorations": profile.effects.get("decorations"),
  }


@router.get("/ai/open-source")
async def companion_open_source_status():
  """Report local open-source AI (Ollama) availability and routing config.

  The probe is sync httpx with a short timeout, so it runs in a worker
  thread to keep the event loop free. When no provider is reachable the raw
  probe result (an ``OpenSourceProvider`` dataclass, serialized with
  ``dataclasses.asdict``) is returned under ``providers`` for diagnostics.
  """
  from dataclasses import asdict

  from companion.ai.open_source import probe_ollama

  # Sync httpx probe: offload so the shared event loop is never blocked.
  ollama = await asyncio.to_thread(probe_ollama)
  if not ollama.available:
    return {"available": False, "providers": {"ollama": asdict(ollama)}}
  return {
    "available": True,
    "active": ollama.name,
    "config": {
      "model": ollama.model,
      "base_url": ollama.base_url,
    },
    "models": (ollama.metadata or {}).get("models", []),
  }


class OpenSourceConfigRequest(BaseModel):
  model: str = Field(min_length=1, max_length=200)
  base_url: str = ""
  tiers: list[str] = Field(default_factory=lambda: ["summary"])


@router.post("/ai/open-source/config")
async def configure_open_source_provider(body: OpenSourceConfigRequest):
  """Persist a selected local Ollama model to provider tiers (Phase 5 M1).

  Re-probes the daemon before writing so a stale wizard page can never
  persist an unreachable route: unreachable daemon → ``502``, model no
  longer installed → ``409``, unsupported tier → ``422``. On success the
  tier patch is merged into core_config.json through the config manager
  (offloaded — sync file IO must stay off the shared event loop).
  """
  from companion.ai.open_source import (
    OLLAMA_CONFIG_TIER_PREFIXES,
    apply_ollama_tier_config,
    ollama_base_url,
  )
  from companion.generator.open_source import detect_ollama

  tiers = [t.strip() for t in body.tiers if t and t.strip()]
  if not tiers:
    raise HTTPException(status_code=422, detail="at least one tier is required")
  unknown = [t for t in tiers if t not in OLLAMA_CONFIG_TIER_PREFIXES]
  if unknown:
    raise HTTPException(
      status_code=422, detail=f"unsupported tiers: {', '.join(unknown)}"
    )

  base = (body.base_url or ollama_base_url()).rstrip("/")
  status = await asyncio.to_thread(detect_ollama, base)
  if not status.available:
    raise HTTPException(
      status_code=502,
      detail=f"Ollama daemon unreachable at {base}: {status.error or 'probe failed'}",
    )
  model = body.model.strip()
  if status.models and model not in status.models:
    raise HTTPException(
      status_code=409,
      detail=f"model '{model}' is not installed (run: ollama pull {model})",
    )

  from utils.config_manager import get_config_manager

  patch = await asyncio.to_thread(
    apply_ollama_tier_config, model, status.base_url, tiers, get_config_manager()
  )
  return {
    "saved": True,
    "provider": "ollama",
    "tiers": tiers,
    "config": {
      "model": model,
      "base_url": patch[f"{OLLAMA_CONFIG_TIER_PREFIXES[tiers[0]]}ModelUrl"],
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


@router.get("/session/{character_name}")
async def companion_session_metadata(character_name: str):
  """Dialogue session metadata for one character (text chat + realtime voice).

  Aggregates the two Phase 4 facades: websocket routing (``/ws/{name}``),
  each channel's provider tier (sanitized — the api_key never leaves the
  server), and the ready-to-send protocol frames. When the main server
  runtime is booted the live session state is included and an unknown
  character 404s (the same registration check ``websocket_router`` performs
  on connect); standalone/unit environments degrade to metadata-only with
  ``runtime.available = false``.
  """
  from companion.ai.chat import CompanionChatBridge
  from companion.ai.realtime_voice import CompanionRealtimeVoiceBridge
  from companion.ai.runtime import live_session_snapshot
  from companion.models.profile import CompanionProfile

  snapshot = live_session_snapshot(character_name)
  if snapshot is not None and not snapshot.get("registered"):
    raise HTTPException(status_code=404, detail="character not found")

  profile = CompanionProfile(
    id=f"session:{character_name}",
    name=character_name,
    display_name=character_name,
  )
  chat = CompanionChatBridge(profile)
  realtime = CompanionRealtimeVoiceBridge(profile)
  # Tier resolution reads core_config.json synchronously — offload both so
  # the shared event loop (main/memory/agent subsystems) is never blocked.
  chat_meta, realtime_meta = await asyncio.gather(
    asyncio.to_thread(chat.session_metadata),
    asyncio.to_thread(realtime.session_metadata),
  )
  return {
    "character_name": character_name,
    "websocket_url": chat.websocket_url(),
    "runtime": {
      "available": snapshot is not None,
      "session": snapshot,
    },
    "chat": chat_meta,
    "realtime_voice": realtime_meta,
  }


@router.post("/generate")
async def create_generation_task(body: GenerationInput, background: bool = False):
  """Run a generation task.

  Default (synchronous) mode blocks until the pipeline finishes and returns
  ``201``. With ``?background=true`` the pipeline runs on a worker thread and
  the response is an immediate ``202`` — poll ``GET /generate/{task_id}``
  until ``status`` is ``completed``/``failed``.
  """
  if background:
    # Fast (SQLite insert + thread spawn), but still off the event loop.
    task = await asyncio.to_thread(start_generation_background, body)
    return JSONResponse(status_code=202, content=task.to_public_dict())
  # LLM + disk IO inside the sync pipeline: offload so the shared event loop
  # (main/memory/agent subsystems) is never blocked by a generation task.
  task = await asyncio.to_thread(start_generation, body)
  return JSONResponse(
    status_code=201,
    content=task.to_public_dict(),
  )


@router.post("/generate/upload")
async def create_generation_task_multipart(
  background: bool = False,
  companion_name: str = Form(min_length=1, max_length=200),
  locale: str = Form("zh-CN"),
  corpus_text: str = Form(""),
  system_prompt: str = Form(""),
  live2d_model_id: str = Form(""),
  live2d_package_path: str = Form(""),
  corpus_files: list[UploadFile] = File(default_factory=list),
  reference_images: list[UploadFile] = File(default_factory=list),
  reference_audio: list[UploadFile] = File(default_factory=list),
  reference_video: list[UploadFile] = File(default_factory=list),
):
  """Multimodal wizard submission: persist uploads, then run the pipeline.

  Accepts multipart/form-data so the wizard can attach corpus files and
  reference images/audio/video alongside the plain generation fields.
  Decodable text corpus files are merged into ``corpus_text`` before the
  pipeline runs; every stored path is forwarded on ``GenerationInput`` so
  later stages (voice cloning, appearance) can pick them up.
  """
  def _pairs(files: list[UploadFile]):
    return [(f.filename, f.file) for f in files if f.filename]

  try:
    saved = await asyncio.to_thread(
      save_generation_uploads,
      _pairs(corpus_files),
      _pairs(reference_images),
      _pairs(reference_audio),
      _pairs(reference_video),
      inline_corpus_text=corpus_text,
    )
  except UploadError as exc:
    raise HTTPException(status_code=413, detail=str(exc))

  gen_input = GenerationInput(
    companion_name=companion_name.strip(),
    locale=locale.strip() or "zh-CN",
    corpus_text=saved.merged_corpus_text or None,
    corpus_files=saved.corpus_files,
    system_prompt=system_prompt.strip() or None,
    live2d_model_id=live2d_model_id.strip() or None,
    live2d_package_path=live2d_package_path.strip() or None,
    reference_images=saved.reference_images,
    reference_audio=saved.reference_audio,
    reference_video=saved.reference_video,
  )
  if background:
    task = await asyncio.to_thread(start_generation_background, gen_input)
  else:
    task = await asyncio.to_thread(start_generation, gen_input)
  payload = task.to_public_dict()
  payload["uploads"] = {"session_dir": saved.session_dir, **saved.counts()}
  return JSONResponse(status_code=202 if background else 201, content=payload)


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


@router.post("/generate/{task_id}/retry")
async def retry_generation_task(task_id: str, background: bool = False):
  """Retry a failed generation task from its failing stage.

  Stage checkpoints persisted by the previous attempt are reused, so
  already-completed stages (including the LLM-backed ones) are not re-run.
  Only ``failed`` tasks are retryable: ``404`` when unknown, ``409`` when
  the task is pending/running/completed. With ``?background=true`` the
  retry runs on a worker thread and the response is an immediate ``202``.
  """
  store = get_task_store()
  task = store.get(task_id)
  if task is None:
    raise HTTPException(status_code=404, detail="task not found")
  if task.status != TaskStatus.FAILED:
    raise HTTPException(
      status_code=409,
      detail=f"only failed tasks can be retried (status={task.status.value})",
    )
  if background:
    task = await asyncio.to_thread(retry_generation, task, background=True)
    return JSONResponse(status_code=202, content=task.to_public_dict())
  task = await asyncio.to_thread(retry_generation, task)
  return task.to_public_dict()


class DialogueSessionRequest(BaseModel):
  companion_name: str = Field(min_length=1, max_length=200)
  character_name: str | None = None
  locale: str = "zh-CN"
  companion_id: str | None = None


@router.post("/dialogue/session")
async def create_dialogue_session(body: DialogueSessionRequest):
  profile = CompanionProfile(
    id=body.companion_id or body.companion_name,
    name=body.companion_name,
    display_name=body.companion_name,
    locale=body.locale,
    memory_character_name=body.character_name or body.companion_name,
  )
  ai = CompanionAI(profile)
  override = body.character_name
  return {
    "profile_id": profile.id,
    "text_chat": ai.chat.connect_info(character_name=override),
    "realtime_voice": ai.realtime.connect_info(character_name=override),
  }


def _workshop_export_root() -> Path:
  from utils.config_manager import get_config_manager

  root = Path(get_config_manager().docs_dir) / "N.E.K.O" / "companions" / "workshop"
  root.mkdir(parents=True, exist_ok=True)
  return root


@router.get("/workshop/catalog")
async def workshop_catalog():
  from companion.workshop.export import scan_workshop_catalog

  entries = await asyncio.to_thread(scan_workshop_catalog, _workshop_export_root())
  return {"entries": entries}


@router.post("/workshop/publish/{task_id}", status_code=201)
async def publish_workshop_entry(task_id: str):
  from companion.workshop.export import export_workshop_bundle

  store = get_task_store()
  task = store.get(task_id)
  if task is None:
    raise HTTPException(status_code=404, detail="task not found")
  try:
    dest = await asyncio.to_thread(
      export_workshop_bundle, task, output_root=_workshop_export_root()
    )
  except ValueError as exc:
    raise HTTPException(status_code=409, detail=str(exc))
  return {"published": True, "export_path": str(dest)}


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


class ImportPackageRequest(BaseModel):
  package_path: str
  register_character: bool = True
  bootstrap_memory: bool = True
  load_avatar: bool = True
  activate_avatar: bool = True


async def _notify_memory_server_reload_safe(*, reason: str) -> bool:
  """Best-effort memory server ``/reload`` after registering a character.

  Lazy import keeps companion importable without the main_routers package
  booted (unit tests, standalone tools); any failure is non-fatal — the
  memory server also discovers new characters on its next config load.
  """
  try:
    from main_routers.characters_router.notify import notify_memory_server_reload
  except Exception:
    return False
  try:
    return await notify_memory_server_reload(reason=reason)
  except Exception:
    return False


@router.post("/import", status_code=201)
async def import_companion_package(body: ImportPackageRequest):
  """Import a ``.neko-companion`` package end to end.

  Steps (each individually toggleable):

  1. register the manifest profile as a character card (characters.json),
  2. bootstrap persona memory seeds into the memory service under the
     **final** card key (conflict renames like ``name(1)`` must key the
     memory files too, or the seeds would land under a ghost character),
  3. register the bundled Live2D avatar for hot swap (best-effort — a
     package without an avatar still imports persona + memory).
  """
  from companion.ai.bootstrap import seed_memory
  from companion.ai.persona import CharacterCardError, register_character_card
  from companion.avatar.loader import load_manifest

  try:
    manifest = await asyncio.to_thread(load_manifest, body.package_path)
  except AvatarPackageError as exc:
    raise HTTPException(status_code=422, detail=str(exc))
  profile = manifest.profile

  result: dict = {
    "package_path": body.package_path,
    "companion_id": profile.id,
    "name": profile.name,
    "character_name": None,
    "memory": None,
    "avatar": None,
  }

  character_name = None
  if body.register_character:
    try:
      character_name = await register_character_card(profile)
    except CharacterCardError as exc:
      raise HTTPException(status_code=422, detail=str(exc))
    result["character_name"] = character_name

  if body.bootstrap_memory:
    memory_name = character_name or profile.resolved_memory_name()
    result["memory"] = await seed_memory(memory_name, manifest.memory_seeds)

  if body.load_avatar:
    try:
      avatar = await asyncio.to_thread(
        load_avatar_from_package,
        body.package_path,
        _get_avatar_registry(),
        body.activate_avatar,
      )
      result["avatar"] = _avatar_public_dict(avatar)
    except AvatarPackageError as exc:
      result["avatar_error"] = str(exc)

  if character_name is not None:
    result["memory_server_reloaded"] = await _notify_memory_server_reload_safe(
      reason=f"companion import: {character_name}"
    )

  return JSONResponse(status_code=201, content=result)


@router.post("/generate/{task_id}/import")
async def import_generated_companion(task_id: str, activate: bool = True):
  """One-click import: register a completed generation as a live companion.

  Delegates to the full ``/import`` path when the generated package exists.
  """
  store = get_task_store()
  task = store.get(task_id)
  if task is None:
    raise HTTPException(status_code=404, detail="task not found")
  if task.status != TaskStatus.COMPLETED or task.artifact is None:
    raise HTTPException(status_code=409, detail="task not completed")
  package_dir = Path(task.artifact.package_path)
  if not package_dir.is_dir():
    raise HTTPException(status_code=404, detail="generated package not found")
  body = ImportPackageRequest(
    package_path=str(package_dir),
    activate_avatar=activate,
  )
  response = await import_companion_package(body)
  content = json.loads(response.body)
  avatar_error = content.get("avatar_error")
  if avatar_error and content.get("avatar") is None:
    raise HTTPException(status_code=422, detail=avatar_error)
  payload = {"imported": True, **content}
  if content.get("avatar") is not None:
    payload["avatar"] = content["avatar"]
  return JSONResponse(status_code=201, content=payload)


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
  registry = _get_avatar_registry()
  profiles = registry.list_profiles()
  active = registry.active()
  return {
    "active_id": active.id if active else None,
    "profiles": [_avatar_public_dict(p) for p in profiles],
  }


@router.get("/avatar/active")
async def get_active_avatar():
  active = _get_avatar_registry().active()
  if active is None:
    return {"active": None}
  return {"active": _avatar_public_dict(active)}


@router.post("/avatar/active")
async def set_active_avatar(profile_id: str):
  profile = _get_avatar_registry().set_active(profile_id)
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
      body.package_path, _get_avatar_registry(), activate=body.activate
    )
  except AvatarPackageError as exc:
    raise HTTPException(status_code=422, detail=str(exc))
  return JSONResponse(status_code=201, content=_avatar_public_dict(profile))


@router.delete("/avatar/{profile_id}")
async def delete_avatar_profile(profile_id: str, delete_package: bool = False):
  """Remove an avatar from the (persisted) registry, optionally with its package.

  ``?delete_package=true`` also removes the package directory from disk,
  guarded by the safe-path rules of
  :func:`companion.avatar.store.remove_package_dir` — only directories
  inside the managed companions data root that contain a ``manifest.json``
  qualify. A violation returns ``409`` and leaves the registry unchanged.
  """
  from companion.avatar.store import PackagePathError, remove_package_dir

  registry = _get_avatar_registry()
  profile = registry.get(profile_id)
  if profile is None:
    raise HTTPException(status_code=404, detail="avatar profile not found")

  removed_path: str | None = None
  if delete_package:
    live2d = profile.effects.get("live2d") or {}
    package_dir = live2d.get("package_dir")
    if package_dir:
      try:
        # rmtree is disk IO: keep it off the shared event loop.
        removed_path = await asyncio.to_thread(remove_package_dir, package_dir)
      except PackagePathError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

  registry.unregister(profile_id)
  active = registry.active()
  return {
    "deleted": profile_id,
    "active_id": active.id if active else None,
    "package_removed": removed_path,
  }


@router.get("/avatar/{profile_id}/resource/{resource_path:path}")
async def get_avatar_resource(profile_id: str, resource_path: str):
  """Serve Live2D model files (entry JSON, textures, motions) from a package.

  pixi-live2d-display resolves textures relative to the entry URL, so the
  whole package subtree must be reachable through this endpoint.
  """
  profile = _get_avatar_registry().get(profile_id)
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


@router.get("/avatar/effects/schema")
async def avatar_effects_schema():
  from companion.avatar.effects import EffectConfig

  return EffectConfig().to_dict()


@router.post("/avatar/effects")
async def set_avatar_effects(
  profile_id: str,
  particles: bool = False,
  border: str = "",
  background: str = "",
):
  registry = _get_avatar_registry()
  profile = registry.get(profile_id)
  if profile is None:
    raise HTTPException(status_code=404, detail="avatar profile not found")
  from companion.avatar.effects import EffectConfig

  fx = EffectConfig(
    particles=particles, border=border, background=background
  )
  profile.effects["decorations"] = fx.to_dict()
  # Write-through: decorations survive restarts (Phase 5 M2).
  registry.save_profile(profile)
  return {"profile_id": profile_id, "effects": fx.to_dict()}


@router.post("/tts/preview")
async def tts_preview(text: str = "你好，我是你的专属虚拟伴侣。"):
  from companion.ai.tts_bridge import CompanionTTSBridge
  from companion.models.profile import CompanionProfile

  active = _get_avatar_registry().active()
  name = active.display_name if active else "companion"
  bridge = CompanionTTSBridge(
    CompanionProfile(id="preview", name=name, display_name=name)
  )
  return bridge.preview_payload(text)
