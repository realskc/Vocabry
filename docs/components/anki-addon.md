# Anki Add-on

> 状态：已有可安装实现；具体 hook 和线程行为仍须在声明支持的 Anki 版本上实测。

## 定位

Anki Add-on 是 Vocabry 与 Anki collection 之间的薄适配器。它翻译身份和事件，不拥有 Card 领域规则。

## 职责

- 使用一次性配对码换取独立、可撤销的客户端 token。
- 创建或验证专用 Note Type：`ExternalCardId`、`Front`、`Back`。
- 监听受管 Note 的用户修改和删除，并回传 `vocabd`。
- 在 Anki 允许的主线程/collection 上下文中应用服务事件。
- 幂等处理事件，成功后 ack，并在重连时执行身份和游标对账。
- 离线时保存足以保全用户变化的最小观察状态。

## 非职责

- 不实现卡型 schema、HTML renderer、导入或数据库逻辑。
- 不清除用户的普通标签或修改非受管字段。
- 不用本地墙上时钟决定同步冲突。
- 不把连接失败变成阻塞 Anki 正常复习的故障。

## 交互边界

| 对方 | 输入 | 输出 |
|---|---|---|
| `vocabd` | 待同步 revision、配对与对账结果 | 用户变化、ack、Note 身份 |
| Anki collection | 受管 Note、hooks | Note 创建、更新、删除结果 |
| 用户 | 配对码、Anki 内编辑 | 非阻塞连接与同步状态 |

## 必须保持

- [`SYNC-001`](../INVARIANTS.md#sync-001-card-与受管-note-一一映射)
- [`SYNC-002`](../INVARIANTS.md#sync-002-事件消费幂等)
- [`SYNC-003`](../INVARIANTS.md#sync-003-成功后才推进游标)
- [`SYNC-004`](../INVARIANTS.md#sync-004-较旧事件不能覆盖更新的-anki-用户操作)

## 主要故障表现

- `vocabd` 离线：Anki 继续工作；Add-on 显示非阻塞状态并保全待回传变化。
- token 无效：停止写入并提示重新配对，不能无限重试刷日志。
- ack 丢失：事件可安全重放。
- Note ID 漂移：通过 `ExternalCardId` 重新识别并修复映射。
- hook 能力不足或版本变化：关闭受影响的写入路径并明确报告，不猜测用户操作。

## 修改影响

修改 Note Type、身份规则、hook 或本地观察状态会影响同步协议、迁移和支持版本矩阵。领域规则变化通常只修改 `vocabd`；若需要同时修改 Add-on，应检查是否正在破坏薄适配器边界。

## 进一步入口

- [Anki 同步协议](../protocols/anki-sync.md)
- [本地 API](../protocols/local-api.md)
- [ADR-0005：薄 Anki 适配器](../decisions/0005-thin-anki-adapter.md)
- [验证策略](../quality/verification.md)
