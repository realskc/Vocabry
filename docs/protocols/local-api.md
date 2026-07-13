# 本地 API

## 边界

- 仅绑定 `127.0.0.1`；第一版不允许改为非 loopback 地址。
- 路径统一使用 `/api/v1`。
- 除健康检查与一次性配对端点外，HTTP 和 WebSocket 均强制 token。
- 完全不启用 CORS。浏览器预览页由服务同源提供。
- CLI、预览器和 Add-on 不直接访问 SQLite。

## 认证

普通客户端使用：

```http
Authorization: Bearer <token>
```

首次启动创建管理 token，保存于当前用户受限配置目录。Anki Add-on 使用短时一次性配对码换取独立、可撤销的客户端 token。数据库只保存 token 哈希和客户端元数据。

## 最小 HTTP 资源

```text
GET    /api/v1/health
POST   /api/v1/ingest
GET    /api/v1/jobs/{job_id}
GET    /api/v1/cards
POST   /api/v1/cards
GET    /api/v1/cards/{card_id}
PATCH  /api/v1/cards/{card_id}
DELETE /api/v1/cards/{card_id}
GET    /api/v1/cards/{card_id}/history
GET    /api/v1/sync/status
POST   /api/v1/sync/reconcile
POST   /api/v1/anki/changes
POST   /api/v1/pairing/codes
POST   /api/v1/pairing/exchange
```

精确请求/响应 schema 在实现前由 OpenAPI 固化并生成测试夹具。写请求携带 `expected_revision`，过期写入返回 `409 revision_conflict`；客户端读取最新状态后再决定重试，不能静默覆盖并发变更。

## WebSocket

```text
WS /api/v1/events
```

认证成功后客户端声明类型和最后确认的事件游标。事件只通知“发生了什么”，完整数据通过 HTTP 或事件中的版本化快照取得。客户端必须回传 ack；未 ack 事件可重发，因此消费者必须幂等。

示例：

```json
{"event_id":1042,"type":"card.updated","card_id":"...","revision":7}
```

## 错误模型

```json
{
  "error": {
    "code": "revision_conflict",
    "message": "Card has changed since revision 6.",
    "details": {"expected": 6, "actual": 7},
    "request_id": "..."
  }
}
```

错误代码属于兼容性契约；HTTP 状态码表达类别，`code` 表达可编程原因。

