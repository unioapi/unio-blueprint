---
title: "功能设计：账务与结算"
description: "记录预付余额、授权、结算、核销、价格与成本快照的当前行为。"
status: active
owner: 网关团队
last_updated: 2026-08-05
related:
  - ../overview.md
  - ../glossary.md
  - request-lifecycle.md
  - ../decisions/adr-0002-route-product-pricing.md
  - ../decisions/adr-0003-billing-settlement.md
  - ../decisions/adr-0017-authoritative-first-token.md
---

# 功能设计：账务与结算

## 摘要

Gateway 当前采用预付余额模型：调用前冻结可用余额，调用后按本次 usage 和锁定售价结算，同时记录
Provider 成本、客户实扣与平台核销。已完成 settlement 的历史事实不随配置变化重算；pending recovery
保存 usage、客户短上下文售价向量、公式版本、成本来源 ID、目标终态、错误事实和长上下文策略。

## 当前计费范围

- 客户收费和 Provider 成本都只使用 `token_v1`，按 token 售价与成本向量计算。
- token 用量区分 `known`、`not_applicable` 和 `unknown`；`unknown` 不按零收费，而是使 `token_v1`
  settlement 失败。
- Anthropic `web_search_requests` 和 `web_fetch_requests` 当前只可能形成附加计量事实，不参与授权金额、
  客户收费或 Provider 成本计算。

## 授权

1. Gateway 对候选逐一使用保守输入估算和输出上限计算金额。模型启用长上下文阶梯时，同一份 token 估算
   分别按普通价和长上下文价计算并取较高值；再从全部候选中取最高金额作为本次授权上界。预授权不依赖本地
   输入估算是否已经越过长上下文门槛，最终是否真正应用阶梯价仍由结算时的可靠 usage 决定。
2. 客户未提供输出上限时，先取候选模型 `max_output_tokens` 的最大值；候选也未配置时回退进程默认值。
3. 可用余额不大于零时拒绝调用上游。可用余额足以覆盖估算金额时冻结估算金额；可用余额大于零但不足时，
   冻结全部剩余可用余额并允许调用。
4. 全部候选的授权估算金额为零时，ledger 以 `CodeLedgerInvalidAmount` 拒绝非正金额，不调用上游。当前价格和
   线路倍率允许配置为零，金额舍入后也可能触发该分支。
5. 线路内 fallback 不重新授权，也不改变本次客户售价边界。

这个上界消除了“本地估算未过门槛、真实 usage 过门槛”造成的价格档位差额，但不保证永远没有超额：输入
数量本身的估算偏差，以及余额不足时只冻结剩余可用余额，仍可能进入二次补扣或平台核销。Admin 对计费异常
汇总数量和平台承担金额，并可按 `authorization_underfunded` 查看明细。

API Key `spend_limit` 在认证阶段检查，是允许并发或在途请求结算后越界的软上限；超出量没有固定上界，
取决于检查后仍在途请求的实际实扣总和。`spent_total`
累加实际 reservation capture 与独立 overage debit，不包含平台 `write_off`。

## 实际结算

结算按本次 usage 计算 `actual_amount`，客户与平台承担关系为：

1. `capture = min(actual_amount, authorized_amount)`，只从原 reservation 捕获该金额。
2. 若 `actual_amount > authorized_amount`，从结算时 `balance - reserved_balance` 的未冻结可用余额独立补扣，
   补扣不扩大 reservation capture。
3. `write_off = actual_amount - capture - overage_debit`；只有客户两笔实扣后仍无法收取的残差形成平台核销。
4. 客户余额不会因结算变为负数。

成功 settlement 在同一收口中保存 token usage、客户价格快照、Provider 成本快照、账本结果和请求/attempt
终态。长上下文是否触发按真实输入 token 合计决定，并同时缩放客户售价和 Provider 成本。

当前成本有两条来源路径：命中的 `channel_prices` 绝对成本覆盖，或 `model_prices` 基数乘 Channel 成本倍率与
充值倍率。正常 settlement 使用请求候选中冻结的来源 pin，不按结算时重新选取另一条成本路径。

Provider 成本的七个金额分项先分别四舍五入到 10 位小数，`total_cost_amount` 再由这些已经舍入的分项
相加生成，不从未舍入的原值独立计算。这样成本快照中的总额始终严格等于分项合计。

流式请求已经取得可靠最终 usage 后又发生尾部错误时，仍按该真实 usage 完整结算，不改用估算，也不释放
为免费请求；但 settlement 同时保存交付失败事实。普通尾部错误把 request/attempt 收为 `failed`，客户端
取消收为 `canceled`，delivery 为 `interrupted`，并且不会继续 fallback 或绑定 Sticky。

## 流式部分结算

没有最终 usage 时，Gateway 只在以下已写出分支使用 `partial_stream_estimate`：

