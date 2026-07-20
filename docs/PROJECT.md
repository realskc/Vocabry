# Vocabry 项目驾驶舱

> 状态：功能 MVP 已实现。核心领域、SQLite、离线导入、API、预览和同步协议已有自动化测试；真实 Anki 版本兼容与 Windows 分发仍待验证。

## 五分钟认识项目

Vocabry 是一个以本地卡片库为核心、通过 Anki 复习的英语词汇卡片管理系统。它把卡片的生成、管理和版本历史留在本地服务中，把 Anki 作为复习端，通过明确协议完成双向同步。

第一版面向 Windows 10/11 上的单用户、单机、单数据库和单 Anki Profile。系统不内置 LLM、词典或复习算法。

完整的产品边界和验收条件见[产品范围](product/scope.md)。

## 核心用户路径

1. 外部生成器通过文件系统 job 投递卡片。
2. `vocabd` 原子校验并导入整个 job，生成当前 HTML 和版本历史。
3. 用户通过 Coding Agent、脚本或其他 API 客户端管理卡片，并通过浏览器检查当前 HTML。
4. Anki Add-on 把本地 Card 映射为 Anki Note。
5. Anki 中的 HTML 编辑和删除回写本地；断线后通过事件游标和对账收敛。

## 系统地图

```text
External generators
       │ filesystem jobs
       ▼
    vocabd ───────── SQLite
      ▲  ▲
 HTTP │  │ authenticated WebSocket
      │  ▼
 API clients     Anki Add-on ⇄ Anki collection
      │
      └──────── Browser preview
```

`vocabd` 是唯一数据库所有者和业务规则执行者；API 客户端、预览器和 Anki Add-on 都不能绕过服务读取或修改数据库。更完整的依赖和数据流见[系统地图](architecture/system-map.md)。

跨组件硬约束以[系统不变量](INVARIANTS.md)为准。

## 当前最关键的问题

发布前仍需补足以下证据：

- 针对目标 Anki 版本验证可用 hook、线程约束和删除检测能力。
- 用故障注入进一步证明导入与同步能够在崩溃后收敛。
- 验证 Windows 下 token、数据库和配置文件的 ACL 与打包方案。

实施顺序和各阶段完成条件见[实施路线图](roadmap/implementation-plan.md)。

## 按问题阅读

| 我想了解 | 首选入口 |
|---|---|
| 产品做什么、明确不做什么 | [产品范围](product/scope.md) |
| 组件如何连接、数据如何流动 | [系统地图](architecture/system-map.md) |
| 哪些规则绝不能被修改破坏 | [系统不变量](INVARIANTS.md) |
| Card、HTML、revision 如何建模 | [卡片领域模型](domain/card-model.md) |
| 某个组件的定位和修改影响 | [组件语义卡片](components/README.md) |
| 外部边界的精确行为 | [协议契约](protocols/README.md) |
| 为什么采用当前架构 | [架构决策记录](decisions/README.md) |
| 安全风险和验证策略 | [安全边界](quality/security.md)、[验证策略](quality/verification.md) |
| 这套文档如何维护 | [文档规范](README.md) |

## 术语与状态约定

- “第一版”指 Windows 10/11 上的首个可用版本。
- `Card` 指本地卡片实体；`Note` 指 Anki Note。
- **结构化字段**是自动渲染的输入真源；`front_html` 与 `back_html` 是持久化的当前交付物，允许被 Anki 手工修改形成当前版本。
- 协议中的端点、JSON 和错误代码是设计契约；实现可以增加兼容字段，破坏性修改必须提升协议版本。
- 文档中的“必须”表示设计约束；在实现出现前，不等同于已经通过自动化验证。
