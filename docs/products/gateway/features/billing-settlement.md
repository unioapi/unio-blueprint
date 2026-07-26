---
title: "功能设计：账务与结算"
description: "记录预付余额、授权、结算、核销、价格与成本快照的当前行为。"
status: active
owner: 网关团队
last_updated: 2026-07-26
related:
  - ../overview.md
  - ../glossary.md
  - request-lifecycle.md
  - ../decisions/adr-0002-route-product-pricing.md
  - ../decisions/adr-0003-billing-settlement.md
---

# 功能设计：账务与结算

## 摘要

Gateway 当前采用预付余额模型：调用前冻结可用余额，调用后按本次 usage 和锁定售价结算，同时记录
Provider 成本、客户实扣与平台核销。已完成 settlement 的历史事实不随配置变化重算；pending recovery
保存 usage、客户短上下文售价向量、公式版本和成本来源 ID。

## 当前计费范围

- 客户收费和 Provider 成本都只使用 `token_v1`，按 token 售价与成本向量计算。
- token 用量区分 `known`、`not_applicable` 和 `unknown`；`unknown` 不按零收费，而是使 `token_v1`
  settlement 失败。
- Anthropic `web_search_requests` 和 `web_fetch_requests` 当前只可能形成附加计量事实，不参与授权金额、
  客户收费或 Provider 成本计算。

## 授权

1. Gateway 对候选逐一使用保守输入估算、输出上限、客户售价和长上下文策略估算金额，并取金额最大者作为
   本次授权上界。
2. 客户未提供输出上限时，先取候选模型 `max_output_tokens` 的最大值；候选也未配置时回退进程默认值。
3. 可用余额不大于零时拒绝调用上游。可用余额足以覆盖估算金额时冻结估算金额；可用余额大于零但不足时，
   冻结全部剩余可用余额并允许调用。
4. 全部候选的授权估算金额为零时，ledger 以 `CodeLedgerInvalidAmount` 拒绝非正金额，不调用上游。当前价格和
   线路倍率允许配置为零，金额舍入后也可能触发该分支。
5. 线路内 fallback 不重新授权，也不改变本次客户售价边界。

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

## 流式部分结算

没有最终 usage 时，Gateway 只在以下已写出分支使用 `partial_stream_estimate`：

| 分支 | 结算输入 | 请求与交付终态 |
| --- | --- | --- |
| 客户取消，至少一帧已确认写出 | 保守输入估算；输出只计已确认写出的可见文本，允许为零 | 内联目标为 canceled，delivery interrupted |
| 上游中断，已确认写出且累计估得正数 output token | 同上 | 内联目标为 failed，delivery interrupted |
| 上游正常结束、缺最终 usage，至少一帧已写出 | 同上 | succeeded，delivery completed |

上游中断时，如果已写帧但累计估得的 output token 不大于零，则不做 partial settlement，而是释放授权；
bill-on-disconnect 渠道可另记平台成本敞口。客户取消与上游中断故意采用不同门槛：客户取消只要求已有
确认写出的帧，上游中断还要求 `partialOutputTokens > 0`。tokenizer 失败时，非空可见文本也可能计为零。

`partial.v1` 复用授权阶段的保守输入估算，按进程配置的固定缓存率拆为 cache-read 与 uncached，默认
60% / 40%；输出只累计成功写出帧中的协议可见文本。当前没有权威 usage 后到替换机制，再次 settlement
必须与已经保存的 usage、来源和映射版本一致，否则发生幂等冲突。

## Settlement Recovery

recoverable settlement 在内联结算前先校验事实并创建 pending job。job 保存 usage、响应标识、授权金额、
客户短上下文售价向量、公式版本以及成本来源 ID；worker 据此重放，不重调上游、不重新解析公开响应。

内联 settlement 失败但 job 已建立时，当前请求可以按 pending recovery 结束协议交付。worker 重试耗尽后
将 job 标为 `dead`；随后只对仍为 `running` 的请求释放冻结、按授权额记录 `risk_exposure` 并标记
`failed`。因此客户可能已收到完整成功响应且 delivery 为 `completed`，后台 request 最终却为 `failed`。

token 事实中的 `unknown` 能进入 recovery job，但 `token_v1` 每次重放都会拒绝结算；若事实不变，job
会持续失败直至 `dead`，再按上述路径释放授权和记录 `risk_exposure`。

