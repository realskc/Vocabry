# Vocabry 系统架构

## 组件

```text
External generators
       │ filesystem jobs
       ▼
    vocabd ───────── SQLite
      ▲  ▲
 HTTP │  │ authenticated WebSocket
      │  ▼
 vocab CLI      Anki Add-on ⇄ Anki collection
      │
      └──────── Browser preview (same-origin page from vocabd)
```

### `vocabd`

唯一数据库写入者和业务规则执行者。负责导入、校验、版本、渲染、API、事件日志及同步游标。

### `vocab`

无本地业务状态的 CLI 客户端。服务不可用时返回明确错误，绝不绕过服务直接访问 SQLite。

### Anki Add-on

薄集成层。监听受管 Note 的修改和删除，将其回传；接收本地变更并在 Anki 主线程中应用。卡型和渲染业务不放入 Add-on。

### 预览器

由 `vocabd` 提供同源页面，通过 API 获取 `front_html` / `back_html`，提供预设样式、翻面和切换；只读且不模拟 Anki 的全部 CSS。

## 依赖方向

- 领域层不依赖 FastAPI、Typer、Anki 或文件系统布局。
- 应用层编排领域对象、事务、渲染器和同步用例。
- HTTP、CLI、SQLite、文件导入及 Anki 是适配器。
- 只有 `vocabd` 可打开业务数据库。

建议的 Python 包边界：

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
  cli/
anki_addon/
demo_generator/
```

## 运行生命周期

- `vocabd start`：前台运行，适合开发与排错。
- `vocabd install`：第一版在当前 Windows 用户会话中注册后台启动。
- `vocabd status|stop`：检查或停止服务。
- 裸 `vocab` 与 `vocab sync` 先请求服务执行一次 ingest；查询命令不隐式写库。

## 技术选择

- Python、FastAPI、Uvicorn、Pydantic、Typer。
- SQLite；schema 迁移使用 Alembic。
- Anki Add-on 仅使用 Anki 自带 Python 环境和标准库，避免安装第三方依赖。
- Windows 发布物最终打包为独立可执行文件。
