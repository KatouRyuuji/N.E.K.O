# Companion Platform Roadmap

> 状态基准：Phase 4 集成已完成；Phase 5 第二波（M1/M2/M3/M5）与第三波
> （M4/M6）已合入 `main`——M1–M6 全部完成，剩 M7/M8（P2）。
> 收尾与分支处置见 [PHASE5_STATUS.md](./PHASE5_STATUS.md)；进展见
> [PHASE5_PROGRESS.md](./PHASE5_PROGRESS.md)。后续规划见 [PHASE5_PLAN.md](./PHASE5_PLAN.md)。

## Phase 1 — 基础骨架（已完成）

- [x] 架构文档与差距分析
- [x] `companion/models` 数据模型
- [x] Generator Pipeline 骨架 + 任务 API
- [x] 并行 Agent：生产力 / Avatar / AI Facade

## Phase 2 — 核心能力封装（已完成）

- [x] `companion/ai/` 记忆/人设/对话/TTS 统一 Facade
- [x] `companion/avatar/` 形象注册表与热替换
- [x] Generator 各阶段接入真实 LLM（`summary` tier → Ollama → 启发式三级降级）
- [x] `.neko-companion` 导入/导出端到端（`POST /api/companion/import`）

## Phase 3 — 生产力与体验（已完成）

- [x] 番茄钟 / Todo / 备忘 UI 面板（`static/companion/productivity/`）
- [x] 多媒体状态监测与 Avatar 联动
- [x] 特效/装饰配置与 Live2D 表情联动（effects schema + panel）
- [x] 生成向导前端（`static/companion/wizard/`，多模态上传 + 一键导入）

## Phase 4 — 跨平台与商业化（已完成，遗留项转入 Phase 5）

- [x] 创意工坊 `.neko-companion` 上架（catalog + publish API + workshop UI）
- [x] 性能与 HA：生成任务 SQLite 持久化、阶段 checkpoint、失败重试 API、
      background 模式（`?background=true` + 轮询）
- [x] 实时对话接入元数据：文字/语音双 facade
      （`GET /api/companion/session/{character_name}`、
      `POST /api/companion/dialogue/session`）
- [x] Companion 向导/工坊 8 语言 i18n（`static/locales` + `companion/i18n.js`）
- [x] 开源 AI（Ollama）一键配置向导 → **Phase 5 M1 已完成**（`static/companion/ollama/`）
- [x] 移动端 Companion 同步协议 → **Phase 5 M6 已完成**（[SYNC_PROTOCOL.md](./SYNC_PROTOCOL.md)）

## Phase 5 — 深化与生态（进行中，M1–M6 已完成）

进度快照：[PHASE5_PROGRESS.md](./PHASE5_PROGRESS.md)。里程碑见 [PHASE5_PLAN.md](./PHASE5_PLAN.md)。

- [x] **M1** Ollama 配置向导（PR #9）
- [x] **M2** Avatar registry SQLite + 删除 API（PR #8）
- [x] **M3** `GET /api/companion/metrics` + 阶段耗时（`5297af8f`）
- [x] **M4** 记忆 / 人设深度集成（PR #12：`extract_fact_seeds` 语料 fact 种子、
      persona refine/apply、版本链 + 回滚）
- [x] **M5** 工坊卡片 / entry / asset API（`b90efb72`）
- [x] **M6** 移动端同步协议（PR #11：`/sync/manifest` + `/sync/memory/{name}`，
      [SYNC_PROTOCOL.md](./SYNC_PROTOCOL.md) v1.0，双桌面实例验证）
- [ ] **M7** Electron Companion Shell（P2，**下一优先**）
- [ ] **M8** 声线克隆与 TTS 深化（P2）
