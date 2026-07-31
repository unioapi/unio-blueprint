---
title: Gateway Provider 映射契约
description: OpenAI、Anthropic 与 DeepSeek Provider 路径的当前字段、流式、错误和 usage 映射边界。
status: active
owner: 网关团队
last_updated: 2026-07-26
related:
  - ../README.md
  - ../glossary.md
  - provider-adaptation.md
  - protocol-compatibility.md
  - public-api-contracts.md
  - billing-settlement.md
  - error-semantics.md
  - ../decisions/adr-0006-protocol-adapter-boundary.md
---

# Gateway Provider 映射契约

## 摘要

Gateway 以客户协议和候选 Channel 的 `adapter_key` 选择 Provider Adapter。公开入口保持 OpenAI 或
Anthropic 协议形状，Adapter 在出站边界执行 Pass、Adapt 或 Drop，响应再恢复客户请求的 Unio 模型标识。
本文只记录当前代码已经实现的 Provider 差异；通用协议字段仍以上游官方资料为准。

## 公共边界

| 边界 | 当前行为 |
| --- | --- |
| Adapter 选择 | 候选注册本次所需的原生 Responses 能力时走直传；否则，同一 `adapter_key` 注册 Chat 能力时走 Responses-to-Chat bridge。OpenAI 与 Anthropic 之间不做跨协议转换。 |
| 模型标识 | 出站使用 Channel 模型绑定中的上游模型；客户响应恢复请求中的 Unio 模型标识。真实上游模型只进入内部 attempt、response facts、结算与恢复事实。 |
| 映射结果 | Pass 保留可表达字段，Adapt 转成上游等价表达，Drop 从 Provider wire 移除合法但无等价表达的字段。入口接受字段不表示当前 Provider 已执行对应能力。 |
| 错误 | Adapter 把上游错误归为稳定类别，客户错误按入口协议重建；上游认证或权限错误不会转换成客户 API Key 的 401。 |
| usage | Adapter 同次解析客户响应和内部 `ResponseFacts`。token 维度使用 `known`、`not_applicable` 或 `unknown`；reasoning/thinking 是输出总量的分解项。 |

Provider Adapter 与 Responses bridge 是两个独立映射层。Provider Adapter 只接收协议族内部 DTO；bridge
先把 Responses 请求转换成 Chat DTO，再由所选 Chat Adapter 执行 Provider 映射。

## OpenAI 官方路径

### Chat Completions

`openai` Chat Adapter 通过结构化 wire 调用上游，不附加 Provider 专属 Drop wrapper。合法字段按通用
OpenAI DTO 编码，包括 `developer`、`max_completion_tokens`、多模态 part、结构化输出、工具和 reasoning
字段。当前非流式响应只把上游 `choices[0]` 返回给客户；若请求包含 `n > 1`，上游整次 usage 会进入结算，
其余 choice 不会返回。

Chat usage 按 OpenAI 通用字段归一输入、缓存读取、缓存写入、输出与 reasoning 分解。部分可选 usage
字段在 wire DTO 中使用整数零值，因此上游未提供和明确返回零当前都可能表现为 `known(0)`。

### Responses

`openai` key 注册原生 Responses、Stream Responses、Responses Tokenizer 和 Responses Compact。直传请求
以客户原始 JSON 为基底，只改写 `model` 和 `stream`。普通成功 payload 与成功事件除模型回显外保留上游
结构；失败 payload、失败事件和异常 SSE 帧会经过安全处理，不是无条件字节透传。

Responses Compact 的候选前置与注册槽位不完全对称：当前候选先必须具备 Chat tokenizer 与
非流式 Chat 能力，然后才按 `HasResponsesCompact` 选择 Native 或 Synthetic。当前 service 固定
开启 Native 404/405 向 Synthetic 的独立准入回落，没有生产 setter 或运行配置入口。

原生流解析器仍从 `response.completed/incomplete` 抽取最终 facts，但 service 会捕获该上游成功终态，
lifecycle 不立即向客户写出。创建 settlement recovery 并完成内联结算或确认 recovery 接管后，Gateway 才
按原始事件内容恢复模型回显并交付终态。

## Anthropic 官方路径

`anthropic` Messages Adapter 固定发送 `anthropic-version: 2023-06-01`。Messages 请求按通用 Anthropic wire
编码文本、thinking、client/custom tool、server tool、`top_k`、metadata 和已建模扩展；模型名替换为
Channel 绑定的上游模型。

客户 `anthropic-beta` 在入口宽进接收。官方 Adapter 每次通过注入的 provider 读取当前
`anthropic.beta_policy`，对 token 去重和过滤后出站；
被策略拦截的 token 只写 `DEBUG` 应用日志。入口还会在候选选择前记录全部 beta token，因此实际随后出站的
token 也可能被入口日志标记为 ignored。

Anthropic usage 归一未缓存输入、cache read、5m/1h cache write、输出与 thinking 分解。完整 usage 中：

