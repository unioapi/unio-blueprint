---
title: Gateway 协议兼容性
description: OpenAI、Anthropic 与 Responses 公开协议的 Unio 特有兼容边界。
status: active
owner: 网关团队
last_updated: 2026-07-26
related:
  - ../README.md
  - ../glossary.md
  - public-api-contracts.md
  - provider-adaptation.md
  - error-semantics.md
  - ../decisions/adr-0006-protocol-adapter-boundary.md
---

# Gateway 协议兼容性

## 原则

公开协议是客户契约，上游能力是适配约束。Gateway 维护 OpenAI 与 Anthropic 两个协议族；
每个[端点](../glossary.md)只归属一个协议。官方协议全文不在本设计复制，调用者应以相应
官方资料了解通用字段；本文只说明 Unio 的兼容选择和已知边界。

| 兼容状态 | 含义 |
| --- | --- |
| 接收 | Gateway 识别并校验协议字段或事件。 |
| 适配 | 字段在保持语义的前提下转换为上游表达。 |
| Provider Drop | 合法字段在当前上游无等价表达时不出站。当前 DeepSeek Adapter 只把被丢弃的字段名写入应用日志；持久审计尚未实现。 |
| 拒绝 | 仅用于非法协议结构、无状态边界或明确业务拒绝。 |

Provider Drop 不代表公开协议成功实现了该能力。当前 Drop 没有形成可关联到调用的脱敏持久审计。

## OpenAI Chat Completions

- 支持 OpenAI 原生请求、非流式响应和 data-only SSE；流式成功以 `[DONE]` 收尾。
- 公开模型回显使用客户请求的 Unio 模型标识。
- `reasoning_content`、工具调用和使用量细分在可获得时与普通内容分离，不将 reasoning 合并进
  内容字段。
- `stream_options.include_usage` 仅控制客户可见 usage 尾包；内部结算仍按可靠用量处理。
- 非流式 adapter 当前只把上游 `choices[0]` 映射回公开响应；即使官方 OpenAI 出站请求保留了
  `n>1`，额外 choices 也不会返回给客户。DeepSeek OpenAI Adapter 则在出站前 Drop `n`。
- 多模态、音频、文件、结构化输出和其他合法字段的入口处理不等于每个上游都能执行该能力。

## Anthropic Messages

- 支持 Anthropic 原生请求、Message 响应和命名 SSE 事件；流式成功以 `message_stop` 收尾。
- Messages 常规凭据形式为 `x-api-key`，但当前所有受保护 `/v1` 入口共用认证提取器：非空
  `x-api-key` 优先，否则接受大小写敏感的 `Authorization: Bearer <key>`。认证失败发生在 Messages
  handler 前，当前返回 OpenAI-compatible 通用错误信封。
- `anthropic-version` 必填，当前只接受 `2023-06-01`；缺失或其他值返回 Anthropic 形状的 400。
  官方 Anthropic Adapter 出站同样固定使用 `2023-06-01`。
- `anthropic-beta` 宽进接收，未知或未登记值不在入口导致 400。是否出站由 Provider 映射决定，
  当前入口在候选选择前以 `DEBUG` 记录所有 beta token；官方 Anthropic Adapter 另以 `DEBUG` 记录
  策略拦截的 token，DeepSeek Anthropic Adapter 则以 `WARN` 记录 `anthropic-beta` 字段类别。三者均
  未形成持久审计，且入口日志可能把随后由官方 Adapter 转发的 beta 误标为 ignored。
- thinking、工具、缓存和用量维度保持协议原生结构；模型能力或 Provider 不支持不改变入口
  对合法结构的接收。

## OpenAI Responses

Responses 是独立的 OpenAI 端点，不是第三个协议族。当前代码按候选 adapter 能力选择两条路径：

| 路径 | 当前选择条件 | 当前代码行为 |
| --- | --- | --- |
| 原生直传 | 非流式候选注册 Responses adapter；流式候选注册 Stream Responses adapter | 以客户原始请求体为基底，只改写 `model` 和 `stream`。普通成功响应与事件保留 JSON 结构并恢复 Unio 模型回显；失败事件和异常帧按下述安全边界处理。 |
| Chat 桥接 | 候选没有本次调用所需的原生能力，但注册对应 Chat Completions adapter | 请求映射为 Chat，响应再合成为 Responses；当前映射覆盖文本、best-effort 多模态输入、function 与 namespace 工具、结构化输出控制、reasoning、refusal、token usage 和相应事件。 |

