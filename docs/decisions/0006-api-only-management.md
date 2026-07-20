# ADR-0006：第一版只提供 API 管理边界

- 状态：已接受（设计）
- 关联：`DATA-001`、`API-001`、`SEC-001`、`SEC-002`

## 背景

`vocabd` 已经通过本地 HTTP API 提供导入、Card 管理、预览 session、配对和同步对账能力。若第一版同时建设完整的 `vocab` CLI，还需要额外设计命令结构、交互式编辑、JSON 输出、退出码和错误呈现，但这些能力本质上仍只是 API 的另一层包装。

第一版主要由项目维护者通过 Coding Agent、脚本或其他 API 工具管理卡片，独立 CLI 的人类体验尚未被实际需求证明。

## 决策

第一版不提供完整的 `vocab` 管理 CLI。本地 API 是唯一正式的管理能力边界，Coding Agent、脚本和未来的 CLI 或 GUI 都作为可替换客户端使用它。

服务自身仍可提供最小生命周期命令：

```text
vocabd start
vocabd install
vocabd status
vocabd stop
```

这些命令只负责启动、安装、检查和停止服务，不承载 Card、导入、预览或同步业务接口。

## 代价

- 不使用 Coding Agent 或 API 工具时，人类手动管理卡片不够方便。
- 调用者需要处理管理 token、JSON 请求和 `revision_conflict`。
- API 必须完整覆盖配对码、预览 session 和显式对账等原本可能由 CLI 提供的入口。
- 排障指南不能假设存在 `vocab status` 等管理命令。

## 重新评估条件

出现以下情况之一时，可以基于本地 API 增加薄 CLI 或管理 GUI：

- 非开发者用户需要脱离 Coding Agent 管理卡片；
- 多个高频操作反复依赖手写 API 请求；
- 自动化脚本开始各自实现重复的认证、冲突处理和错误展示；
- API 已稳定，增加客户端不会反过来牵制核心契约设计。

重新引入客户端时，不把业务规则或数据库访问复制到客户端；API 仍是正式能力边界。
