---
title: Gateway 错误语义
description: Gateway 的当前内部分类、fallback、协议错误包络与敏感信息边界。
status: active
owner: 网关团队
last_updated: 2026-07-29
related:
  - ../README.md
  - public-api-contracts.md
  - protocol-compatibility.md
  - provider-adaptation.md
  - request-lifecycle.md
  - admission-control.md
  - resilience-circuit-breakers.md
  - ../../../specifications/api-style.md
---

# Gateway 错误语义

## 摘要

Gateway 使用稳定错误代码和 Adapter 上游错误类别驱动重试、候选切换与公开响应，不解析 Provider
错误文案。客户 API Key 错误、Gateway 自身错误和上游错误是不同边界；上游认证或权限失败不会伪装成
客户凭据错误。

## 客户身份与入口错误

| 条件 | 当前 HTTP 状态 |
| --- | --- |
| API Key 缺失、无效、禁用或过期 | 401 |
| API Key 可用额度或消费上限不足 | 402 |
| 请求结构或字段校验失败 | 400 |
| Content-Type 不支持 | 415 |
| 请求体超过受控大小限制 | 413 |
| 模型不存在或调用方当前不可访问 | 404 |
| 调用方请求级限流或并发限制 | 429 |
| 必需的准入、运行控制或基础设施不可用 | 503 |

Chat Completions 与 Responses handler 使用 OpenAI-compatible 错误信封；Messages handler 使用 Anthropic
错误信封。认证中间件位于协议 handler 之前，因此 Anthropic 请求的 API Key 认证失败当前也返回共享的
OpenAI-compatible 通用错误信封。

公开错误正文使用受控文案，不包含 Provider、Channel、凭据、上游地址、真实上游模型
或原始 Provider 响应。

## 上游错误分类

Adapter 当前使用以下稳定类别：`rate_limit`、`timeout`、`bad_request`、`auth`、`permission`、
`server_error`、`canceled` 和 `unknown`。

| 上游类别 | 是否切换同模型候选 | 候选耗尽后的客户状态 |
| --- | --- | --- |
| `rate_limit` | 是 | 429 |
| `timeout` | 是 | 504 |
| `server_error` | 是 | 502 |
| `auth` | 是 | 502 |
| `permission` | 否 | 502 |
| `bad_request` | 否 | 400 |
| `canceled` | 否 | 按取消路径终止，不启动 fallback |
| `unknown` 或没有稳定类别 | 否 | 502 或对应 Gateway 安全错误 |

`auth` 可以切换候选，最终渲染为上游 502，不会成为客户 401。`permission` 和 `bad_request` 不切换。
客户端取消不作为上游故障，也不触发替代调用。

OpenAI Chat、OpenAI Responses 与 Anthropic Messages 各自把同一上游类别渲染成协议原生错误类型和安全
文案；HTTP 状态映射保持上表一致。

OpenAI Responses 原生流中的 `response.failed` 或 `error` 事件会按稳定错误 code 分类。`rate_limit`、
`rate_limit_error` 和 `rate_limit_exceeded` 归为上游 `rate_limit`，即使该 SSE transport 的真实 HTTP 状态是
200；内部仍记录上游状态类 failure code 与真实 HTTP metadata，不改写为 Gateway 自身的请求级或候选准入
限流。该错误可以切换同模型候选，并在 permit Finish 确认后为实际 Channel 写入 cooldown。

## 候选拒绝与错误收口

一次请求的候选循环会分别遇到候选准入拒绝和已调用上游后的错误。当前收口规则如下：

1. 候选准入拒绝会累计为一个 `attemptDenialSummary`。
2. 如果没有任何上游错误，且全部候选都是容量拒绝：包含渠道 rate limit 时返回 429；全部为渠道
   concurrency limit 时也返回 429。
3. 如果拒绝中包含 breaker、权限暂停或其他非容量原因，返回 no available channel，对外为安全 503。
4. 一旦发生可重试上游错误，循环只保存 `lastErr`。所有候选耗尽后直接返回最后一个可重试上游错误，
   不再用前述 denial summary 或更早的上游错误形成综合结论。
5. 非可重试上游错误立即结束候选循环。

因此，当前只对“没有上游错误、全部候选在准入阶段被拒绝”的场景做原因聚合；对多个上游失败或
“上游失败加候选拒绝”的组合没有完整聚合，最终客户状态可能由最后一个可重试上游错误决定。

## `Retry-After`

Gateway 只在能够从以下事实证明恢复时间时返回 `Retry-After`：

- 最后返回错误携带的上游 `Retry-After` metadata；
- Redis cooldown 错误字段中的 `retry_after_ms`。

更早候选的恢复时间不会参与最终计算，也不会根据错误类型猜测等待时间。没有正数恢复时长时不生成
该提示。

## 流式错误

| 时点 | 当前行为 |
| --- | --- |
| 尚未写出客户流事件 | 可以切换候选；最终失败时仍可使用正常 HTTP 状态和协议错误信封。 |
| 已写出客户流事件 | HTTP 状态已经提交，不能再变更；Gateway 尽力写入入口协议的流式 error event 后中断。 |
| 客户取消 | 终止当前流，不切换候选。 |
| Gateway 生成成功终态前结算或 recovery 建立失败 | 省略成功终态并写流式错误。 |
| 原生 Responses 已收到 `response.completed` | 该事件当前先透传；随后 settlement 或 recovery 失败不能撤回已交付的成功终态。 |
| 原生 Responses 收到内联 rate limit 失败事件 | 保留已提交的 HTTP 状态，按上游 `rate_limit` 收口并反馈实际 Channel cooldown，不作为 Gateway 本地限流。 |

Chat 流不会在已开流后写普通 JSON 错误；Messages 使用 Anthropic `error` 事件；Responses 使用受控的
Responses error 事件。流式错误不附带 Provider 原始响应正文。

## 内部诊断边界

Adapter 可以从非成功上游响应读取受限、截断的 `ResponseSnippet`，用于错误分类和 Channel 检测。
该片段不进入普通 request/attempt 记录，也不进入客户响应。Gateway 保存稳定错误类别、HTTP 状态、
上游 request ID 等受控 metadata；Provider 原始 body、凭据和完整 prompt/response 不属于普通错误事实。

DeepSeek Adapter 的字段 Drop 和 Anthropic beta policy 当前只形成应用日志；Responses bridge 的
`DroppedFields` 在生产路径未被消费。这些诊断不是完整、可关联的错误审计。

## 当前边界

- fallback 只保留最后一个可重试上游错误，没有完整候选错误聚合。
- `Retry-After` 只来自最终错误或 cooldown，不能表达更早候选的最早恢复时间。
- Anthropic API Key 认证失败发生在协议 handler 前，当前不是 Anthropic 原生错误信封。
- 流开始后无法改变 HTTP 状态；原生 Responses 的成功终态还可能早于 settlement recovery 持久化。
- Provider 原始 body 只可作为受限 snippet 参与内部判断，没有进入普通审计；Drop 诊断也没有持久审计。

## 状态说明

本文于 2026-07-26 按当前 Gateway 代码和现有测试接收为 `active`。
