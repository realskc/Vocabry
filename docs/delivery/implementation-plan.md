# 分阶段实施计划

## 阶段 0：工程骨架与契约

- Python 项目、格式化、类型检查和测试。
- 固化卡型标识、离线协议 v1、API 错误模型与 OpenAPI 初稿。
- 建立协议样例与 golden files。

完成条件：协议示例可由独立校验脚本验证，设计中的错误代码有测试。

## 阶段 1：领域、数据库与渲染

- Card、revision、source、job、outbox 模型。
- 两种卡型 schema 和安全 HTML renderer。
- SQLite/Alembic、事务和迁移前备份。

完成条件：状态机与事务不变量通过单元/集成测试。

## 阶段 2：离线导入与 demo 生成器

- 文件系统邮箱、原子领取、完整校验、结果归档、崩溃恢复。
- 独立 demo 生成器及合法/非法 job 场景。

完成条件：任一错误整批零写入，故障注入后可安全收敛。

## 阶段 3：`vocabd` API 与 CLI

- loopback 服务、token、版本化 API、WebSocket/outbox。
- CLI 的 status、ingest、card list/show/add/edit/delete/history、sync。
- Windows 前台运行和单实例管理；后台安装可在本阶段末完成。

完成条件：CLI 全程不接触数据库，鉴权和 revision conflict 契约通过测试。

## 阶段 4：预览

- 同源页面、短时预览 session、sandbox iframe、翻面与调试元数据。

完成条件：自动 HTML 和 Anki 回写 HTML 均能安全显示，不暴露管理 token。

## 阶段 5：Anki Add-on 与一致性

- 配对、Note Type、身份映射、hooks、WebSocket、ack 和重连对账。
- 离线编辑、删除、重复消息、崩溃恢复测试。

完成条件：产品范围中的双向同步验收场景全部通过。

## 阶段 6：Windows 分发

- 独立可执行文件、当前用户后台启动、配置 ACL、安装与卸载说明。
- 支持的 Anki/Windows 版本矩阵和端到端冒烟测试。

## 明确延后

多下游、跨设备同步、语义去重、LLM 生成器、Markdown、媒体、自定义卡型、版本恢复 UI/CLI 和 macOS/Linux 服务安装。

