# Phase 5 进展快照（Situation / Progress）

> 本文是 **Phase 5 第二波**（M1–M3、M5 已合入 `main`）后的可读现状摘要。
> 详细里程碑定义见 [PHASE5_PLAN.md](./PHASE5_PLAN.md)；交接与历史见
> [PHASE5_STATUS.md](./PHASE5_STATUS.md)。**测试基线**（2026-08-24）：
> `uv run pytest tests/unit/test_companion_*.py` → **175 passed**。

## 已完成里程碑

| 里程碑 | 主题 | 主要交付 | 合入方式 |
|--------|------|----------|----------|
| M1 | Ollama 一键配置 | `static/companion/ollama/`、`POST /api/companion/ai/open-source/config` | PR [#9](https://github.com/KatouRyuuji/N.E.K.O/pull/9) |
| M2 | Avatar 持久化 | SQLite registry、`DELETE /api/companion/avatar/{profile_id}` | PR [#8](https://github.com/KatouRyuuji/N.E.K.O/pull/8) |
| M3 | 监控 / 指标 | `GET /api/companion/metrics`、`stage_timings_ms` 透出 | `main` `5297af8f` |
| M5 | 工坊市场 UX | 元数据/封面、`GET /workshop/entry/{id}`、`GET /workshop/asset/...`、卡片 UI | `main` `b90efb72` |

Phase 4 集成、文档与 Phase 5 计划基线：PR #1–#7；实时对话 / HA / 工坊 i18n 等见 #5–#6。

## 10 项必达功能 — 当前覆盖（摘要）

与 [GAP_ANALYSIS.md](./GAP_ANALYSIS.md) 对齐：

- **无剩余缺口（实现可用）**：#4 实时语音、#5 实时文字、#8 Live2D 资源服务。
- **Phase 5 已闭合的深化项**：#9 形象热替换（registry 持久化）、#10 开源 AI（Ollama 向导 UI + config 写入）。
- **仍待 Phase 5+**：#1 记忆 fact 层种子与同步、#2 人设迭代/版本、#3 声线克隆、#6/#7 体验增强、**M6** 移动同步、**M7** Electron、**M8** TTS 深化。

## 关键 API 索引（第二波新增或强化）

前缀均为 `/api/companion`，**无末尾斜杠**。

| 能力 | 方法与路径 |
|------|------------|
| 运行指标 | `GET /metrics` |
| Ollama 状态 | `GET /ai/open-source` |
| Ollama 写入 tier | `POST /ai/open-source/config` |
| 工坊条目详情 | `GET /workshop/entry/{catalog_id}` |
| 工坊静态资源 | `GET /workshop/asset/{catalog_id}/{path}` |
| 生成阶段耗时 | `GET /generate/{task_id}` 响应中的 `stage_timings_ms` |

静态页：`/static/companion/ollama/index.html`（本地模型配置）、
`/static/companion/workshop/index.html`（卡片目录 + 预览）。

## 建议下一认领顺序

1. **M4** 记忆 / 人设深度集成（P1，依赖 M1 已就绪）。
2. **M6** 移动端 Companion 同步协议（P1，协议 + 桌面双实例验证）。
3. **M7** Electron Shell（P2，依赖 M2/M5 稳定）。
4. **M8** 声线克隆（P2）。

并行约束不变：`.agent/rules/neko-guide.md`（8 locale、LLM tier/budget/timeout、async 零阻塞）。

## 分支与 PR 约定

- 新工作从 **`main`** 拉 `cursor/<descriptive-name>-3e93`。
- 已合入的 `cursor/companion-*-3e93` 历史分支仅追溯，勿续写（列表见 PHASE5_STATUS）。
