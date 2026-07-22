# 卡型与 Generator

本文是当前产品中全部内置卡型和 generator 的人类可读目录。新增、删除或改变卡型与 generator 时必须同步更新本文；精确字段校验仍以代码和 API schema 为事实源。

## 卡片的共同字段

当前两种卡型使用相同的纯文本字段：

| 字段 | 必填 | 用户看到的内容 |
|---|---|---|
| `word` | 是 | 英语单词 |
| `phonetic` | 否 | 音标 |
| `definition` | 是 | 释义 |
| `example` | 否 | 例句 |
| `notes` | 否 | 补充说明 |

卡片 HTML 不显示 “Example”“Pronunciation”“Definition”“Notes”等字段名称。字段的顺序、内容形态和卡面样式已经能表达其用途，省略标签可以减少无意义的视觉占用。空的可选字段不会产生对应区块。

## 内置卡型

### `standard_definition`

面向“看到单词和语境，回忆释义”的常规词汇复习。

- 正面：单词、例句（若有）。
- 背面：单词、音标、释义、例句、备注；只展示非空内容。
- 当前生产者：`vocabry-demo`，也可由 API 或文件导入创建。

### `word_only`

面向“只看到单词，直接回忆一个释义”的简洁复习。

- 正面：仅单词。
- 背面：单词、音标、释义、例句、备注；只展示非空内容。
- 当前生产者：单词查询、`vocabry-demo`，也可由 API 或文件导入创建。

两种卡型的 `word` 和 `definition` 都必填。所有输入按纯文本处理并进行 HTML 转义；换行在卡面中保留。Vocabry 当前不允许 generator 动态定义新卡型或自带 HTML renderer。

## 内置 Generator

### 单词查询（`word-query`）

GUI 中的交互式 generator。用户输入一个英语单词后，它使用共享的 DeepSeek API Key 调用 `deepseek-v4-flash`，并显式关闭思考模式：

1. 在独立 LLM 对话中生成中文解释；
2. 把解释作为同一对话上下文，追加制卡请求；
3. 生成唯一一张 `word_only` 候选卡；
4. `word` 保持英文，`phonetic` 使用音标，`definition` 与 `notes` 使用中文，`example` 使用英文；
5. 用户在 GUI 中选择添加或放弃。

单词查询不直接写数据库，也不生成 HTML。它通过 UTF-8 JSON Lines 把结构化候选交给 GUI，再由 `vocabd` 校验、预览和保存。

### Demo 生成器（`vocabry-demo`）

用于演示和验证原子文件导入协议的命令行 generator。它在指定 exchange 目录创建一个完整 job，内含：

- 一张 `standard_definition` 示例卡；
- 一张 `word_only` 示例卡；
- 描述 generator 名称、版本和 payload 的 manifest。

它只负责把 job 原子移动到 `inbox`，不会自动触发导入。`--invalid` 会故意生成缺少必填字段的任务，用来验证整批失败且不产生部分 Card。它是协议示例和诊断工具，不是面向日常制卡的 GUI 工作流。

## 非 Generator 的参与者

- Vocabry GUI 是 generator 宿主和管理界面，本身不生成词汇内容。
- `vocabd` 校验、渲染、保存并发布同步事件，不是 generator。
- Anki Add-on 消费已经保存的 Card 并适配 Anki，也不是 generator。
- 外部脚本或 Coding Agent 可以遵守文件或 HTTP 边界创建 Card，但只有纳入产品的具体 generator 才列入上面的内置目录。
