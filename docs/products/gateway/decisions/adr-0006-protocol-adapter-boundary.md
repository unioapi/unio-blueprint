---
title: "ADR-0006：协议与 Provider 适配边界"
description: "记录公开协议分离、Adapter 运行时选择与统一商业事实的当前实现。"
status: active
owner: 网关团队
last_updated: 2026-07-27
related:
  - ../README.md
  - ../glossary.md
  - ../features/public-api-contracts.md
  - ../features/protocol-compatibility.md
  - ../features/provider-adaptation.md
  - ../features/provider-mapping-contracts.md
  - ../features/request-lifecycle.md
  - ../features/error-semantics.md
  - ../features/billing-settlement.md
  - adr-0001-domain-terminology.md
  - adr-0004-model-capabilities.md
---

# ADR-0006：协议与 Provider 适配边界

## 背景

Gateway 当前维护 OpenAI 与 Anthropic 两个公开协议族。OpenAI Chat Completions、
OpenAI Responses 和 Anthropic Messages 有独立的入口 DTO、公开响应、流式事件和错误映射；
Responses 是 OpenAI 协议族下的端点，不是第三个协议族。

本 ADR 使用 ADR-0001/0012 的术语：协议是 API 格式族，端点是公开操作/路径，Provider 的 `origin` 是
上游根地址并与公共故障域同属 Provider；Channel 是凭据、定价和适配选择单元。

数据库先按 Channel `protocol` 限定同协议候选，lifecycle 再按
`(protocol, adapter_key, operation capability)` 过滤本次操作可用的代码能力。
`model_capabilities` 不参与这个运行时选择，其当前边界由 ADR-0004 记录。

## 当前实现边界

1. OpenAI 与 Anthropic 公开协议不互相转换。路由 SQL 只返回与入口协议相同的
   Channel，Responses-to-Chat bridge 仍属于 OpenAI 协议族内部转换。
2. Channel 以 `protocol` 与 `adapter_key` 绑定运行时适配选择。Admin 写入和 Gateway 启动
   preflight 只保证复合键至少注册一种代码能力；每个请求还会按 tokenizer、非流式或
   流式能力继续过滤。
3. Adapter 不选择 Channel，不查询 Provider、Origin、Channel 或价格表，也不保存请求级
   业务状态。一次 Adapter 调用只执行一次 HTTP `Do`，redirect 跟随在 bootstrap 被禁用；
   retry 和跨 Channel fallback 由 lifecycle 建立新 attempt。Adapter 仍读取少量进程级配置，
   官方 Anthropic Adapter 还会通过注入的 provider 读取热更新 `anthropic.beta_policy`。
4. Responses 主操作按候选与本次调用方式分流：非流式分别检查 Responses 或 Chat
   能力，流式分别检查 Stream Responses 或 Stream Chat 能力。同一 key 有本次所需的
   原生能力时直传，否则使用 Chat bridge。混合候选只能在首个客户可见事件前互相
   fallback。
5. `/v1/responses/compact` 在候选准备阶段先要求 Chat tokenizer 与非流式 Chat 能力，
   然后在调用阶段按 `HasResponsesCompact` 选择 Native Compact 或 Synthetic Compact。因此仅注册
   Compact 而没有 Chat 基线能力的 key 当前不能服务该端点。当前 service 构造后固定开启
   同候选 404/405 回落，没有生产 setter 或运行配置入口；回落的 Synthetic 调用会重新取得
   permit 并创建独立 attempt。2xx 缺少可计费 usage 不回落，而是记录 `risk_exposure` 并失败收口。
6. Pass、Adapt、Drop 和 Reject 分布在公开入口、Responses bridge 与 Provider Adapter 三层。
   当前 Provider Drop 只有字段名应用日志；bridge mapper 返回的 `DroppedFields` 被五个
   生产调用点丢弃。两层都没有可稳定关联到 request 或 attempt 的脱敏持久审计。
7. Adapter 在同一次上游响应解析中生成协议内部响应或受控原文，以及独立的
   `ResponseFacts`。settlement、recovery 和审计不反向解析公开响应；两个协议族与
   Responses 直传/bridge 共用 attempt、usage、结算和恢复不变量。
