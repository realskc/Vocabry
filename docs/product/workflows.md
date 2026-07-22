# 使用流程

本文描述当前仓库真正支持的操作。示例使用 PowerShell，默认在项目根目录执行。

## 安装和启动

Vocabry 需要 Python 3.11 或更高版本。

### 桌面 GUI

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
.\.venv\Scripts\vocabry-gui
```

GUI 自动启动自己的 `vocabd`。如果默认端口已经被 Vocabry 或其他程序占用，GUI 会拒绝启动；它不会连接或结束外部服务。关闭 GUI 时会先结束已打开的 generator，再请求服务优雅退出，确认服务进程结束后 GUI 才退出。

在“设置”中输入 DeepSeek API Key 后进入“单词查询”。输入一个英语单词或词组，GUI 会展示中文解释和唯一一张 `word_only` 候选卡的正反面；卡片释义与备注使用中文，例句使用英文。处理当前卡片前不能开始下一项任务：选择“添加”会通过 API 保存卡片，选择“放弃”不写数据。同词卡会警告但仍允许二次确认添加。

GUI 与 generator 之间的 stdin/stdout 协议固定使用 UTF-8 JSON Lines。Windows 本地代码页不能参与协议编码，否则中文、音标等字符可能让候选消息无法写出。

API Key 保存于 Windows Credential Manager。修改或删除只影响之后启动的 generator；已经启动的进程继续使用初始化时的凭据快照。

### 单独启动服务

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
$body = @{ card_type = "word_only"; word = "concise"; definition = "简明的"; phonetic = "/kənˈsaɪs/"; example = "Keep the answer concise."; notes = "" } | ConvertTo-Json
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

在 GUI 首页点击“配对 Anki”生成一次性配对码，然后在 Anki 的“工具”菜单选择“配对 Vocabry...”并输入。配对码 5 分钟后过期且只能使用一次。插件会创建名为 `Vocabry` 的 Note Type 和牌组，并开始接收已有事件。

配对 token、cursor 和 managed mappings 都属于某一个具体的 Vocabry 数据库。切换数据目录、重建数据库或服务端不再识别旧 token 时，必须重新配对。新版 Add-on 在配对成功后把 cursor 重置为 0 并清空旧服务的 mappings，确保新数据库中尚未消费的事件不会因旧 cursor 过大而被跳过；已有 Anki Note 不会因此自动删除。

Anki 的“工具”菜单会显示不可点击的 Vocabry 连接状态：未配对、正在连接、已连接、未运行或连接失败。关闭 Vocabry 后状态变为“未运行”，不会弹出错误；服务恢复后 Add-on 自动重连并更新状态。

每个 Vocabry 数据库首次创建时会获得一个永久 `database_id`。Add-on 将它与 `ExternalCardId` 一起写入 Note，用来区分当前数据库卡片、旧数据库卡片和旧版来源未标记的卡片。

需要清理或修复时，在 GUI 首页点击“全量对账 Anki”，并保持 Anki 当前 profile 打开。GUI 会先显示盘点报告，不会在扫描阶段修改 Anki。报告包括缺失卡片、旧版 Note 归属迁移、重复 Note、已删除卡片残留、孤立 Note 和其他数据库 Note；只有确认后才会补建或更新活动卡片并删除报告中的残留 Note，拒绝则不修改 collection。

当前 Add-on 是原型，尚未声明支持的 Anki 版本。正式数据上使用前请阅读[当前状态](../STATUS.md)和[同步设计](../design/anki-sync.md)。

## 运行测试

```powershell
.\.venv\Scripts\pytest -q
```

测试需要通过 `.[dev]` 安装 `pytest` 与 `httpx`。普通测试包含真实 DeepSeek 调用，并有一项端到端测试实际启动 Word Query 子进程，验证中文解释、UTF-8 JSON Lines 和包含中文/音标的 candidate 能完整送达。仓库仍不覆盖真实 Anki UI 与 Windows 打包。
