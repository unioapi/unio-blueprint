---
title: Gateway 公开 API 契约
description: Gateway 对外协议入口、认证、模型标识和流式交付边界。
status: active
owner: 网关团队
last_updated: 2026-08-02
related:
  - ../README.md
  - ../glossary.md
  - protocol-compatibility.md
  - request-lifecycle.md
  - runtime-control-recovery.md
  - ../../../specifications/api-style.md
  - ../decisions/adr-0005-request-identity.md
  - ../decisions/adr-0006-protocol-adapter-boundary.md
---

# Gateway 公开 API 契约

## 摘要

Gateway 以协议原生形式提供模型调用服务：OpenAI 协议包含 Chat Completions 与
Responses 端点，Anthropic 协议包含 Messages 端点。调用者使用其所选协议的认证、请求、
响应、流式事件和错误信封；网关不把一个协议的公开形状转换为另一个协议的公开形状。

## 当前实现事实

`POST /v1/responses` 当前按候选 `AdapterKey` 在 registry 中注册的能力选择原生 Responses 直传或
Responses-to-Chat 桥接。
直传保留原始 Responses JSON 与命名 SSE，桥接只合成 Chat 能表达的字段、token usage 和事件族。
桥接存在已登记的字段/工具 Drop，`multi_agent` 在桥接候选上明确拒绝；`background:true` 则在入口
稳定拒绝。mapper 会列出 bridge-level `DroppedFields`，但生产调用点目前丢弃该返回值，因此这些 Drop
不写入日志、持久审计或公开响应。完整映射见[协议兼容性](protocol-compatibility.md)。

## 使用者与范围

| 使用者 | 任务 | 契约 |
| --- | --- | --- |
| OpenAI 兼容客户端 | 调用对话或 Responses 操作 | 使用 OpenAI 形状；协议常规凭据形式为 Bearer API Key。 |
| Anthropic 兼容客户端 | 调用 Messages 操作 | 使用 Anthropic 形状；协议常规凭据形式为 `x-api-key`。 |
| 运营人员 | 配置可调用模型和渠道 | 不对客户暴露 Provider、渠道或上游模型名。 |

当前代码提供的公开操作为：

| 协议 | 端点 | 用途 |
| --- | --- | --- |
| OpenAI | `POST /v1/chat/completions` | 对话补全，支持非流式与 SSE。 |
| OpenAI | `POST /v1/responses` | Responses 主操作，支持非流式与 SSE。 |
| OpenAI | `POST /v1/responses/compact` | 上下文压缩；原生路径回传上游成功 JSON 并仅改写顶层模型回显，摘要降级路径只返回 `output` 数组（0 或 1 个 assistant message），两者均非 SSE。 |
| OpenAI | `POST /v1/responses/input_tokens` | 本地输入 token 估算；解析 Route 候选计划的首个 OpenAI 候选以选择 tokenizer，但不执行运行态快照、fallback 或上游调用，也不写请求记录或产生客户计费。 |
| Anthropic | `POST /v1/messages` | 消息生成，支持非流式与命名 SSE 事件。 |
| OpenAI | `GET /v1/models` | 返回当前 API Key 所在线路 Channel 池聚合出的模型目录；当前查询不按 Channel 协议过滤。 |

依赖服务端状态的 Responses 查询、删除、输入项与取消操作不在本契约范围内；它们稳定返回 HTTP
501 和当前字面错误码 `unsupported_origin_stateless`。`background:true` 不被转换为同步请求，而是稳定
返回 HTTP 400 和错误码 `unsupported_background`。本地 `input_tokens` 是近似估算，不承诺与任一上游的
精确 tokenizer、缓存折扣或最终结算 usage 一致。

## 路径兼容与非业务入口

当前 Router 在匹配业务路由前把客户路径规范化为恰好一个 `/v1` 前缀：

- 已带一个或多个前导 `/v1` 的路径会折叠为单一 `/v1`，包括未知的 `/v1` 子路径。
- 缺少前缀时，只为已知业务入口补齐 `/v1`；根级未知路径保持原样并返回 404。
- `/`、`/healthz`、`/readyz` 和 `/metrics` 不参与该规范化。访问日志和 HTTP 指标保留客户实际发送的原始路径，下游 Router 使用规范化路径。

