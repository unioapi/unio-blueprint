---
title: "ADR-0003：预付授权、结算与恢复的账务边界"
description: "Gateway 在上游调用前冻结可用余额，按 token_v1 结算，并以补扣、核销、快照和恢复记录账务事实。"
status: active
owner: 网关团队
last_updated: 2026-08-04
related:
  - ../overview.md
  - ../features/access-control.md
  - ../features/billing-settlement.md
  - ../features/request-lifecycle.md
  - adr-0002-route-product-pricing.md
  - adr-0017-authoritative-first-token.md
---

# ADR-0003：预付授权、结算与恢复的账务边界

## 背景

Gateway 在调用上游前通常只有输入估算和输出上限，无法取得最终 usage；调用完成后又必须同时解释客户
实扣、平台核销、Provider 成本和异常恢复。当前个人账户模式把余额、reservation、ledger 和请求用量直接
归属 User Account；Project 不属于当前身份或账务结构。

## 预授权

- 授权使用候选的保守输入估算、客户输出上限、候选模型最大输出上限或进程兜底上限计算金额，并取候选中
  最大的估算金额作为本次授权上界。
- `estimated_amount` 必须大于零。可用余额是 `balance - reserved_balance`；可用余额不大于零时拒绝请求，
  不调用上游。
- 可用余额足以覆盖估算金额时冻结估算金额；可用余额为正但不足时冻结全部剩余可用余额并继续请求。
  因此 `authorized_amount = min(estimated_amount, available_balance)`，且不会形成负余额。
- 一次请求只建立一条 reservation。Route 内 fallback 复用该授权，不重新冻结余额。
- API Key `spend_limit` 在认证时按 `spent_total >= spend_limit` 拒绝。`spent_total` 在结算事务中累加客户
  实际承担的 capture 和 overage debit；并发或在途请求可以使最终累计值超过上限，因此它是软上限。

## 当前计费公式

- 客户收费和 Provider 成本都使用 `token_v1`。公式消费未缓存输入、缓存读取、5 分钟缓存写入、1 小时
  缓存写入、30 分钟缓存写入、输出总量和 reasoning 输出七个 token 维度。
- token 状态为 `not_applicable` 时按零参与公式；当前公式需要的任一维度为 `unknown` 时 settlement 失败，
  不把未知用量静默当作零。
- Anthropic `web_search_requests` 与 `web_fetch_requests` 当前不参与授权金额、客户收费或 Provider 成本。
  合法正数可以作为 `usage_line_items` 事实保存，但没有对应的售价、成本或金额快照。
- 客户售价和 Provider 成本来源服从 [ADR-0002](adr-0002-route-product-pricing.md)：客户售价按模型基准价和
  Route 倍率确定，Channel fallback 不改客户价；Provider 成本使用绝对覆盖或模型基准价乘成本倍率与充值倍率。

## 结算与核销

结算按 usage 算出 `actual_amount`，并在同一数据库事务中提交 usage、客户价格快照、Provider 成本快照、
ledger、API Key `spent_total` 以及 request/attempt 终态。

当 `actual_amount > 0` 时：

1. `capture = min(actual_amount, authorized_amount)`，结束整条 reservation 并释放未捕获的冻结余额。
2. 若仍有差额，从结算时未被其他 reservation 冻结的可用余额独立执行 overage debit；该 debit 有独立
   幂等键，不扩大 `reservation.captured_amount`，也不使余额变负。
3. `write_off = actual_amount - capture - overage_debit`；只有两笔客户实扣后仍无法收取的残差形成平台核销。

当 `actual_amount = 0` 时，settlement 仍保存 usage、价格和成本快照，但释放 reservation，不写零金额 debit，
也不增加 `spent_total`。

价格快照保存结算使用的 token 售价向量、公式版本、Route 倍率和长上下文应用标记。成本快照保存成本向量、
各 token 分项金额、总成本、Provider/Channel、来源 pin/倍率和长上下文应用标记。客户总实扣由一条 capture
debit 和可选的一条 overage debit 表达，不保存在价格快照中。

## 流式部分结算

已向客户写出内容但没有 final usage 时，Gateway 可以用 `partial_stream_estimate` 进入同一结算管道：

| 当前分支 | 结算与终态 |
| --- | --- |
| 客户取消，有效生成 Token 已确认写出 | 使用保守输入估算和已写出可见文本的输出估算；request/attempt 目标为 `canceled`，delivery 为 `interrupted`。即使输出估算为零，也会结算保守输入。 |
| 上游中断，有效生成 Token 已确认写出且输出估算为正 | 使用同一 partial 事实；request/attempt 目标为 `failed`，delivery 为 `interrupted`。 |
| 上游正常结束、缺 final usage，且有效生成 Token 已确认写出 | 使用同一 partial 事实；request/attempt 为 `succeeded`，delivery 为 `completed`。 |
| 有效生成 Token 交付前终止，或仅前导帧后缺 usage / 上游中断后输出估算不大于零 | 不做 partial settlement，释放授权；bill-on-disconnect Channel 可以另记平台成本敞口。 |

`partial.v1` 复用授权阶段的保守输入估算，并按进程配置的固定比例拆分缓存读取与未缓存输入，默认
60% / 40%；输出只累计成功写出帧中的协议可见文本。已提交的 partial usage 当前不能被后到的权威 usage
替换，不同 usage 的再次 settlement 会发生幂等冲突。

## Settlement Recovery

- recoverable settlement 先验证事实并创建 pending recovery job，再尝试内联 settlement。job 保存 usage、
  响应标识、授权金额、客户短上下文售价向量、公式版本、成本来源 ID、request/attempt 目标终态、错误事实和
  独立长上下文策略，不重新调用上游，也不通过成本来源 ID 推断长上下文策略。
