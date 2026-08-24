# Companion Platform Roadmap

## Phase 1 — 基础骨架（当前）

- [x] 架构文档与差距分析
- [x] `companion/models` 数据模型
- [x] Generator Pipeline 骨架 + 任务 API
- [ ] 并行 Agent：生产力 / Avatar / AI Facade

## Phase 2 — 核心能力封装

- [ ] `companion/ai/` 记忆/人设/对话/TTS 统一 Facade
- [ ] `companion/avatar/` 形象注册表与热替换
- [ ] Generator 各阶段接入真实 LLM（替换 mock）
- [ ] `.neko-companion` 导入/导出端到端

## Phase 3 — 生产力与体验

- [ ] 番茄钟 / Todo / 备忘 UI 面板
- [ ] 多媒体状态监测与 Avatar 联动
- [ ] 特效/装饰配置与 Live2D 表情联动
- [ ] 生成向导前端（`static/companion/wizard/`）

## Phase 4 — 跨平台与商业化

- [ ] 移动端 Companion 同步协议
- [ ] 创意工坊 `.neko-companion` 上架
- [ ] 开源 AI（Ollama）一键配置向导
- [ ] 性能与 HA：任务队列持久化、失败重试、监控指标