`/healthz` 和 `/readyz` 位于 API Key 认证组之外；前者当前固定返回 200 `{"status":"ok"}`，
后者根据当前 readiness 返回 200 `{"status":"ready"}` 或 503 `{"status":"not_ready"}`。`/metrics`
只在 Router 注入 metrics handler 时挂载。完整 readiness 语义见[运行控制与恢复](runtime-control-recovery.md)。

所有已注册且受保护的 `/v1` 操作在进入各自 handler 前都会取得 request-admission token，包括
`GET /v1/models`、`POST /v1/responses/input_tokens` 和当前返回 501 的 Responses 状态操作。因此这些本地或
未实现操作也可能先返回共享 admission 的 429/503；它们不执行候选快照、请求 TPM Reserve 或上游调用。

## 身份、模型与可见性

- API Key 识别调用主体。所有受保护的 `/v1` 入口共用同一提取规则：先读取非空 `x-api-key`，
  否则读取大小写敏感的 `Authorization: Bearer <key>`。因此当前 OpenAI 入口也接受 `x-api-key`，
  Messages 入口也接受 Bearer；两者同时存在时 `x-api-key` 优先。
- 缺失、无效、已撤销、禁用或过期的 Key 在进入协议 handler 前被共享 middleware 拒绝。当前无论入口协议
  都使用 OpenAI-compatible 的通用 `{ "error": { "message", "type", "param", "code" } }` 形状；
  `/v1/messages` 的认证失败尚不是 Anthropic 原生错误信封。
- 客户请求的 `model` 是 Unio 模型标识，亦是客户可见响应中的模型标识；上游模型映射不公开。
- 每条 Route 都具有显式 Channel 池。`GET /v1/models` 只从该池中聚合模型；`fixed` 要求池内恰有一条
  Channel，`balanced` 要求至少一条且允许单 Channel 或多 Channel，二者都不越池展示模型。当前目录 SQL 没有
  `channels.protocol` 条件，因此 OpenAI-compatible `/v1/models` 可以包含只由该 Route 内 Anthropic Channel
  绑定的模型；实际 OpenAI 生成或压缩请求的候选查询会按 ingress protocol 过滤，二者当前可能不一致。
- `/v1/models` 的 `capabilities` 聚合模型所有非 `unsupported` 声明，`?capability=` 对这些 key 执行 AND
  过滤。当前查询不读取能力字典的 `protocol_scope`，不会只保留 `shared` 或 `openai` scope 标签。
- 请求一个不在调用者线路可服务范围内的模型时，使用与不存在模型相同的协议原生语义；不得跨线路
  或因模型列表可见性而猜测内部供给。
- 模型不存在或当前主体不可用时，以协议原生的“模型不存在”语义响应，避免泄露运营配置。
- 客户相关标识可用于调用方自身的协议字段，但不能替代网关生成的业务请求标识。

## 请求与响应边界

Gateway 校验协议结构、类型、必填字段和联合类型合法性。合法字段即使暂不能被当前上游表达，
通常会保留到 Provider 映射边界执行 Adapt 或 Drop；但当前 bridge 对无法安全降级的 `multi_agent`
明确 Reject。bridge mapper 能识别部分被 Drop 的字段类别，生产路径不消费该诊断；这些 Drop 不写入
持久审计或公开响应。

JSON 入口接受缺省 `Content-Type` 或媒体类型为 `application/json` 的值（允许参数且不区分大小写）；
其他或无法解析的类型返回 415。请求体上限由运行配置控制，正常启动的缺省值为 32 MiB，超限返回 413；
该上限与模型上下文窗口或计费无关，详见[协议兼容性](protocol-compatibility.md)。