| 分支 | 结算输入 | 请求与交付终态 |
| --- | --- | --- |
| 客户取消，有效生成 Token 已确认写出 | 保守输入估算；输出只计已确认写出的可见文本，允许为零 | 内联目标为 canceled，delivery interrupted |
| 上游中断，有效生成 Token 已确认写出 | 同上；tokenizer 估算 output 为零时仍使用保守输入事实 | 内联目标为 failed，delivery interrupted |
| 上游正常结束、缺最终 usage，有效生成 Token 已写出 | 同上 | succeeded，delivery completed |

上游中断时，如果仅有前导帧或没有有效生成 Token，则不做 partial settlement，而是释放授权；
bill-on-disconnect 渠道可另记平台成本敞口。客户取消与上游中断都以有效生成 Token 已交付作为 partial
资格；tokenizer 失败时，非空可见文本可能计为零，但不取消该资格。仅前导帧后缺 usage 同样释放预扣并
返回 usage-missing。

`partial.v1` 复用授权阶段的保守输入估算，按进程配置的固定缓存率拆为 cache-read 与 uncached，默认
60% / 40%；输出只累计有效生成 Token 交付后成功写出帧中的协议可见文本。当前没有权威 usage 后到替换机制，再次 settlement
必须与已经保存的 usage、来源和映射版本一致，否则发生幂等冲突。

## Settlement Recovery

recoverable settlement 在内联结算前先校验事实并创建 pending job。job 保存 usage、响应标识、授权金额、
客户短上下文售价向量、公式版本、成本来源 ID、request/attempt 目标终态、错误事实，以及长上下文开关、
门槛和输入/输出倍率；worker 据此重放，不重调上游、不重新解析公开响应，也不回查价格表推断策略。

worker 重放使用 job 中的目标终态和错误事实。若首次 settlement 已提交、但 job 完成标记失败，重复重放只在
request、attempt、usage、错误和账务事实与 job 一致时按幂等成功返回。partial estimate 对应的 attempt 保持
`final_usage_received=false`；客户取消、上游中断和正常缺 final usage 分别保持 canceled、failed、succeeded。

内联 settlement 失败但 job 已建立时，当前请求可以按 pending recovery 结束协议交付。worker 重试耗尽后
将 job 标为 `dead`；随后只对仍为 `running` 的请求释放冻结、按授权额记录 `risk_exposure` 并标记
`failed`。因此客户可能已收到完整成功响应且 delivery 为 `completed`，后台 request 最终却为 `failed`。

token 事实中的 `unknown` 能进入 recovery job，但 `token_v1` 每次重放都会拒绝结算；若事实不变，job
会持续失败直至 `dead`，再按上述路径释放授权和记录 `risk_exposure`。

进程默认（均可由环境变量覆盖）：`max_attempts=20`、claim 锁 TTL `30s`、首次可领延迟 `30s`、单次结算超时
`10s`、指数退避上限 `5m`、单轮批量 `16`。

## 附加计量项现状

- Anthropic parser 对存在的 `web_search_requests` / `web_fetch_requests` 字段创建 metered item，包括显式零。
- metered item 校验与 `usage_line_items` 表约束都要求 quantity 大于零。因此显式零会使 settlement facts
  校验失败，而不是被保存为已知零。
- 正数 web search/fetch 次数可以写入 `usage_line_items`，但 `token_v1` 不读取这些行，客户收费与
  Provider 成本金额不变。
- recovery job 的两个工具次数字段是默认零的非空数值，重建时只恢复正数；缺失、已知零、未知和不适用
  不能在 recovery 路径中区分。
- partial stream 只保存 token 估算，不携带 server-tool 次数；当前也没有权威 usage 后到收口机制。

## 授权清扫：三方边界

网关失败路径普遍是「先 `ReleaseAuthorization`、再写请求终态」两步，与 settlement recovery / 进程崩溃
遗留组合后，会出现三类需要 worker 兜底的 `authorized` 冻结。三条路径按请求状态与是否存在 recovery job
互斥，共用年龄阈值与批量配置（默认年龄 `15m`、单轮批量 `100`，环境变量
`WORKER_ORPHAN_RESERVATION_SWEEP_AGE_THRESHOLD` / `_BATCH_SIZE`）。

| 路径 | 命中条件 | 收口动作 | 稳定码 / 告警 |
| --- | --- | --- | --- |
| settlement recovery（dead job） | job 重试耗尽为 `dead`，请求仍为 `running` | 释放冻结、按授权额记 `risk_exposure`、请求标 `failed` | 既有 recovery 路径 |
| orphan reservation sweeper | `authorized` + 请求仍 `running` + delivery 尚未开始 + 超年龄阈值 + 无 recovery job；无 running attempt，或 running attempt 的 permit 已失效 | 遗留 attempt 标为平台失败；释放冻结、按授权额记 `risk_exposure`（reason `orphan_reservation_swept`）、请求标 `failed` | `gateway_request_orphan_reclaimed` |
| stranded reservation sweeper | `authorized` + 请求已为 `failed`/`canceled` + 超年龄阈值 + 无 recovery job | 仅释放冻结；**不**写 `risk_exposure`，**不**改请求终态 | `gateway_request_stranded_reclaimed`；成功回收日志带 `alert=stranded_reservation_reclaimed` |

