# Vocabry 文档

文档按读者和用途分成三层：

| 位置 | 读者 | 保存什么 |
|---|---|---|
| [`product/`](product/README.md) | 用户、产品参与者、不熟悉实现的人 | 产品为何存在、怎样使用、Anki 与卡片概念 |
| [`design/`](design/README.md) | 维护者、Coding Agent | 跨模块技术语义、数据状态机、协议边界和设计原因 |
| [`archive/`](archive/README.md) | 维护者、历史查阅者 | 版本记录与历史设计决策归档 |
| `docs/` 根目录 | 所有人 | 文档导航、当前实现状态等仓库级元信息 |

## 推荐阅读

第一次了解项目：

1. [产品介绍](product/README.md)
2. [核心概念](product/concepts.md)
3. [卡型与 Generator](product/cards-and-generators.md)
4. [使用流程](product/workflows.md)
5. [当前状态](STATUS.md)

查阅版本历史：

1. [文档归档](archive/README.md)
2. 对应版本文档中的历史目标、取舍与验收记录
3. 当前产品和技术事实仍回到 `product/` 与 `design/` 查阅

准备修改代码：

1. [技术设计导航](design/README.md)
2. 与任务相关的 data model、import、API 或 Anki sync 文档
3. [开发规范](development.md)
4. [历史设计决策](archive/decisions/README.md)
5. 对应实现与测试

## 收录标准

一段内容只有满足至少一个条件才值得进入文档：

- 帮助人类理解产品、概念、能力或限制；
- 保存无法从局部代码轻易恢复的跨模块语义；
- 解释仍会影响后续工作的上层决策与代价；
- 清楚区分已实现、已验证和尚未完成。

以下内容通常不应写入：

- 函数、文件和端点的机械清单，除非它们构成导航或权限矩阵；
- “模块应低耦合”“输入应校验”等不指导具体修改的原则；
- 可直接从类型、schema 或一小段代码准确得到的事实；
- 已完成阶段的流水账式实施计划；
- 把目标行为写成已实现保证的愿望清单。

## 维护方式

开发和文档更新规则见[开发规范](development.md)。只有跨多个模块、长期影响后续选择，并且经过用户确认的变化才新增 ADR。