公共 Gateway API Router 处理的每个 HTTP 请求都在响应 `X-Request-ID` 中返回本次日志 `trace_id`。客户
提供的值仅在长度不超过 128，且只含 ASCII 字母、数字、`.`、`_`、`-`、`:` 时原样采用；缺失或不安全时
由 Gateway 生成替代值。客户发送 `X-Request-ID: ABC` 时，响应头和全部请求级日志都使用 `ABC`，不会另行
生成一个不同的返回 ID。客户可以重复使用该值，也可以提交 `req_...` 形状；它没有数据库唯一约束，不能
仅凭前缀解释为账务和请求记录使用的服务端业务请求标识。

Chat Completions、Responses 主操作、Responses compact 和 Messages 在通过认证、request admission 与协议
前置校验并进入相应 service 的持久请求生命周期后，另行创建 `req_` 业务 ID 和持久请求记录。compact 当前仍以 `responses`
endpoint 分类。`/v1/models`、`responses/input_tokens`、501 状态操作虽也取得 request-admission token，但不会创建
`request_records`；业务记录创建前的认证、admission、
decode/validation 拒绝都不会创建 `request_records`。

`X-Request-ID` 始终返回 `trace_id`；持久业务 ID 不进入常规客户成功或错误响应。两类标识只有结构化
日志关联，没有数据库 trace-to-request 映射。Messages handler 进入协议处理后的普通 Anthropic
错误使用 Anthropic 形状，但当前大多数错误调用点未写错误体 `request_id`；request-admission 错误写入的是
`trace_id`，stream writer 构造失败分支则直接读取原始请求 header。客户仍可从 HTTP 响应头取得经过
middleware 处理的 `trace_id`。

公开响应按当前路径映射：Chat 非流式重建单 choice，Responses bridge 合成已支持的字段子集，原生 Responses
普通成功 payload 除模型回显外保留上游结构，失败响应和失败事件可能被脱敏重建。内部计费、审计和恢复
使用独立事实，不在公开响应中增加内部字段；客户看到的模型回显恢复为所请求的 Unio 模型标识。

## 流式传输与交付

| 条件 | 行为 |
| --- | --- |
| OpenAI Chat Completions 流式成功 | 以 data-only SSE 输出 Chat chunk，并在可选 usage 尾包后写出 `[DONE]`。 |
| Responses 原生直传成功 | 转发上游 Responses 命名 SSE 并恢复 Unio 模型回显；上游终态暂存到 settlement/recovery 接管后原样交付，不追加 `[DONE]`。 |
| Responses Chat 桥接成功 | 合成当前 Chat 映射器支持的最小事件族与单调递增 `sequence_number`；映射后的 token usage 只在终态 Response 中出现，不发送 `[DONE]`。 |
| Anthropic 流式成功 | 以 Anthropic 命名 SSE 事件输出，并以 `message_stop` 结束。 |
| 首个客户可见事件前失败 | 可返回普通协议错误；允许在同协议候选间尝试替代路径。 |
| 首个客户可见事件后失败 | 不改变 HTTP 状态；输出协议原生流式错误，且不伪造成功终态。 |
| 流式请求的账务恢复事实无法持久化 | Gateway 不输出 `[DONE]`、`message_stop` 或 Responses 成功终态；直传已捕获的上游成功终态也会丢弃。 |

流式 usage 是否对客户输出由公开协议字段控制；网关为结算所需的可靠用量不依赖客户是否
请求展示该字段。

## 当前兼容性边界

- 当前 registry 分流使具有本次原生 Responses 能力的候选走直传；缺少该能力但具有相应 Chat 能力的
  候选走 Responses-to-Chat bridge。
- bridge mapper 返回的 `DroppedFields` 未被生产调用点消费，也没有进入可关联的持久审计；Provider
  Adapter 的字段名日志属于另一层，不能补足该事实。

本文于 2026-07-26 按当前 Gateway 代码、Schema 和现有测试接收为 `active`。

## 非目标

- 不把 Provider 私有请求、凭据、上游模型或错误正文作为客户契约。
- 不实现服务端对话存储、后台任务或 Provider 的内置工具执行。
- 不承诺第三方官方协议中未由本设计明确声明的操作或能力。

## 相关设计

- [协议兼容性](protocol-compatibility.md)
- [Provider 适配](provider-adaptation.md)
- [请求生命周期](request-lifecycle.md)
- [错误语义](error-semantics.md)
