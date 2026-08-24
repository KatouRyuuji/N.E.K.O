# Companion Platform Roadmap

> 状态基准：Phase 4 集成已完成（分支 `cursor/companion-phase4-integration-3e93`）。
> 后续规划见 [PHASE5_PLAN.md](./PHASE5_PLAN.md)。

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
- [ ] 移动端 Companion 同步协议 → **转入 Phase 5（P1）**
- [ ] 开源 AI（Ollama）一键配置向导 → **转入 Phase 5（P0）**
      （检测/路由已在 Phase 2 落地：`companion/generator/open_source.py`、
      `companion/ai/open_source.py` + `GET /api/companion/ai/open-source`；
      缺的是引导 UI）

## Phase 5+ — 深化与生态（规划中）

优先级、里程碑与验收标准见 [PHASE5_PLAN.md](./PHASE5_PLAN.md)。主题包括：
Ollama 配置向导、监控与指标、记忆/人设深度集成、工坊市场体验、
移动端同步、Electron Companion Shell。