## 附加计量项现状

- Anthropic parser 对存在的 `web_search_requests` / `web_fetch_requests` 字段创建 metered item，包括显式零。
- metered item 校验与 `usage_line_items` 表约束都要求 quantity 大于零。因此显式零会使 settlement facts
  校验失败，而不是被保存为已知零。
- 正数 web search/fetch 次数可以写入 `usage_line_items`，但 `token_v1` 不读取这些行，客户收费与
  Provider 成本金额不变。
- recovery job 的两个工具次数字段是默认零的非空数值，重建时只恢复正数；缺失、已知零、未知和不适用
  不能在 recovery 路径中区分。
- partial stream 只保存 token 估算，不携带 server-tool 次数；当前也没有权威 usage 后到收口机制。

## 超时授权清扫

orphan reservation sweeper 查询以下记录：reservation 为 `authorized`、创建时间早于配置阈值、关联 request
仍为 `running`，并且查询当时不存在 settlement recovery job。当前默认年龄阈值为 15 分钟。收口事务只
重新锁定并检查 request 是否仍为 `running`，随后释放 reservation、按授权额记录 `risk_exposure` 并把
request 标记为 `failed`。

列表查询和单条收口分属不同事务。收口事务只重查 request 是否仍为 `running`，不重查 recovery job；流本体
没有总时限，只有 idle timeout。因此查询后并发创建的 recovery job 和超过年龄阈值的活跃长流仍可能被该
收口事务处理。

## 断开仍计费渠道

对声明 bill-on-disconnect 的 Channel，Gateway 在本 attempt 没有形成真实 settlement 成本的客户取消、
上游 timeout 或 5xx/传输失败路径中，可以记录与客户账本隔离的平台成本敞口：

- 使用调用前的保守输入估算、模型输出上限和候选成本口径估算平台金额；
- 不写客户 usage、余额或 ledger，也不回填已释放的 TPM；
- 已形成完整或 partial settlement 成本时不再记录，避免同一 attempt 双计；
- 记录是 best effort；成本计算失败会被静默放弃，生产 recorder 的数据库写入失败会记录 `WARN`；两者都
  不改变客户响应。

当前成本计算失败不写日志或指标；数据库写入失败只写 `WARN`，caller 忽略该错误。

## 当前边界

- recovery job 不保存 partial settlement 的 request/attempt 目标终态和错误事实。初次事务未提交时，worker
  默认按 succeeded 重放；已提交为 canceled/failed 的 partial 又不被当前幂等入口接受。
- recovery job 没有直接保存长上下文策略。倍率路径可从 `CostBaseModelPriceID` 重建；绝对
  `channel_prices` 覆盖路径该 pin 为零，重放使用空策略，可能漏算客户售价和 Provider 成本的长上下文倍率。
- partial token usage 结算后不能被后到权威 usage 修正。
- token `unknown` 只有重试直至 `dead` 的现有结果，没有可结算降级口径。
- orphan sweeper 的列表查询与收口事务分离，收口时不重查 recovery job，也不判断 transport 是否仍在执行。
- bill-on-disconnect 成本计算失败当前静默丢失；数据库写入失败由 recorder 记录 `WARN`，caller 忽略错误。
- 服务端工具次数只支持正数事实；显式零会使整组 settlement facts 失败，三态和独立按次收费均未实现。

## 数据、安全与可观测性

余额、reservation、ledger、usage、价格快照和成本快照属于敏感业务事实。公开 API 不暴露内部 Channel、
Provider 成本、倍率或凭据；只有被授权的客户或运营角色可查看与职责相符的记录。

当前可关联授权、capture、overage debit、write-off、release、recovery job 和 `risk_exposure`。已结算实际
Provider 成本、平台核销和 bill-on-disconnect 估算敞口保存在不同事实中。成本计算失败不写记录，数据库
写入失败只写 `WARN`；partial settlement 没有后到权威 usage 替换记录。

## 关联决策

- [ADR-0003：预付账务与可审计结算](../decisions/adr-0003-billing-settlement.md)
- [ADR-0002：线路作为产品档位与定价边界](../decisions/adr-0002-route-product-pricing.md)
