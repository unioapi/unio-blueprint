---
title: Gateway 请求生命周期
description: 请求从身份确认到协议交付、结算与恢复的当前行为。
status: active
owner: 网关团队
last_updated: 2026-08-05
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
  - ../decisions/adr-0017-authoritative-first-token.md
---

# Gateway 请求生命周期

## 摘要

不同公开协议共享请求身份、候选执行、账务和审计生命周期，但不共享公开 DTO。本文记录当前代码、
Schema 和测试能够共同证明的行为。

## 当前调用流程

1. 认证调用方，为当前受保护的公开 `/v1` 请求取得一次由独立 UUID 标识的 `(Route, User Account)`
   request-admission session。Chat Completions、Responses 主操作、Responses compact 和 Messages 通过协议前置
   校验并进入 service 后，才另行创建 `req_` 持久业务请求 ID；HTTP `trace_id` 不替代这两个标识。
2. 对生成或压缩请求，按入口协议和客户模型形成候选计划，过滤不支持当前 Endpoint 或传输方式的 Adapter，以及
   缺少 Channel-Model 映射的候选；模型能力声明当前不是运行时准入闸门。
3. 对候选执行一次只读运行态快照，取得资格、Channel 并发和评分 control，再结合最近 30 分钟 attempt 样本，
   计算成本、并发、TTFT、错误率和 Priority 五项客观分并确定性排序；然后对每个候选按最终上游 wire 分别估算
   完整输入 token。快照不预占候选资源；runtime-sync/pending/stale identity/config 会使整批失败。
4. 账务授权按所有可用候选中最保守的输入与输出估算冻结余额。余额不大于零时不调用上游；余额大于零但不足
   完整授权额时冻结全部剩余可用余额并继续调用，不自动缩小客户输出上限，也不把账务输出估算写入上游请求。
   输入估算不预占任何限额：它只服务于余额冻结、价格计算与 TPM 观测。
5. 按实际扫描顺序执行。每个真实 transport 前取得新的 `AttemptPermit`，permit 成功后才创建 attempt；denied
   candidate 不创建 attempt、不调用该候选上游。单候选并发满立即扫描下一候选；只有整池都仅因并发满时，
   才共享一次有界等待并完整重扫。除候选 Acquire 的 Store 类故障外，执行器继续后续候选。
6. Adapter 对一个 attempt 发起一次真实调用并生成协议响应和 `ResponseFacts`。生命周期同时记录请求是否完整
   写出、是否收到响应头、是否出现协议定义的有效生成 Token。首字前协议事件先按 attempt 暂存，不向客户
   泄漏失败渠道身份；有效生成 Token 成功写出前可按稳定错误类别 fallback，向客户写出任意帧后不再切换候选。
   明确的上游 HTTP 403 在精确 Channel-Model 权限暂停写入成功后属于可切换错误；缺少 403 metadata 的
   `permission` 仍不可切换。
   明确未写出才 `Abort` 释放 Channel 并发；已有交互证据或结果不确定时 `Finish` 保留 Channel attempt 事实。
   Channel `response_timeout_ms` 区分响应头和非流式响应体
   阶段；流式首个有效生成 Token 还受 `first_token_timeout_ms`（上游首字超时）限制，之后由全局 stream-idle
   timeout 接管。
7. 取得可结算事实后，recoverable settlement 先校验事实并创建 pending recovery job，再尝试内联结算。
   内联结算成功后尽力把 job 标为 succeeded；内联失败但 job 已持久化时由 worker 接管。
8. 非流式响应和全部流式成功终态都在第 7 步完成或由 recovery 接管后才交付。缺少上游 final usage 的
   partial 成功仍必须写出协议终态（Responses `response.completed/incomplete`、Anthropic `message_stop`）；
   Responses 直传使用暂存的上游原始终态，bridge 与 Messages 使用 Gateway 生成的终态。
9. handler 返回后唯一 Finalize request-admission session：只释放入口并发并关闭 token，RPM/RPD 作为已接收
   请求保留，不接收任何 token 用量。候选 fallback 不重复取得或终结入口
   资源。普通 revision 更新不改变该收口；integrity epoch 已换代时 Finalize 会在 Redis 调用前失败，入口资源只能
   等待 TTL 过期。

客户显式输出上限由各公开协议校验并原样映射；OpenAI Chat Completions、Responses 和 Responses Compact 省略
输出上限时，Gateway 不合成固定默认值或模型能力上限。协议输出上限和账务预授权分别承担协议约束和金额风险
控制职责，不互相回流。

