# Gap Analysis: 10 项必达功能

| # | 功能 | 现有能力 | 缺口 | 优先级 |
|---|------|----------|------|--------|
| 1 | 长期记忆 | 五维记忆系统 (`memory/`)、`GET /new_dialog/{lanlan_name}` | Companion 侧统一记忆桥接、从生成产物初始化记忆种子 | P0 |
| 2 | 人设扮演 | 角色卡、`utils/prompt_state/`、`characters_router` | Companion Profile 与角色卡双向映射 | P0 |
| 3 | TTS | `utils/tts/` 多 provider | Companion 声线配置、从参考音频映射 | P1 |
| 4 | 实时语音对话 | Realtime API、`websocket_router` | Companion Facade 封装 | P1 |
| 5 | 实时文字对话 | ChatCompletion、`react-neko-chat` | Companion Facade 封装 | P1 |
| 6 | 番茄钟/Todo/备忘/音乐/多媒体/始终 | `music_router`、`jukebox_router`、widget_mode | 统一生产力模块、番茄钟、Todo、备忘、媒体监测 | P1 |
| 7 | 特效和装饰 | Avatar UI、表情联动 | 可配置特效 schema、装饰层 | P2 |
| 8 | Live2D 集成 | `live2d_router`、参数编辑器 | Companion 包内 L2D 资源加载 | P0 |
| 9 | 形象热替换 | `model_manager`、VRM/MMD/PNG 切换 | 注册表 + 一键切换 API | P1 |
| 10 | 开源 AI + 程序化生成 | `config/api_providers.json`、Agent 系统 | 生成 Pipeline、Ollama 路由、`.neko-companion` 规范 | P0 |

## 覆盖率摘要

- **已有（可直接复用）**：约 60%（记忆、对话、TTS、Live2D、音乐）
- **需薄封装**：约 25%（Companion Facade、API 聚合）
- **需新建**：约 15%（生成 Pipeline、生产力套件、特效配置、伴侣包格式）
