# 可靠性与测试

## 必须保持的不变量

- 只有 `vocabd` 写数据库。
- 一个 job 要么全部导入，要么零导入。
- 每次 Card 当前态变化都有对应 revision 和 outbox event。
- 同一 `(card_id, revision)` 可安全重复消费。
- 游标只在对应变更成功应用后推进。
- Anki 用户修改不会被较旧的服务事件覆盖。

## 测试层次

### 单元测试

- 两种卡型校验和确定性 HTML 渲染；HTML 转义、空字段、换行。
- revision 状态机：renderer、Anki 手工 HTML、结构化字段再编辑、删除。
- 错误代码稳定性和路径安全校验。

### 数据库集成测试

- job 中途错误回滚。
- Card、revision、outbox 同事务提交。
- 重启恢复 `processing` job。
- 迁移前后数据与历史不丢失。

### 协议契约测试

- 固定 JSONL/manifest/result 样例。
- OpenAPI schema 与 CLI/Add-on fixture 一致。
- 重复事件、乱序 ack、断线重连和过期 revision。

### Anki 集成测试

- 创建、更新、删除 Note。
- 用户 HTML 编辑回写。
- Add-on 自身更新不形成回声循环。
- Anki 离线编辑后重连时保留用户最新操作。

目标 Anki API 可能随版本变化；发布前至少在声明支持的最低与最新稳定版本上人工验证。

## 故障注入

在关键边界强制终止进程：job 移动后、数据库提交前后、result 写入前后、Anki 应用前后和 ack 前后。重启后结果必须收敛且不重复创建。

## 备份

迁移前自动创建 SQLite 一致性备份并保留有限代数。第一版提供备份但不承诺 CLI 恢复流程；恢复步骤必须文档化并人工可执行。

