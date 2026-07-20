# 协议契约

协议文档定义外部进程、文件和组件边界上的精确行为。它们是人类与 Agent 共享的设计契约；实现后，OpenAPI、JSON Schema、golden files 和契约测试应成为可执行证据。

| 协议 | 边界 | 核心保证 |
|---|---|---|
| [离线导入](offline-import.md) | 外部生成器 → `vocabd` | 原子投递、整批校验、机器可读结果 |
| [本地 API](local-api.md) | 管理客户端 / 预览 / Add-on ↔ `vocabd` | loopback 认证、revision 并发控制、可重放事件 |
| [Anki 同步](anki-sync.md) | `vocabd` ↔ Anki Add-on | 稳定身份、幂等消费、断线后收敛 |

协议的破坏性修改必须提升版本或提供迁移路径。组件定位见[组件语义卡片](../components/README.md)，跨协议约束见[系统不变量](../INVARIANTS.md)。
