# Companion AI Integration

## 架构

`companion/ai/` 作为薄封装层，复用 N.E.K.O. 核心：

| 模块 | 封装目标 |
|------|----------|
| `memory_bridge.py` | memory server `GET /new_dialog/{lanlan_name}` |
| `persona.py` | `characters_router` 角色卡字段 |
| `chat.py` | ChatCompletion / `react-neko-chat` 会话角色名 |
| `realtime_voice.py` | `websocket_router` Realtime API |
| `tts_bridge.py` | `utils/tts/` 多 provider |
| `bootstrap.py` | 从 GenerationArtifact 初始化记忆种子 |

## 开源 AI

Phase 2 将在 `open_source.py` 增加 Ollama 路由；当前通过 `config/api_providers.json` 配置本地 endpoint。
