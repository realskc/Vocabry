# Vocabry 系统地图

> 文档角色：建立系统级心智模型。组件内部实现不在这里展开。

## 组件与通信边界

```text
External generators
       │ offline import v1
       ▼
    vocabd ───────── SQLite
      ▲  ▲
 HTTP │  │ authenticated WebSocket + HTTP
      │  ▼
 API clients     Anki Add-on ⇄ Anki collection
      │
      └──────── Browser preview (same-origin page from vocabd)
```

| 组件 | 系统定位 | 拥有的状态 | 主要边界 |
|---|---|---|---|
| `vocabd` | 业务核心与本地服务 | Card、revision、job、事件、映射和客户端身份 | 文件系统导入、本地 API、同步协议 |
| API 客户端 | Coding Agent、脚本或其他管理工具 | 不持有业务状态 | 本地 HTTP API |
| Anki Add-on | Anki 的薄适配器 | token 与必要的轻量观察状态 | 本地 API、Anki hooks/collection |
| 浏览器预览 | 当前 HTML 的只读检查界面 | 短时预览 session | 同源预览 API |
| 外部生成器 | 卡片生产者 | 自己的生成上下文 | 离线导入协议 |

组件级职责、非职责和修改影响见 [`components/`](../components/)。

## 三条主数据流

### 生成与导入

外部生成器只依赖已发布的离线协议，把完整 job 从 `staging` 原子移动到 `inbox`。认证客户端调用 ingest 后，`vocabd` 领取、完整校验并在单个事务中创建 Card、HTML、来源和初始 revision。协议见[离线导入](../protocols/offline-import.md)。

### 本地管理与预览

Coding Agent、脚本或其他客户端通过认证 HTTP API 查询或修改 Card。修改或删除既有 Card 时携带 `expected_revision`，并发冲突由调用者显式处理。预览页面由 `vocabd` 同源托管，只获得短时、最小权限的访问能力。协议见[本地 API](../protocols/local-api.md)。

### Anki 双向同步

`vocabd` 持久化待同步事件，Add-on 主动连接并在 Anki 允许的上下文中应用。Anki 用户产生的 HTML 修改和删除通过 Add-on 回写；断线后依靠持久事件、游标和身份对账收敛。协议见[Anki 同步](../protocols/anki-sync.md)。

## 依赖方向

- 领域层不依赖 FastAPI、Typer、Anki 或文件系统布局。
- 应用层编排领域对象、事务、渲染器和同步用例。
- HTTP、SQLite、文件导入及 Anki 都是适配器。
- 只有 `vocabd` 可以打开业务数据库。
- Add-on 不拥有卡型 schema、HTML renderer 或导入规则。

建议的实现边界尚未落地，当前方案为：

```text
src/vocab/
  domain/
  application/
  adapters/
    database/
    import_fs/
    http/
    rendering/
  daemon/
anki_addon/
demo_generator/
```

## 运行形态

- `vocabd start`：前台运行，面向开发和排错。
- `vocabd install`：第一版在当前 Windows 用户会话中注册后台启动。
- `vocabd status|stop`：检查或停止服务。
- 第一版不提供独立的 `vocab` 管理 CLI；导入、管理、预览 session 与显式对账由认证 API 调用触发。原因和重新评估条件见 [ADR-0006](../decisions/0006-api-only-management.md)。

## 技术选择

- Python、FastAPI、Uvicorn、Pydantic、Typer。
- SQLite，schema 迁移使用 Alembic。
- Anki Add-on 只使用 Anki 自带 Python 环境和标准库。
- Windows 发布物最终打包为独立可执行文件。

选择原因和重新评估条件见[架构决策记录](../decisions/README.md)。
