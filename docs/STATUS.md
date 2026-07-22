# 当前实现状态

本文只记录无法从源码和设计文档轻易判断、但会影响使用或开发决策的验证边界与高风险缺口。

## 验证边界

- 普通完整测试包含真实 DeepSeek 调用，需要当前 Windows 用户的 Credential Manager 中存在可用 Key；不同 Windows 身份不能共享这一凭据。
- Anki Add-on 尚未在目标 Anki 版本中完成真实兼容性验证。Note Type 升级、hooks、collection 主线程约束、WebSocket 生命周期、profile 切换和全量对账仍只有代码与进程外测试证据。
- 当前只验证 Windows 源码运行；没有安装器、独立可执行文件、自动更新或其他平台支持证据。

## 高风险缺口

### 数据与导入

- SQLite 没有通用 schema migration、迁移前备份或人工恢复机制。当前启动迁移只覆盖已明确实现的个别兼容变化。
- 没有跨进程数据库单实例锁；端口检查不能替代数据库所有权锁。

### API 与安全

- Anki token 的权限过宽，可调用多数普通 Card API。
- Windows 文件 ACL、Add-on token 存储和归档 job 权限没有验证。
- 配对码没有失败次数限制，过期凭据和幂等记录没有清理策略。

### Anki

- WebSocket 请求中的 cursor 与服务端持久 cursor 尚未收敛为单一恢复事实源，异常窗口可能造成跳过或 ack 冲突。
- Anki 修改没有持久离线队列；revision conflict 只报告失败，没有恢复或合并流程。
- 全量对账会在 GUI 明确报告并确认后删除孤立、重复及其他数据库的 Note，但真实 Anki 中的 note ID 漂移与中断恢复尚未验证。
