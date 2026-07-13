# 外部 demo 生成器

## 目的

验证离线协议，而不是展示主应用内置能力。demo 位于独立目录，不依赖 `src/vocab` 包，只使用 Python 标准库。

## 行为

- 接受 exchange 根目录和少量示例词参数。
- 生成两个卡型的 `manifest.json` 与 `cards.jsonl`。
- 先写 `staging`，再原子重命名到 `inbox/<job-id>`。
- 提供故意生成非法字段的选项，用于验证整批失败和错误报告。
- 可读取 `succeeded/failed/<job-id>/result.json` 并输出摘要，但不自动修改重投；后续可增加演示性修正。

## 独立性测试

测试环境只把已发布的离线协议样例和目录路径交给 demo。若 demo 必须导入主应用模型才能工作，说明协议并未真正解耦。

