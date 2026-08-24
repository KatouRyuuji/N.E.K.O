# Companion Platform Vision

## 定位

基于 **Project N.E.K.O.** 二次开发的跨平台虚拟伴侣平台。N.E.K.O. 提供端到端的 AI 伴侣运行时；Companion Platform 在其上增加**可编程生成、可打包分发、可模块化扩展**的伴侣工程能力。

## 核心差异化

**输入** → 语料、提示词、Live2D 形象、参考图、音频、视频  
**处理** → 程序化长任务分析（人设提取、声线映射、记忆种子、形象配置）  
**输出** → 可导入的专属虚拟伴侣包（`.neko-companion`）

## 设计原则

1. **最小侵入**：复用 `memory/`、`brain/`、`utils/tts/`、`main_routers/live2d_router` 等现有模块
2. **薄封装**：`companion/` 包作为 Facade，不重写核心对话/记忆管线
3. **跨平台**：桌面（Electron）、Web、移动端共享同一 Companion Profile 与记忆同步协议
4. **开源 AI 优先**：Ollama / 本地模型作为一等公民，与云端 API 并列

## 与 N.E.K.O. 的关系

| 层级 | 职责 |
|------|------|
| N.E.K.O. Core | 会话编排、五维记忆、Avatar 渲染、TTS、插件 SDK |
| Companion Platform | 伴侣配置模型、生成 Pipeline、生产力模块、形象热替换、统一 API |
| 用户产物 | `.neko-companion` 包、角色卡、Live2D 资源、语音包 |
