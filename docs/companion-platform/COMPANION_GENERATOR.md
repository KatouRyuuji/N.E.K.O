# Companion Generator Pipeline

## 输入 Schema (`GenerationInput`)

| 字段 | 类型 | 说明 |
|------|------|------|
| `corpus_text` | `str?` | 语料文本（聊天记录、小说片段等） |
| `corpus_files` | `list[str]?` | 语料文件路径 |
| `system_prompt` | `str?` | 用户提供的提示词 |
| `live2d_model_id` | `str?` | 已有 Live2D 模型 ID |
| `live2d_package_path` | `str?` | 上传的 L2D 包路径 |
| `reference_images` | `list[str]?` | 参考图路径（人设/外观） |
| `reference_audio` | `list[str]?` | 参考音频（声线） |
| `reference_video` | `list[str]?` | 参考视频（动作/表情） |
| `companion_name` | `str` | 目标伴侣名称 |
| `locale` | `str` | 默认 `zh-CN` |

## Pipeline 阶段

1. **ingest** — 校验输入、落盘临时资源
2. **analyze_corpus** — 语料分析（人设关键词、说话风格、关系设定）
3. **extract_persona** — 生成 system prompt + 角色卡字段
4. **configure_avatar** — 绑定 Live2D / 参考图元数据
5. **configure_voice** — 映射 TTS 声线（provider + voice_id）
6. **init_memory** — 写入记忆种子（persona 初始条目）
7. **package** — 打包 `.neko-companion` manifest + 资源

## 任务状态机

`pending` → `running` → `completed` | `failed`

每阶段可独立重试；任务 ID 全局唯一（UUID）。

## 输出 Artifact

见 `companion/models/manifest.py` 中 `CompanionManifest`。包结构：

```
<name>.neko-companion/
├── manifest.json
├── persona/
│   └── character.json
├── avatar/
│   └── live2d/...
├── memory/
│   └── seeds.json
└── voice/
    └── config.json
```
