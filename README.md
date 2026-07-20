# Vocabry

一个以本地卡片库为核心、通过 Anki 复习的英语词汇卡片管理系统。当前包含可运行的本地服务、SQLite 卡片库、原子文件导入、HTTP/WebSocket API、安全预览、Demo 生成器和 Anki Add-on。

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
.\.venv\Scripts\vocabd start --data-dir .vocabry
```

首次启动后，管理 token 位于 `.vocabry/admin.token`。认证后的 OpenAPI schema 位于 `/api/v1/openapi.json`；服务不公开交互式文档页面。

生成并导入示例：

```powershell
.\.venv\Scripts\vocabry-demo .vocabry\exchange
$token = (Get-Content -Raw .vocabry\admin.token).Trim()
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/api/v1/ingest -Headers @{Authorization="Bearer $token"}
```

运行测试：`.\.venv\Scripts\pytest -q`。项目设计和约束见[项目驾驶舱](docs/PROJECT.md)。

Anki Add-on 位于 `anki_addon/`；将该目录作为一个 Add-on 安装，启动 `vocabd` 后在 Anki 的“工具”菜单选择 “Pair Vocabry…”。
