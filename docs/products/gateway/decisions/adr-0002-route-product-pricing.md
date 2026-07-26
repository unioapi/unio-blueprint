---
title: "ADR-0002：线路作为 API Key 绑定的供给与定价边界"
description: "Route 由 API Key 隐式确定，限定候选池和调度，并以模型基准价与线路倍率确定客户售价。"
status: active
owner: 网关团队
last_updated: 2026-07-26
related:
  - ../overview.md
  - ../glossary.md
  - ../features/access-control.md
  - ../features/billing-settlement.md
  - ../features/routing-load-balancing.md
  - adr-0001-domain-terminology.md
---

# ADR-0002：线路作为 API Key 绑定的供给与定价边界

## 背景

Gateway 的公开模型请求携带 API Key、模型标识和协议请求，不携带 Route 选择参数。当前身份结构为
`User Account -> API Key -> Route`；Project、项目默认 Route 和内置 Route 回落均不属于当前实现。

Route 是管理端维护的内部边界，用于组合候选 Channel 池、调度模式、客户售价倍率和线路级运行策略。
客户请求稳定模型标识，实际使用哪条 Route 由本次 API Key 的绑定隐式确定。

## 当前决策

- 每把 API Key 的 `route_id` 在数据库中必填并引用一条 Route。运行时只接受状态为 `enabled` 的绑定
  Route；绑定缺失、Route 不存在、停用或已归档时拒绝请求，不使用其他 Route 回落。
- Route 的 `route_channels` 是候选供给上界。最终候选仍需满足请求模型映射、入口协议、模型与供给实体
  状态、Channel 凭据、用户模型策略、有效模型基准价和可解析 Channel 成本等条件；没有候选时失败，
  不跨 Route fallback。
- 常规管理写路径要求 `fixed` Route 恰好包含一条 Channel，`balanced` Route 至少包含一条 Channel。
  Router 会再次检查 `fixed` 池大小，损坏的配置按无可用 Channel 失败。
- 短上下文客户售价向量在候选规划时按“当前生效的模型基准售价 × Route `price_ratio`”生成。
  同一 Route、模型和请求的候选共享该售价向量与倍率；fallback 命中其他 Channel 不改变客户售价。
  结算时可根据实际输入量再应用该模型价格配置的长上下文倍率。
- Channel 成本与客户售价分离。成本优先使用有效的绝对 `channel_prices`；没有绝对覆盖时，按模型基准
  价格映射的成本向量乘 Channel 成本倍率和充值倍率计算。币种、计价单位或价格向量无法比较，或任一
  计价分项出现负毛利时，该候选被拒绝；全部候选被拒绝时请求失败。
- `request_records.route_id` 保存请求创建时 API Key 绑定的 Route ID。只有结算事务成功提交的请求才保存
  最终客户售价向量和 `price_ratio`；失败且未结算的请求没有价格快照。后续 API Key 换绑或 Route 倍率
  修改不会改写已有 Route ID 和已提交的价格快照。

## Route 生命周期

- Route 仍有绑定 API Key 时，归档操作必须在同一操作中把这些 Key 迁移到另一条 `enabled` Route；没有
  绑定 Key 时可以直接归档。
- 归档保留原 `route_channels`，把状态改为 `archived`，并在名称后追加 `__archived_<id>` 释放名称唯一性。
- 恢复把 Route 改为 `disabled` 并保留 Channel 池，不恢复原名称，也不会把已迁走的 API Key 绑定回来。
- 只有已归档 Route 可以硬删除；仍受外键引用时数据库拒绝删除。

## 当前可观察行为

- 公开请求不能逐请求选择 Route；使用哪把 API Key 决定本次请求进入哪条 Route。
- Channel fallback 可以改变平台实际成本、成本来源和毛利，但不会改变本次请求冻结的客户售价向量。
- `/v1/models` 只列出 API Key 当前 Route 的 Channel 池内、满足用户策略和基础供给/定价条件的模型。
- API Key 换绑后，新请求使用新 Route；旧请求仍保存创建时的 Route ID。

## 当前边界

- API Key 创建和换绑的管理写路径只校验 Route ID 为正数且外键存在，没有要求目标 Route 为
  `enabled`。因此当前可以把 Key 绑定到 `disabled` 或 `archived` Route，也可以在 Route 归档后重新绑定；
  这些 Key 会在运行时被拒绝。
- `price_ratio` 默认 `1` 并允许任意非负十进制，`0` 也能保存；但模型请求的预授权金额必须大于零，
  因而零倍率请求会在调用上游前因无效授权金额失败，当前不能形成免费调用。
- `/v1/models` 当前不按 Channel 协议或具体 Endpoint 的 Adapter 支持能力过滤。模型出现在列表中，不保证
  它能通过每一种公开协议或 Endpoint 形成可调用候选。
- 历史请求快照的是 Route ID，不是 Route 名称和 mode。Admin 展示会通过该 ID 读取 Route 当前名称与
  mode；Route 归档后，历史请求会显示追加了归档后缀的名称。
- 价格快照保存结算使用的最终售价向量与 Route 倍率，但没有统一保存客户售价所使用的
  `model_prices` 行 ID；不能据此宣称每个已结算请求都保留了精确的模型价格来源行。

## 来源谱系

| 原 DEC | 原始日期 | 原状态 | 当前处理与取代/修订关系 |
| --- | --- | --- | --- |
| DEC-017 | 未记录 | accepted，部分修订 | 保留分档网关、Channel 不对客户公开和 Route 内不降档；“档位使用独立模型标识”和旧 `ProviderEndpoint` 用语分别由 DEC-026、ADR-0001 修订。 |
| DEC-026 | 2026-06-29 | accepted | Route 成为档位载体并绑定 API Key；客户售价改为模型基准价乘 Route 倍率，Route 内 Channel fallback 不改价。 |

当前代码随后移除了 Project、项目默认 Route 和内置 Route 回落，并把 API Key 的 Route 绑定改为必填。
这些是本 ADR 接收时核验到的当前实现事实，不改写 DEC-017、DEC-026 的历史内容。

## 状态说明

本文于 2026-07-26 按当前 Gateway 代码、Schema 与现有测试接收为 `active`。

## 取代关系

- 取代：无 Blueprint ADR。
- 被取代：无。

## 参考资料

- [Gateway 概览](../overview.md)
- [访问控制](../features/access-control.md)
- [账务与结算](../features/billing-settlement.md)
- [路由负载均衡](../features/routing-load-balancing.md)
- [ADR-0001：统一领域术语](adr-0001-domain-terminology.md)
