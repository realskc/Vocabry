# Anki Add-on 设计

## 职责边界

Add-on 是薄适配器，不实现卡型 schema、HTML renderer、导入或数据库逻辑。它负责配对、连接、受管 Note 身份、Anki hook 和同步应用。

## 配对

用户在 CLI 创建短时一次性配对码，在 Add-on 配置界面输入。Add-on 调用配对端点换取独立 token，并使用 Anki Add-on 配置机制保存。token 可由 CLI 撤销。

## Anki 对象

Add-on 创建或验证专用 Note Type，字段为 `ExternalCardId`、`Front`、`Back`。模板只负责把字段插入卡片页面和提供基础样式；业务 HTML 已由主应用生成。

## Hook 行为

- 监听 Note 保存：仅处理带合法 `ExternalCardId` 的受管 Note；比较最近应用快照，确认是用户修改后回传 HTML。
- 监听删除：回传受管 ID；若 hook 无法提供完整信息，维护必要的轻量映射以便识别。
- 应用服务事件：切换到 Anki 允许的主线程/collection 操作上下文，成功后 ack。

需要在编码前针对目标 Anki 版本核实稳定 hook API，并把版本兼容矩阵写入 Add-on manifest 文档。

## 故障表现

- `vocabd` 离线：Anki 正常复习；Add-on 显示非阻塞状态并暂存待回传变化的最小信息。
- 重连：先发送本地观察到的用户变化，再按 revision/游标对账，避免服务旧值覆盖离线用户编辑。
- 无效 token：停止写入并提示重新配对，不能无限重试刷日志。

