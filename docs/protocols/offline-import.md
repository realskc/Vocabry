# 离线导入协议

> 状态：v1 设计契约，尚未由 schema 和契约测试固化。关联不变量：`IMPORT-001`、`SEC-003`。

## 目标

允许外部生成器与主应用在不同时间运行，通过文件系统交换任务、结果与机器可读错误。生成器不需要导入主应用代码，也不需要网络访问。

## 目录布局

```text
exchange/
  staging/                    # 生成器写入中的私有临时目录
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

exchange 根目录由 `vocabd` 配置并创建。收到认证 ingest 请求后，`vocabd` 只扫描 `inbox` 的直接子目录，不递归解释任意文件；目录出现本身不触发导入。

## 原子投递

生成器必须：

1. 在与 `inbox` 相同卷的 `staging/<temporary-id>` 中写完整任务。
2. 关闭并刷新文件。
3. 将目录原子重命名为 `inbox/<job-id>`。

`job-id` 必须匹配 `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`，且与 manifest 中的 `job_id` 完全相同。已处理过的 `job-id` 不得复用；重试必须使用新 ID，并可在 manifest 中填写 `retry_of`。

## `manifest.json`

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

未知的必需协议版本整批拒绝。未知非关键字段可忽略但必须保留在审计载荷中。

## `cards.jsonl`

UTF-8（无 BOM），每个非空行是一个 JSON 对象。第一版禁止注释。

```json
{"type":"standard_definition","word":"run","phonetic":"/rʌn/","definition":"经营；管理","example":"She runs a small restaurant.","notes":""}
{"type":"single_definition_word","word":"concise","phonetic":"/kənˈsaɪs/","definition":"简明的","example":"Keep the answer concise.","notes":""}
```

## 原子处理

1. 服务将 job 原子移至 `processing`，防止重复领取。
2. 校验 manifest、编码、JSONL、每行 schema 和所有卡型字段。
3. 在单个数据库事务内创建所有 Card、HTML、来源和初始 revision。
4. 任意错误均回滚整个事务。
5. 写入 `result.json` 后，将整个 job 移入 `succeeded` 或 `failed`。
6. 服务崩溃后检查 `processing`，依据数据库中的 job 状态安全续办或完成归档。

## 结果格式

成功：

```json
{"protocol_version":1,"job_id":"demo-20260713-001","status":"succeeded","accepted":2,"card_ids":["...","..."]}
```

失败：

```json
{
  "protocol_version": 1,
  "job_id": "demo-20260713-001",
  "status": "failed",
  "accepted": 0,
  "errors": [{
    "code": "missing_required_field",
    "file": "cards.jsonl",
    "line": 3,
    "field": "definition",
    "message": "Field 'definition' is required."
  }]
}
```

错误代码必须稳定，`message` 面向人类；自动生成器应依据 `code`、`line` 和 `field` 修正。一个 job 尽可能返回全部独立校验错误，而不是只返回首个错误。

## 兼容性与证据

- `protocol_version` 决定必需字段和处理语义；不支持的必需版本整批拒绝。
- 实现阶段以 JSON Schema、合法/非法 golden files 和独立 Demo 生成器作为可执行证据。
- 目录生命周期或事务语义变化必须检查 [`IMPORT-001`](../INVARIANTS.md#import-001-job-全有或全无) 和 [ADR-0003](../decisions/0003-atomic-filesystem-import.md)。
