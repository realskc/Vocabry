# 组件语义卡片

组件文档面向人类建立心智模型，也为 Coding Agent 提供调查入口。它们描述组件的定位、边界、关系、不变量、故障表现和修改影响，不复述内部代码结构。

| 组件 | 定位 | 主要边界 |
|---|---|---|
| [`vocabd`](vocabd.md) | 唯一业务核心与数据库所有者 | 离线导入、本地 API、同步事件 |
| [Anki Add-on](anki-addon.md) | Anki 的薄适配器 | 本地 API、Anki collection/hooks |
| [预览器](preview.md) | 当前 HTML 的只读检查界面 | 同源预览 session/API |
| [Demo 生成器](demo-generator.md) | 离线协议的独立示例消费者 | 文件系统 job |

组件之间的整体关系见[系统地图](../architecture/system-map.md)，跨组件硬约束见[系统不变量](../INVARIANTS.md)，边界上的精确行为见[协议契约](../protocols/README.md)。