8. 公开错误与 SSE 按入口协议渲染。Chat 成功流以 `[DONE]` 结束，Messages 以
   `message_stop` 结束，Responses 使用命名终态事件且不发 `[DONE]`。首个客户可见事件后
   发生错误时不改写 HTTP 状态，只尝试写协议内错误并中断，不伪造成功终态。

## 当前边界

- Responses bridge 只合成 Chat 可表达的字段、usage 和 SSE 事件。部分顶层字段、
  input item 和内置/custom/local-shell 工具会被 Drop 或忽略，且当前没有完整的
  客户可见降级信号。
- `background:true` 在 Responses 入口拒绝。`multi_agent.enabled=true` 在 bridge 候选上本地
  拒绝；该错误没有上游 retry 分类，因此排在前面的 bridge 候选会阻止继续尝试后续
  原生 Responses 候选。
- Responses 原生直传不是无条件字节透传。请求会重新编码并覆盖 `model` 与
  `stream`；普通成功 payload 会改写模型回显，失败信封、`[DONE]` 和部分畸形 SSE 帧还有
  额外的安全或兼容处理。
- `/v1/responses/input_tokens` 始终取 Route 计划的第一个 OpenAI 候选，先映射为 Chat
  再使用 Chat tokenizer。它不使用原生 Responses tokenizer，也不执行生成请求的候选能力
  过滤、运行态准入、fallback、请求记录或计费。
- 原生 Responses 流的上游成功终态可能在 settlement recovery 事实持久化前已经转发给
  客户；后续结算失败时 Gateway 无法撤回该终态。

## 来源与取代谱系

下表保留迁入来源的编号、来源日期、来源状态与当前处置。“来源状态”是历史文档状态；
本 ADR 的 `active` 只表示上述当前代码事实已被接收为 Blueprint 权威记录。

| 原 DEC | 来源日期 | 来源状态 | 当前处置、取代或修订 |
| --- | --- | --- | --- |
| DEC-002 | 未记录 | accepted | Adapter 不查询 Provider/Channel 业务数据的边界保留；官方 Anthropic Adapter 读取运行时 beta policy 是当前例外。 |
| DEC-009 | 未记录 | superseded by DEC-010 | 仅保留谱系；“仅 OpenAI 公开契约”不得恢复。 |
| DEC-010 | 未记录 | accepted | 当前双协议公开入口、协议原生响应与统一事实的主要来源。 |
| DEC-011 | 未记录 | accepted | retry 归 lifecycle、每次真实 transport 对应独立 attempt，bootstrap 禁止 redirect 重放。 |
| DEC-012 | 未记录 | accepted | Provider 映射 Pass/Adapt/Drop 保留；“已审计”收紧为当前应用日志和未消费诊断的实际状态。 |
| DEC-013 | 未记录 | accepted | beta header 入口宽进、出站按 Provider 策略转发或拦截；当前只有应用日志。 |
| DEC-014 | 未记录 | accepted | Responses-to-Chat 桥接保留；受 DEC-018 补充，不再适用于所有 Responses 请求。 |
| DEC-016 | 未记录 | accepted | Responses reasoning 显式 opt-in 与 DeepSeek 归一保留。 |
| DEC-018 | 未记录 | accepted | 补充 DEC-014：Responses 主操作按本次所需的非流式/流式能力在原生直传与 Chat bridge 间分流。 |
| DEC-019 | 未记录 | accepted | 请求体安全上限与 Native/Synthetic Compact 分流保留；本 ADR 补记 Chat 基线前置与回落开关的当前实现。 |
| DEC-024 | 2026-06-23 | accepted | 能力闸门已移除；`model_capabilities` 不参与 Adapter 选择或协议请求准入。 |

## 取代关系

- 取代：无；本 ADR 是对上述来源按当前代码事实的 Blueprint 合并记录。
- 被取代：无。

## 参考资料

- [ADR-0001：统一领域术语](adr-0001-domain-terminology.md)
- [ADR-0004：模型能力声明与运行时能力分离](adr-0004-model-capabilities.md)
- [公开 API 契约](../features/public-api-contracts.md)
- [协议兼容性](../features/protocol-compatibility.md)
- [Provider 适配](../features/provider-adaptation.md)
- [Provider 映射契约](../features/provider-mapping-contracts.md)
- [请求生命周期](../features/request-lifecycle.md)
- [错误语义](../features/error-semantics.md)
- [账务与结算](../features/billing-settlement.md)
