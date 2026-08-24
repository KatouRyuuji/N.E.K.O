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

"""Unit tests for companion productivity SQLite persistence and API."""

from pathlib import Path

import pytest

from companion.productivity.memo import MemoService
from companion.productivity.service import ProductivityService
from companion.productivity.storage import (
  ENV_DB_PATH,
  ProductivityStorage,
  default_db_path,
)
from companion.productivity.todo import TodoService


# ------------------------------------------------------------------ storage


def test_storage_todo_crud(tmp_path):
  store = ProductivityStorage(tmp_path / "prod.db")
  created = store.create_todo("写周报")
  assert created["title"] == "写周报"
  assert created["done"] is False
  assert created["created_at"]

  todos = store.list_todos()
  assert [t["id"] for t in todos] == [created["id"]]

  updated = store.set_todo_done(created["id"], True)
  assert updated["done"] is True
  assert updated["updated_at"] >= created["updated_at"]

  renamed = store.update_todo_title(created["id"], "写月报")
  assert renamed["title"] == "写月报"

  assert store.set_todo_done("missing", True) is None
  assert store.update_todo_title("missing", "x") is None

  assert store.delete_todo(created["id"]) is True
  assert store.delete_todo(created["id"]) is False
  assert store.list_todos() == []
  store.close()


def test_storage_memo_crud(tmp_path):
  store = ProductivityStorage(tmp_path / "prod.db")
  first = store.create_memo("第一条")
  second = store.create_memo("第二条")

  memos = store.list_memos()
  assert len(memos) == 2
  # Newest first.
  assert memos[0]["id"] == second["id"]
  assert memos[1]["id"] == first["id"]

  assert store.delete_memo(first["id"]) is True
  assert store.delete_memo(first["id"]) is False
  assert len(store.list_memos()) == 1
  store.close()


def test_storage_persists_across_reopen(tmp_path):
  db = tmp_path / "prod.db"
  store = ProductivityStorage(db)
  todo = store.create_todo("持久化验证")
  store.set_todo_done(todo["id"], True)
  memo = store.create_memo("重启后还在")
  store.close()

  reopened = ProductivityStorage(db)
  todos = reopened.list_todos()
  memos = reopened.list_memos()
  assert len(todos) == 1
  assert todos[0]["title"] == "持久化验证"
  assert todos[0]["done"] is True
  assert memos[0]["id"] == memo["id"]
  reopened.close()


def test_default_db_path_env_override(monkeypatch, tmp_path):
  target = tmp_path / "custom" / "neko.db"
  monkeypatch.setenv(ENV_DB_PATH, str(target))
  assert default_db_path() == target


# ----------------------------------------------------------------- services


def test_services_share_storage(tmp_path):
  storage = ProductivityStorage(tmp_path / "prod.db")
  todo_service = TodoService(storage)
  memo_service = MemoService(storage)

  item = todo_service.create("学习 SQLite")
  assert todo_service.toggle(item.id, True).done is True
  assert todo_service.rename(item.id, "学习 SQLite 事务").title == "学习 SQLite 事务"
  assert todo_service.get(item.id).done is True
  assert todo_service.toggle("missing", True) is None

  memo = memo_service.create("备忘")
  assert [m.id for m in memo_service.list_memos()] == [memo.id]
  assert memo_service.delete(memo.id) is True
  storage.close()


def test_productivity_service_persistence(tmp_path):
  db = tmp_path / "svc.db"
  service = ProductivityService(db)
  service.todo.create("A")
  service.memo.create("B")
  service.close()

  restarted = ProductivityService(db)
  assert [t.title for t in restarted.todo.list_items()] == ["A"]
  assert [m.content for m in restarted.memo.list_memos()] == ["B"]
  restarted.close()


