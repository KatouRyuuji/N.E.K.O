# 开发指南

Project N.E.K.O. 是包含形象渲染、实时/文本交互、持久记忆、Agent 执行与插件的开源 AI 伴侣平台。本站面向当前仓库的贡献者和集成者，不是价格、额度或 Provider 能力宣传页。

主要边界包括 `app/` 的 Python 3.11 服务、`main_logic/` 与 `memory/`、`brain/`、Jinja/static + 共享 React 聊天、Vue plugin manager、N.E.K.O.-PC Electron shell，以及 `docker/`。

## 使用前评估 N.E.K.O

| 买家问题 | 说明页 |
| --- | --- |
| 应用是否免费，AI 服务还可能产生哪些费用？ | [费用与 Provider](./cost-and-providers) |
| 能否完全离线运行？ | [本地与离线边界](./local-and-offline) |
| 对话和记忆可能发送到哪里？ | [技术数据流与隐私控制](./data-and-privacy) |
| 应该选择哪个安装渠道？ | [Steam、GitHub Releases 或源码](./install-options) |

## 开发入口

| 目标 | 页面 |
| --- | --- |
| 检查工具 | [前置条件](./prerequisites) |
| 配置环境 | [开发环境搭建](./dev-setup) |
| 首次运行 | [快速开始](./quick-start) |
| 浏览仓库 | [项目结构](./project-structure) |
| 理解服务 | [架构](/zh-CN/architecture/) |
| 开发插件 | [插件快速开始](/zh-CN/plugins/quick-start) |
| 部署 | [部署](/zh-CN/deployment/) |

## Companion Platform（虚拟伴侣平台）

Companion Platform（`companion/` 包，Phase 4 已集成）把语料、提示词与参考素材加工为可导入的 `.neko-companion` 包，并运行在 N.E.K.O. 核心之上。设计文档见仓库内 `docs/companion-platform/`。

- **生成向导** — `/static/companion/wizard/index.html`：多模态上传（语料 / 参考图 / 音频 / 视频 / Live2D 包）、7 阶段进度、一键「导入为角色」。
- **创意工坊页** — `/static/companion/workshop/index.html`：浏览本地已发布的 `.neko-companion` 目录，并可将已完成的生成任务发布上架。
- **API** — 全部位于 `/api/companion/*` 前缀（不带末尾斜杠）：`GET /api/companion/health`、生成（`POST /api/companion/generate`、`POST /api/companion/generate/upload`）、导入（`POST /api/companion/import`）、形象热替换（`/api/companion/avatar/*`）、生产力（`/api/companion/productivity/*`）、工坊（`GET /api/companion/workshop/catalog`、`POST /api/companion/workshop/publish/{task_id}`）。
- **对话会话** — `GET /api/companion/session/{character_name}` 返回文字 + 实时语音的聚合会话元数据（websocket 路由、脱敏 provider tier、协议帧）；`POST /api/companion/dialogue/session` 由 companion profile 生成双通道 connect info。
- **长任务生成** — 生成端点支持 `?background=true`（立即返回 `202`，轮询 `GET /api/companion/generate/{task_id}`）；失败任务经 `POST /api/companion/generate/{task_id}/retry` 从失败阶段恢复——已完成的 LLM 阶段不会重跑。
- **本地开源 AI 状态** — `GET /api/companion/ai/open-source` 探测本地 Ollama daemon（`OLLAMA_HOST`，默认 `http://127.0.0.1:11434`），返回可用性与解析出的模型 / base-URL 路由配置；未配置云端 key 时，生成 Pipeline 会自动降级到该路由（启发式为最终兜底）。

所有 Python 示例都使用 `uv run`。若文档与同 revision 的入口、loader 或 workflow 冲突，以当前代码为准并报告文档漂移。