Route/User 的 RPM、RPD 和并发是请求层准入资源。Channel 只有并发是候选硬门槛；Channel RPM、RPD 由真实
attempt 的分钟/UTC 日观测桶自动聚合，不参与拒绝或评分。观测写入 best effort，失败不改写客户请求结果。

TPM 在任何一层都不是准入维度。Route 与 Channel 的 TPM 各自记在独立的分钟观测桶里：请求发出时按输入估算
写入 provisional，流式输出按每个 chunk 的实际观察分钟累加，非流式输出整体归入完整响应到达的分钟。可靠
usage 到达后，输入差额落在输入原始分钟，实际输出按各分钟已观察到的权重等比分配，最后一个分钟承担整数
除法余数，分钟合计严格等于实际输出。观测输入等于互斥的 uncached input、cache read 与各类 cache write 之和，
输出等于 `output_tokens_total`；reasoning 只是输出总量的分解项。目标分钟桶已过保留期或超出回溯窗口时放弃
修正、绝不重建，任何字段都不会变成负数。可靠 usage 缺失时保留已观察到的估算并增加 missing 计数，Admin 可以
同时看到当前分钟的 TPM 与 usage 覆盖率。

## 资金与恢复事实

| 事实 | 当前行为 |
| --- | --- |
| 授权先于上游调用 | 授权发生在逐候选 permit 和 transport 之前；余额不大于零时不调用上游。启用长上下文阶梯时，普通价和阶梯价按同一 token 估算分别计算并取较高值。 |
| 超额结算 | `capture = min(actual, authorized)`；随后从结算时未冻结可用余额独立补扣，剩余差额才形成 `write_off`，客户余额不为负。 |
| 历史结算 | 已完成 settlement 会写 usage、售价和 Provider 成本快照，后续配置变化不重算已完成账单。 |
| pending recovery | job 保存 usage、客户短上下文售价向量、成本来源 pin、目标终态、错误事实和长上下文策略；worker 不重调上游、不重新解析公开响应，也不回查价格表推断策略。 |
| token 用量为 `unknown` | 账务仍按既有规则拒绝不可靠 usage；TPM 观测不按零或本地输出猜测 actual，而是保留已观察到的估算并增加 missing 计数。 |
| recovery 耗尽 | job 进入 `dead` 后，worker 仅在请求仍为 `running` 时释放授权、按授权额记录 `risk_exposure`，并把请求标记为 `failed`。 |
| 孤儿授权清扫 | `authorized` + 请求仍 `running` + delivery 尚未开始 + 超年龄阈值 + 无 recovery job；没有 running attempt 时直接收口，有 running attempt 时必须确认 permit 已失效。遗留 attempt 标为平台失败，释放冻结、记 `risk_exposure`，请求标 `failed`（`gateway_request_orphan_reclaimed`）。 |
| 搁浅授权清扫 | `authorized` + 请求已 `failed`/`canceled` + 超年龄阈值 + 无 recovery job；只释放冻结，不改请求终态（`gateway_request_stranded_reclaimed`）。三方边界见 [账务与结算](billing-settlement.md)。 |

输出总量是权威输出计量；reasoning 是其可能的分解。token 维度区分 `known`、`not_applicable` 和
`unknown`，`unknown` 不会按零结算。只有满足完整性约束的可靠 usage 会修正 TPM 观测桶；本地或 partial
usage 不参与修正。

## 流式分支

| 条件 | 交付与 fallback | 账务与状态 |
| --- | --- | --- |
| 有效生成 Token 成功写出前失败 | 尚可按错误类别 fallback；前导帧暂存被丢弃 | 当前候选 attempt 失败；候选耗尽后释放授权。 |
| 客户取消，且有效生成 Token 已确认写出 | 不再 fallback，交付记 interrupted | 使用 `partial_stream_estimate`；即使已写帧没有更多可见文本，仍按保守输入和已累计输出结算。请求与 attempt 的内联目标状态为 canceled。 |
| 上游中断，有效生成 Token 已确认写出 | 不再 fallback，交付记 interrupted | 使用 `partial_stream_estimate`；即使 tokenizer 估算 output 为零，也按保守输入事实结算；请求与 attempt 的内联目标状态为 failed。 |
| 上游中断，仅前导帧或没有有效生成 Token | 不再 fallback（若已有前导帧）；交付记 interrupted | 不做 partial settlement，释放授权；bill-on-disconnect 渠道可另记平台成本敞口。 |
| 上游正常结束、缺少最终 usage，且有效生成 Token 已写出 | 不再 fallback，交付记 completed | 使用 `partial_stream_estimate`，请求与 attempt 按 succeeded 收口。 |
| 上游正常结束、缺少最终 usage，且仅有前导帧暂存 | 不向客户交付暂存前导帧 | 不做 partial settlement，释放授权，返回 usage-missing。 |
| 已取得可靠 `ResponseFacts` 后发生尾部错误 | 不再 fallback；已开始交付时记 interrupted | 仍按可靠 usage 完整结算；普通错误把请求与 attempt 收为 failed，客户端取消收为 canceled，并保存对应错误事实。 |
| 内联结算失败但 recovery 已接管 | 按上述分支继续结束当前交付 | 请求可暂时保持 `running`；worker 后续重放或进入 `dead`。 |