搁浅路径的成因是：release 自身失败（如 5s 超时、行锁竞争）而随后的终态审计写入成功，于是冻结留在
`authorized`、请求已是终态——既不进孤儿清扫，也不被 settlement recovery 接管。自动释放的安全性依据是：
网关与两个 finalizer 的释放路径均「release 在前、终态在后」或与终态同事务，因此 `authorized` 配
`failed`/`canceled` 不存在合法瞬时态。`authorized` 配 `succeeded` **不**自动回收（capture 未发生却已
告知客户成功属更严重异常），留给运维巡检暴露。

orphan / stranded 的列表查询与单条收口分属不同事务。orphan worker 先读取当前全部 running attempt：permit
仍为 `active` 时保留正常长请求；permit 已 finished、aborted 或消失时，才把它当作进程已无法继续的候选。
Redis 读取失败或 permit 状态无法识别时不处理。旧记录没有 permit ID 时，只允许回收既没有
`upstream_started_at`、也没有 `gateway_first_token_at` 的 attempt。

单条 orphan 收口先锁 request，再重查 request 仍为 `running`、delivery 仍为 `not_started`、不存在 recovery
job，并锁定 running attempt，要求 attempt ID 与 permit ID 集合和 worker 先前看到的死亡证明完全一致。attempt
创建与 recovery job 创建也会取得与该收口互斥的 request 行锁，因此不能在清扫提交后迟到插入。遗留 attempt
以平台故障收口，不进入 Channel 错误率或 breaker 样本。stranded 收口以「请求仍为 `failed`/`canceled`」为
幂等闸门，已释放或不存在的 reservation 按幂等成功返回。

运维残余检查见 Gateway 仓库 `scripts/ledger_reservation_audit.sql`：终态请求配 `authorized` 冻结、以及
`user_balances.reserved_balance` 与 authorized 之和不等，两条均应恒为 0 行（worker 未跑或出现新泄漏形态时除外）。

## 断开仍计费渠道

对声明 bill-on-disconnect 的 Channel，Gateway 在本 attempt 没有形成真实 settlement 成本的客户取消、
上游 timeout 或 5xx/传输失败路径中，可以记录与客户账本隔离的平台成本敞口：

- 使用调用前的保守输入估算、模型输出上限和候选成本口径估算平台金额；
- 不写客户 usage、余额或 ledger；
- 已形成完整或 partial settlement 成本时不再记录，避免同一 attempt 双计；
- 记录是 best effort；成本计算失败会被静默放弃，生产 recorder 的数据库写入失败会记录 `WARN`；两者都
  不改变客户响应。

当前成本计算失败不写日志或指标；数据库写入失败只写 `WARN`，caller 忽略该错误。

## 当前边界

- partial token usage 结算后不能被后到权威 usage 修正。
- token `unknown` 只有重试直至 `dead` 的现有结果，没有可结算降级口径。
- 进程崩溃后，orphan sweeper 只自动处理 delivery 尚未开始的请求。已经向客户交付内容后仍停在 `running`
  的 request/attempt 不自动释放或改终态，仍需巡检识别并人工处理。
- stranded sweeper 不自动处理 `authorized` 配 `succeeded`；该类行只能靠巡检发现。
- bill-on-disconnect 成本计算失败当前静默丢失；数据库写入失败由 recorder 记录 `WARN`，caller 忽略错误。
- 服务端工具次数只支持正数事实；显式零会使整组 settlement facts 失败，三态和独立按次收费均未实现。

## 数据、安全与可观测性

余额、reservation、ledger、usage、价格快照和成本快照属于敏感业务事实。公开 API 不暴露内部 Channel、
Provider 成本、倍率或凭据；只有被授权的客户或运营角色可查看与职责相符的记录。

当前可关联授权、capture、overage debit、write-off、release、recovery job、`risk_exposure`，以及 orphan /
stranded 清扫的稳定错误码与 `alert=` 日志键。已结算实际 Provider 成本、平台核销和 bill-on-disconnect
估算敞口保存在不同事实中。成本计算失败不写记录，数据库写入失败只写 `WARN`；partial settlement 没有后到
权威 usage 替换记录。

## 关联决策

- [ADR-0003：预付账务与可审计结算](../decisions/adr-0003-billing-settlement.md)
- [ADR-0017：权威首字判定与双 TTFT](../decisions/adr-0017-authoritative-first-token.md)
- [ADR-0002：线路作为产品档位与定价边界](../decisions/adr-0002-route-product-pricing.md)