桥接不是 OpenAI 与 Anthropic 间的跨协议路由。当前桥接不向 Chat 上游传递
`previous_response_id`、`truncation`、`background:false`、多数
`include` 语义、未建模顶层扩展，以及 Chat 无法承载的内置/custom/local-shell 工具；请求级
`reasoning.summary` 也没有映射或 Drop 记录。`background:true` 在入口拒绝，`multi_agent.enabled=true`
在桥接候选上显式拒绝。`item_reference`、`compaction` 和未知 input item 在桥接构造 Chat messages 时
被忽略；reasoning input item 只在紧邻后续 `function_call` 时用于回灌，否则也被忽略。

`include` 不是完全无效：当其包含 `reasoning.encrypted_content`，或请求显式 `store:false` 时，桥接会在
reasoning output item 上附加 `unio-rsn-v1:` 加 Base64 的可逆 `encrypted_content` 载体。相同 reasoning
文本同时以 `content.reasoning_text` 明文返回，因此该载体不是加密内容，也不等价于 OpenAI 的加密
reasoning token。后续桥接只解码该前缀的载体，并在工具调用轮回灌 reasoning。

bridge mapper 的 `DroppedFields` 目前只收集顶层无承载字段、顶层扩展和不支持的工具类型；上述被忽略的
input item 与请求级 `reasoning.summary` 不在其中。非流式、流式、compact、`input_tokens` 和候选估算的
生产调用点又都丢弃 translation 返回值，因此 bridge-level Drop 连应用日志都没有形成。本文前述
`Provider Drop` 是 Provider adapter 出站策略；当前 DeepSeek Adapter 的字段名日志与 bridge translation
不在同一层，也不能替代可关联的持久审计。

原生直传也不是字节级无条件透传：非流式 2xx 若 `status=failed` 或带 `error` 会转为安全的上游错误；
流式 `response.failed` 与 `error` 会重建为脱敏最小信封，上游附加的 Chat `[DONE]` 会被截留且不能替代
`response.completed/incomplete`，畸形的多行 `data` 帧可能被修复。普通成功 payload 除模型回显改写外
保持上游结构；流式成功终态会暂存到 settlement/recovery 接管后再原样交付。

`/v1/responses/compact` 没有独立的 Compact-only 候选过滤。它先按强制 Chat bridge 的口径
要求候选同时具备 Chat tokenizer 与非流式 Chat 能力，然后在调用阶段按
`HasResponsesCompact` 选择原生路径或摘要型降级。因此仅注册 Responses Compact、但没有
Chat 基线能力的 AdapterKey 当前不能服务该端点。

当前 Responses service 构造后固定开启同候选 404/405 回落，没有生产 setter 或运行配置
入口。命中时会以一次独立准入的 Chat transport 转入摘要路径；鉴权、限流、超时、
其他 4xx/5xx 不触发同候选的这次透明调用，但普通候选生命周期仍可对可重试错误切换
到下一候选。2xx 但缺少可靠 usage 会记录 `risk_exposure` 并失败收口，不触发摘要回落。

原生 compact 成功时保留上游完整 JSON，仅改写顶层模型回显；响应可以是包含 `id`、`object`、`model`、
`output` 和 `usage` 的完整 Response-like 对象，也可以包含上游 `compaction` item。Gateway 不解释其中的
`encrypted_content`。摘要路径只返回带 `output` 数组的对象，数组包含 0 或 1 个 assistant message；
当前不会签发 `compaction` item 或任何 Unio compaction token。两条 compact 路径都不使用 SSE；后续请求
若落到 Chat bridge，回传的 `compaction` 或 `item_reference` input item 会被忽略。

`/v1/responses/input_tokens` 始终选取 Route 计划的第一个 OpenAI 候选，把请求映射为 Chat 后调用该
候选的 Chat tokenizer；即使候选注册了原生 Responses 能力，也不改用 Responses tokenizer。该操作不执行
生成请求的候选能力筛选、运行态 admission、fallback、上游调用、请求记录或计费，因此只是一项本地近似估算。

### 桥接流事件

当前 Chat 桥接的 Responses SSE 只生成可由 Chat 语义表达的事件族。实现为每条流从 0 开始生成单调递增的
`sequence_number`，将 delta 作为增量、`*.done` 作为映射后的最终值，并只在终态 Response 中附带
映射后的 token usage。

