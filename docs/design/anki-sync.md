# Anki 同步设计

本设计连接两个不同模型：Vocabry 保存内容、历史和当前 HTML；Anki 保存 Note、由 Note 生成的复习 Card，以及复习排程。Add-on 负责适配 Anki API，不复制 Vocabry 的领域规则。

## 身份映射

专用 Anki Note Type 名为 `Vocabry`，字段固定为：

```text
ExternalCardId, Front, Back
```

模板用 `Front` 作为问题面，用 `FrontSide`、分隔线和 `Back` 作为答案面，因此每个 Note 生成一张 Anki Card。

`ExternalCardId` 保存 `card_id`，是跨数据库的稳定身份。服务端 `anki_note_mappings` 保存最近 ack 的 `note_id`、revision 和同步状态；Add-on config 另存 `managed_cards[card_id] = {note_id, revision}` 与事件 cursor。

同一活动 Card 不应产生多个受管 Note。应用创建事件前，Add-on 先按 `ExternalCardId` 搜索已有 Note；事件重复投递因此可以更新同一 Note，而不是再次创建。

## Vocabry 到 Anki

Card 的每个 revision 都产生 outbox event。Add-on WebSocket 收到事件后：

- `card.created` / `card.updated`：查找 Note；不存在则创建，存在则覆盖 `Front` 与 `Back`；
- `card.deleted`：删除找到的 Note，并移除本地 managed state；
- 应用成功后发送 ack，其中包含 event ID、note ID 和状态；
- 服务记录 mapping 并推进该客户端连续 cursor。

Add-on 使用 `_applying` 集合标记自己正在写入的 Card，避免 `note_will_flush` 把同一次远端更新回送成用户编辑。这个标记只在内存中存在，崩溃边界尚未验证。

## Anki 到 Vocabry

`note_will_flush` 观察受管 Note。若它有已知 managed state 且不是 Add-on 自己正在应用：

1. 读取当前 `Front` 与 `Back`；
2. 带 managed revision 调用 `POST /api/v1/anki/changes`；
3. 服务保存 `html_origin=anki_manual` 的新 revision；
4. 回调成功后更新 Add-on config 中的 revision。

Anki 操作完成后，Add-on 扫描 managed note ID。找不到的 Note 被作为 `deleted` 回传；成功后从 managed state 移除。

当前回写只处理 HTML 和删除，不把 Anki 的 deck、tag、模板或排程写入 Vocabry。

## 冲突语义

Vocabry 以服务提交顺序定义当前版本，不比较 Anki 与服务进程的墙上时钟：

- Anki HTML 回写提交后，手工 HTML 成为当前版本；
- 后续结构化字段编辑提交后，renderer HTML 成为当前版本；
- 再次发生 Anki 编辑时，又产生新的手工版本。

每次回写必须匹配 `expected_revision`。当前 Add-on 遇到冲突只显示警告，没有自动读取、比较和重试。因此不会静默覆盖，但用户编辑可能暂时没有同步，需要未来的冲突恢复 UX。

## 连接与重放

Add-on profile 打开后连接 WebSocket，使用 config 中的 cursor。断线 3 秒后重连，每 10 秒发送 ping。事件应用成功后先发送 ack，然后立即把 event ID 写入 config。

WebSocket 与持久 cursor 的目标语义是“至少一次投递、幂等应用、成功后推进连续前缀”。当前代码实现了基本重复安全，但仍有崩溃窗口：

- Anki 已写入、ack 尚未发送：事件会重放，按 `ExternalCardId` 找到 Note 后覆盖，通常安全。
- ack 已发送、Add-on config 尚未写 cursor：服务端 cursor 已前进，但重连 query 可能仍旧；API 当前没有统一两者。
- Add-on config 写 cursor、服务尚未持久 ack：客户端 cursor 可能领先服务端。

修复时应让服务端持久 cursor 成为恢复事实源，客户端 cursor 只作提示，或设计显式握手；不要继续添加双方各自推进的隐式状态。

## 当前未实现的对账

`POST /api/v1/sync/reconcile` 只返回 `{"status":"scheduled"}`，没有调度任务。当前 Add-on 也没有调用全量 mapping API 来修复 note ID 漂移。

旧设计曾描述“重连时先提交离线变化、再增量对账”和“只发现 Note 缺失时标为 missing”，这些都不是当前行为：

- 没有持久的离线编辑队列；服务不可用时 note flush 只显示失败，之后是否再次触发取决于 Anki 行为。
- 删除扫描无法可靠区分用户删除、note ID 漂移和其他缺失原因，当前一律提交 deleted。
- API 支持 `kind=missing`，但 Add-on 当前不发送它。

在把 Add-on 称为可靠双向同步前，必须补全这些能力。

## Anki 线程与兼容性

网络回写使用 `mw.taskman.run_in_background`，collection 变更发生在 WebSocket Qt 回调和 GUI hooks 中。是否符合目标 Anki 版本的线程约束尚未通过真实环境测试。

`note_will_flush` 导入失败时插件会静默跳过编辑 hook；这保持了可加载性，但可能让用户误以为双向同步正常。正式版本应检测能力并明确显示降级状态。

需要真实 Anki 验证：Note Type 创建、deck API、搜索语法、Note flush hook、删除检测、WebSocket 生命周期、profile 切换和 Add-on 卸载/升级。

## 修改同步代码的检查清单

- 重复同一 `(card_id, revision)` 不会创建第二个 Note。
- 只有 Anki 写入成功后才 ack。
- Add-on 自己的写入不会回声回传。
- revision conflict 不会被盲目强制覆盖。
- 删除、missing 与 note ID 漂移有明确不同语义。
- 任一持久状态只存在一个恢复事实源。
- 真实 Anki 主线程与 collection 约束有测试证据。