`partial.v1` 使用预授权阶段的保守输入估算，并按进程配置的固定缓存率拆为 cache-read 与 uncached，
默认比例为 60% / 40%。输出只累计有效生成 Token 交付后确认写出的协议可见文本；tokenizer 失败时非空文本
也可能累计为零，但这不取消“有效生成 Token 已交付”这一 partial 资格。当前没有用后到权威 usage 替换 partial 估算的机制；重复 settlement 要求原 usage、
来源和映射版本一致。

Gateway TTFT（`gateway_first_token_at - started_at`）与上游 TTFT
（`upstream_first_token_at - upstream_started_at`）独立记录；判定与字段边界见
[ADR-0017](../decisions/adr-0017-authoritative-first-token.md)。

## 交付与审计

非流式成功结果绑定 first-terminal-wins 的 delivery finalizer：响应写入成功记 `completed`，写入错误或 panic
记 `interrupted`。流式路径按上表推进 delivery。delivery 更新使用脱离客户取消的短超时上下文，写入错误被
忽略；该字段记录 Gateway 写入路径的结果，不确认客户程序已经收到数据。

Gateway HTTP server 不使用从请求头读取完成开始计算的绝对写超时，以免合法长流被固定总时长截断。普通 JSON
响应在真正写出前设置一次下游写窗口；SSE 在每个 event 写出前刷新滑动窗口，正常启动时窗口为 30 秒。
因此活跃长流可以持续，而停止读取的慢客户端不能无限占用一次写操作。

公开成功只表示当前协议交付路径已满足返回条件，不等于后台 settlement 已最终成功。pending recovery
最终耗尽时，客户可能已经完整收到成功响应且 delivery 保持 `completed`，但 request 后来被标记为 `failed`。

审计默认只保存协议、操作、模型、完成分类、用量、Provider/Channel 安全标识和有限诊断，不保存 prompt、
完整响应、凭据、API Key 明文或上游错误正文。

请求日志始终携带入口 `trace_id`。`request_records` 插入成功后才增加 `request_id`；取得 Permit 并成功创建
真实 attempt 后增加 `attempt_id`；上游返回可选请求标识后才增加 `upstream_request_id`。INFO 模式用一条
`http/request/request completed` 汇总业务请求的最终 Provider/Channel、双 TTFT、attempt/fallback、容量等待、
Sticky、交付、结算、usage、收费和稳定错误码；临时 DEBUG 模式保存认证、完整候选评分、Sticky、Permit、
attempt 时序、首字、交付和结算过程。四种 ID 的边界见
[ADR-0005](../decisions/adr-0005-request-identity.md)。

每个进入候选规划的请求另保存一条结构化 routing trace，从 `partial` 收口到 `complete`，记录候选资格、五项
评分、基准与实际扫描顺序、Sticky CAS、容量等待、真实 attempt、timeout phase 和最终结果。trace 与请求记录
一对一绑定并随请求级联删除。

## 当前边界事实

- orphan / stranded 清扫与 settlement recovery 的互斥条件、permit 存活判断、request 行锁、默认参数与巡检
  边界见[账务与结算](billing-settlement.md)。orphan 只自动处理尚未开始交付的请求；active permit、Redis 状态
  不明或已交付内容的请求都会保守保留。
- delivery 状态写入是 best effort；部分流式 settlement 或 recovery job 创建失败分支会在标记 interrupted 前
  返回，记录可能停留在 `in_progress`。
- token partial settlement 没有权威 usage 后到修正路径；当前幂等校验会拒绝不同 usage 的再次 settlement。

## 关联决策

- [ADR-0003：预付账务与可审计结算](../decisions/adr-0003-billing-settlement.md)
- [ADR-0005：HTTP 关联标识与持久请求标识分离](../decisions/adr-0005-request-identity.md)
- [ADR-0006：协议适配边界](../decisions/adr-0006-protocol-adapter-boundary.md)
- [ADR-0007：原子准入控制](../decisions/adr-0007-atomic-admission-control.md)
