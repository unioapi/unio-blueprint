---
title: "ADR-0017：权威首字判定与双 TTFT"
description: "统一三协议有效生成 Token 判定，拆分上游 TTFT 与 Gateway TTFT，并以前导帧缓冲保护 fallback 与计费边界。"
status: active
owner: 网关团队
last_updated: 2026-07-31
related:
  - ../glossary.md
  - ../features/request-lifecycle.md
  - ../features/routing-load-balancing.md
  - ../features/billing-settlement.md
  - adr-0003-billing-settlement.md
  - adr-0016-five-factor-routing-and-cas-sticky.md
---

# ADR-0017：权威首字判定与双 TTFT

## 背景

流式链路曾把「首个可识别协议事件」「上游首个有效生成 Token」和「Gateway 首次向客户交付有效 Token」混用。
OpenAI Responses 的 `response.created`、Chat Completions 的 role-only chunk、Anthropic Messages 的
`message_start` 都可能提前停止首字超时、锁死 fallback、写入 TTFT，甚至让仅交付协议前导帧的请求进入
partial settlement。

## 决策驱动因素

- 三种流式协议必须共用同一套「算不算首字」的判定事实，不能依赖每个构造点是否记得盖章。
- 上游 attempt 诊断、渠道评分与客户体验延迟使用不同起点和终点，不能共用一个时间戳。
- 首字前失败不得向客户泄漏失败渠道身份，并保留按错误类别 fallback 的能力。
- partial settlement 只能在有效生成 Token 已交付后成立；仅前导帧不能扣客户费。

## 备选方案

### 方案：继续用首个可识别协议事件

把任何可解析 SSE/JSON 事件当作首字。

**优点**

- 实现简单，与早期超时看门狗一致。

**缺点**

- 前导帧会提前停超时、锁 fallback、污染 TTFT，并可能错误收费。

### 方案：拆分上游与 Gateway 两套权威首字

以协议纯函数判定有效生成 Token；上游与客户交付分别计时；首字前缓冲前导帧。

**优点**

- 超时、评分、客户体验、fallback 与计费边界可单独解释。

**缺点**

- 三协议需要维护判定矩阵；零输出成功流要在结算后再 flush 前导/终态事件。

## 决策

1. 有效生成 Token 由各协议 `FirstTokenPayload(chunk)` 纯函数判定：返回非空字符串即算首字，不做
   `TrimSpace`；空格等真实生成字符也算。未识别事件默认不算首字。
2. OpenAI Chat Completions 以非空 `content` / `reasoning_content` / `refusal` / 工具或函数名称与参数为
   首字；role-only、纯 ID/model、usage/finish-only、空 delta 不算。
3. OpenAI Responses 以非空 output/reasoning/refusal delta、function arguments delta、携带真实工具名称或
   参数的 output item 为首字；`response.created/queued/in_progress`、控制事件、usage、终态与 `error`
   不算。
4. Anthropic Messages 以非空 text/thinking/input JSON delta、携带工具名称的 tool-use block 为首字；
   `message_start`、空 `content_block_start`、ping、signature-only、usage/message delta、stop 与 error
   不算。DeepSeek 复用对应 OpenAI/Anthropic adapter 判定，不维护分叉规则。
5. 上游 TTFT 起点是紧邻 `http.Client.Do` 前的 transport start，终点是成功解析首个有效生成 Token；用于
   `first_token_timeout_ms`、渠道评分样本和 attempt 诊断。Admin 文案称「上游首字超时」。
6. Gateway TTFT 起点是业务请求记录 `started_at`，终点是对应有效生成 Token 成功写入客户响应
   （`gateway_first_token_at`）；用于 Dashboard、请求列表和客户体验。请求级 API 字段为
   `gateway_ttft_ms`。
7. 首字前协议事件在 lifecycle 中按 attempt 暂存，上限 64 个事件或 256 KiB。失败、超时或 fallback 时
   丢弃暂存；首字到达后按原顺序写出前导事件和首字事件。任意客户帧成功写出只推进 delivery；只有真正
   携带生成负载的客户帧成功写出才确认 Gateway 首字，两个事实分别 first-write-wins 持久化。Responses
   Chat 桥接一个上游 chunk 展开的多个事件必须按实际事件确认，不能用 `response.created` 或空 item 帧代替。
8. 向客户写出任意帧后不得 fallback。partial settlement 必须已有有效生成 Token 成功交付；仅前导帧后失败
   时释放预扣，并可记录上游成本敞口。上游正常结束但缺 final usage 时，partial settlement 之后仍必须写出
   `response.completed/incomplete` 或 `message_stop`。Responses 直传的上游成功终态同样先暂存，durable
   settlement 后再原样交付，不重建或重复；零输出成功流仍写出必要前导/终态事件，两套 TTFT 均可为空。

## 影响

### 正面影响

- 首字超时与渠道评分只反映真实生成开始，不被前导帧污染。
- 首字超时没有有效 Token 终点时只形成错误率事实，不生成 TTFT 样本。
- 客户侧 Gateway TTFT 包含完整业务等待，与单次 attempt 上游 TTFT 可同时展示。
- 首字前失败不泄漏渠道身份，并可继续 fallback。
- 计费边界与「是否已交付有效生成内容」一致。

### 负面影响

- 协议判定矩阵需要随上游事件演进维护。
- 前导帧缓冲占用固定内存上限；超限按首字前上游协议失败处理。

## 风险与缓解措施

| 风险 | 缓解措施 | 负责人 |
| --- | --- | --- |
| 漏判有效 Token 导致空流或超时 | 判定是 chunk 纯函数；三协议正反矩阵测试 | 网关团队 |
| 误把前导帧当首字导致错误收费 | partial 路径要求 Gateway 首字已交付；仅前导帧释放预扣 | 网关团队 |
| 字段改名破坏 Admin | Gateway Admin API、Dashboard 与 Admin 前端同步改名，无兼容双写 | 网关团队、Admin 团队 |

## 落地与验证

当前 Schema 使用 `gateway_first_token_at`；attempt 保留 `upstream_started_at`、`upstream_first_token_at` 与
派生 `upstream_ttft_ms`。Dashboard 聚合使用 `gateway_ttft_*`；渠道质量评分继续使用上游 TTFT 样本。测试覆盖
三协议判定矩阵、前导缓冲、首字前后 fallback/计费分支，以及 Admin 双 TTFT 展示。

## 取代关系

- 取代：无。
- 修订：[ADR-0016](adr-0016-five-factor-routing-and-cas-sticky.md) 中「首个有效协议事件」停止首字超时的表述；
  [ADR-0003](adr-0003-billing-settlement.md) 中以「首个客户帧」作为 partial 门槛的表述。
- 被取代：无。

## 参考资料

- [网关词汇表](../glossary.md)
- [请求生命周期](../features/request-lifecycle.md)
- [路由负载均衡](../features/routing-load-balancing.md)
- [计费结算](../features/billing-settlement.md)
