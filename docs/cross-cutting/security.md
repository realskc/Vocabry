# 安全设计

## 威胁边界

主要风险包括恶意网页访问 localhost、同机其他进程猜测接口、token 泄露、路径穿越、恶意 HTML 预览和未经授权的 Anki Note 篡改。

## 控制措施

- API 只绑定 `127.0.0.1`，拒绝非 loopback Host/来源策略绕过。
- 所有业务 API 和 WebSocket 强制独立客户端 token；token 高熵、可撤销、仅存哈希。
- 完全不启用 CORS；预览同源且使用短时最小权限 session。
- Windows 配置、数据库和 token 文件 ACL 限制为当前用户。
- job ID 与 manifest 文件名采用允许列表，并验证解析后的真实路径仍位于 job 目录。
- 限制单 job 文件数、总大小、单行大小和卡片数，防止资源耗尽。
- 纯文本字段统一 HTML 转义；Anki 回写 HTML 在预览时置于严格 sandbox iframe。
- 日志不记录 token，不默认记录完整敏感原始载荷。
- 配对码短时、单次使用；健康检查只返回最少信息。

## 信任 Anki 用户操作

用户在已配对 Anki Profile 中对受管 Note 的修改被视为高优先级手动操作。但 Add-on 必须验证 `ExternalCardId` 存在于本地库，不能允许任意伪造 ID 修改其他记录。

