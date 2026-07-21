# 使用流程

本文描述当前仓库真正支持的操作。示例使用 PowerShell，默认在项目根目录执行。

## 安装和启动

Vocabry 需要 Python 3.11 或更高版本。

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
.\.venv\Scripts\vocabd start --data-dir .vocabry
```

服务默认监听 `127.0.0.1:8765`。数据目录中会出现管理 token、SQLite 数据库和 `exchange` 文件交换目录。若未传 `--data-dir`，服务优先读取 `VOCABRY_DATA_DIR`，否则在 Windows 使用 `%LOCALAPPDATA%\Vocabry`。端口可用 `--port` 或 `VOCABRY_PORT` 指定；监听地址固定为本机回环地址。

`vocabd status --data-dir <path>` 只报告数据库与 token 文件是否存在，不检查进程是否正在运行。当前没有 install、stop 或后台服务命令。

## 获取管理 token

```powershell
$token = (Get-Content -Raw .vocabry\admin.token).Trim()
$headers = @{ Authorization = "Bearer $token" }
```

管理 token 应视为密码，不要放进 URL、日志或提交到 Git。OpenAPI schema 位于 `/api/v1/openapi.json`，也需要管理 token；服务不开放 Swagger 或 ReDoc 页面。

## 创建与查看卡片

创建请求还需要一个由调用者生成的 `Idempotency-Key`。同一客户端用同一 key 重试相同请求只会得到原结果；用同一 key 发送不同内容会得到冲突错误。

```powershell
$body = @{ card_type = "single_definition_word"; word = "concise"; definition = "简明的"; phonetic = "/kənˈsaɪs/"; example = "Keep the answer concise."; notes = "" } | ConvertTo-Json
$card = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/api/v1/cards `
  -Headers ($headers + @{ "Idempotency-Key" = [guid]::NewGuid().ToString() }) `
  -ContentType "application/json" -Body $body
```

修改和删除必须携带当前的 `expected_revision`。如果返回 `409 revision_conflict`，先重新读取卡片，再决定是否重新应用修改。

## 批量导入

仓库自带的 Demo 生成器可以创建一个合规 job：

```powershell
.\.venv\Scripts\vocabry-demo .vocabry\exchange
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/api/v1/ingest -Headers $headers
```

生成器只把任务投递到 `inbox`；任务不会因为目录出现而自动导入。调用 ingest 后，结果被归档到 `succeeded/<job-id>/result.json` 或 `failed/<job-id>/result.json`。用 `--invalid` 可以生成故意缺少释义的任务，验证整批失败。

自定义生成器需要遵守[离线导入设计](../design/offline-import.md)。

## 浏览器预览

预览前向 `POST /api/v1/preview/sessions` 提交 `card_id`。返回的 `path` 在 10 分钟内有效，只能查看指定卡片。页面分别展示正反面，并在无权限 iframe 中呈现当前 HTML。当前预览器没有翻面动画、卡片浏览或编辑功能。

## 安装并配对 Anki Add-on

`anki_addon/` 是插件源码，`anki_addon/anki_addon.zip` 是当前打包产物。安装后确保 `vocabd` 正在运行。

使用管理 token 调用 `POST /api/v1/pairing/codes`，然后在 Anki 的“工具”菜单选择 “Pair Vocabry…”并输入配对码。配对码 5 分钟后过期且只能使用一次。插件会创建名为 `Vocabry` 的 Note Type 和牌组，并开始接收已有事件。

当前 Add-on 是原型，尚未声明支持的 Anki 版本。正式数据上使用前请阅读[当前状态](../STATUS.md)和[同步设计](../design/anki-sync.md)。

## 运行测试

```powershell
.\.venv\Scripts\pytest -q
```

测试需要通过 `.[dev]` 安装 `pytest` 与 `httpx`。仓库测试覆盖核心数据库、导入、API、预览和 WebSocket 基本路径，但不覆盖真实 Anki 与 Windows 打包。
