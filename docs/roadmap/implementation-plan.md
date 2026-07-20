# 分阶段实施路线图

> 状态：计划。阶段编号表达依赖顺序，不代表当前已经完成；完成状态应在实际开发开始后根据证据更新。

## 阶段 0：工程骨架与契约

- Python 项目、格式化、类型检查和测试入口。
- 固化卡型标识、离线协议 v1、API 错误模型与 OpenAPI 初稿。
- 建立协议样例、golden files 和不变量到测试的追踪方式。

完成条件：协议示例可由独立校验脚本验证，设计中的错误代码有测试，`INVARIANTS.md` 的相关计划证据已替换为真实路径。

## 阶段 1：领域、数据库与渲染

- Card、revision、source、job 和 outbox 模型。
- 两种卡型 schema 和安全 HTML renderer。
- SQLite/Alembic、事务和迁移前备份。

完成条件：`CARD-001/002`、`HTML-001/002` 和 `CHANGE-001` 通过单元与数据库集成测试。

## 阶段 2：离线导入与 Demo 生成器

- 文件系统邮箱、原子领取、完整校验、结果归档和崩溃恢复。
- 独立 Demo 生成器及合法/非法 job 场景。

完成条件：`IMPORT-001` 有 golden files、整批回滚和故障注入证据；Demo 不依赖主应用内部包。

## 阶段 3：`vocabd` API 与服务生命周期

- loopback 服务、token、版本化 API、WebSocket/outbox。
- 完成 ingest、Card CRUD/history、预览 session、配对和同步对账 API。
- Windows 前台运行和单实例管理；后台安装可在本阶段末完成。

完成条件：外部客户端可以只通过 API 完成管理流程；`DATA-001`、`API-001` 和 `SEC-001` 的契约测试通过。

## 阶段 4：预览

- 同源页面、短时预览 session、sandbox iframe、翻面与调试元数据。

完成条件：自动 HTML 和 Anki 回写 HTML 都能安全显示；`SEC-002/003` 有浏览器层验证，页面无法取得管理 token。

## 阶段 5：Anki Add-on 与一致性

- 配对、Note Type、身份映射、hooks、WebSocket、ack 和重连对账。
- 离线编辑、删除、重复消息、崩溃恢复和真实 Anki 版本测试。

完成条件：`SYNC-001..004` 和产品范围中的双向同步验收场景全部有可重复证据。

## 阶段 6：Windows 分发

- 独立可执行文件、当前用户后台启动、配置 ACL、安装与卸载说明。
- 支持的 Anki/Windows 版本矩阵和端到端冒烟测试。
- 人工恢复流程演练。

完成条件：干净 Windows 用户环境可完成安装、导入、预览、Anki 同步、备份和卸载；支持矩阵与限制已经发布。

## 明确延后

独立管理 CLI、完整管理 GUI、多下游、跨设备同步、语义去重、LLM 生成器、Markdown、媒体、自定义卡型、版本恢复界面和 macOS/Linux 服务安装。
