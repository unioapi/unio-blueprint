---
title: Gateway 请求生命周期
description: 请求从身份确认到协议交付、结算与恢复的当前行为。
status: active
owner: 网关团队
last_updated: 2026-07-29
related:
  - ../README.md
  - ../glossary.md
  - public-api-contracts.md
  - provider-adaptation.md
  - error-semantics.md
  - billing-settlement.md
  - admission-control.md
  - ../decisions/adr-0003-billing-settlement.md
  - ../decisions/adr-0005-request-identity.md
  - ../decisions/adr-0006-protocol-adapter-boundary.md
  - ../decisions/adr-0007-atomic-admission-control.md
---

# Gateway 请求生命周期

## 摘要

不同公开协议共享请求身份、候选执行、账务和审计生命周期，但不共享公开 DTO。本文记录当前代码、
Schema 和测试能够共同证明的行为。

## 当前调用流程

1. 认证调用方，为当前受保护的公开 `/v1` 请求取得一次由独立 UUID 标识的 `(Route, User Account)`
   request-admission session。Chat Completions、Responses 主操作、Responses compact 和 Messages 通过协议前置
   校验并进入 service 后，才另行创建 `req_` 持久业务请求 ID；HTTP correlation ID 不替代这两个标识。
2. 对生成或压缩请求，按入口协议和客户模型形成候选计划，过滤不支持当前 Endpoint 或传输方式的 Adapter，以及
   缺少 Channel-Model 映射的候选；模型能力声明当前不是运行时准入闸门。
3. 对候选执行一次只读 `SnapshotMany`，取得运行态资格、经济、健康和容量事实，再结合冻结的 Priority
   计算客观分并确定性排序，然后对每个候选分别估算输入 token 和输出预算。快照不预占候选资源；
   runtime-sync/pending/stale identity/config 会使整批失败。
4. 每个候选形成 `input_estimate + output_budget = candidate_budget`，Route 请求层 TPM 一次性 Reserve
   所有可用候选的最大 `candidate_budget`，再根据同一输出上限完成账务授权。余额不大于零时不调用上游；余额
   大于零但不足完整预算时冻结全部剩余可用余额并继续调用，不自动缩小客户输出上限。
5. 按候选顺序执行。每个真实 transport 前取得新的 `AttemptPermit`，permit 成功后才创建 attempt；denied
   candidate 不创建 attempt、不调用该候选上游。普通容量拒绝立即 fallback；只有 Sticky 固定首候选可短等
   一次。除候选 Acquire 的 Store 类故障外，执行器继续后续候选。
6. Adapter 对一个 attempt 发起一次真实调用并生成协议响应和 `ResponseFacts`。生命周期同时记录请求是否完整
   写出、是否收到响应头、是否出现协议定义的有效首字。首个客户帧成功写出前可按稳定错误类别 fallback；
   成功写出后不再切换候选。明确未写出才 `Abort` 释放 Channel 预占；已有交互证据或结果不确定时 `Finish`
   保留 Channel attempt 事实。
7. 取得可结算事实后，recoverable settlement 先校验事实并创建 pending recovery job，再尝试内联结算。
   内联结算成功后尽力把 job 标为 succeeded；内联失败但 job 已持久化时由 worker 接管。
8. 非流式响应，以及由 Gateway 生成成功收尾帧的 Chat、Messages 和 Responses 桥接流，在第 7 步完成或由
   recovery 接管后才交付成功终态。Responses 直传流会在 Adapter 回调期间原样写出上游终态，存在下述例外。
9. handler 返回后唯一 Finalize request-admission session；候选 fallback 不重复取得或终结入口资源。普通 revision
   更新不改变该收口；integrity epoch 已换代时 Finalize 会在 Redis 调用前失败，入口资源只能等待 TTL 过期。

Route 与 Channel 的 RPM、RPD、TPM 和并发由各自资源主体独立记录，不要求严格求和。Route RPD 是入口请求事实；
Channel 全局 RPD 是有上游交互证据的 attempt 容量事实，当前 Route 的 Channel 行另读 `(route, channel, UTC day)`
归因桶。Channel RPD 日桶必须覆盖完整 UTC 日和终态缓冲，原始桶意外丢失时 `Finish/Abort/Renew` 走
`runtime-sync-required`，不能静默重新计数或释放。

## 资金与恢复事实

| 事实 | 当前行为 |
| --- | --- |
| 授权先于上游调用 | 授权发生在逐候选 permit 和 transport 之前；余额不大于零时不调用上游。 |
| 超额结算 | `capture = min(actual, authorized)`；随后从结算时未冻结可用余额独立补扣，剩余差额才形成 `write_off`，客户余额不为负。 |
| 历史结算 | 已完成 settlement 会写 usage、售价和 Provider 成本快照，后续配置变化不重算已完成账单。 |
| pending recovery | job 保存 usage、客户短上下文售价向量和成本来源 pin；worker 不重调上游，也不重新解析公开响应。 |
| token 用量为 `unknown` | 账务仍按既有规则拒绝不可靠 usage；准入 TPM 不按零处理：已有上游交互时至少保留输入估算，Gateway 有本地输出计量时保留输入加输出，明确未写出才释放预占。 |
| recovery 耗尽 | job 进入 `dead` 后，worker 仅在请求仍为 `running` 时释放授权、按授权额记录 `risk_exposure`，并把请求标记为 `failed`。 |
| 超时授权清扫 | sweeper 选择 `authorized`、超过配置年龄阈值、请求为 `running` 且查询时不存在 recovery job 的记录；收口时释放授权、按授权额记录 `risk_exposure` 并把仍为 `running` 的请求标记为 `failed`。 |

