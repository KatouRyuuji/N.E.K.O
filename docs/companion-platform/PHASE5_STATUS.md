# Phase 5 状态与交接（Status & Handoff）

> 本文是 Phase 4 收尾（wrap-up）后的状态基线：记录收尾清单、分支处置结论，
> 以及 Phase 5 首批里程碑（M1 / M2，定义见 [PHASE5_PLAN.md](./PHASE5_PLAN.md)）
> 的 subagent 交接说明。里程碑完成后请在此追加状态，不要改写历史结论。

## Phase 4 收尾清单（已完成）

- [x] `ROADMAP.md` / `GAP_ANALYSIS.md` / `ARCHITECTURE.md` 更新为
      「Phase 4 已完成」基线，遗留项（Ollama 向导 UI、移动端同步）显式转入 Phase 5。
- [x] `PHASE5_PLAN.md`：M1–M8 里程碑、优先级、验收标准与依赖关系图。
- [x] 开发者手册（`docs/guide/index.md`、`docs/zh-CN/guide/index.md`、
      `docs/ja/guide/index.md`）加入 Companion Platform 章节：
      生成向导（`/static/companion/wizard/`）、创意工坊
      （`/static/companion/workshop/`）、`/api/companion/*` API 索引、
      对话会话、后台生成，以及 Ollama 状态 API
      （`GET /api/companion/ai/open-source`）。
- [x] 代码收尾修复：`GET /api/companion/ai/open-source` 不可用分支对
      dataclass 误调 `model_dump()` 导致 500 → 改用 `dataclasses.asdict`；
      探测改为 `asyncio.to_thread` offload（遵循 async 零阻塞规则）；
      `companion/ai/open_source.py` docstring 与实际行为对齐。
- [x] 单测基线：`tests/unit/test_companion_*.py` → **175 passed**（2026-08-24；
      含 M1/M2/M3/M5 路由与 store 覆盖）。进展快照见
      [PHASE5_PROGRESS.md](./PHASE5_PROGRESS.md)。

## 分支处置（open branches to ignore）

以下 `origin/cursor/companion-*-3e93` 分支已**全部合入 main**
（`git merge-base --is-ancestor` 验证），仅作历史追溯保留，
**后续开发一律从 `main` 拉新分支，不要基于它们续写**：

| 分支 | 内容 | PR |
|------|------|----|
| `cursor/companion-platform-integration-3e93` | Phase 1–3 集成底座 | #1 |
| `cursor/companion-avatar-swap-ui-3e93` | Avatar 热替换 + L2D 桥接 | #2 |
| `cursor/companion-productivity-ui-3e93` | 生产力面板 + SQLite | #3 |
| `cursor/companion-generator-llm-3e93` | Pipeline 真实 LLM + Ollama 降级 | #4 |
| `cursor/companion-phase4-integration-3e93` | Phase 4 HA / 对话 / 工坊 i18n | #5 |
| `cursor/companion-docs-phase5-plan-3e93` | Phase 4 完成文档 + Phase 5 计划 | #6 |
| `cursor/companion-ollama-wizard-3e93` | Phase 5 M1 Ollama 向导 | #9 |
| `cursor/companion-avatar-persist-3e93` | Phase 5 M2 Avatar 持久化 | #8 |

## M1 / M2 完成状态（Phase 5）

