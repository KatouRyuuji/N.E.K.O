# Companion 同步协议（Phase 5 M6）

> 状态：v1.0，协议先行（[PHASE5_PLAN.md](./PHASE5_PLAN.md) M6）。移动端客户端
> **不在本里程碑**——协议用第二台桌面实例验证（见 §7）。实现：
> `companion/sync/service.py` + `companion/api/routes.py` 的 `/sync/*` 路由；
> 单测 `tests/unit/test_companion_sync_m6.py`。

## 1. 目标与范围

让另一台设备（第二台桌面实例，未来是移动端）能够：

1. **发现** 本机注册的全部 companion（人设卡 + 形象 / 声线引用）；
2. **搬运** 单个 companion——交换单元是 `.neko-companion` manifest，
   走既有 `POST /api/companion/import` 导入路径，零新格式；
3. **增量拉取** 记忆——以 memory 层已有的事实 / 时间索引做游标，
   幂等、可分页、可断点续传。

本版协议**只读**：桌面端是唯一写入方（见 §5 冲突策略），因此不需要
上行端点、不需要合并逻辑、不需要新鉴权机制。

## 2. 传输与鉴权

- 端点挂载在主服务器 `/api/companion/sync/*`（无末尾斜杠），经
  `main_routers/companion_router` 与其余 companion API 同栈。
- **鉴权沿用主服务器既有机制，不自造**：主服务器当前在局域网 /
  本机信任边界内运行，配置了何种访问控制（如反代 / 隧道 / 未来的
  token 中间件），`/sync/*` 自动继承——路由本身不新增任何凭据体系。
- 响应为 UTF-8 JSON；游标是不透明字符串，客户端只需原样回传。

## 3. `GET /api/companion/sync/manifest`

设备级快照：本机 characters.json 注册的每只猫娘（companion）一条。

```json
{
  "protocol": {
    "version": "1.0",
    "exchange_unit": ".neko-companion",
    "conflict_strategy": "desktop-authoritative"
  },
  "generated_at": "2026-08-25T12:00:00.000000",
  "companions": [
    {
      "name": "小柚",
      "manifest": { "version": "1.0", "profile": { "...": "..." }, "memory_seeds": [], "resource_paths": {}, "generator_metadata": {} },
      "memory": {
        "fact_count": 42,
        "fact_cursor": "2026-08-25T11:59:01.123456|fact_20260825115901_ab12cd34",
        "persona_digest": "sha256:…",
        "persona_entry_count": 17
      }
    }
  ]
}
```

- `manifest` 就是 `.neko-companion` 包的 `manifest.json` 形状
  （`CompanionManifest`，由角色卡经 `CompanionPersonaBridge` 反渲染），
  接收端可直接落盘成包并走 `/import`。`memory_seeds` 恒为空——种子是
  **导入期**语义，活体记忆走 §4 的增量端点，避免同一内容两条通道。
- `memory.fact_cursor` 是该角色 fact 层当前最新游标（§4.1 格式）；
  客户端拿它与本地已同步位置比较即可判断是否需要拉增量。
- `memory.persona_digest` 是 persona 层可携带视图的内容摘要（§4.3），
  用于判断 persona 快照是否需要重新拉取。

## 4. `GET /api/companion/sync/memory/{name}?since=...`

单角色记忆增量。查询参数：

| 参数 | 默认 | 说明 |
|------|------|------|
| `since` | 空 | 上次响应的 `next_cursor`（精确续传）；或纯 ISO 时间戳（按时间续传，at-least-once）；空 = 全量自举 |
| `limit` | 500 | 单页事实数上限（1–2000，越界收敛） |
| `include_persona` | false | 是否附带 persona 层完整可携带快照 |

未注册角色返回 `404`（与对话路由同源：characters.json）。

### 4.1 游标：复用 fact 层的时间索引

memory 层 fact 存储（`memory/{name}/facts.json`，`FactStore`）为每条事实
落 `created_at`（ISO，时间索引锚点，与 `time_indexed.db` 的 timestamp
索引同一时间轴）与全局唯一 `id`（`fact_<ts>_<hash8>` 等）。协议游标即：

```
next_cursor = "<created_at>|<fact_id>"
```

- 排序键 `(created_at, id)` 是**严格全序**：同一瞬间的多条事实由 id
  决出先后，分页永不丢行、永不重发（与 `timeindex.py` keyset 分页的
  `(timestamp, rowid)` 设计对偶）。
- `since` 传复合游标 ⇒ 严格大于比较，exactly-once 续传；传纯时间戳 ⇒
  等价于 `(ts, "")`，该瞬间的事实会重发（at-least-once），适合只记了
  "上次同步时间" 的粗粒度客户端。
