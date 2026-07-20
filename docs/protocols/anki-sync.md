# Anki 同步协议

> 状态：v1 设计契约，目标 Anki 版本的 hook 能力仍待实测。关联不变量：`SYNC-001` 至 `SYNC-004`。

## 身份映射

一张本地 Card 对应一个受管 Anki Note，第一版该 Note 只生成一张复习卡。Note Type 至少包含：

```text
ExternalCardId, Front, Back
```

`ExternalCardId` 是本地稳定 ID，也是 Anki ID 丢失后的重新识别依据。数据库保存 `card_id`、Anki `note_id`、最近推送 revision、最近观察到的 Anki 修改标记和同步状态。

## 本地到 Anki

- 新建 Card：创建 Note 并记录映射。
- HTML 更新：覆盖 `Front` 与 `Back`。
- 删除：删除对应 Note，并保留本地墓碑。
- 收到明确的 Anki 删除事件：回写本地软删除。仅在对账时发现 Note 不存在：标记为 `missing` 并停止该 Card 的自动同步，不删除本地，也不自动重建 Note，等待用户处理。

本工具只管理专用字段和自有标签命名空间；用户的其他 Anki 标签不被清除。牌组与 Note Type 属于集成配置，第一版由 Add-on 初始化并验证。

## Anki 到本地

- 用户修改 `Front` / `Back`：创建新本地 revision，只更新 HTML，`html_origin=anki_manual`；允许与结构化字段不一致。
- 用户删除受管 Note：本地软删除并创建 revision，然后将删除传播为最终状态。
- 用户修改非受管字段或普通标签：忽略。

Add-on 应标记由自身应用的远端更新，避免把同一次变更作为用户编辑回送形成循环。

## 最后写入胜出

“最后”指 `vocabd` 接受并提交变更的顺序，而不是比较不同进程的墙上时钟：

- Anki HTML 回写后，本地当前 HTML 为手工版本。
- 之后结构化字段被修改，则服务重新渲染并覆盖手工 HTML。
- 之后 Anki 再修改，则 Anki HTML 再次成为当前版本。

所有提交产生单调 revision。若两个客户端基于同一旧 revision 写入，后到请求得到 `409`，Add-on 重新读取后只在确认它代表更新的用户操作时重试。

## 实时与对账

- Add-on 主动建立认证 WebSocket；服务推送待同步 revision。
- Add-on 应用后 ack，并上报 Anki `note_id` 与结果。
- 连接断开时，数据库事件日志保留待处理变更。
- 重连时 Add-on 先扫描并提交离线期间观察到的 Anki 用户变化；这些变化提交完成后，再携带最后连续游标拉取服务事件并执行增量对账。
- 周期性任务或显式 `POST /api/v1/sync/reconcile` 可触发全量身份检查，修复丢失 ack、Note ID 变化等漂移。

## 幂等性

- 重复接收同一 `(card_id, revision)` 不得重复创建 Note。
- 创建前先按映射及 `ExternalCardId` 查找。
- 删除不存在的 Note 视为成功。
- ack 可重试；游标按客户端保存，且只能越过已经连续成功应用的事件前缀。

## 验证边界

- 同步正确性不能只由单元测试证明；必须覆盖真实 Anki 的创建、修改、删除和线程约束。
- 重复事件、乱序 ack、断线编辑、Note ID 漂移以及应用/ack 前后的崩溃都属于契约测试场景。
- hook 或 Note Type 的破坏性变化需要迁移策略，并重新评估 [ADR-0005](../decisions/0005-thin-anki-adapter.md)。
