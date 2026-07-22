# 桌面 GUI 与进程生命周期

本文记录桌面宿主的长期设计语义。版本实施流水与历史验收记录放在 [`archive/updates/`](../archive/updates/README.md)，用户操作步骤见[使用流程](../product/workflows.md)。

## 系统边界

Vocabry GUI 是本地桌面宿主，不是数据库所有者。它管理用户交互和子进程，但所有 Card 写入、revision、outbox event 和 HTML renderer 仍由 `vocabd` 负责。

GUI 在创建任何窗口前，将系统默认应用字体统一增加 1.5pt。所有普通 Qt 控件继承这一字体；卡片 HTML 预览仍由 renderer 样式决定，不随宿主字体设置改变。

```text
用户
 │
 ▼
Vocabry GUI ── HTTP/admin token ── vocabd ── SQLite
 │
 └── stdin/stdout JSON Lines ── headless generator
```

generator 不取得 admin token、不直接访问 SQLite，也不提交 HTML。GUI 从 generator 接收卡型与结构化字段，交给 `vocabd` 校验和渲染；用户确认后再通过 Card API 创建。

## 服务所有权

GUI 与 `vocabd` 是不同进程。GUI 启动前检查配置端口：已有 Vocabry 或其他程序占用端口时均拒绝启动，不连接、不接管也不终止外部进程。只有健康检查返回正确的服务身份和 API 版本后，GUI 才开放功能。

关闭窗口后 GUI 进入不可逆关闭状态：

1. 取消活动 generator 任务并关闭所有由 GUI 启动的 generator；
2. 用 admin token 请求 `vocabd` 优雅退出；
3. 等待服务 PID 确实消失；
4. 超时后记录故障并强制结束自己拥有的 PID；
5. 只有确认服务进程结束后，GUI 才退出。

HTTP shutdown 响应只表示服务接受请求，不能作为进程已经退出的证据。

## Generator 发现和页面生命周期

GUI 扫描应用内置 manifest，并按 manifest 的显示名称生成入口。当前不安装或执行用户提供的第三方程序。manifest 只保存身份、版本、入口模块、协议、版式和所需凭据；欢迎语等运行时内容由 generator 通过协议发送。

generator 在用户进入页面时按需启动，离开页面时关闭：

- 空闲离开可直接关闭；
- 有活动任务或未处理候选卡时，GUI 先提示取消和丢弃；
- 页面会话内保留对话历史，离开即清空，不持久化；
- generator 崩溃属于当前任务的技术故障，GUI 不自动重启以掩盖持续问题。

当前唯一版式是 `chat-v1`。版式实现属于 GUI；generator 不能创建 Qt 控件或传入自定义界面代码。未来增加版式时应使用新的显式 layout 标识，不能改变既有 `chat-v1` 的含义。

## 候选卡交互

GUI 只做非空、长度等通用输入限制，业务输入规则属于 generator。一个 `chat-v1` 页面同一时刻只处理一个候选：

输入框只有在 generator 完成初始化且当前没有活动任务时可用。“发送”按钮还要求输入去除首尾空白后非空；文字变化时必须立即刷新按钮状态。回车与点击按钮调用同一提交路径，不能出现按钮禁用但回车仍可提交的状态分叉。

```text
等待输入 → 执行任务 → 展示解释与候选 → 等待添加/放弃 → 等待下一输入
```

候选卡未处理前禁止开始下一任务。预览静态并排显示正反面，不模拟复习、翻面或评分。预览和最终 Card 创建必须复用 `vocabd` 的卡型校验及 renderer。

添加前 GUI 按规范化单词查询已有 Card。同词只触发警告和二次确认，不自动覆盖、合并或更新。创建成功后才通知 generator `added`；放弃不写数据库并通知 `discarded`。如果 Card 已提交但 generator 通知失败，数据库结果不回滚，GUI 记录严重状态分叉并关闭页面。

## 凭据

GUI 在 Windows Credential Manager 中管理一份共享 DeepSeek Key。多个 manifest 可以声明使用 `deepseek`，但 GUI 只向明确声明的 generator 传递该凭据。

凭据采用启动快照：generator 初始化时取得当前值；之后修改或删除 Key 不影响已启动进程，只影响新启动进程。Key 不写入项目配置、数据库、命令行、日志或异常文本。模型、API 地址、prompt 和生成参数属于具体 generator，不是 GUI 的共享设置。

Windows Credential Manager 按 Windows 用户身份隔离。不同账户即使运行同一个虚拟环境，也看不到彼此保存的 Key；测试结果必须结合实际执行身份解释。

## 日志与诊断

日志位于 Vocabry 数据目录并按 GUI、`vocabd` 和 generator 分文件。GUI 捕获 generator stderr；stdout 是协议专用通道，不能作为日志保存。一次任务的各组件记录使用同一 `task_id` 关联。

日志必须轮转并脱敏 Authorization header、API Key、初始化凭据消息和其他秘密。用户界面展示可回查的任务 ID，不直接展示 traceback。GUI 提供打开日志目录的入口。

## Anki 配对入口

GUI 通过 admin API 生成五分钟一次性配对码，用户在 Anki Add-on 中手工输入。GUI 不直接读取或修改 Anki Add-on config。配对状态与数据库身份、cursor 重置规则见 [Anki 同步](anki-sync.md)。
