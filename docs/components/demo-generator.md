# 外部 Demo 生成器

> 状态：设计基线。它是协议消费者和测试夹具，不是主应用内置生成能力。

## 定位

Demo 生成器从仓库外部消费者的视角验证离线导入协议是否真正自包含。它只使用 Python 标准库和已发布的协议样例。

## 职责

- 接受 exchange 根目录和少量示例词参数。
- 生成两种内置卡型的 `manifest.json` 与 `cards.jsonl`。
- 在 `staging` 写完后原子重命名到 `inbox/<job-id>`。
- 提供故意生成非法字段的模式，验证整批失败和机器可读错误。
- 读取终态 `result.json` 并输出摘要。

## 非职责

- 不导入 `src/vocab` 内部模型或复用私有校验器。
- 不自动修正错误并重投，也不参与业务去重。
- 不代表未来 LLM、词典或抓取生成器的产品范围。

## 必须保持

- [`IMPORT-001`](../INVARIANTS.md#import-001-job-全有或全无)
- [`SEC-003`](../INVARIANTS.md#sec-003-外部文本和路径不受信任)

若 Demo 必须导入主应用内部包才能工作，说明协议或样例没有形成独立契约，应修复协议边界，而不是增加内部依赖。

## 主要故障表现

- 目标 `job-id` 已存在：生成新 ID，不覆盖或复用历史 job。
- staging 与 inbox 不在同卷：拒绝声称原子投递。
- 结果失败：原样报告稳定 `code`、`line` 和 `field`，不依赖自然语言 `message` 自动判断。

## 修改影响

Demo 跟随已发布协议升级，但不能反过来以内部实现便利定义协议。协议变化需要更新 golden files、兼容性说明和独立性测试。

## 进一步入口

- [离线导入协议](../protocols/offline-import.md)
- [ADR-0003：原子文件系统导入](../decisions/0003-atomic-filesystem-import.md)
- [验证策略](../quality/verification.md)
