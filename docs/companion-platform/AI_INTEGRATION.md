# Companion AI Integration

## 架构

`companion/ai/` 作为薄封装层，复用 N.E.K.O. 核心：

| 模块 | 封装目标 |
|------|----------|
| `memory_bridge.py` | memory server `GET /new_dialog/{lanlan_name}` |
| `persona.py` | `characters_router` 角色卡双向映射 + 注册 |
| `chat.py` | `websocket_router` 文字会话协议 + `conversation` tier + `react-neko-chat` |
| `realtime_voice.py` | `websocket_router` 语音会话协议 + `realtime` tier / `api_type` |
| `runtime.py` | 两个对话 facade 共用的运行时解析（config manager / live session / 脱敏投影） |
| `tts_bridge.py` | `utils/tts/` 多 provider |
| `bootstrap.py` | 从 GenerationArtifact 写入记忆种子（persona seeds） |

## 记忆种子初始化（Phase 3）

`bootstrap.py` 通过 `memory.persona.manager.PersonaManager.aadd_fact` 把
`.neko-companion` 包 manifest 里的 `memory_seeds` 逐条写入 persona 记忆
（矛盾检查 + 角色级锁 + 原子写 `persona.json`），不重复造文件格式：

- **manager 解析**：单进程架构下优先复用 memory_server 的**在跑实例**
  （`app.memory_server.runtime.persona_manager`），保证其内存缓存与写入一致；
  memory 子系统未启动时（单测 / 独立工具）回退到独立 `PersonaManager`，
  写同一份磁盘文件，服务器下次加载 / `/reload` 时可见。
- **entity 映射**：种子 `entity ∈ {master, neko, relationship}`，未知实体
  归入 `neko`；每条种子落盘 `source="companion_seed"`，与对话沉淀事实可区分。
- **入口**：
  - `seed_memory(character_name, seeds)` — 核心写入；
  - `bootstrap_from_artifact(profile, artifact)` — 从生成产物读 manifest 后写入
    （async，`CompanionAI.bootstrap_from_generation` 同步跟进为 async）。

## 角色卡双向映射（Phase 3）

`persona.py` 的 `CompanionPersonaBridge` 与 `characters.json` 的
`猫娘.<档案名>` 卡片互转：

- `to_character_card()` — 昵称、自定义字段（`metadata["card_fields"]`）走平铺，
  `system_prompt` / `voice_id` / `avatar.model_type` / `avatar.live2d.model_path`
  经 `utils.config_manager.set_reserved` 落 `_reserved`（与 characters_router
  产出的卡片形状一致）。
- `from_character_card(name, card)` — 经 `get_reserved` 读取，兼容旧版平铺字段
  （`system_prompt` / `voice_id` / `model_type` / `live2d`）。
- `register_character_card(profile)` — 校验档案名（复用
  `utils.character_name.validate_character_name`）、Windows 风格冲突改名
  （`name(1)`）后写入 characters.json，返回**最终档案名**——调用方必须用它
  （而非 `profile.name`）作为记忆角色名。

## 导入端点（Phase 3）

`POST /api/companion/import`：

```json
{
  "package_path": "/path/to/pkg.neko-companion",
  "register_character": true,
  "bootstrap_memory": true,
  "load_avatar": true,
  "activate_avatar": true
}
```

流程：读 manifest → 注册角色卡 → 以**最终档案名**为 key 写入记忆种子 →
best-effort 注册/激活包内 Live2D avatar（缺失不致命，回 `avatar_error`）→
best-effort 通知 memory server `/reload`。

## 实时文字/语音对话接入（Phase 4）

### 调研结论：对话通道只有一条

N.E.K.O. 的文字与语音对话共用**同一条**按角色划分的 WebSocket
（`main_routers/websocket_router.py` 的 `/ws/{lanlan_name}`），差异只在
`start_session` 的 `input_type`：

- **文字**：`{"action": "start_session", "input_type": "text"}` →
  `{"action": "stream_data", "input_type": "text", "data": "..."}`。
  聊天 UI 唯一实现 `frontend/react-neko-chat`（构建为
  `neko-chat-window.iife.js`）经 `static/app/app-buttons.js` /
  `app-websocket.js` 走的就是这套协议——companion 角色一经注册即复用同一
  聊天窗口，无需新 UI。
- **语音**：`{"action": "start_session", "input_type": "audio"}` →
  `stream_data` 携带麦克风采样数组（`static/app/app-audio-capture.js`）。
  后端 session manager（`main_logic/core`）把帧转发给 realtime provider
  client（`main_logic/omni_realtime_client`）。

Provider 一律走 tier（neko-guide：不 hardcode 模型）：文字 =
`get_model_api_config('conversation')`；语音 =
`get_model_api_config('realtime')`，其生效 `api_type` 与
`main_logic/core/lifecycle.py` 的 `core_api_type` 同源——realtime tier 自带
`api_type` 优先，否则回退 `CORE_API_TYPE`。

### 可调用 facade

`chat.py` 的 `CompanionChatBridge` 与 `realtime_voice.py` 的
`CompanionRealtimeVoiceBridge` 结构对偶（共用 `runtime.py` 的解析 helper），
均暴露：

- `character_name` / `websocket_url()` — 角色路由（`/ws/{角色名}`）；
- `provider_config(config_manager=None)` — 对应 tier 的**脱敏**配置
  （`model` / `base_url` / `is_custom` / `has_api_key`，绝不外泄
  `api_key`；语音侧另含 `api_type`）；不传 config manager 时回退全局
  `utils.config_manager.get_config_manager()`，不可达时安全降级为空配置；
- `start_session_message()` / `end_session_message()` 及
  `text_message(text)`（文字）/ `audio_chunk_message(samples)`（语音）—
  与 `websocket_router` 逐字段一致的待发送协议帧；
- `session_metadata(config_manager=None)` — 上述信息的聚合快照。

facade **不自行开 socket**：会话生命周期仍由 `websocket_router` + session
manager 独占管理，保持最小侵入。

### 会话元数据端点

`GET /api/companion/session/{character_name}` 聚合两个 facade：

```json
{
  "character_name": "小柚",
  "websocket_url": "/ws/小柚",
  "runtime": {"available": true, "session": {"registered": true, "connected": false}},
  "chat": {"provider": {"tier": "conversation", "model": "...", "has_api_key": true}, "protocol": {...}},
  "realtime_voice": {"provider": {"tier": "realtime", "api_type": "qwen", ...}, "protocol": {...}}
}
```

主服务器运行时（shared_state 已初始化）：未注册角色返回 404（与
`websocket_router` 连接时的检查一致），`runtime.session` 给出
live 状态；单测 / 独立工具环境降级为 `runtime.available = false` 的
纯元数据模式。tier 解析涉及同步读 `core_config.json`，端点内经
`asyncio.to_thread` offload，遵守单进程零阻塞规范。

## 开源 AI

Phase 2 将在 `open_source.py` 增加 Ollama 路由；当前通过
`config/api_providers.json` 配置本地 endpoint。
