# Gap Analysis: 10 项必达功能

> 更新于 Phase 4 集成完成后。「Companion 侧现状」列反映 `companion/` 包与
> `static/companion/` 前端的实际实现；「剩余缺口」是 Phase 5+ 的输入
> （详见 [PHASE5_PLAN.md](./PHASE5_PLAN.md)）。

| # | 功能 | N.E.K.O. 底座 | Companion 侧现状（Phase 4 后） | 剩余缺口 | 优先级 |
|---|------|----------|------|------|--------|
| 1 | 长期记忆 | 五维记忆系统 (`memory/`) | `memory_bridge.py` 桥接 + `bootstrap.py` 记忆种子写入（复用在跑 `PersonaManager`，导入后通知 `/reload`） | 生成语料 → fact/reflection 层的深度种子；跨设备记忆同步 | P1 |
| 2 | 人设扮演 | 角色卡、`utils/prompt_state/` | `persona.py` 与 characters.json 双向映射 + 冲突改名注册 | 生成人设的迭代式微调 UI；人设版本管理 | P1 |
| 3 | TTS | `utils/tts/` 多 provider | `tts_bridge.py` 声线配置 + `voice_mapping.py` 参考音频映射 + `/tts/preview` | 参考音频真实声线克隆（当前为映射启发式） | P2 |
| 4 | 实时语音对话 | Realtime API、`websocket_router` | `realtime_voice.py` facade：协议帧 + `realtime` tier 脱敏配置 + session 元数据 API | 无（facade 完成；语音全链路由核心承担） | — |
| 5 | 实时文字对话 | ChatCompletion、`react-neko-chat` | `chat.py` facade：协议帧 + `conversation` tier + `POST /dialogue/session` | 无（facade 完成；聊天 UI 复用 react-neko-chat） | — |
| 6 | 番茄钟/Todo/备忘/音乐/多媒体 | `music_router`、`jukebox_router` | `productivity/` 全套（SQLite 持久化）+ 面板 UI + 伴侣联动 hook | 番茄钟完成时的主动对话触发深度联动；OS 级媒体监测 | P2 |
| 7 | 特效和装饰 | Avatar UI、表情联动 | effects schema + `/avatar/effects` API + effects panel | 特效持久化到包 manifest；更多装饰类型 | P2 |
| 8 | Live2D 集成 | `live2d_router`、参数编辑器 | 包内 L2D 资源经 `/avatar/{id}/resource/{path}` 直出（pixi 相对路径可解析） | 无（自包含包 + 资源服务完成） | — |
| 9 | 形象热替换 | `model_manager`、多格式切换 | `AvatarRegistry` + swap panel + 一键导入激活 | registry 进程内存态 → 持久化（重启后需重导入） | P1 |
| 10 | 开源 AI + 程序化生成 | `config/api_providers.json` | 生成 Pipeline 7 阶段（LLM 三级降级）+ SQLite HA + 重试 + workshop 上架 | Ollama 一键配置**向导 UI**（检测/路由已有）；生成质量评估 | P0 |

## 覆盖率摘要（Phase 4 后）

- **已交付**：10 项功能全部有可用实现；其中 #4、#5、#8 无剩余缺口。
- **深化项**（Phase 5 输入）：#10 Ollama 向导 UI（P0）、#1 记忆深度种子、
  #9 avatar registry 持久化（P1）、#3/#6/#7 体验增强（P2）。
- **横向缺口**（不属于单项功能）：移动端同步协议、运行监控/指标、
  Electron Companion Shell——见 [PHASE5_PLAN.md](./PHASE5_PLAN.md)。