- **幂等**：存储不变时，同一 `since` 的响应逐字节一致；用
  `next_cursor` 反复拉直到 `count == 0` 即排空，且空页会**原样回显**
  游标——继续轮询不会漂移。

### 4.2 响应

```json
{
  "name": "小柚",
  "since": "2026-08-25T11:00:00.000000|fact_20260825110000_00000000",
  "count": 2,
  "has_more": false,
  "next_cursor": "2026-08-25T11:59:01.123456|fact_20260825115901_ab12cd34",
  "facts": [
    {
      "id": "fact_20260825115900_deadbeef",
      "text": "主人喜欢抹茶拿铁。",
      "entity": "master",
      "importance": 6,
      "source": "conversation",
      "created_at": "2026-08-25T11:59:00.000001",
      "event_start_at": null,
      "event_end_at": null
    }
  ],
  "persona": { "digest": "sha256:…", "entry_count": 17 }
}
```

事实只携带**可携带字段**（id / text / entity / importance / source /
created_at / event_*）；派生缓存（embedding、token_count、refine 戳）与
本机管线状态（absorbed / signal_processed）**不出网**——接收端按自己的
硬件与管线重新计算，避免把设备相关状态当成内容同步。

### 4.3 persona 层：摘要比对的快照，而非增量

persona 条目（`persona.json`）没有逐条时间戳（id 形如 `card_*` /
`manual_<ts>_*`，但 card 来源条目无时间信息），强行造增量游标就违背
"复用已有索引" 的前提。因此 persona 走 **snapshot-on-change**：

- 每次响应都带 `persona.digest`——对可携带视图（各 entity 分节内
  条目按 id 排序、只保留 id / text / source / source_id / protected）
  做 `sha256`，与磁盘条目顺序、缓存字段无关，两台内容一致的实例
  digest 必然一致；
- 客户端 digest 不同时再带 `include_persona=true` 拉完整快照整体替换。
  persona 条目量级小（几十条），全量替换成本可忽略。

## 5. 冲突策略：桌面权威（desktop-authoritative）

二选一（桌面权威 / 最后写入胜）中选**桌面权威**，理由：

1. **写路径的不变量在桌面**。记忆写入不是裸 append：fact 层有
   SHA-256 + FTS5 语义去重（`FactStore`），persona 层有矛盾检测、
   角色卡保护、per-character 锁与事件溯源日志
   （`PersonaManager.aadd_fact` / `arecord_and_save`）。Last-write-wins
   让远端裸数据绕过这条管线直接落盘，等于放弃全部一致性检查；
   要保住检查就得在协议里复刻整条管线，远超 M6 范围。
2. **LWW 需要本协议没有的基础设施**。可信的 "最后写入" 判定要求
   跨设备时钟可比或版本向量；本地优先架构里两台桌面 / 一台手机的
   墙钟不可信，而 memory 层现有索引只有单机 `created_at`，没有
   lamport/vector clock 可复用。
3. **与产品形态一致**。移动端定位是随身**读取 + 对话**伴侣；对话产生
   的新记忆未来（后续里程碑）通过 "把对话回灌桌面、由桌面管线正常
   消化" 的方式进入记忆，而不是设备间互相覆写文件。只读协议是这个
   演进路径的第一步，且天然幂等、无合并 bug 面。

推论：客户端本地记忆只是**缓存**，与服务器分歧时无条件以桌面为准
（丢弃本地、按游标重放即可恢复，见 §4.1 幂等性）。将来若引入双写，
再升级协议版本并引入事件日志级合并——事件溯源日志（event_log）已经
存在，是天然的升级锚点。

## 6. 版本与演进

- `protocol.version` 当前 `1.0`；字段只增不改（接收端忽略未知字段）。
- 破坏性变更（游标格式、冲突策略升级）必须递增主版本号，并保持旧
  版本端点至少一个发布周期。

## 7. 双桌面实例验证流程（M6 验收）

1. 实例 A 正常使用（生成 / 导入 companion、积累记忆）。
2. 实例 B 调 `GET /sync/manifest`，为目标 companion 落一个
   `.neko-companion` 包（manifest.json 即响应中的 `manifest` 字段），
   走 `POST /api/companion/import` 完成人设 / 形象注册。
3. 实例 B 以空 `since` 全量拉 `GET /sync/memory/{name}`，之后持
   `next_cursor` 周期性增量；A 端新增事实只出现一次，重复拉取结果
   逐字节一致（幂等验收）。
4. persona 变更通过 digest 变化被 B 发现，`include_persona=true`
   拉快照整体替换。

单测 `tests/unit/test_companion_sync_m6.py` 覆盖：manifest 形状、游标
幂等 / 排空 / 分页、纯时间戳续传、可携带字段白名单、persona digest
稳定性、双实例搬运闭环与 404 路径。
