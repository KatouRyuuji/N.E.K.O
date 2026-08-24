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
2. **analyze_corpus** — 语料分析（人设关键词、说话风格、关系设定）——**真实 LLM**（Phase 2）
3. **extract_persona** — 生成 system prompt + 角色卡字段——**真实 LLM**（Phase 2）
4. **configure_avatar** — 绑定 Live2D / 参考图元数据
5. **configure_voice** — 映射 TTS 声线（provider + voice_id）
6. **init_memory** — 写入记忆种子（persona 初始条目）
7. **package** — 打包 `.neko-companion` manifest + 资源；若提供了
   `live2d_package_path`，模型目录会被复制进包内 `avatar/live2d/` 并写入
   manifest `resource_paths["live2d"]` 提示，使生成结果**自包含、可直接导入**
   （路径无效时降级为纯元数据包，不失败）

## API（Phase 3）

| 端点 | 说明 |
|------|------|
| `POST /api/companion/generate` | JSON 提交（`GenerationInput`），同步跑完 pipeline 后返回任务 |
| `POST /api/companion/generate/upload` | **multipart/form-data** 多模态提交（见下） |
| `GET /api/companion/generate` | 任务列表 |
| `GET /api/companion/generate/{task_id}` | 任务详情（完成后含 `artifact`） |
| `GET /api/companion/generate/{task_id}/manifest` | 下载生成的 manifest.json |
| `POST /api/companion/generate/{task_id}/import` | **一键导入为角色**：把生成包注册进 avatar 热替换注册表 |

### 多模态上传（`POST /generate/upload`）

表单字段：`companion_name`（必填）、`locale`、`corpus_text`、`system_prompt`、
`live2d_model_id`、`live2d_package_path`；文件字段（均可多文件）：
`corpus_files`、`reference_images`、`reference_audio`、`reference_video`。

- 文件持久化在 `<docs>/N.E.K.O/companions/uploads/<session uuid>/<类别>/` 下，
  文件名做 basename 化 + 白名单字符清洗（防路径穿越），加 `NN_` 序号前缀防重名；
- 可解码的文本语料文件（`.txt/.md/.json/.jsonl/.csv/...`）会与内联 `corpus_text`
  合并后送入 analyze_corpus，其余文件仅按路径挂到 `GenerationInput` 上；
- 防御性上限（`config/companion_settings.py`）：单文件
  `COMPANION_UPLOAD_MAX_FILE_BYTES`（100 MB）、单字段
  `COMPANION_UPLOAD_MAX_FILES_PER_FIELD`（20 个）、语料合并
  `COMPANION_CORPUS_FILE_MERGE_MAX_CHARS`（200k 字符）；超限整个请求返回 **413**；
- 响应：`201` + 任务公开字段 + `uploads`（session_dir 与各类别文件数）。

### 一键导入（`POST /generate/{task_id}/import`）

复用 `companion/avatar/loader.load_avatar_from_package`（与
`/avatar/load-package` 同一代码路径）：任务不存在 `404`、未完成 `409`、包内
无 Live2D 模型 `422`（此时提示用户补 `live2d_package_path` 重新生成）。成功
返回 `201` + avatar 公开字段（含 `slug` 与 `entry_url`，可直接交给 Live2D
bridge / 热替换面板）。

## 生成向导前端（`static/companion/wizard/`）

`index.html` + `wizard.js`，视觉与 productivity 面板同一套设计变量（暗色
玻璃拟态卡片）。功能：

- 基本信息（名称 / 语言 / 系统提示词）+ 内联语料 + 语料文件上传；
- 多模态参考素材上传（参考图 / 音频 / 视频）与 Live2D 模型 ID / 包路径；
- 以 `FormData` 提交 `POST /generate/upload`，按 7 个 pipeline 阶段渲染进度；
- 完成后展示任务 ID / 包路径 / 实际 LLM 路由（provider + 模型 slug + 是否降级），
  提供「查看 manifest」与「**导入为角色**」按钮（调 `/import` 端点，成功显示
  模型 slug，422 时给出补充 L2D 包路径的提示）。

## LLM 集成（Phase 2）

`analyze_corpus` 与 `extract_persona` 两个阶段通过
`utils.llm_client.create_chat_llm` 调用真实 LLM，路由按以下优先级解析：

1. **`summary` tier** — `config_manager.get_model_api_config('summary')`，与
   memory 子系统的 fact extraction / reflection 同档（模型 slug 由用户配置决定，
   不做 hardcoded 模型 fallback）。
2. **本地 Ollama** — summary tier 未配置时，`companion/generator/open_source.py`
   探测本地 Ollama（`GET /api/tags`，默认 `http://127.0.0.1:11434`），选第一个
   非 embedding 模型，走 OpenAI 兼容的 `/v1` facade。
3. **启发式 fallback** — 无任何可用 LLM 或调用失败时退回确定性的关键词启发式，
   **生成任务永不因 LLM 不可用而失败**；降级会记录在 manifest 的
   `generator_metadata.llm.degraded`。

调用约定（遵循 neko-guide 辅助 LLM 规范）：

- **不传 `temperature`**（provider 默认值）；
- 每次构造必带 **budget + timeout**：`max_completion_tokens=LLM_OUTPUT_GUARD_MAX_TOKENS`
  与 `timeout=COMPANION_GENERATOR_LLM_TIMEOUT_SECONDS`（90s，< 上游 120s hard timeout）；
- **输入 budget**：语料按 `COMPANION_CORPUS_MAX_TOKENS`（3000）HEAD+TAIL 截断，
  用户提示词种子按 `COMPANION_PROMPT_SEED_MAX_TOKENS`（800）截断，分析 JSON 回灌按
  `COMPANION_ANALYSIS_CONTEXT_MAX_TOKENS`（1200）截断。常量在 `config/companion_settings.py`。

Prompt 模板（zh / en / ja / ko / ru 五语）在 `config/prompts/prompts_companion.py`，
按 `GenerationInput.locale` 选择语言（未识别的 locale 回退英文）。

### 开源模型检测（`open_source.py`）

| 函数 | 说明 |
|------|------|
| `is_ollama_endpoint(base_url, model)` | 启发式判定（默认端口 11434 / `/ollama` 路径 / 本地地址 + 模型名含 "ollama"），与 `brain/openfang_adapter` 保持一致 |
| `detect_ollama(base_url)` | 探测本地 daemon 并列出已安装模型 |
| `resolve_ollama_api_config(base_url)` | 返回 `get_model_api_config` 形状的路由 dict（跳过 embedding 模型），无可用模型时返回 `None` |

### 生成元数据

manifest 的 `generator_metadata` 记录本次生成的实际路由：

```json
{
  "analysis": {"analysis_source": "llm", "detected_traits": ["温柔"], "...": "..."},
  "llm": {"provider": "summary", "model": "<用户配置的模型 slug>"}
}
```

`provider` 取值：`summary`（tier 路由）/ `ollama`（本地开源模型）/ `heuristic`（无 LLM）。

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
