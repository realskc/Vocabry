# Vocabry

一个以本地卡片库为核心、通过 Anki 复习的英语词汇卡片管理系统。当前包含 Windows-first 桌面 GUI、Word Query、可运行的本地服务、SQLite 卡片库、原子文件导入、HTTP/WebSocket API、安全预览、Demo 生成器和 Anki Add-on。

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
.\.venv\Scripts\vocabry-gui
```

首次使用“单词查询”时，在 GUI 的“设置”中保存 DeepSeek API Key。密钥进入 Windows Credential Manager，不写入项目配置。界面、运行时提示和 DeepSeek 释义使用中文；卡片例句保留英文。

仍可单独启动服务：`.\.venv\Scripts\vocabd start --data-dir .vocabry`。

首次启动后，管理 token 位于 `.vocabry/admin.token`。认证后的 OpenAPI schema 位于 `/api/v1/openapi.json`；服务不公开交互式文档页面。

生成并导入示例：

```powershell
.\.venv\Scripts\vocabry-demo .vocabry\exchange
$token = (Get-Content -Raw .vocabry\admin.token).Trim()
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/api/v1/ingest -Headers @{Authorization="Bearer $token"}
```

运行测试：`.\.venv\Scripts\pytest -q`。修复缺陷前必须先添加并确认失败的回归测试；修改代码后还要同步当前事实文档，具体流程见[开发规范](docs/development.md)。产品介绍、使用方式与技术设计见[项目文档](docs/README.md)。

Anki Add-on 位于 `anki_addon/`；安装 `anki_addon/anki_addon.zip` 并重启 Anki，然后在 GUI 首页生成配对码，在 Anki 的“工具”菜单选择“配对 Vocabry...”完成配对。