- job 创建失败时不会执行内联 settlement；调用路径会释放 reservation、记录账务异常 `risk_exposure` 并把
  请求收口为失败。该 `risk_exposure` 使用授权金额作为风险上界，不是已确认的 Provider 实际成本。
- job 已创建而内联 settlement 失败时，worker 按 job 事实幂等重放。重试耗尽后 job 进入 `dead`；worker
  仅对仍为 `running` 的请求释放授权、按授权额记录 `risk_exposure` 并标记 `failed`。已经交付的 delivery
  状态不会回滚。
- partial recovery 按 job 保存的 canceled、failed 或 succeeded 目标收口；已提交终态的再次重放只有在状态、
  错误、usage、`final_usage_received` 和账务事实一致时才按幂等成功返回。
- 授权清扫与 settlement recovery 按请求状态互斥：孤儿路径处理仍为 `running` 的 `authorized` 冻结（释放并记
  `risk_exposure`、请求标 `failed`），但必须同时没有 running attempt 和 recovery job；搁浅路径处理已为
  `failed`/`canceled` 的 `authorized` 冻结（只释放，不写敞口、不改终态）。orphan finalizer 与 recovery job
  创建通过同一 request 行锁串行化。参数、稳定码与巡检以 [账务与结算](../features/billing-settlement.md) 为准。
- 对 bill-on-disconnect Channel，客户取消、timeout、传输失败或部分 5xx 路径可以另记估算 Provider 成本
  敞口。该事实与客户 usage、余额和 ledger 分离，已形成完整或 partial settlement 成本时不重复记录。

## 当前边界

- token `unknown` 可以进入 recovery job，但 `token_v1` 每次重放仍会拒绝 settlement；事实不变时最终进入
  `dead`，没有可结算降级口径。
- orphan / stranded 清扫的列表与单条收口不在同一事务；orphan 收口在 request 行锁内重查 recovery job 和
  running attempt，recovery 创建使用同一行锁。崩溃后永久残留的 running attempt 不自动回收；
  `authorized` 配 `succeeded` 也不自动回收。细节见功能文档。
- `web_search_requests` / `web_fetch_requests` 的 line item 只接受正数；显式零会使 settlement facts 校验失败。
  recovery 又把零与缺失折叠，当前不能表达完整三态，也没有独立按次收费。
- `price_snapshots.price_id` 当前是可选的 `channel_prices` 成本覆盖行 ID，不是客户售价使用的
  `model_prices` 行 ID；价格快照也不保存客户总应收金额。
- bill-on-disconnect 成本计算失败不写记录；数据库写入失败只写日志，caller 忽略该错误，客户响应不变。

## 来源谱系

| 原 DEC | 原始日期 | 原状态 | 当前处理与取代/修订关系 |
| --- | --- | --- | --- |
| DEC-001 | 未记录 | accepted，当前实现部分超越 | 保留余额归 User Account；Project、API Key 容器和用量归集的旧层级由当前 `User Account -> API Key -> Route` 结构取代。 |
| DEC-003 | 未记录；2026-06-25 修订；2026-07-31 再修订 | accepted，部分修订 | 有效生成 Token 交付前终止或无输出不收费保留；已交付有效生成 Token 且无 final usage 的分支由 DEC-025 / ADR-0017 修订。 |
| DEC-006 | 未记录 | accepted，超额结算部分已取代 | 部分余额授权和余额不为负保留；“实扣封顶于原授权、差额全部核销”由当前 capture + 独立 overage debit + 残差 write-off 取代。 |
| DEC-007 | 未记录 | accepted，当前实现有不同边界 | 保留持久 recovery 负责上游成功后结算失败收口的边界；job 创建失败、partial 终态和长上下文恢复按当前代码记录。 |
| DEC-008 | 未记录 | accepted，部分超越 | 金额、usage、售价和成本快照保留；“不支持倍率”由 DEC-026 的售价倍率和 DEC-027 的成本倍率超越。 |
| DEC-025 | 2026-06-25 | accepted，来源标注待实施 | 代码已实现 partial settlement；实际三分支和不结算边界以本文当前事实为准。 |
| DEC-026 | 2026-06-29 | accepted | 客户售价采用模型基准价乘 Route 倍率，Route 内 Channel fallback 不改价。 |
| DEC-027 | 未记录 | accepted，部分修订 | 成本倍率、充值倍率、绝对覆盖和成本快照保留；独立参考成本基数由 DEC-031 取代。 |
| DEC-030 | 2026-07-10 | accepted | 30 分钟缓存写入是独立 token usage、售价和成本维度，不并入 5 分钟或 1 小时维度。 |
| DEC-031 | 2026-07-14 | accepted，来源称已实现 | 售价和成本共用 `model_prices` 基数；DEC-027 的倍率、充值倍率、绝对覆盖和快照机制不变。 |

## 状态说明

本文于 2026-07-26 按当前 Gateway 代码、Schema 与现有测试接收为 `active`。

## 取代关系

- 取代：DEC-006 的“客户实扣不超过原授权、差额全部核销”超额结算子句。
- 修订来源：DEC-003 由 DEC-025 部分修订；DEC-008 的无倍率结论由 DEC-026、DEC-027 超越；DEC-027 的
  独立成本基数由 DEC-031 修订。
- 被取代：无 Blueprint ADR。

## 参考资料

- [账务与结算](../features/billing-settlement.md)
- [请求生命周期](../features/request-lifecycle.md)
- [线路作为 API Key 绑定的供给与定价边界](adr-0002-route-product-pricing.md)
