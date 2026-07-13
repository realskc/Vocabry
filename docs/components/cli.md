# `vocab` CLI 设计

## 原则

- 只调用 `vocabd` API，不读取数据库。
- 面向人类的默认输出清晰；自动化命令支持稳定 JSON 输出。
- 服务未运行、未认证、校验失败和冲突使用不同退出码。

## 第一版命令

```text
vocab                       # 检查服务并触发 ingest，展示摘要
vocab ingest
vocab sync [--wait]
vocab status
vocab card list [filters] [--json]
vocab card show <id> [--json]
vocab card add
vocab card edit <id>
vocab card delete <id>
vocab card history <id>
vocab preview [<id>]
```

`card edit` 把结构化字段写入安全临时 JSON，调用 `%EDITOR%`，关闭后带 `expected_revision` 提交。校验失败时保留临时文件路径供修正。第一版无显式 history restore。

`preview` 请求服务生成短时同源预览 URL，再调用系统浏览器；浏览器页面不能获得可用于通用 API 的长期管理 token。

## 退出码建议

```text
0 success
2 CLI usage error
3 daemon unavailable
4 authentication/pairing error
5 validation/import failure
6 revision conflict
7 synchronization failure
```

