---
title: Gateway Provider 适配
description: Provider、Origin、Channel、Adapter、协议转换和 usage 归一的当前实现边界。
status: active
owner: 网关团队
last_updated: 2026-08-05
related:
  - ../README.md
  - ../glossary.md
  - protocol-compatibility.md
  - provider-mapping-contracts.md
  - request-lifecycle.md
  - ../decisions/adr-0006-protocol-adapter-boundary.md
---

# Gateway Provider 适配

## 摘要

Gateway 以 `(protocol, adapter_key)` 选择代码适配能力，把客户协议、业务生命周期和上游 wire
处理分开。当前数据边界是：Provider 表示供应商与记账主体，持有全局唯一 `origin` 并作为公共故障域；
Channel 直接绑定 Provider，持有协议、AdapterKey、凭据、限额并关联
上游成本；`channel_models` 保存客户模型到上游模型的映射。客户售价由模型价格与线路价格倍率确定，
不直接存放在 Channel 上。

## 职责边界

| 边界 | 当前职责 |
| --- | --- |
| 公开入口 | 协议 decode、结构校验、认证前置处理、协议错误包络和客户流输出。 |
| Service 与 lifecycle | 路由、候选能力过滤、运行态准入、输入估算、预授权、attempt、fallback、结算、恢复、公开响应映射和客户模型回显。 |
| Adapter | 把协议族内部请求编码为上游 wire，发起一次 HTTP 调用，解析非流式响应或 SSE，分类稳定上游错误，并在同次解析中生成内部响应与 `ResponseFacts`。 |

Adapter 不选择 Channel，不查询 Provider、Channel 或价格表，也不保存请求级业务状态。调用参数来自候选
运行快照，其中包含 Provider origin、Channel 凭据与超时，上游模型来自候选模型映射。
当前 Adapter 仍读取少量进程级配置：非流式上游响应体上限、流式 idle timeout，以及 tokenizer 的
媒体估算选项。官方 Anthropic Adapter 还有一个明确例外：每次请求通过注入的 provider 读取热更新的
`anthropic.beta_policy`，该 provider 底层使用 SettingsStore 的本地、Redis 与数据库读取链。

Adapter 代码每次调用只执行一次 HTTP `Do`。Gateway bootstrap 禁止 HTTP redirect 跟随，避免 POST
因 3xx 被重放；一般重试和跨 Channel fallback 由 lifecycle 创建新的 attempt。`/responses/compact`
的原生 404/405 回落是 service 层的显式例外，仍为 Synthetic Compact 另取 permit 并创建独立 attempt。

正常启动时，非流式上游响应体缺省限制为 8 MiB，超限按稳定 Adapter 错误收口。默认上游 HTTP client
使用进程专用 Transport，允许 HTTP/2，并限制为全局最多 256 条 idle 连接、每个上游 host 最多 32 条
idle 连接和 64 条并发连接；调用方显式注入自定义 Transport 时保留其自身策略。

## 注册与候选选择

当前进程注册矩阵如下：

| 客户/候选协议 | AdapterKey | 已注册能力 |
| --- | --- | --- |
| OpenAI | `openai` | Chat、Stream Chat、Chat Tokenizer、Responses、Stream Responses、Responses Tokenizer、Responses Compact。 |
| OpenAI | `deepseek` | Chat、Stream Chat、Chat Tokenizer。 |
| Anthropic | `anthropic` | Messages、Stream Messages、Messages Tokenizer。 |
| Anthropic | `deepseek` | Messages、Stream Messages、Messages Tokenizer。 |

Channel 创建时，空 `adapter_key` 会取协议同名 key；写入路径和 Gateway 启动 preflight 都会拒绝完全
未注册的 `(protocol, adapter_key)`。preflight 只要求该复合键至少有一种代码能力，具体请求仍会在
候选准备阶段按 tokenizer、非流式或流式能力继续过滤。Provider slug 与 AdapterKey 之间没有代码级
配对约束，因此运行时事实由 Channel 上的 `protocol` 与 `adapter_key` 决定。

正常生成请求先按代码能力过滤候选，再读取运行态状态并进行估算、准入和授权：

- Chat 与 Messages 候选要求对应协议的输入 tokenizer，以及本次所需的非流式或流式调用能力。
- Responses 非流式与流式候选可由原生 Responses 能力或 Chat 能力服务；同一 key 有本次所需的原生
  Responses 能力时走直传，否则走 Responses-to-Chat bridge。候选输入估算也按这一路径选择 Responses
  tokenizer 或 Chat tokenizer。
- Responses Compact 是例外：候选准备先固定要求 Chat tokenizer 与非流式 Chat 能力，
  调用时才按 `HasResponsesCompact` 选 Native 或 Synthetic。仅注册 Compact 而没有 Chat
  基线能力的 key 会在调用前被过滤。
- `/v1/responses/input_tokens` 是例外：它直接取 Route 计划的第一个 OpenAI 候选，固定使用该 key 的
  Chat tokenizer，不执行生成请求的能力过滤、运行态 admission、fallback、上游调用、请求记录或计费。

