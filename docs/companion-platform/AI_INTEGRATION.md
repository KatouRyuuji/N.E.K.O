# Companion AI Integration

## 架构

`companion/ai/` 作为薄封装层，复用 N.E.K.O. 核心：

| 模块 | 封装目标 |
|------|----------|
| `memory_bridge.py` | memory server `GET /new_dialog/{lanlan_name}` |
| `persona.py` | `characters_router` 角色卡双向映射 + 注册 |
| `chat.py` | ChatCompletion / `react-neko-chat` 会话角色名 |
| `realtime_voice.py` | `websocket_router` Realtime API |
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

## 开源 AI

Phase 2 将在 `open_source.py` 增加 Ollama 路由；当前通过
`config/api_providers.json` 配置本地 endpoint。
