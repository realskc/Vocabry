# `vocabd` 设计

## 职责

- 独占 SQLite 读写与迁移。
- 执行卡片用例、版本控制和 HTML 渲染。
- 处理文件系统 job。
- 提供认证 HTTP/WebSocket API 与预览页面。
- 持久化事件日志、客户端游标及 Anki 映射。

## 启动顺序

1. 解析 Windows 用户配置目录。
2. 获取单实例锁；已有实例时退出并指出端口。
3. 检查文件权限、加载 token、打开数据库并执行安全迁移。
4. 恢复 `processing` 中断任务和未完成同步事件。
5. 绑定 loopback 端口并写入运行状态文件。
6. 接受客户端连接。

## 数据库建议表

```text
cards
card_revisions
card_sources
import_jobs
sync_targets
anki_note_mappings
outbox_events
client_cursors
api_clients
```

具体列在迁移实现时固化。关键不变量由数据库约束和应用校验共同维护：稳定 ID 唯一、revision 单调、job ID 不重复、每张活动卡至多一个 Anki Note 映射。

## 事务边界

- 一个导入 job 是一个事务。
- 一次卡片编辑或删除是一个事务：Card 当前态、revision 和 outbox event 同时提交。
- 使用 transactional outbox，避免数据库已更新但实时事件丢失。
- SQLite 开启 WAL、外键和合理 busy timeout；只有 daemon 写入。

## HTML 渲染

每种卡型由代码内置 schema 和 renderer。renderer 是纯函数：结构化字段输入，确定性输出 front/back HTML。输出使用语义化 class，不内嵌脚本；文本统一转义。

缓存策略：日常读取直接使用持久 HTML；结构化字段编辑即时重建单张；渲染器升级时标记陈旧并按需重建。手工 Anki HTML 不因单纯升级自动覆盖。