Responses bridge 对 `multi_agent.enabled=true` 返回本地 `adapter_request_unsupported`。该错误不带
上游错误分类，因此若排序在前的 bridge 候选命中这一分支，当前 lifecycle 不会继续尝试后续原生
Responses 候选。

## 请求、响应与事实

当前代码中的映射行为包括 Pass、Adapt、Drop 和 Reject，但这些行为分布在不同层：

- 公开入口负责非法协议结构和已登记业务边界的 Reject。
- Responses service 负责直传与 bridge 的请求/响应转换，并生成客户可见 Responses 形状。
- Provider Adapter 负责上游特有的 Adapt、Drop、wire 解析和稳定错误分类。
- Adapter 返回协议族内部 DTO，或原生 Responses 的受控原始 JSON，同时生成独立的
  `ResponseFacts`；客户协议响应由 service 与公开入口继续映射和写出。

`ResponseFacts` 当前保存上游协议、响应 ID、上游模型、稳定结束分类、原始结束原因、归一 usage、
usage 来源、映射版本、上游 HTTP 状态和 request ID。流式结束时只有取得可靠最终 usage 才返回完整
facts；否则 lifecycle 进入 release、partial estimate 或 risk exposure 路径。

上游模型不仅用于 Adapter 出站，也用于候选 token 估算、span、内部错误字段、attempt、settlement、
recovery 与 partial usage。客户公开响应仍恢复客户请求的 Unio 模型标识；上游模型只保留在内部事实中。

原生 Responses 的普通成功 payload 除模型回显改写外保持上游 JSON 结构，但它不是无条件字节透传：
失败响应或失败事件会脱敏重建，`[DONE]` 会被截留，部分畸形 SSE 帧会被修复。完整差异见
[协议兼容性](protocol-compatibility.md)。OpenAI Chat 非流式响应则只消费上游 `choices[0]`；即使请求
把 `n>1` 发给官方 OpenAI，上游整次调用的 usage 会进入结算，但客户只收到一个 choice。

## 当前 Provider 路径

| 上游路径 | 当前行为 |
| --- | --- |
| OpenAI 官方 Chat | 使用 `openai` Chat Adapter 调用 `/v1/chat/completions`，没有额外 Provider 专属 Drop wrapper；请求经结构化 wire 编码，响应解析为内部单 choice DTO 与 `ResponseFacts`。 |
| OpenAI 官方 Responses | 使用同一 `openai` key 的原生 `/v1/responses`、流式 Responses、Responses tokenizer 和 `/v1/responses/compact` 能力。普通成功 payload 走受控原文路径。 |
| Anthropic 官方 Messages | 使用 `anthropic` Messages Adapter 调用 `/v1/messages`，固定发送 `anthropic-version: 2023-06-01`，并按运行时 beta policy 对 `anthropic-beta` 去重和过滤后出站。 |
| DeepSeek OpenAI | 使用 `deepseek` Chat Adapter；Responses 由 service 走 Chat bridge。Adapter 会执行 DeepSeek 特有的 Adapt/Drop，并复用 OpenAI Chat 响应解析和 usage 映射。 |
| DeepSeek Anthropic | 使用 `deepseek` Messages Adapter 调用 Anthropic-compatible `/v1/messages`；Adapter 在通用 Anthropic wire 前执行 DeepSeek 特有的 Adapt/Drop。 |

OpenAI 原生 Compact 成功时返回上游完整 Response-like JSON。当前 service 构造后固定开启
原生不支持回落，没有生产 setter 或运行配置入口：同一 Channel 的原生 404/405 会再执行
一次独立准入的 Synthetic Compact；原生 2xx 若 usage 不完整或数值不可信，则不执行 Synthetic 回落，
而是记录 cost risk exposure 并失败收口。

### DeepSeek OpenAI 出站

当前 Adapt 包括 `developer -> system`、`max_completion_tokens -> max_tokens`、可转换的 legacy function
字段到 tools、合法 `user -> user_id`，以及把 reasoning effort 归一为 `high` 或 `max`。Responses bridge 未请求
reasoning 时会设置内部 `ReasoningDisabled`，DeepSeek Adapter 据此在未显式提供 `thinking` 时注入
`thinking: {type: "disabled"}`。

当前 Drop 包括无等价表达的多模态 part、custom tool、`n`、部分采样字段、`json_schema`、音频、metadata、
store、service tier、prompt cache 控制和非白名单扩展；非法或过长的 `user` 也不会出站。这里只列出
Provider 适配边界，逐字段表由[Provider 映射契约](provider-mapping-contracts.md)继续承载。

### DeepSeek Anthropic 出站

当前会 Drop `anthropic-beta`、`top_k`、不支持的 content block、内置 server tool 定义、除 `user_id`
以外的 metadata，以及 `container`、`inference_geo`、`mcp_servers`、`service_tier` 等扩展。
`output_config.format` 会被移除，`output_config.effort` 会归一为 `high` 或 `max`；未知 effort 会被移除。
历史消息中的部分 server-tool result block 可以保留，但这不表示 DeepSeek 会执行客户声明的内置工具。

