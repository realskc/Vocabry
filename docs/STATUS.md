# 当前实现状态

本文是仓库级元文档，用于区分“代码已经存在”“自动化测试已经证明”和“仍是目标”。更新功能时只记录重要能力与风险，不复制 issue 列表。

## 当前定位

版本为 0.1.0。核心服务是可运行 MVP；Anki Add-on 是尚未经过真实版本验证的原型；Windows 分发尚未开始。产品范围见 [`product/`](product/README.md)，技术上下文见 [`design/`](design/README.md)。

## 已实现

- Python 3.11+ 包和 `vocabd` / `vocabry-demo` 入口。
- 数据目录、管理 token、SQLite schema、WAL 和基本事务。
- 两种卡型、确定性安全渲染、当前 HTML 与 revision 历史。
- Card CRUD、软删除、乐观并发和创建幂等性。
- 原子文件 job 领取、整批校验、提交、结果归档与部分启动恢复。
- bearer token、一次性 Anki 配对、客户端撤销和受保护 OpenAPI。
- 短时预览 session 与 sandbox iframe。
- outbox WebSocket、顺序 ack、cursor 和 Anki mapping。
- Anki Note Type 创建、事件应用、HTML 编辑回写和删除扫描。

## 仓库现有自动化测试

现有 15 个 pytest 测试覆盖：

- renderer 的 HTML 转义、换行与确定性；
- Card 当前态、history 与 outbox 同事务的基本路径；
- 旧 revision 冲突；
- Anki 手工 HTML 被保留，直到结构化字段再次编辑；
- renderer 升级只处理自动 HTML；
- 合法 job 整批导入与非法 job 零新增；
- job 在数据库提交前、提交后和最终目录移动前中断后的恢复；
- 旧版成功 job 缺少 result 时的重建，以及重复恢复不重复创建 Card；
- API 认证、Card 创建/重放/修改/冲突；
- 一次性配对码与 preview sandbox；
- WebSocket 单事件 ack 推进 cursor。

测试数量不等于发布证据。当前没有 CI 配置，仓库也没有锁定依赖版本。

## 已知缺口

### 数据与导入

- 没有 schema migration、迁移前备份或恢复流程。
- 没有跨进程单实例锁；两个服务可能同时尝试打开数据库和端口。
- 目前的故障测试在进程内模拟中断；还没有真实进程终止、资源边界和恶意输入的系统测试。

### API 与安全

- Anki token 的权限过宽，可调用多数普通 Card API。
- Windows 文件 ACL、Add-on token 存储和归档 job 权限未验证。
- 配对码没有尝试次数限制；过期凭据与 idempotency 记录不清理。
- WebSocket query cursor 与服务端持久 cursor 可能不一致。
- reconcile 端点是占位实现。

### Anki

- 没有真实 Anki 版本测试或支持矩阵。
- 没有持久离线编辑队列、全量身份对账或可靠 note ID 漂移修复。
- revision conflict 只提示失败，没有用户可操作的恢复流程。
- 删除检测可能把无法读取或身份漂移误判为用户删除。
- hook 与线程使用没有验证，部分 hook 缺失时会静默降级。

### 产品与分发

- 没有完整管理 UI/CLI。
- 没有后台服务、安装器、升级/卸载和备份体验。
- preview 是静态正反面检查页，不是交互式卡片浏览器。

## 下一阶段优先级

在增加新卡型、生成器或 UI 前，优先把现有数据闭环变得可信：

1. 运行并稳定现有测试环境，增加 CI。
2. 扩展导入的资源边界与恶意输入测试。
3. 明确 WebSocket 恢复握手与唯一 cursor 事实源。
4. 在目标 Anki 版本上验证 hooks 和线程，补离线队列与对账。
5. 引入首次 schema migration、备份与人工恢复流程。
6. 收紧 token capability 并验证 Windows 权限。

这个顺序关注已承诺的数据安全与同步正确性，不代表长期产品路线图。
