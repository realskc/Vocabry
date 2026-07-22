# 本地 API 与安全边界

HTTP API 是第一版正式的管理边界；Coding Agent、脚本、预览器和 Anki Add-on 都通过它与 `vocabd` 交互。精确请求 schema 由运行中服务的 `/api/v1/openapi.json` 给出，本文只记录权限、并发和跨端点语义。

## 监听与认证

服务固定绑定 `127.0.0.1`，默认端口 8765。FastAPI 使用 Trusted Host middleware 接受 `127.0.0.1`、`localhost` 和测试环境的 `testserver`，没有配置 CORS。

除健康检查、预览 URL 和配对码交换外，HTTP 请求使用：

```http
Authorization: Bearer <token>
```

WebSocket 同样从 Authorization header 认证。当前客户端类型有 `admin` 和 `anki`：

- admin token 首次启动时写入数据目录的 `admin.token`；
- Anki token 由一次性配对码交换产生，可由 admin 撤销；
- 数据库只保存 token 的 SHA-256 hash；
- token 比较和文件权限尚未经过专门安全加固或 Windows ACL 验证。

不要把“只监听 localhost”当成取消认证的理由。浏览器访问 localhost、同机其他程序和意外端口暴露都是边界的一部分。

## 端点与权限

| 端点 | 权限 | 语义 |
|---|---|---|
| `GET /api/v1/health` | 无 | 最小健康状态与版本 |
| `GET /api/v1/openapi.json` | admin | 当前 OpenAPI schema |
| `POST /api/v1/ingest` | admin | 扫描并处理 inbox |
| `POST /api/v1/maintenance/rerender` | admin | 重渲染陈旧的自动 HTML |
| `GET /api/v1/jobs/{job_id}` | 任意 token | 查询导入 job |
| `GET/POST /api/v1/cards` | 任意 token | 列表或创建 Card |
| `GET/PATCH/DELETE /api/v1/cards/{id}` | 任意 token | 读取、修改或软删除 |
| `GET /api/v1/cards/{id}/history` | 任意 token | 完整 revision 列表 |
| `POST /api/v1/preview/sessions` | 任意 token | 为指定 Card 创建 10 分钟 session |
| `POST /api/v1/preview/candidate` | admin | 校验并渲染未持久化的结构化候选卡 |
| `POST /api/v1/admin/shutdown` | admin | 请求 GUI 所拥有的服务优雅退出 |
| `GET /preview/{card_id}` | preview session | 只读 HTML 预览 |
| `GET /api/v1/sync/status` | 任意 token | 当前客户端 cursor 和全部 Anki mappings |
| `POST /api/v1/sync/reconcile` | admin | 创建持久化全量对账任务 |
| `GET /api/v1/sync/reconcile/{id}` | admin | 查询 inventory、报告、计划和执行结果 |
| `POST /api/v1/sync/reconcile/{id}/execute|cancel` | admin | 明确批准或取消对账计划 |
| `GET /api/v1/anki/reconcile/pending` | anki | 领取 inventory 或 execute 命令 |
| `POST /api/v1/anki/reconcile/{id}/inventory|complete` | anki | 提交 collection 盘点或执行结果 |
| `POST /api/v1/anki/changes` | anki | 回写 HTML、删除或 missing 状态 |
| `POST /api/v1/pairing/codes` | admin | 创建 5 分钟一次性配对码 |
| `POST /api/v1/pairing/exchange` | 无 | 消费配对码，得到 Anki token、client ID 和 database ID |
| `DELETE /api/v1/clients/{id}` | admin | 撤销非 admin 客户端 |
| `WS /api/v1/events` | 任意 token | 顺序消费 outbox 事件 |

“任意 token”是当前代码事实，不代表最终最小权限模型。特别是 Anki token 当前也能调用 Card CRUD、读取 history、创建 preview session 和查看全部 mappings。若产品要求真正隔离权限，应先定义 capability，再收紧依赖并补测试。

