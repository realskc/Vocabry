# 安全边界

> 文档角色：解释威胁、信任边界和安全取舍。精确实现应由配置、schema 和安全测试证明。

## 资产与威胁

需要保护的资产包括 Card 内容与历史、Anki 受管 Note、管理和 Add-on token、SQLite 与备份，以及外部 job 中可能包含的来源信息。

第一版主要威胁：

- 恶意网页访问 localhost API；
- 同机其他进程猜测端口、配对码或 token；
- job ID 和 manifest 文件名造成路径穿越；
- 超大或畸形 job 耗尽资源；
- Anki 回写 HTML 在预览页面执行脚本或导航；
- 伪造 `ExternalCardId` 修改不属于当前库的记录；
- 日志、URL 或配置文件泄露长期凭据。

第一版是单用户本地产品，不把已经控制当前 Windows 用户会话的恶意程序视为可完全防御的对手；仍通过 ACL、token 和最小权限降低意外泄露与跨应用访问。

## 信任边界

| 边界 | 默认信任 |
|---|---|
| 外部生成器与 job | 不信任路径、编码、大小和字段内容 |
| 浏览器页面 | 不持有管理能力；页面来源和嵌入 HTML 分别隔离 |
| 管理 API 客户端 | 可持有管理 token，但请求仍由服务校验 |
| Anki Add-on | 配对后的独立客户端；只信任已登记的身份和受管字段 |
| Anki 用户操作 | 视为高优先级手工意图，但必须匹配真实 `ExternalCardId` |

## 必须控制

### 本地 API

- 只绑定 `127.0.0.1`，拒绝非 loopback Host/来源策略绕过。
- 除最小健康检查和一次性配对入口外，HTTP 与 WebSocket 强制 token。
- token 高熵、可撤销，数据库只保存哈希和必要元数据。
- 完全不启用 CORS；配对码短时且单次使用；健康检查只返回最少信息。

对应 [`SEC-001`](../INVARIANTS.md#sec-001-业务边界默认不公开)。

### 文件系统与日志

- Windows 配置、数据库、备份和 token 文件 ACL 限制为当前用户。
- job ID 与载荷文件名采用允许列表，并确认解析后路径仍在 job 目录内。
- 限制单 job 文件数、总大小、单行大小和卡片数。
- 日志不记录 token，不默认记录完整敏感原始载荷。

对应 [`SEC-003`](../INVARIANTS.md#sec-003-外部文本和路径不受信任)。

### HTML 与预览

- 纯文本字段在 renderer 中统一 HTML 转义。
- 预览使用短时、限定用途的 session，不把管理 token 放进 URL 或页面。
- Anki 回写 HTML 放入严格 sandbox iframe，禁止脚本、表单、顶层导航和任意源访问。

对应 [`SEC-002`](../INVARIANTS.md#sec-002-浏览器不持有管理能力) 和 `SEC-003`。

## 需要实现验证的问题

- Windows 打包后配置目录和备份文件能否稳定应用预期 ACL。
- FastAPI/Uvicorn 对 Host、WebSocket 和代理相关头的实际处理是否符合 loopback 假设。
- 预览 session 是否真正只能访问所需卡片和只读资源。
- 目标 Anki 版本中 Add-on token 的存储暴露范围。

任何放宽绑定地址、CORS、iframe sandbox 或预览权限的提议都属于架构与安全边界变化，需要 ADR 和威胁复核。
