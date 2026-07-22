# Generator 协议与 Word Query

本文定义 GUI 与内置无界面 generator 之间的稳定协议，以及 Word Query 当前工作流。用户可见流程见[使用流程](../product/workflows.md)，版本历史见 [`archive/updates/`](../archive/updates/README.md)。

## 进程与传输

GUI 启动 generator 子进程，通过 stdin/stdout 传输 UTF-8 JSON Lines：每行恰好一个 JSON object，不允许跨行消息。stdout 只能包含协议消息；日志和 traceback 只能写 stderr。

UTF-8 是协议本身的一部分，不能依赖 Windows 当前代码页。GUI 启动 Python generator 时显式设置 UTF-8 I/O 环境，generator 入口同时重新配置 stdin、stdout 和 stderr。中文、国际音标或其他 Unicode 内容无法编码时必须成为测试失败，不能静默丢弃 candidate。

每条消息必须包含字符串 `type`。任务消息使用唯一 `task_id`；未知消息、乱序状态、错误 task ID、裸文本或非法 JSON 均属于协议故障。

## Manifest 与握手

manifest 至少声明：

```json
{
  "id": "word-query",
  "name": "单词查询",
  "version": "0.2.0",
  "protocol_version": 1,
  "layout": "chat-v1",
  "module": "vocabry.generators.word_query",
  "required_credentials": ["deepseek"]
}
```

严格握手为：

```text
generator → hello（id、protocol_version、layout）
GUI       → initialize（manifest 声明的凭据和任务无关配置）
generator → initialized
generator → 运行时欢迎消息
GUI       → 开放用户输入
```

`hello` 必须与 manifest 一致。初始化完成前的其他运行时消息、握手超时或进程退出都使启动失败。初始化凭据消息禁止进入日志或测试失败输出。

## `chat-v1` 消息能力

协议 v1 至少表达：

- `user_input`、`status` 和纯文本 `message`；
- 唯一 `candidate`，包含 `card_type` 和 `fields`；
- `cancel` / `cancelled`；
- `network_timeout`、`retry` 和不可重试 `error`；
- `candidate_action`：`added` 或 `discarded`；
- `ready_for_input` 与 `shutdown`。

聊天内容当前只支持 `content_type=text`，GUI 按纯文本并保留换行。Markdown 若加入必须使用新内容类型；未知类型不能猜测渲染。generator 或 LLM 不能向聊天区提供 HTML。

candidate 只能选择 Vocabry 白名单卡型并填写结构化字段，不能提供 `card_id`、revision、Anki Note ID、HTML 或 renderer。未知卡型和字段由核心校验拒绝。

## 任务失败与重试

一个任务的 LLM、协议、候选校验、渲染或 GUI 处理任一失败，整个任务失败，不能添加部分结果。普通技术故障显示任务 ID 并写入脱敏日志，不提供自动或人工重试。

唯一可重试情况是明确的 DeepSeek 网络超时。generator 在发送前冻结完整 HTTP 请求体；用户点击重试时必须原样重发同一个请求，不能重新生成 prompt 或前序解释。超时不证明服务端没有处理请求，因此 UI 应允许用户理解可能发生重复调用和费用。

取消是正常操作。GUI 发送当前 `task_id`，generator 丢弃整个任务结果并返回 `cancelled`。有限时间内不响应时 GUI 可以结束自己启动的子进程。

## Word Query

Word Query 接受英语单词或词组；除英文字母、空格、连字符和撇号外，也允许用 `.` 或 `…` 表示句型中的省略部分。查询必须至少包含一个英文字母。业务输入不合法时不调用 DeepSeek，而是返回中文纯文本引导；这不是技术故障。

两轮请求均使用 `deepseek-v4-flash`，请求体必须显式携带 `"thinking":{"type":"disabled"}`。DeepSeek 当前默认开启思考模式，因此不能依赖省略字段来表达非思考调用。模型和思考开关都由统一的冻结请求构造器写入，解释请求、制卡请求及超时后的原样重试必须保持一致。

每次单词或词组查询都是独立任务和独立 LLM 对话：

1. 使用中文 prompt 请求中文解释，包括主要词性、常见中文释义、用法细节和英文例句；
2. 第一轮解释返回后，GUI 展示解释，同时 generator 在同一对话中追加第二轮制卡请求；
3. 第二轮把第一轮 assistant 内容作为上下文，生成且只生成一张 `word_only`；
4. `word` 保持英文，`phonetic` 使用音标，`definition` 与 `notes` 使用中文，`example` 使用英文；
5. generator 解析并通过 `CardInput` 校验后发送 candidate；下一次查询不能继承本任务上下文。

“展示解释”和“追加第二轮请求”在第一轮完成后可以并行，但第二轮在语义上依赖第一轮对话，不能作为独立请求重做。

## 必须保留的测试边界

直接调用 DeepSeek HTTP client 只能证明 API 和内容解析，不能证明子进程协议。真实端到端测试必须实际启动 Word Query，走完整握手和两轮 DeepSeek 调用，并断言：

- stdout 每行能按 UTF-8 解码为 JSON；
- 收到两条中文进度消息和中文解释；
- 最终收到包含中文或音标 Unicode 的 candidate；
- candidate 可由 `CardInput` 接受；
- `discarded` 后 generator 回到 `ready_for_input` 并能正常关闭。

这项边界专门防止“API 测试通过，但 candidate 因 Windows 本地编码在 stdout 写出时崩溃”的回归。
