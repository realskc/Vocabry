# 技术设计导航

本目录保存仅靠浏览单个函数不容易恢复、但会影响后续修改正确性的上下文。它面向维护者和进入项目工作的 Coding Agent。

产品解释在 [`product/`](../product/README.md)，实现完成度在[当前状态](../STATUS.md)。不要在技术文档中重复面向用户的产品介绍，也不要把代码中的函数列表改写成散文。

## 版本语义

Vocabry 应用版本唯一写在 `pyproject.toml`。运行时 `__version__` 从已安装的 Python 分发元数据读取，GUI 与 API 复用该值。Anki add-on 和 generator 是独立组件，各自维护 manifest 或协议版本，不要求与 Vocabry 应用同步。

完成发布的代码快照用 `vX.Y.Z` Git tag 标记。标签只应指向已经包含该版本全部改动的提交。

## 系统边界

```text
外部生成器
    │ filesystem job
    ▼
  vocabd ───────── SQLite
    ▲  ▲ ▲
HTTP│  │WebSocket + HTTP
    │  │ └── Vocabry GUI ⇄ 内置 headless generators
    │  ▼
管理客户端     Anki Add-on ⇄ Anki collection
    │
    └──── 浏览器预览（由 vocabd 同源提供）
```

`vocabd` 是一致性边界：卡片当前态、历史版本和待同步事件都由它排序并写入。外部生成器、管理客户端、预览页和 Add-on 不直接打开 SQLite。

这个边界不是为了隐藏 SQLite，而是为了让一次修改的三个结果处在同一事务中：更新卡片当前态、追加不可变 revision、追加供 Anki 消费的 outbox event。任何绕过 `Database` 业务方法直接更新 `cards` 的实现，都可能让历史或同步事件永久缺失。

## 代码地图

| 路径 | 责任 | 修改时通常还要检查 |
|---|---|---|
| `src/vocabry/models.py` | 卡型与输入校验 | renderer、API schema、导入器 |
| `src/vocabry/renderer.py` | 纯文本到当前 HTML | HTML 状态规则、重渲染测试 |
| `src/vocabry/database.py` | schema、事务、历史、outbox、身份与 token | 几乎所有设计文档和数据库测试 |
| `src/vocabry/importer.py` | job 领取、校验、归档和恢复 | 离线协议、导入测试 |
| `src/vocabry/api.py` | HTTP/WebSocket 适配层与预览页 | API、同步、安全测试 |
| `src/vocabry/service.py` | 数据目录、管理 token 和组件装配 | 启动/权限行为 |
| `src/vocabry/config.py` | 数据目录、端口和交换目录 | 产品使用说明 |
| `anki_addon/__init__.py` | Anki Note Type、hooks、事件应用和回传 | 同步协议、真实 Anki 兼容性 |
| `src/vocabry/demo_generator.py` | 独立文件协议示例生产者 | 离线协议 |
| `src/vocabry/gui.py` | 桌面宿主、服务/generator 生命周期和 `chat-v1` 界面 | 桌面 GUI、generator 协议、API |
| `src/vocabry/generator_protocol.py` | manifest 与 JSON Lines 基础协议 | generator 协议与进程测试 |
| `src/vocabry/generators/word_query.py` | Word Query 业务校验与两轮 DeepSeek 对话 | generator 协议、凭据和真实 API 测试 |

当前实现刻意保持一个小型扁平包，没有虚构的 domain/application/adapters 目录。只有在模块职责确实难以维护时再分层。

## 三条数据流

### 生成与导入

生成器在 `staging` 写完整 job，再把目录原子移动到 `inbox`。导入请求触发 `JobImporter` 领取和校验。合法 job 的全部 Card 在同一数据库事务中创建；输入和结果最终归档到 `succeeded` 或 `failed`。精确格式与恢复语义见[离线导入](offline-import.md)。

### 管理与预览

认证客户端通过 HTTP 创建、查询、修改或软删除 Card。创建使用幂等 key；修改和删除使用 `expected_revision`。预览使用与管理 token 分离的短时 session。端点、权限和错误行为见[本地 API](api.md)。

v0.2.0 的桌面 GUI 启动并拥有一个独立 `vocabd` 子进程，通过 admin API 管理候选预览和 Card 创建。内置 generator 是无界面子进程，以 JSON Lines stdin/stdout 与 GUI 通信；它们不取得管理 token，不写 SQLite，也不提供 Card HTML。

### Anki 同步

Card 事务产生持久 outbox event。Add-on 从 WebSocket 顺序消费事件，在 Anki collection 中创建、更新或删除 Note，随后 ack；用户对 Note 的 HTML 修改和删除通过 HTTP 回写。

当前实现包含显式全量对账，但尚未完成持久离线编辑队列，也未在目标 Anki 版本上验证完整恢复行为。详见[Anki 同步](anki-sync.md)。

## 设计文档索引

- [数据模型与事务](data-model.md)
- [离线导入](offline-import.md)
- [本地 API 与安全边界](api.md)
- [Anki 同步](anki-sync.md)
- [桌面 GUI 与进程生命周期](desktop-gui.md)
- [Generator 协议与 Word Query](generator-protocol.md)
- [历史设计决策](../archive/decisions/README.md)

## 修改时必须保留的约束

这里只列真正难以从局部代码推断、破坏后会造成数据错误的约束；细节和证据放在对应主题文档中。

- 一个导入 job 的 Card 必须全有或全无。
- Card 当前态、revision 和 outbox event 必须同事务提交。
- `card_id` 永不复用，revision 对单卡单调增加。
- Anki 手工 HTML 不能仅因 renderer 升级而被覆盖；结构化字段编辑则有意重新渲染。
- 旧 revision 的写入必须冲突，不能静默覆盖。
- 同一事件可重放，Add-on 不能因此重复创建 Note。
- 客户端只有成功应用事件后才能 ack；持久游标只能推进连续前缀。
- Add-on 应用远端事件时不能把自己的写入作为用户编辑回传。
- 用户删除、Note 缺失和 note ID 漂移是不同状态，不能在没有证据时互相替代。

诸如“组件应该职责清晰”“外部输入要校验”之类无法指导具体实现的表述，不作为独立不变量维护。

## 文档与代码谁是事实源

- 具体端点和请求字段：`src/vocabry/api.py` 生成的 OpenAPI。
- 数据库的当前物理 schema：`SCHEMA` in `src/vocabry/database.py`。
- 卡面输出：renderer 代码和测试。
- 导入限制与错误代码：importer 代码和测试。
- 产品语义、跨模块事务与冲突规则、尚未实现的目标：本目录。
- 历史上“为什么这样选”：`archive/decisions/`。

文档若与代码冲突，应先判断是实现 bug 还是文档过期；不要自动把当前代码的偶然行为提升为设计。
