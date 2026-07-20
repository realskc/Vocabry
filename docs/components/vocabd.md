# `vocabd`

> 状态：设计基线。本文描述组件语义，不代表数据库表或内部包已经实现。

## 定位

`vocabd` 是 Vocabry 的业务核心、唯一数据库所有者和本地集成中心。所有 Card 状态变化最终都由它验证、排序并提交。

## 职责

- 独占 SQLite 读写、迁移和备份边界。
- 执行 Card 创建、编辑、删除、版本控制和 HTML 渲染规则。
- 领取、校验、提交并归档文件系统 job。
- 提供认证 HTTP/WebSocket API 和同源预览页面。
- 持久化 revision、outbox event、客户端游标和 Anki 身份映射。
- 在启动时恢复中断的导入和尚未收敛的同步工作。

## 非职责

- 不生成词义内容，也不内置 LLM、词典或抓取器。
- 不实现复习算法或 Anki UI。
- 不把业务规则复制给 API 客户端、浏览器或 Add-on 执行。
- 不根据内容做语义去重或自动合并。

## 交互边界

| 对方 | 输入 | 输出 |
|---|---|---|
| 外部生成器 | 原子投递的 job | 归档 job 与机器可读结果 |
| 管理 API 客户端 | 认证 HTTP 请求 | Card、job、预览 session、同步状态和错误 |
| 预览器 | 短时预览请求 | 当前 HTML 与调试元数据 |
| Anki Add-on | 配对、变化、ack、对账请求 | 待同步 revision 和身份状态 |
| SQLite | 事务 | Card 当前态、历史、事件与映射 |

## 必须保持

- [`DATA-001`](../INVARIANTS.md#data-001-单一数据库所有者)
- [`IMPORT-001`](../INVARIANTS.md#import-001-job-全有或全无)
- [`CHANGE-001`](../INVARIANTS.md#change-001-当前态历史和事件一致提交)
- [`CARD-001`](../INVARIANTS.md#card-001-稳定身份与单调版本)
- [`API-001`](../INVARIANTS.md#api-001-过期写入不得静默覆盖)

事务实现应采用 transactional outbox。SQLite 计划开启外键、WAL 和合理的 busy timeout；这些设置在实现后由迁移与集成测试成为事实源。

## 主要故障表现

- 已有实例占用数据库或端口：新实例应明确退出，不能形成两个写入者。
- job 在领取或提交附近中断：重启后应依据数据库状态安全续办或归档。
- 数据库提交后实时通知失败：持久 outbox 保留待发送事件。
- 迁移失败：不得带着部分迁移继续提供服务；迁移前保留一致性备份。
- token 或配置权限不安全：启动失败并给出可诊断错误。

## 修改影响

修改 Card 模型、revision 或 HTML 状态机会影响 API 客户端、预览和 Anki 同步；修改事件、游标或身份映射会影响 Add-on；修改 job 生命周期会影响所有外部生成器。此类变更必须检查相关协议、不变量和 ADR。

## 进一步入口

- [卡片领域模型](../domain/card-model.md)
- [离线导入协议](../protocols/offline-import.md)
- [本地 API](../protocols/local-api.md)
- [Anki 同步协议](../protocols/anki-sync.md)
- [安全边界](../quality/security.md)
- [验证策略](../quality/verification.md)
