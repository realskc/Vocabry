# 设计决策记录

这里归档会长期影响产品或多个技术模块、且仅看当前代码无法知道原因的选择。当前行为和精确协议不在 ADR 中维护，分别见上级设计文档与代码。

| ADR | 状态 | 决策 |
|---|---|---|
| [0001](0001-local-card-library.md) | 已接受、已实现 | 本地 Card 库独立于 Anki |
| [0002](0002-single-database-owner.md) | 已接受、已实现 | `vocabd` 是唯一业务数据库所有者 |
| [0003](0003-atomic-filesystem-import.md) | 已接受、已实现 | 生成器使用原子文件系统 job |
| [0004](0004-current-html-and-manual-overrides.md) | 已接受、已实现 | 持久化当前 HTML，并允许 Anki 手工版本优先 |
| [0005](0005-thin-anki-adapter.md) | 已接受、部分实现 | Anki Add-on 保持薄适配器，使用持久事件同步 |
| [0006](0006-api-only-management.md) | 已接受、已实现 | 第一版以 API 作为管理边界，不建设完整管理 CLI |

新增 ADR 应包含背景、决策、代价和重新评估条件。不要为局部重构、可轻松撤销的选择或从依赖文件即可看出的技术选型创建 ADR。