- `server_tool_use.web_search_requests` 指针存在时生成 `web_search` 附加计量项；
- `server_tool_use.web_fetch_requests` 指针存在时生成独立的 `web_fetch` 附加计量项；
- 附加项只有数量大于零才通过通用 facts 校验；明确返回零会生成零数量项并使 facts 无效；
- 通过校验的正数项可以随 usage line item 和 recovery 字段持久化，但当前 `token_v1` 公式不读取这些数量，
  不据此计算客户收费或 Provider 成本。

## DeepSeek OpenAI 路径

`deepseek` OpenAI Adapter 只注册 Chat、Stream Chat 和 Chat Tokenizer；Responses 请求因此走 Chat bridge。

### 当前 Adapt

- `developer` role 转为 `system`。
- `max_completion_tokens` 转为 `max_tokens`。
- 合法且长度受控的 `user` 转为 `user_id`；非法或过长值不出站。
- legacy function 字段在可转换时转为 tools。
- reasoning effort 归一为 `high` 或 `max`，未知值移除。
- Responses bridge 未携带 reasoning 时设置禁用标志；Adapter 在没有显式 `thinking` 时注入
  `thinking: {type: "disabled"}`。
- 工具轮中的 `reasoning_content` 与 assistant content、tool calls 分开传递。

### 当前 Drop

Adapter 移除无等价表达的多模态 part、音频、custom tool、`n`、部分采样字段、`json_schema`、metadata、
store、service tier、prompt cache 控制及非白名单扩展。`function.strict` 可以进入 wire，但是否生效取决于
实际 DeepSeek 渠道配置。

被移除的字段名只写 `DEBUG` 应用日志。日志不含字段值，也没有稳定的 request/attempt 关联，更没有进入
持久审计。

DeepSeek OpenAI 复用 OpenAI Chat usage 解析器。当前生产解析不读取 DeepSeek 专有的
`prompt_cache_hit_tokens` 和 `prompt_cache_miss_tokens`；若上游没有同时填充 OpenAI 风格的 cached details，
这些专有字段不会形成缓存命中事实。

## DeepSeek Anthropic 路径

`deepseek` Messages Adapter 调用 Anthropic-compatible Messages wire，并在通用 Anthropic 编码前执行
Provider 映射。

### 当前保留与适配

- 支持的消息 content block 为 text、thinking、tool_use、tool_result、server_tool_use 和
  web_search_tool_result。
- client custom tool 定义保留；历史 server-tool result 可以保留，但这不表示 DeepSeek 会执行客户声明的
  server tool。
- `thinking.type` 保留；`output_config.effort` 归一为 `high` 或 `max`，未知值移除。
- 真实上游返回 OpenAI 风格错误时，客户仍收到 Anthropic 错误形状。

### 当前 Drop

Adapter 移除 `anthropic-beta`、`top_k`、图像、文档、MCP、`redacted_thinking`、不支持的 content block、
server tool 定义、缓存控制、除 `user_id` 外的 metadata，以及 `container`、`inference_geo`、
`mcp_servers`、`service_tier` 等扩展。`output_config.format` 也会移除。

被移除的字段名只写 `WARN` 应用日志，不进入持久审计。DeepSeek Anthropic tokenizer 当前直接复用通用
Anthropic 估算，没有先执行上述 Drop，因此被移除的媒体或扩展仍可能计入保守输入估算。

## Responses-to-Chat Bridge

bridge 当前映射文本、best-effort 多模态输入、function 与 namespace tool、结构化输出控制、reasoning、
refusal 和 token usage，并合成 Responses 非流式或 SSE 响应。它不传递 Chat 无法承载的内置/custom/
local-shell tool、`previous_response_id`、`truncation`、多数 `include` 语义、未建模扩展和部分 input item。
`background:true` 在入口拒绝；`multi_agent.enabled=true` 在 bridge 候选上拒绝。

mapper 会计算部分 `DroppedFields`，但非流式、流式、候选估算、Synthetic Compact 和 input-tokens 的生产
调用点都丢弃该返回值。部分被忽略的 input item 与 reasoning 字段也没有加入 `DroppedFields`。因此 bridge
Drop 当前既无应用日志，也无持久记录。

bridge 生成的 SSE 只覆盖可由 Chat 表达的 Responses 事件。正常结束可合成 `response.completed` 或
`response.incomplete`；开流后失败尽力追加 `event: error` 并中断，不合成成功终态。

## 当前边界

- Provider Adapter Drop 只有不完整的字段名应用日志，Responses bridge Drop 诊断未被生产调用点消费；
  两层都没有可关联的持久审计。
- Anthropic server-tool 次数的明确零值不能作为有效 facts 保存；缺失、零和不适用也未在 recovery 中形成
  完整三态。
- 正数 `web_search` 与 `web_fetch` 次数可以持久化，但当前收费和成本仍只使用 token 公式。
- OpenAI Chat 非流式只返回第一个 choice；DeepSeek 专有 cache hit/miss 字段没有生产解析。

## 状态说明

本文于 2026-07-26 按当前 Gateway 代码和 Schema 接收为 `active`。
