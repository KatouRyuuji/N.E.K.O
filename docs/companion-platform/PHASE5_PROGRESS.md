# Phase 5 进展快照（Situation / Progress）

> 本文是 **Phase 5 第三波**（M4、M6 已合入 `main`；累计 M1–M6 全部完成）后的
> 可读现状摘要。详细里程碑定义见 [PHASE5_PLAN.md](./PHASE5_PLAN.md)；交接与
> 历史见 [PHASE5_STATUS.md](./PHASE5_STATUS.md)。**测试基线**（2026-08-25）：
> `uv run pytest tests/unit/test_companion_*.py` → **219 passed**
> （CI「Companion pytest (Linux)」于 `main` HEAD 绿色）。

## 已完成里程碑

| 里程碑 | 主题 | 主要交付 | 合入方式 |
|--------|------|----------|----------|
| M1 | Ollama 一键配置 | `static/companion/ollama/`、`POST /api/companion/ai/open-source/config` | PR [#9](https://github.com/KatouRyuuji/N.E.K.O/pull/9) |
| M2 | Avatar 持久化 | SQLite registry、`DELETE /api/companion/avatar/{profile_id}` | PR [#8](https://github.com/KatouRyuuji/N.E.K.O/pull/8) |
| M3 | 监控 / 指标 | `GET /api/companion/metrics`、`stage_timings_ms` 透出 | `main` `5297af8f` |
| M5 | 工坊市场 UX | 元数据/封面、`GET /workshop/entry/{id}`、`GET /workshop/asset/...`、卡片 UI | `main` `b90efb72` |
| M4 | 记忆 / 人设深化 | 语料 fact 种子（`extract_fact_seeds` 可选阶段）、`POST /persona/{name}/refine`（diff 提案）+ `/refine/apply`、版本链 `GET /persona/{name}/versions` + `POST /persona/{name}/rollback` | PR [#12](https://github.com/KatouRyuuji/N.E.K.O/pull/12) |
| M6 | 移动同步协议 | [SYNC_PROTOCOL.md](./SYNC_PROTOCOL.md) v1.0、`GET /sync/manifest`、`GET /sync/memory/{name}?since=...`（只读、桌面权威、游标幂等） | PR [#11](https://github.com/KatouRyuuji/N.E.K.O/pull/11) |

Phase 4 集成、文档与 Phase 5 计划基线：PR #1–#7；实时对话 / HA / 工坊 i18n 等见 #5–#6。

## 10 项必达功能 — 当前覆盖（摘要）

与 [GAP_ANALYSIS.md](./GAP_ANALYSIS.md) 对齐：

- **无剩余缺口（实现可用）**：#4 实时语音、#5 实时文字、#8 Live2D 资源服务。
- **Phase 5 已闭合的深化项**：#9 形象热替换（registry 持久化）、#10 开源 AI
  （Ollama 向导 UI + config 写入）、#1 记忆 fact 种子 + 跨设备同步协议（M4/M6）、
  #2 人设迭代 / 版本管理（M4，API 级；专属 UI 待 M7 收口）。
- **仍待 Phase 5+**：#3 声线克隆（M8）、#6/#7 体验增强、**M7** Electron、
  **M8** TTS 深化。

## 关键 API 索引（第二、三波新增或强化）

前缀均为 `/api/companion`，**无末尾斜杠**。

| 能力 | 方法与路径 |
|------|------------|
| 运行指标 | `GET /metrics` |
| Ollama 状态 | `GET /ai/open-source` |
| Ollama 写入 tier | `POST /ai/open-source/config` |
| 工坊条目详情 | `GET /workshop/entry/{catalog_id}` |
| 工坊静态资源 | `GET /workshop/asset/{catalog_id}/{path}` |
| 生成阶段耗时 | `GET /generate/{task_id}` 响应中的 `stage_timings_ms` |
| 语料 fact 种子 | 生成输入 `extract_fact_seeds: true`（默认关；LLM-only，无启发式兜底） |
| 人设迭代提案 | `POST /persona/{name}/refine`（`correction` tier → diff，不落盘） |
| 人设迭代写回 | `POST /persona/{name}/refine/apply`（先快照后写，`expected_system_prompt` 乐观锁） |
| 人设版本链 | `GET /persona/{name}/versions`、`POST /persona/{name}/rollback` |
| 同步设备快照 | `GET /sync/manifest`（协议见 [SYNC_PROTOCOL.md](./SYNC_PROTOCOL.md)） |
| 同步记忆增量 | `GET /sync/memory/{name}?since=...&limit=...&include_persona=...` |

静态页：`/static/companion/ollama/index.html`（本地模型配置）、
`/static/companion/workshop/index.html`（卡片目录 + 预览）。

## Phase 5 第三波后规划

M1–M6 全部合入后，优先级按 [PHASE5_PLAN.md](./PHASE5_PLAN.md) 收口到两个
P2 里程碑与剩余体验缺口：

1. **M7 Electron Companion Shell**（P2，优先）——依赖项 M2/M5 已稳定：
   向导 / 工坊 / 生产力面板适配 Electron 窗口路由、生产力常驻小窗、
   PyInstaller spec 收入 `companion/` 与 `static/companion/`。人设 refine
   的确认式 diff UI 也建议随 M7 页面一并落地（后端 API 已就绪）。
2. **M8 声线克隆与 TTS 深化**（P2）——克隆 provider（GPT-SoVITS /
   fish-speech）接入 `utils/tts/`，`configure_voice` 阶段走克隆路径，
   不可用时静默回退映射启发式。
3. **剩余缺口**（见 [GAP_ANALYSIS.md](./GAP_ANALYSIS.md)）：#6 番茄钟主动
   对话深度联动与 OS 级媒体监测、#7 更多装饰类型、移动端原生客户端
   （M6 协议已验证，客户端实现明确不在 Phase 5 范围）。

并行约束不变：`.agent/rules/neko-guide.md`（8 locale、LLM tier/budget/timeout、async 零阻塞）。

## 分支与 PR 约定

- 新工作从 **`main`** 拉 `cursor/<descriptive-name>-3e93`。
- 已合入的 `cursor/companion-*-3e93` 历史分支仅追溯，勿续写（列表见 PHASE5_STATUS）。