## Drop 可观测性

当前 Drop 诊断分别写入以下位置：

- DeepSeek OpenAI Adapter 以 `DEBUG` 记录字段名，DeepSeek Anthropic Adapter 以 `WARN` 记录字段名。
- Anthropic 官方 beta policy 以 `DEBUG` 记录被拦截的 beta token。
- 上述日志不记录字段值，但也没有增加稳定的 request、attempt 或 Channel 关联标识。
- Responses bridge mapper 会返回部分 `DroppedFields`，但非流式、流式、候选估算、Synthetic Compact 和
  `/responses/input_tokens` 的生产调用点都丢弃该返回值。
- Bridge 跳过的 `item_reference`、`compaction`、未知 input item 和部分 reasoning item 不会加入
  `DroppedFields`，因此当前既没有日志，也没有持久记录。

Provider Adapter Drop 与 Responses bridge Drop 是两层不同事实。当前两层都没有同时包含稳定 request、
attempt 或 Channel 关联标识的持久记录。

## 输入估算

所有 tokenizer 都是本地保守估算，真实结算使用上游 usage：

- OpenAI Chat 与原生 Responses tokenizer 只对提取的文本计数，媒体按进程配置使用 tile/patch 或固定值，
  不把整包 JSON 或 base64 当文本。
- DeepSeek OpenAI tokenizer 先执行与真实出站相同的 Adapt/Drop，再估算清理后的 Chat 请求。
- Anthropic 官方 tokenizer 使用 tiktoken 近似并增加消息、工具和媒体开销。
- DeepSeek Anthropic tokenizer 当前直接复用 Anthropic 估算，没有先执行 DeepSeek Drop，因此被真实出站
  移除的多模态块仍可能进入估算；该结果是保守上界。

## Usage 归一

内部 `usage.Facts` 以 `known`、`not_applicable` 和 `unknown` 表达 token 维度；reasoning/thinking 是
输出总量的分解项，不是额外生成量。

OpenAI Chat 与原生 Responses 把输入拆为未缓存、cache read 与 30m cache write，5m/1h cache write 标为
不适用；输出总量包含 reasoning。当前 OpenAI wire DTO 对 cached、cache write 和 reasoning 可选分解使用
整数零值，因此上游未提供这些可选字段时会成为 `known(0)`，不能区分“未提供”和“已知零”。

OpenAI Chat、原生 Responses 与 Responses Compact 的非流式成功响应必须实际带有完整的输入、输出和
总 token 字段，且总数与输入加输出一致；字段明确返回数字零是合法用量。usage 不存在、为 null、缺少
任一必需字段、出现负数或总数不一致时，请求不会交付给客户，也不会继续切换其他渠道。Gateway 不向
客户扣费，而是释放冻结金额并记录一条上游可能已经产生费用的风险事实。Responses-to-Chat bridge 和
Compact 的 Synthetic 路径沿用同一规则。

DeepSeek OpenAI 复用上述解析器。当前生产代码没有解析 DeepSeek 专有的
`prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`；如果上游只返回这两个字段而没有填充
`prompt_tokens_details.cached_tokens`，对应输入会全部进入未缓存量。

Anthropic usage 把 `input_tokens` 作为未缓存输入，分别保存 cache read、5m/1h cache write、输出总量与
thinking 分解；只有 flat cache creation 总量时归入 5m，30m 标为不适用。`server_tool_use` 中的
web search 与 web fetch 次数会转换为受控附加计量项；显式零当前也会生成 item，但通用 facts 校验只接受
正数，因此显式零可能使完整 facts 校验失败。

Anthropic 非流式响应只有同时带有 `usage.input_tokens` 和 `usage.output_tokens` 才能进入成功结算；字段
明确为零是合法用量。usage 不存在、为 null 或缺少其中一个字段时，请求失败且不再切换其他渠道，Gateway
释放客户冻结金额并记录一条上游可能已经产生费用的风险事实，不会把缺失用量当成 0 元成功。

当前候选要求客户售价与 Channel 成本使用相同币种和相同 pricing unit。币种或计价单位不一致时，
候选在负毛利保护中 fail closed；运行时没有汇率换算。

## 能力画像边界

当前只有 DeepSeek OpenAI 与 DeepSeek Anthropic Adapter 提供代码能力画像。Admin 可以把画像作为
`adapter_seed` 物化到模型能力声明，但 Gateway 运行时路由和 Adapter
选择不读取 `model_capabilities`，也没有按能力画像执行请求拒绝或候选闸门。

## 状态说明

本文于 2026-07-26 按当前 Gateway 代码和 Schema 接收为 `active`。

## 文档范围

- 本文件不复制 Provider 官方 API reference、模型清单、Base URL、凭据或实时价格。
- 公开协议形状由[公开 API 契约](public-api-contracts.md)和[协议兼容性](protocol-compatibility.md)维护。
- Provider 逐字段差异由[Provider 映射契约](provider-mapping-contracts.md)维护。
- attempt、fallback、结算和恢复由[请求生命周期](request-lifecycle.md)与相关账务文档维护。
