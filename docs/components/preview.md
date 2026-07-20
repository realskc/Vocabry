# 浏览器预览器

> 状态：设计基线。它是参考预览，不承诺与各 Anki WebView 像素级一致。

## 定位

预览器是由 `vocabd` 同源提供的只读界面，用于检查系统当前交付的正反面 HTML、来源和 revision，而不是新的卡片编辑器。

## 职责

- 按 ID 打开或浏览卡片。
- 提供正反面翻转、键盘切换和固定参考样式。
- 显示卡型、revision、HTML 来源和陈旧状态等调试信息。
- 隔离并安全呈现 renderer 生成或 Anki 回写的当前 HTML。

## 非职责

- 不编辑 Card，不实现业务写入。
- 不模拟所有 Anki 版本、插件和用户 CSS 的最终效果。
- 不加载外部脚本或远程资源。
- 不持有可调用通用业务 API 的长期 token。

## 必须保持

- [`SEC-001`](../INVARIANTS.md#sec-001-业务边界默认不公开)
- [`SEC-002`](../INVARIANTS.md#sec-002-浏览器不持有管理能力)
- [`SEC-003`](../INVARIANTS.md#sec-003-外部文本和路径不受信任)

第一版 sandbox 禁止脚本、表单、顶层导航和任意源访问。结构化字段生成的 HTML 同样按不受信任输出显示，避免安全模型依赖来源判断。

## 主要故障表现

- session 过期：由认证 API 客户端重新签发，不回退到管理 token。
- HTML 包含不支持或危险能力：安全降级显示，不放宽 sandbox。
- 卡片已变化：明确显示 revision，避免用户误以为旧页面代表当前状态。

## 修改影响

放宽 iframe、资源加载或 session 权限属于安全边界变更，必须同步检查安全设计和 `SEC-002/003`。新增编辑能力将改变组件定位，应先形成 ADR，而不是直接增加写端点。

## 进一步入口

- [本地 API](../protocols/local-api.md)
- [卡片 HTML 状态](../domain/card-model.md#html-状态规则)
- [安全边界](../quality/security.md)
