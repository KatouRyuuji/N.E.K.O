# Avatar / Live2D Subsystem

复用 `main_routers/live2d_router`、`static/avatar/`、`model_manager`。

## 组件

- `registry.py` — 形象注册与热替换
- `profile.py` — AvatarProfile 元数据
- `effects.py` — 特效/装饰配置 schema
- `static/companion/avatar/swap-panel.html` — 切换 UI 原型

## Live2D 桥接

前端通过 `/api/live2d/*` 加载模型；Companion 包内资源由 `loader`（Phase 2）解压到用户 Live2D 目录。