def test_media_monitor_music_state_shape():
  from companion.productivity.media_monitor import MediaMonitor

  state = MediaMonitor().music_state()
  assert isinstance(state, dict)
  assert "available" in state
  if state["available"]:
    assert isinstance(state["source_domains"], list)
    assert "proxy_cache" in state
    assert "netease_vip_resolver" in state
  else:
    assert "reason" in state


# ---------------------------------------------------------------------- API


@pytest.fixture()
def companion_client(monkeypatch, tmp_path):
  fastapi = pytest.importorskip("fastapi")
  from fastapi.testclient import TestClient

  monkeypatch.setenv(ENV_DB_PATH, str(tmp_path / "api.db"))
  import companion.api.routes as routes

  monkeypatch.setattr(routes, "_productivity", None)
  app = fastapi.FastAPI()
  app.include_router(routes.router)
  with TestClient(app) as client:
    yield client
  if routes._productivity is not None:
    routes._productivity.close()
    routes._productivity = None


def test_api_todo_lifecycle(companion_client):
  res = companion_client.post(
    "/api/companion/productivity/todos", json={"title": "  api todo  "}
  )
  assert res.status_code == 201
  todo = res.json()
  assert todo["title"] == "api todo"
  assert todo["done"] is False

  res = companion_client.patch(
    f"/api/companion/productivity/todos/{todo['id']}", json={"done": True}
  )
  assert res.status_code == 200
  assert res.json()["done"] is True

  res = companion_client.patch(
    f"/api/companion/productivity/todos/{todo['id']}", json={"title": "renamed"}
  )
  assert res.json()["title"] == "renamed"

  res = companion_client.get("/api/companion/productivity/todos")
  assert [t["id"] for t in res.json()["todos"]] == [todo["id"]]

  res = companion_client.delete(f"/api/companion/productivity/todos/{todo['id']}")
  assert res.status_code == 200
  res = companion_client.delete(f"/api/companion/productivity/todos/{todo['id']}")
  assert res.status_code == 404
  res = companion_client.patch(
    "/api/companion/productivity/todos/missing", json={"done": True}
  )
  assert res.status_code == 404


def test_api_memo_lifecycle(companion_client):
  res = companion_client.post(
    "/api/companion/productivity/memos", json={"content": "记住这件事"}
  )
  assert res.status_code == 201
  memo = res.json()

  res = companion_client.get("/api/companion/productivity/memos")
  assert [m["id"] for m in res.json()["memos"]] == [memo["id"]]

  res = companion_client.delete(f"/api/companion/productivity/memos/{memo['id']}")
  assert res.status_code == 200
  res = companion_client.delete(f"/api/companion/productivity/memos/{memo['id']}")
  assert res.status_code == 404


def test_api_status_and_music(companion_client):
  companion_client.post(
    "/api/companion/productivity/todos", json={"title": "status todo"}
  )
  companion_client.post(
    "/api/companion/productivity/memos", json={"content": "status memo"}
  )
  res = companion_client.get("/api/companion/productivity/status")
  assert res.status_code == 200
  status = res.json()
  assert status["pomodoro"]["phase"] == "idle"
  assert [t["title"] for t in status["todos"]] == ["status todo"]
  assert [m["content"] for m in status["memos"]] == ["status memo"]
  assert "media" in status

  res = companion_client.get("/api/companion/productivity/music")
  assert res.status_code == 200
  assert "available" in res.json()


def test_api_validation_rejects_blank(companion_client):
  res = companion_client.post("/api/companion/productivity/todos", json={"title": ""})
  assert res.status_code == 422
  res = companion_client.post(
    "/api/companion/productivity/memos", json={"content": ""}
  )
  assert res.status_code == 422


def test_api_persists_across_service_restart(companion_client, tmp_path):
  companion_client.post(
    "/api/companion/productivity/todos", json={"title": "survive restart"}
  )
  import companion.api.routes as routes

  routes._productivity.close()
  routes._productivity = None

  res = companion_client.get("/api/companion/productivity/todos")
  assert [t["title"] for t in res.json()["todos"]] == ["survive restart"]
