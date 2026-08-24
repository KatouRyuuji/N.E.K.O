# Productivity Module

复用 `music_router`、`jukebox_router`、`widget_mode_router` 的音乐与常驻能力。

## 子模块

- `pomodoro.py` — 番茄钟状态机
- `todo.py` — Todo CRUD
- `memo.py` — 备忘
- `media_monitor.py` — 系统媒体状态（Phase 2 对接 OS API）
- `service.py` — 统一 Facade + 伴侣联动 hook

## API

挂载于 `/api/companion/productivity/*`（见 `companion/api/routes.py`）。