桌面 GUI 通过 admin 权限调用 pairing code 端点，并在首页向用户展示配对码；Key 或 token 不经过剪贴板协议自动传给 Anki。Add-on 消费新配对码后必须把旧数据库的本地 cursor 和 mappings 重置，具体原因见 [Anki 同步](anki-sync.md)。

## 创建幂等性

`POST /cards` 强制要求 `Idempotency-Key`。数据库按 `(client_id, key)` 保存请求 body hash 与第一次响应：

- 相同 key、相同 body：返回第一次创建的 Card；
- 相同 key、不同 body：`409 idempotency_conflict`；
- key 在不同客户端之间互不影响。

当前实现只给 Card 创建提供幂等 key；配对码创建、preview session 等创建型端点没有同一机制。

## 乐观并发

PATCH、DELETE 和 Anki 回写必须携带 `expected_revision`。数据库在写事务内比较当前 revision：匹配才提交，不匹配返回 `409 revision_conflict` 与 expected/actual 信息。

客户端遇到冲突后必须重新读取并重新判断用户意图，不能机械替换成最新 revision 后盲目重试。否则协议虽然阻止了静默覆盖，客户端仍会重新制造覆盖。

## WebSocket 事件流

客户端连接 `/api/v1/events?cursor=N`。服务按 event ID 顺序发送完整 payload，一次只等待当前事件的 ack；ack event ID 不匹配时关闭连接。Anki 客户端的 ack 还会更新 note mapping。

数据库持久 cursor 只接受 `current + 1`，因此它表达已连续成功消费的前缀。重复 ack 不会倒退 cursor。

当前协议有两个需谨慎的实现细节：

- 查询参数 cursor 由客户端提供，服务没有先与数据库持久 cursor 取一致；传入过大的值可能跳过发送，传入与持久 cursor 不一致的值可能在 ack 时冲突。
- 每批最多读取 100 个事件，空闲时通过 `idle` / `ping` / `pong` 保活；没有事件通知条件变量，连接循环轮询。

在扩展同步前应先把“连接从哪个 cursor 恢复”收敛为单一服务端规则。

## 错误格式

业务与验证错误统一返回：

```json
{
  "error": {
    "code": "revision_conflict",
    "message": "Card has changed since revision 1",
    "details": {"expected": 1, "actual": 2},
    "request_id": "..."
  }
}
```

`request_id` 当前每次处理错误时随机生成，没有贯穿日志或请求生命周期。稳定的程序分支应依据 HTTP status 与 code，不解析 message。

## 预览隔离

预览 session 与 Card 绑定，数据库只存 hash，10 分钟后失效。预览页把当前 HTML 放进无 `allow-*` 权限的 sandbox iframe，并将 HTML 转义后写入 `srcdoc` 属性。响应还设置 `nosniff`、`no-referrer` 和限制性 CSP。

当前没有 session 撤销或过期记录清理。任何增加脚本、表单、外部资源或管理操作的改动都会改变安全边界，不能当作普通页面增强。

候选预览不创建 Card、revision 或 outbox event。它与 Card 创建复用 `CardInput` 和 renderer，返回正反面 HTML 供 GUI 静态并排展示。GUI 不接受 generator 自带 HTML。

shutdown 端点只负责发出退出请求；实际 Uvicorn server 在返回 `202` 后停止。GUI 必须等待自己启动的服务 PID 确实退出，不能仅凭 HTTP 响应结束自身。

## 尚未满足的安全目标

- `admin.token` 只做 `chmod(0600)` best effort，Windows ACL 未验证。
- 数据库、Add-on config、归档 job 与日志没有统一权限/敏感信息策略。
- 没有请求体之外的速率限制，也没有 pairing 失败次数限制。
- preview 与 pairing 过期记录不会清理。
- 没有专门的 Origin、代理头和 DNS rebinding 测试。

这些是当前风险，不应在其他文档中写成已经实现的保证。
