# 数据模型与事务

本文记录 Card 状态机和 SQLite 表之间的关系。字段的最终事实源仍是 `src/vocabry/database.py` 中的 `SCHEMA`。

## Card 当前态

`cards` 每行保存一张卡的当前快照：

| 字段组 | 含义 |
|---|---|
| `card_id` | 创建时生成的 UUID；永久稳定 |
| `card_type`, `schema_version` | 卡型与字段 schema 版本 |
| `structured_fields` | JSON：`word`、`phonetic`、`definition`、`example`、`notes` |
| `front_html`, `back_html` | 当前交付给预览器和 Anki 的 HTML |
| `html_origin` | `renderer` 或 `anki_manual` |
| `renderer_version`, `render_input_hash` | 自动渲染版本与输入摘要 |
| `revision` | 单卡单调递增的乐观并发版本 |
| 时间戳 | 创建、最后更新和软删除时间 |

代码当前生成 UUIDv4，不应把旧文档中“建议 UUIDv7”的内容当成契约。`structured_fields` 存为 JSON text；改变字段集合时必须同时考虑旧行解析、API、导入文件和 Anki 当前 HTML。

## 卡型与渲染

第一版支持 `standard_definition`（正面为单词和例句）与 `single_definition_word`（正面仅单词）。两种卡型的背面都包含非空的单词、音标、释义、例句和备注。

`word`、`definition` 必填，所有字段必须是字符串。renderer 先 HTML 转义，再把换行变成 `<br>`；相同输入必须产生相同 HTML 和 input hash。

新增卡型或字段不是只改一个常量：还要定义旧数据兼容、渲染结果、API schema、离线格式以及 Add-on 是否仍只需要 `Front`/`Back`。

## HTML 状态机

```text
创建 / 结构化编辑 ──render──> html_origin=renderer
                                  │
                         Anki 修改 Front/Back
                                  ▼
                         html_origin=anki_manual
                                  │
                         后续结构化字段编辑
                                  ▼
                         html_origin=renderer
```

必须保留的行为：

- Anki HTML 回写只改 `front_html` / `back_html`，不反向改结构化字段。
- 结构化字段变化会重新渲染并覆盖当前手工 HTML。
- renderer 维护任务只选择 `html_origin=renderer` 且版本陈旧的活动卡；手工 HTML 不参与批量升级。
- 任何真正改变当前状态的操作都增加 revision 并写历史与 outbox。
- 内容完全相同的结构化编辑、HTML 回写或重复删除不增加 revision。

## 历史与 outbox

`card_revisions` 保存每个 revision 变更后的完整快照、来源、原因和服务端提交时间。历史当前只读，没有恢复接口。

`outbox_events` 保存同一 revision 的同步事件。`UNIQUE(card_id, revision)` 保证一个 revision 只产生一个事件。创建、修改、重渲染、Anki HTML 回写与删除都应通过 `_record_change` 在修改 Card 的同一事务中写入历史和 outbox。

这个同事务关系是最重要的数据约束之一。若未来引入后台发布器，可以改变事件投递方式，但不能先提交 Card、再“尽力”补写事件。

## 软删除

首次删除设置 `deleted_at`、增加 revision、保存快照并发布 `card.deleted`。默认列表隐藏已删除卡；按 ID 查询当前仍可返回墓碑。重复删除返回当前快照，不产生新版本。

当前没有恢复、物理清理或墓碑保留策略。实现这些能力前必须先定义对历史与 Anki 已确认删除的影响。

## 来源与导入任务

`card_sources` 仅用于记录导入来源：job ID、行号、生成器名称/版本和 manifest 的 source JSON。来源不参与去重，同一内容重复导入会得到新的 Card。

`import_jobs` 记录 job 的状态、manifest、接受数量和结果。job ID 是永久幂等边界，处理过的 ID 不能复用。

## 客户端与同步辅助表

- `api_clients` 保存客户端元数据和 SHA-256 token hash，不保存明文 token。
- `pairing_codes` 保存一次性 code hash、过期时间和使用时间。
- `preview_sessions` 保存短时 session hash、允许访问的 card ID 和过期时间。
- `idempotency_keys` 按 `(client_id, key)` 缓存创建请求 hash 与响应。
- `anki_note_mappings` 保存 Anki `note_id`、已推送 revision 与状态；`note_id` 唯一。
- `client_cursors` 保存每个客户端已连续 ack 的全局事件 ID。

这些表和 outbox 当前都没有清理机制。新增清理任务前要定义 retention，不能删除仍用于请求重放判断或同步恢复的数据。

## SQLite 生命周期

当前 `Database` 每个服务实例打开一个 `check_same_thread=False` 连接，用进程内 `RLock` 和 `BEGIN IMMEDIATE` 串行化写事务，并启用 foreign keys、WAL 和 5 秒 busy timeout。启动时执行 `CREATE TABLE IF NOT EXISTS`。

当前没有迁移框架、schema 版本迁移、单实例锁、备份或恢复流程。修改 `SCHEMA` 时不能假设 `CREATE TABLE IF NOT EXISTS` 会升级已有表；在做第一个不兼容 schema 变更前必须先引入迁移策略。
