# 卡片领域模型

## Card

卡片是系统的核心单位，而不是单词或义项。第一版每张卡关联一个单词；领域模型应允许未来关联少量多个单词，但不得为此提前增加第一版导入字段。

通用属性：

| 字段 | 含义 |
|---|---|
| `card_id` | 应用生成的永久稳定 ID（建议 UUIDv7） |
| `card_type` | 内置卡型标识 |
| `schema_version` | 该卡型结构化字段版本 |
| `structured_fields` | 卡型定义的纯文本字段 |
| `front_html`, `back_html` | 当前交付给下游的 HTML |
| `html_origin` | `renderer` 或 `anki_manual` |
| `renderer_version` | 最近一次自动渲染器版本 |
| `render_input_hash` | 自动渲染输入摘要 |
| `revision` | 每次有效变更后单调递增 |
| `created_at`, `updated_at`, `deleted_at` | 服务端时间戳；删除为软删除 |

## 第一版卡型

两种卡型字段相同：

```text
word, phonetic, definition, example, notes
```

全部字段为纯文本。渲染前必须 HTML 转义；换行按统一规则变为段落或 `<br>`。不解析 Markdown 或原始 HTML。

### `standard_definition`

- 正面：单词、例句。
- 背面：单词、音标、释义、例句、备注。

### `single_definition_word`

- 正面：单词。
- 背面：单词、音标、释义、例句、备注。

空的可选字段不渲染其标题或空容器。`word` 与 `definition` 必填；其余字段是否必填由第一版 schema 明确固定，推荐允许为空。

## HTML 状态规则

结构化字段是自动逻辑的唯一输入真源，HTML 是持久化派生产物，但 Anki 手动编辑可以成为当前 HTML：

1. 导入或修改结构化字段：调用对应内置渲染器，覆盖当前 HTML，`html_origin=renderer`。
2. Anki 回写 HTML：只替换当前 HTML，保留结构化字段，`html_origin=anki_manual`。
3. 此后再次修改结构化字段：重新渲染，旧手工 HTML 作废。
4. 渲染器升级：HTML 标记为陈旧；按需重建。若当前 HTML 来自手工修改，不因单纯版本升级自动覆盖，只有结构化字段变更才覆盖。此条避免软件升级无意抹掉用户操作。

## Revision

每次导入、结构化编辑、自动重渲染、Anki HTML 回写和删除都追加不可变 revision。revision 保存变更后的完整快照、变更来源、原因和服务端提交时间。第一版支持查看，不提供恢复接口。

## Source provenance

来源不参与去重或更新判断。每张新卡至少记录：

- 外部 `job_id`、job 内行号；
- `generator.name` 与可选版本；
- 可选来源描述、来源 URI 或文件名；
- 可选原始载荷或摘要；
- 创建时间。

大载荷与隐私数据允许只保存摘要。相同来源重复提交始终产生新 Card。

## 删除

本地与 Anki 的删除都转换为软删除和新 revision。墓碑保留到所有下游确认删除，且历史长期保留。第一版不做物理清理。