输出总量是权威输出计量；reasoning 是其可能的分解。token 维度区分 `known`、`not_applicable` 和
`unknown`，`unknown` 不会按零结算。

## 流式分支

| 条件 | 交付与 fallback | 账务与状态 |
| --- | --- | --- |
| 首个客户帧成功写出前失败 | 尚可按错误类别 fallback | 当前候选 attempt 失败；候选耗尽后释放授权。 |
| 客户取消，且至少一帧已确认写出 | 不再 fallback，交付记 interrupted | 使用 `partial_stream_estimate`；即使已写帧没有可见文本，仍按保守输入和零输出结算。请求与 attempt 的内联目标状态为 canceled。 |
| 上游中断，已确认写出且累计估得正数 output token | 不再 fallback，交付记 interrupted | 使用 `partial_stream_estimate`；请求与 attempt 的内联目标状态为 failed。 |
| 上游中断，已写帧但累计估得的 output token 不大于零 | 不再 fallback，交付记 interrupted | 不做 partial settlement，释放授权；bill-on-disconnect 渠道可另记平台成本敞口。 |
| 上游正常结束、缺少最终 usage，且至少一帧已写出 | 不再 fallback，交付记 completed | 使用 `partial_stream_estimate`，请求与 attempt 按 succeeded 收口。 |
| 已取得可靠 `ResponseFacts` 后发生尾部错误 | 不再 fallback；已开始交付时记 interrupted | 仍按可靠 usage 完整结算。 |
| 内联结算失败但 recovery 已接管 | 按上述分支继续结束当前交付 | 请求可暂时保持 `running`；worker 后续重放或进入 `dead`。 |

`partial.v1` 使用预授权阶段的保守输入估算，并按进程配置的固定缓存率拆为 cache-read 与 uncached，
默认比例为 60% / 40%。输出只累计至少有一个客户帧成功写出的协议可见文本；tokenizer 失败时非空文本
也可能累计为零。当前没有用后到权威 usage 替换 partial 估算的机制；重复 settlement 要求原 usage、
来源和映射版本一致。

## 交付与审计

非流式成功结果绑定 first-terminal-wins 的 delivery finalizer：响应写入成功记 `completed`，写入错误或 panic
记 `interrupted`。流式路径按上表推进 delivery。delivery 更新使用脱离客户取消的短超时上下文，写入错误被
忽略；该字段记录 Gateway 写入路径的结果，不确认客户程序已经收到数据。

公开成功只表示当前协议交付路径已满足返回条件，不等于后台 settlement 已最终成功。pending recovery
最终耗尽时，客户可能已经完整收到成功响应且 delivery 保持 `completed`，但 request 后来被标记为 `failed`。

审计默认只保存协议、操作、模型、完成分类、用量、Provider/Channel 安全标识和有限诊断，不保存 prompt、
完整响应、凭据、API Key 明文或上游错误正文。

## 当前边界事实

- Responses 直传流会先原样写出上游 `response.completed`，Adapter 返回后才创建 recovery job 并结算。
  如果 job 创建失败，客户可能已经收到成功终态，request 随后却走失败收口。
- recovery job 不保存 partial settlement 的 request/attempt 目标终态和错误事实。初次结算未提交时，worker
  重放会默认按 succeeded 收口；若 canceled/failed settlement 已提交但 job 完成标记丢失，后续重放又会因
  request 终态不被幂等入口接受而持续失败。
- recovery job 没有直接保存长上下文策略。倍率成本路径可通过 `CostBaseModelPriceID` 重建策略；绝对
  `channel_prices` 成本覆盖路径该 pin 为零，worker 使用空策略，可能漏算客户售价和 Provider 成本的长上下文倍率。
- orphan sweeper 的列表查询与单条收口不在同一事务；收口只重查 request 是否仍为 `running`，不重查是否已
  并发创建 recovery job。流本体只有 idle timeout、没有总时限，正常活跃长流也可能超过年龄阈值并被误收口。
- delivery 状态写入是 best effort；部分流式 settlement 或 recovery job 创建失败分支会在标记 interrupted 前
  返回，记录可能停留在 `in_progress`。
- token partial settlement 没有权威 usage 后到修正路径；当前幂等校验会拒绝不同 usage 的再次 settlement。

## 关联决策

- [ADR-0003：预付账务与可审计结算](../decisions/adr-0003-billing-settlement.md)
- [ADR-0005：HTTP 关联标识与持久请求标识分离](../decisions/adr-0005-request-identity.md)
- [ADR-0006：协议适配边界](../decisions/adr-0006-protocol-adapter-boundary.md)
- [ADR-0007：原子准入控制](../decisions/adr-0007-atomic-admission-control.md)
