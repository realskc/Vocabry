# Anki 同步设计

本设计连接两个不同模型：Vocabry 保存内容、历史和当前 HTML；Anki 保存 Note、由 Note 生成的复习 Card，以及复习排程。Add-on 负责适配 Anki API，不复制 Vocabry 的领域规则。

## 身份映射

专用 Anki Note Type 名为 `Vocabry`，字段固定为：

```text
VocabryDatabaseId, ExternalCardId, Front, Back
```

模板用 `Front` 作为问题面，用 `FrontSide`、分隔线和 `Back` 作为答案面，因此每个 Note 生成一张 Anki Card。

`VocabryDatabaseId` 保存数据库首次创建时生成、随数据库文件永久保留的 UUID；`ExternalCardId` 保存该库中的 `card_id`。二者共同组成 Note 的稳定身份。服务端 `anki_note_mappings` 保存最近 ack 的 `note_id`、revision 和同步状态；Add-on config 另存 `managed_cards[card_id] = {note_id, revision}` 与事件 cursor。升级前创建的三字段 Note Type 会自动增加 `VocabryDatabaseId`；字段为空的旧 Note 只会在全量对账中按卡片 ID 归属到当前数据库。

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

Add-on 还会在后台轮询待处理的全量对账任务。`vocabd` 未运行或正在关闭属于正常的暂时离线状态：轮询连接被拒绝时不显示“全量对账失败”，而是等待后续轮询。只有服务可达后出现的对账协议、数据或 collection 执行故障才向用户报告为对账错误。

Anki 的“工具”菜单包含一个不可点击的 Vocabry 状态项，显示未配对、正在连接、已连接、未运行或连接失败。状态来自 WebSocket 信号：连接成功才显示已连接；连接拒绝、远端关闭和超时显示未运行；其他 socket 错误显示连接失败。状态变化不弹窗，也不占用 Anki 状态栏。

### 配对与数据库身份

Anki token、客户端 cursor 和 `managed_cards` 只能与签发 token 的那一个 Vocabry 数据库一起使用。GUI 使用新的数据目录或数据库重建后，旧 token 会被认证拒绝；即使新服务恰好也从 event 1 开始，旧 cursor 也不能沿用。

GUI 首页通过 admin API 生成一次性配对码。配对响应同时返回 `database_id`。Add-on 交换成功后必须把本地 cursor 设为 0，并清空旧 `managed_cards`，再建立 WebSocket。这个重置让新服务从自己的事件起点重放，同时避免把旧数据库中的 Note mapping 当作新数据库状态。旧 Anki Note 不会在配对时自动删除，可由全量对账识别和清理。

服务日志出现连续 WebSocket `403` 时，优先检查 token 是否来自当前数据库，而不是假设 outbox 没有产生事件。

WebSocket 与持久 cursor 的目标语义是“至少一次投递、幂等应用、成功后推进连续前缀”。当前代码实现了基本重复安全，但仍有崩溃窗口：

- Anki 已写入、ack 尚未发送：事件会重放，按 `ExternalCardId` 找到 Note 后覆盖，通常安全。
- ack 已发送、Add-on config 尚未写 cursor：服务端 cursor 已前进，但重连 query 可能仍旧；API 当前没有统一两者。
- Add-on config 写 cursor、服务尚未持久 ack：客户端 cursor 可能领先服务端。

修复时应让服务端持久 cursor 成为恢复事实源，客户端 cursor 只作提示，或设计显式握手；不要继续添加双方各自推进的隐式状态。

## 全量对账

GUI 的“全量对账 Anki”创建一个持久化对账任务。Add-on 每两秒检查待办命令，并枚举当前 profile 中 Note Type 为 `Vocabry`、且 `ExternalCardId` 非空的全部 Note。vocabd 将盘点结果分类为：当前数据库的活动卡片、已删除卡片残留、未知卡片 ID、其他数据库 Note、旧版无数据库 ID Note，以及同一身份的重复 Note。

对账采用扫描与执行分离的两阶段流程：

1. Add-on 只提交 inventory，不修改 collection；
2. GUI 展示补建、归属迁移、重复、孤立和跨数据库 Note 的数量；
3. 用户拒绝则任务取消，不修改 Anki；
4. 用户确认后，Add-on 更新或补建所有活动卡片，给可归属的旧 Note 写入当前 `database_id`，并删除报告中的残留 Note；
5. Add-on 回报最终 note ID，vocabd 重建 mapping 并把任务标为 completed。

其他数据库 Note 只会在报告明确计数且用户确认后删除。全量对账以 Anki Note 为单位，不以模板生成的复习 Card 为单位。任务状态保存在 SQLite，GUI 或 Anki 暂时关闭不会让任务消失。

当前仍没有持久的离线编辑队列；服务不可用时 note flush 失败后是否再次触发取决于 Anki 行为。增量删除扫描也仍只覆盖 `managed_cards`，全量对账是修复其遗漏与 note ID 漂移的显式操作。

## Anki 线程与兼容性

网络回写使用 `mw.taskman.run_in_background`，collection 变更发生在 WebSocket Qt 回调和 GUI hooks 中。是否符合目标 Anki 版本的线程约束尚未通过真实环境测试。

`note_will_flush` 导入失败时插件会静默跳过编辑 hook；这保持了可加载性，但可能让用户误以为双向同步正常。正式版本应检测能力并明确显示降级状态。

需要真实 Anki 验证：Note Type 创建、deck API、搜索语法、Note flush hook、删除检测、WebSocket 生命周期、profile 切换和 Add-on 卸载/升级。