- [x] **M1** Ollama 一键配置：`static/companion/ollama/`、`POST /ai/open-source/config`（[#9](https://github.com/KatouRyuuji/N.E.K.O/pull/9)）。
- [x] **M2** Avatar Registry SQLite + `DELETE /avatar/{profile_id}`（[#8](https://github.com/KatouRyuuji/N.E.K.O/pull/8)）。
- [x] **M3** 指标：`GET /metrics`、阶段耗时（[#10+ / main `5297af8f`]）。
- [x] **M5** 工坊市场 UX：catalog 卡片元数据、封面资源、`GET /workshop/entry/{catalog_id}`、`GET /workshop/asset/...`（`main` `b90efb72`）。

## Phase 5 第二波（文档与现状）

- [x] [PHASE5_PROGRESS.md](./PHASE5_PROGRESS.md)：M1–M3/M5 完成态、API 索引、下一认领顺序。
- [x] 开发者手册 en/ja/zh Companion 章节：metrics、Ollama 向导页、工坊 entry/asset API。
- [x] [ROADMAP.md](./ROADMAP.md) / [GAP_ANALYSIS.md](./GAP_ANALYSIS.md) / [ARCHITECTURE.md](./ARCHITECTURE.md) 与 `main` 实现对齐。

## Phase 5 第三波（M4 / M6，已完成）

- [x] **M4** 记忆 / 人设深化（PR [#12](https://github.com/KatouRyuuji/N.E.K.O/pull/12)）：
      语料 → fact 种子可选阶段（`GenerationInput.extract_fact_seeds`，默认关，
      LLM-only 无启发式兜底；`bootstrap.py` 经 memory fact 写入路径落 fact 层，
      带 `external_import` 溯源）；人设迭代
      `POST /persona/{name}/refine`（`correction` tier → diff 提案，确认后
      `POST /persona/{name}/refine/apply` 先快照后写回）；版本链
      `GET /persona/{name}/versions` + `POST /persona/{name}/rollback`
      （`companion/ai/persona_versions.py`，上限
      `COMPANION_PERSONA_VERSION_MAX_SNAPSHOTS`）。
      单测 `tests/unit/test_companion_memory_m4.py`（26 项）。
- [x] **M6** 移动同步协议（PR [#11](https://github.com/KatouRyuuji/N.E.K.O/pull/11)）：
      协议规范 [SYNC_PROTOCOL.md](./SYNC_PROTOCOL.md)（v1.0，只读、桌面权威）；
      `GET /sync/manifest` 设备快照 + `GET /sync/memory/{name}?since=...`
      记忆增量（`(created_at, id)` 复合游标，幂等 / 分页 / 断点续传；persona
      层 digest 比对 + snapshot-on-change）。实现
      `companion/sync/service.py`；双桌面实例验证闭环见协议 §7。
      单测 `tests/unit/test_companion_sync_m6.py`（18 项）。
- [x] CI 测试门禁：`.github/workflows/companion-tests.yml`（scoped pytest gate，
      push `main`/`cursor/**` + PR，命令即验收命令）。
- [x] 单测基线更新：`uv run pytest tests/unit/test_companion_*.py` →
      **219 passed**（2026-08-25；175 + M4 26 项 + M6 18 项）。
- [x] 历史分支追加（同「仅追溯，勿续写」规则）：
      `cursor/companion-sync-m6-3e93`（#11）、`cursor/companion-memory-m4-3e93`（#12）。

M1–M6 至此全部完成；第三波后规划（M7 / M8 / 剩余缺口）见
[PHASE5_PROGRESS.md](./PHASE5_PROGRESS.md) 与 [PHASE5_PLAN.md](./PHASE5_PLAN.md)。

## M1 交接 — Ollama 一键配置向导（P0，已完成）

认领 subagent 需要知道的现状与坑：

1. **存在两个 Ollama 探测模块，职责不同，勿合并出回归**：
   - `companion/generator/open_source.py`：生成 pipeline 用。
     `detect_ollama()`（`GET /api/tags`，timeout 走
     `config.COMPANION_OLLAMA_DETECT_TIMEOUT_SECONDS`）、
     `resolve_ollama_api_config()`（产出 `get_model_api_config` 形状、
     指向 `/v1` OpenAI 兼容面、跳过 embedder 模型）、
     `is_ollama_endpoint()`（与 `brain/openfang_adapter` 同构启发式）。
   - `companion/ai/open_source.py`：API 层轻量版，纯 env 驱动
     （`OLLAMA_HOST` / `COMPANION_OLLAMA_MODEL`），无 `config`/logger 依赖，
     支撑 `GET /api/companion/ai/open-source`。
2. **状态 API 响应形状**（向导前端以此为契约）：
   - 不可用：`{"available": false, "providers": {"ollama": {…asdict…}}}`；
   - 可用：`{"available": true, "active": "ollama", "config": {"model", "base_url"}}`。
   - 收尾修复前不可用分支会 500（`model_dump` bug），已修；
     probes 现经 `asyncio.to_thread` offload——新增端点请沿用该模式。
3. **写入端点**（M1 交付物 2）：`POST /api/companion/ai/open-source/config`
   落 `config/api_providers.json` 时必须复用 config_manager 的写入路径，
   async 路由走 `a*` 版本；不要自造 JSON 读写。
4. **测试缺口**：`tests/unit/test_companion_platform.py` 已覆盖两个模块的
   probe / resolve（含 monkeypatch httpx 模式，可直接照抄），但**没有**
   `/ai/open-source` 的路由级测试——M1 请一并补上
   （不可用分支 + 可用分支 + config 写入 + 探测失败降级）。
5. **i18n**：向导文案经 `static/companion/i18n.js` + `static/locales`
   8 个 locale 同步；新增 key 必须 8 份齐全
   （`tests/unit/test_i18n_locale_keys.py` 做 key 对齐校验）。

## M2 交接 — Avatar Registry 持久化（P0）

1. **现状锚点**：`companion/api/routes.py` 模块级
   `_avatar_registry = AvatarRegistry()`（进程内存态）；类实现在
   `companion/avatar/registry.py`。重启后 `/avatar/list` 为空，需重新 import。
2. **持久化模板**：与 `companion/generator/tasks.py` 的
   `GenerationTaskStore` 结构对偶——路径解析三级优先
   （env 覆盖 → config_manager 用户数据目录 `companion/` 下 →
   项目内 `memory/store/` 兜底，见 `default_tasks_db_path()`），
   `check_same_thread=False` + 锁，模块级单例 + 测试用 reset 钩子。
   registry 建议同模式落 `companion_avatars.db`
   （或 JSON，二选一后在 PR 里写明理由）。
3. **必须一起持久化的状态**：active avatar id、`profile.effects`
   （含 `decorations` 与 `live2d` 键——资源端点
   `/avatar/{id}/resource/{path}` 依赖 `live2d.relative_entry`）。
4. **写入入口共 3 处**，恢复逻辑要覆盖全部：`POST /import`、
   `POST /generate/{task_id}/import`、`POST /avatar/load-package`；
   effects 变更入口为 `POST /avatar/effects`。
5. **GC / 删除**（M2 交付物 2）：新增 `DELETE /api/companion/avatar/{profile_id}`
   时注意包目录（uploads session 目录、workshop 导出目录）的清理端点
   与 registry 记录解耦——删记录不误删共享资源。
6. **验收测试**：导入 → 重建 store（模拟重启）→ list/active/resource
   仍可用；并发写入用 `GenerationTaskStore` 现有测试作参照。
