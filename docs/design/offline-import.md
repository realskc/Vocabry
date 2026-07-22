# 离线导入

离线协议让生成器通过文件系统提交一批卡片，无需依赖 Vocabry Python 包或直接访问数据库。协议版本当前为 1。

## 目录生命周期

```text
exchange/
  staging/<temporary-id>/
  inbox/<job-id>/
    manifest.json
    cards.jsonl
  processing/<job-id>/
  succeeded/<job-id>/
    manifest.json
    cards.jsonl
    result.json
  failed/<job-id>/
    manifest.json
    cards.jsonl
    result.json
```

生成器必须在与 `inbox` 同一文件系统卷的 staging 目录写完两个文件，关闭文件后用原子目录重命名发布到 `inbox/<job-id>`。不要直接在 inbox 中逐个写文件。

目录出现不会自动导入。管理客户端调用 `POST /api/v1/ingest` 后，服务按名称顺序扫描 inbox 的直接子目录。

## job ID 与限制

目录名必须匹配 `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`，manifest 中的 `job_id` 必须与目录名相同。当前限制为：job 普通文件总大小不超过 10 MiB、单行不超过 64 KiB、最多 10,000 张 Card，且 job 根目录只允许 `manifest.json` 和 `cards.jsonl`。

`job_id` 一旦进入数据库，无论成功或失败都不能复用。当前 schema 没有 `retry_of` 的专门语义；实现会保存但不解释额外 manifest 字段。

## manifest

```json
{
  "protocol_version": 1,
  "job_id": "demo-20260713-001",
  "created_at": "2026-07-13T12:00:00+08:00",
  "generator": {"name": "demo-generator", "version": "0.1.0"},
  "payload": {"format": "jsonl", "file": "cards.jsonl"},
  "source": {"description": "demo words"}
}
```

实现实际要求：`protocol_version == 1`、匹配的 `job_id`、字符串 `generator.name`，以及完全等于 `{"format":"jsonl","file":"cards.jsonl"}` 的 payload。`created_at` 和 generator version 当前不校验；额外 manifest 字段会随原始 JSON 保存。

## cards.jsonl

文件必须是无 BOM 的 UTF-8。每个非空行是一个 JSON object，禁止注释。

```json
{"type":"standard_definition","word":"run","phonetic":"/rʌn/","definition":"经营；管理","example":"She runs a small restaurant.","notes":""}
{"type":"word_only","word":"concise","definition":"简明的"}
```

允许用 `type` 或 `card_type` 表示卡型。未知字段会使该行失败。`word` 和 `definition` 是非空字符串，其余字段缺省为空字符串。

## 处理与事务

`JobImporter.process` 的顺序是：

1. 将目录从 inbox 原子移动到 processing，取得处理权。
2. 收集 manifest、文件和每行 Card 的所有可发现校验错误。
3. 合法时，在一个 SQLite 事务中创建 job、全部 Card、初始 revision 和 outbox event。
4. 非法时，在单独事务中记录失败 job，数据库零新增 Card。
5. 原子写入 `result.json`，再把目录移动到终态。

“整批 Card 全有或全无”是协议的硬约束。不要为了流式性能把每行独立提交，除非先做新的协议决策。

## 结果与错误

成功结果包含 `protocol_version`、`job_id`、`status=succeeded`、`accepted` 和 `card_ids`。失败结果包含 `accepted=0` 与 errors；每个 error 尽可能提供稳定 `code`、文件、行和字段。

错误码由 `ImportIssue` 与处理分支定义，包括 `invalid_job_id`、`unexpected_file`、`job_too_large`、`missing_file`、`invalid_manifest`、`unsupported_protocol_version`、`job_id_mismatch`、`missing_required_field`、`invalid_payload`、`line_too_large`、`invalid_encoding`、`too_many_cards`、`invalid_json`、`invalid_card`、`empty_job` 和 `duplicate_job`。

自动生成器应依据 code/line/field 处理错误，不解析面向人的 message。

## 崩溃恢复

成功结果与 Card、revision 和 outbox event 在同一个数据库事务中提交。因此数据库不会再出现“Card 已创建但 job 没有成功结果”的新状态。

服务启动时扫描 processing：

- 数据库没有该 job，说明事务尚未提交；目录移回 inbox 后整批重试。
- 数据库已有结果，说明事务已经提交；重新写入 `result.json` 并完成终态归档。
- 旧版本可能留下 `status=succeeded` 但没有 result 的记录；恢复逻辑按照该 job 的 `card_sources` 重建结果，确认 Card 数量与 accepted 一致后再归档。

若旧记录的来源数量与 accepted 不一致，恢复逻辑不会猜测或自动归档，保留 processing 目录供人工诊断。

自动化测试覆盖数据库提交前失败、提交后尚未归档、旧版缺失 result、result 文件已写但目录尚未移动，以及重复恢复不重复创建 Card。
