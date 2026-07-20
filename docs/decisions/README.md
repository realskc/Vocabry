# 架构决策记录

ADR 保存代码和协议不容易表达的“为什么”、代价以及重新评估条件。组件文档描述当前边界，协议描述精确行为，不在其中重复完整决策过程。

| ADR | 状态 | 决策 |
|---|---|---|
| [ADR-0001](0001-local-card-library.md) | 已接受（设计） | 本地 Card 库独立于 Anki，Anki 是复习下游 |
| [ADR-0002](0002-single-database-owner.md) | 已接受（设计） | `vocabd` 是唯一数据库所有者 |
| [ADR-0003](0003-atomic-filesystem-import.md) | 已接受（设计） | 外部生成器使用原子文件系统 job |
| [ADR-0004](0004-current-html-and-manual-overrides.md) | 已接受（设计） | 持久化当前 HTML，并允许 Anki 手工版本暂时优先 |
| [ADR-0005](0005-thin-anki-adapter.md) | 已接受（设计） | Add-on 保持为薄适配器，通过持久事件最终一致 |
| [ADR-0006](0006-api-only-management.md) | 已接受（设计） | 第一版不提供完整管理 CLI，以本地 API 作为正式管理边界 |

“已接受（设计）”表示方案已成为当前设计基线，但还没有实现和运行证据。新决策使用下一个编号；被替代的 ADR 保留原文并标记替代关系。