| 场景 | 最小事件与终态 |
| --- | --- |
| 文本输出 | `response.created`、message `output_item.added`、`content_part.added`、`output_text.delta`、`output_text.done`、`content_part.done`、带完整 message 的 `output_item.done`。 |
| reasoning 输出 | reasoning `output_item.added`、`content_part.added`、`reasoning_text.delta`、`reasoning_text.done`、`content_part.done`、带完整 reasoning item 的 `output_item.done`；满足条件时该 item 含 Unio reasoning 回放载体。 |
| function 调用 | function `output_item.added`、`function_call_arguments.delta`、带完整 `call_id`、名称和 arguments 的 `output_item.done`。 |
| refusal | message `output_item.added`、refusal `content_part.added`、`response.refusal.delta`、`response.refusal.done`、`content_part.done`，并在最终 message `output_item.done` 与终态 Response 中保留完整 refusal part。 |
| 正常终态 | `stop`、工具调用等映射为 `response.completed`；`length` 或 `content_filter` 映射为 `response.incomplete`。 |
| Bridge 开流后失败 | 尽力追加 `event: error` 后中断，不合成 `response.failed`，也不得发送 `response.completed`。 |
| 原生直传失败事件 | 上游 `response.failed` 或 `error` 经脱敏重建后转发，随后按失败收口，不追加成功终态。 |

内置工具、文件搜索、图像生成和其他 Chat 无法表达的 OpenAI 专属事件不由桥接路径伪造。

### 当前边界

- bridge mapper 的 `DroppedFields` 未被生产调用点消费；Provider Adapter 当前只有字段名应用日志，
  两层都没有可关联的脱敏持久审计。
- bridge 跳过的部分 input item 与 reasoning 字段不进入 `DroppedFields`，客户响应也没有统一的降级字段。
- 入口在候选选择前以 `DEBUG` 记录全部 `anthropic-beta` token，官方 Adapter 又记录策略拦截项；因此
  实际会转发的 beta 也可能在入口被标成 ignored，并产生重复记录。

本文于 2026-07-26 按当前 Gateway 代码、Schema 和现有测试接收为 `active`。

请求体大小限制可配置，正常启动的缺省值为 128 MiB，超过限制返回 413；底层 JSON reader 只有在
未初始化或 setter 收到非正值时才回退 1 MiB。若前置代理配置了更小的限制，请求会先被代理拒绝；
Gateway 的配置不能控制该外部边界。请求体限制与模型上下文窗口和计费无关。

## 同协议路由

OpenAI 入口只在 OpenAI 协议候选间选择，Anthropic 入口只在 Anthropic 协议候选间选择。任何
OpenAI 与 Anthropic 间的桥接当前均未实现。公开协议字段被入口接收也不构成运行时能力保证；
模型能力声明当前只用于展示和运营配置，不参与该字段的运行时准入。

## 上游参考

本文不保存第三方协议快照。以下记录只用于追溯本次迁移核验过的来源；“未记录”表示旧来源没有
写明查阅日期，不能用文件时间或 Git 提交时间补写。通用字段与事件始终以当前官方资料为准。

| 迁移来源主题 | 当前官方来源 | 旧来源查阅基线 |
| --- | --- | --- |
| OpenAI Chat Completions | [Create Chat Completion](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) | 2026-06-07 |
| OpenAI Responses 创建 | [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create) | 未记录 |
| OpenAI Responses 流式事件 | [Streaming Responses](https://developers.openai.com/api/docs/guides/streaming-responses?api-mode=responses) | 旧资料曾在 2025-10-19 / 2026-01-21 交叉核验社区与 wire 样例；官方页查阅日未记录 |
| OpenAI Responses 其他操作与错误 | [Responses resources](https://developers.openai.com/api/reference/resources/responses) | 未记录；旧资料明确存在待官方复核字段 |
| Anthropic Messages | [Create a Message](https://platform.claude.com/docs/en/api/go/messages/create) | 2026-06-07 |
| DeepSeek Anthropic 兼容 | [Anthropic API](https://api-docs.deepseek.com/guides/anthropic_api) | 2026-06-01 |
| DeepSeek 通用 API | [DeepSeek API Docs](https://api-docs.deepseek.com/) | 按具体适配变更重新核验 |

上游页面变化不会自动改变当前 Gateway 代码行为。旧来源中标记为待核验或由非官方资料交叉整理的
内容不作为本文当前实现事实。
