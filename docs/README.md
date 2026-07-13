# Vocabry 设计文档索引

## 阅读路线

1. [产品范围](product/scope.md)：目标、边界与第一版验收标准。
2. [系统架构](architecture/system-overview.md)：组件、依赖方向与运行形态。
3. [领域模型](domain/card-model.md)：卡片、版本、来源及 HTML 派生产物。
4. [离线导入协议](protocols/offline-import.md)：外部生成器的文件系统邮箱协议。
5. [本地 API](protocols/local-api.md)：CLI、预览器和 Anki Add-on 的通信边界。
6. [同步协议](protocols/anki-sync.md)：双向同步、一致性与冲突规则。
7. 组件设计：[`vocabd`](components/vocabd.md)、[CLI](components/cli.md)、[Anki Add-on](components/anki-addon.md)、[预览器](components/preview.md)、[外部 demo 生成器](components/demo-generator.md)。
8. 横切设计：[安全](cross-cutting/security.md)、[可靠性与测试](cross-cutting/reliability-testing.md)。
9. [实施计划](delivery/implementation-plan.md)。

## 文档约定

- “第一版”指 Windows 10/11 上的首个可用版本。
- `Card` 指本地卡片实体；`Note` 指 Anki Note。
- **结构化字段**是卡片内容真源；`front_html` 与 `back_html` 是持久化派生产物，但允许被 Anki 手动修改形成当前版本。
- 文档中的端点和 JSON 是设计契约；实现阶段可以补充字段，但破坏性修改必须提升协议版本。
