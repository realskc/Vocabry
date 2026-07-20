# 本地 API

> 状态：v1 设计契约，精确 schema 待 OpenAPI 固化。关联不变量：`DATA-001`、`API-001`、`SEC-001`、`SEC-002`。

## 边界

- 仅绑定 `127.0.0.1`；第一版不允许改为非 loopback 地址。
- 路径统一使用 `/api/v1`。
- 除健康检查和 `POST /api/v1/pairing/exchange` 外，HTTP 和 WebSocket 均强制 token；创建配对码仍需管理 token。
- 完全不启用 CORS。浏览器预览页由服务同源提供。
- 管理 API 客户端、预览器和 Add-on 不直接访问 SQLite。

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
POST   /api/v1/preview/sessions
GET    /api/v1/sync/status
POST   /api/v1/sync/reconcile
POST   /api/v1/anki/changes
POST   /api/v1/pairing/codes
POST   /api/v1/pairing/exchange
```

精确请求/响应 schema 在实现前由 OpenAPI 固化并生成测试夹具。修改或删除既有 Card 时必须携带 `expected_revision`；过期写入返回 `409 revision_conflict`。创建型 POST 使用 `Idempotency-Key`，同一客户端重复提交相同 key 返回第一次的结果，不重复创建资源。

## WebSocket

```text
WS /api/v1/events
```

认证成功后客户端声明类型和最后确认的连续事件游标。事件只通知“发生了什么”，完整数据通过 HTTP 或事件中的版本化快照取得。客户端逐条回传 ack；只有连续前缀全部成功后才推进该客户端的持久游标。未 ack 事件可重发，因此消费者必须幂等。

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

## 兼容性与证据

- `/api/v1` 内允许增加向后兼容的可选字段；删除、改名或改变既有语义需要新版本或迁移期。
- 实现阶段以生成的 OpenAPI 为请求/响应精确事实源，并由独立客户端与 Add-on fixture 做契约测试。
- Card 修改与删除覆盖过期 revision；创建型 POST 覆盖重复 `Idempotency-Key`；所有受保护端点覆盖未认证访问。
