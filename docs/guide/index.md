# Developer Guide

Project N.E.K.O. is an open-source AI companion platform with avatar rendering, realtime/text interaction, persistent memory, agent execution, and plugins. This site documents the current repository for contributors and integrators; it is not a product-pricing or provider-capability catalog.

## Repository surfaces

- Python 3.11 FastAPI/Uvicorn services under `app/`
- Conversation and persistent-memory domains under `main_logic/` and `memory/`
- Agent execution under `brain/` and the agent server
- Jinja/static pages plus one shared React chat implementation
- Vue plugin manager under `frontend/plugin-manager/`
- Electron desktop distribution built from N.E.K.O.-PC plus this packaged backend
- Container deployment under `docker/`

## Evaluate N.E.K.O. before setup

| Question | Buyer guide |
| --- | --- |
| Is the app free, and what can AI services cost? | [Cost and providers](./cost-and-providers) |
| Can it run completely offline? | [Local and offline boundaries](./local-and-offline) |
| Where can conversations and memory be sent? | [Technical data flow and privacy controls](./data-and-privacy) |
| Which installation channel should I choose? | [Steam, GitHub Releases, or source](./install-options) |

## Start here

| Goal | Page |
| --- | --- |
| Check tools | [Prerequisites](./prerequisites) |
| Prepare a checkout | [Development Setup](./dev-setup) |
| Run N.E.K.O. | [Quick Start](./quick-start) |
| Navigate code | [Project Structure](./project-structure) |
| Understand services | [Architecture](/architecture/) |
| Build a plugin | [Plugin Quick Start](/plugins/quick-start) |
| Deploy | [Deployment](/deployment/) |

## Companion Platform

The Companion Platform (the `companion/` package, integrated through Phase 4) turns corpus text, prompts, and reference media into an importable `.neko-companion` package, then runs it on the N.E.K.O. core. Design docs live in the repository under `docs/companion-platform/`.

- **Generation wizard** — served at `/static/companion/wizard/index.html`: multimodal upload (corpus, images, audio, video, Live2D package), 7-stage progress, one-click "import as character".
- **Workshop page** — `/static/companion/workshop/index.html`: browse the local catalog of published `.neko-companion` bundles and publish completed generation tasks.
- **API** — everything sits under `/api/companion/*` (no trailing slashes): `GET /api/companion/health`, generation (`POST /api/companion/generate`, `POST /api/companion/generate/upload`), import (`POST /api/companion/import`), avatar hot swap (`/api/companion/avatar/*`), productivity (`/api/companion/productivity/*`), workshop (`GET /api/companion/workshop/catalog`, `POST /api/companion/workshop/publish/{task_id}`).
- **Dialogue sessions** — `GET /api/companion/session/{character_name}` returns aggregated text + realtime-voice session metadata (websocket routing, sanitized provider tiers, protocol frames); `POST /api/companion/dialogue/session` builds connect info for both channels from a companion profile.
- **Long-running generation** — generation endpoints accept `?background=true` (immediate `202`, poll `GET /api/companion/generate/{task_id}`); failed tasks resume from the failing stage via `POST /api/companion/generate/{task_id}/retry` — completed LLM stages are not re-run.

All Python examples use `uv run`. If a page conflicts with the same-revision entrypoint, loader, or workflow, current code is the source of truth; please report the documentation drift.
