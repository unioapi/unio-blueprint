---
title: "ADR-0014：Provider 与 Channel 熔断归因"
description: "定义真实上游结果进入 Provider 与 Channel breaker、证据、冷却和权限闸门的当前规则。"
status: active
owner: 网关团队
last_updated: 2026-08-04
related:
  - ../features/resilience-circuit-breakers.md
  - ../features/routing-load-balancing.md
  - adr-0010-upstream-breaker-attribution.md
  - adr-0013-provider-runtime-fencing.md
---

# ADR-0014：Provider 与 Channel 熔断归因

## 背景

Origin 并入 Provider 后，公共地址和服务故障域、breaker、短窗证据、围栏和 reset 都归属于 Provider。原
[ADR-0010](adr-0010-upstream-breaker-attribution.md) 的真实 transport 归因原则继续适用，但不再存在独立
Origin breaker 或 Origin key。

## 决策驱动因素

- 公共地址和公共故障必须按 Provider 隔离，不能因单凭据或单模型问题摘除整个 Provider。
- 只有已经开始真实上游 transport 的结果可以影响 breaker。
- 429、403、401、breaker 与 Channel TTFT/错误率评分样本必须保持不同责任边界。
- 多 Gateway 必须共享同一状态机、half-open 权利与证据事实。

## 备选方案

### 方案：只保留 Channel breaker

所有失败只影响具体 Channel。

**优点**

- 状态机作用域较少。

**缺点**

- 公共地址、网络或服务故障会被每个 Channel 重复试错。

### 方案：Provider 与 Channel 双层 breaker（选中）

Provider breaker 承担公共连接、地址和服务故障；Channel breaker 承担具体凭据路径、协议和上游调用故障，
歧义结果通过跨 Channel、跨模型证据升级到 Provider。

**优点**

- 公共故障快速隔离，单 Channel 故障不会无证据扩大。
- 两层状态、reset 和可观测事实均可独立解释。

**缺点**

- Finish 需要同时处理两层 generation、归因和 stale disposition。

## 决策

1. Provider 与 Channel 各自在 Redis 维护 `closed`、`open`、`half_open`、generation、eligible 窗口、连续
   失败、open level 和 half-open lease；多个 Gateway 共享状态。
2. 只有 timing observer 已记录 transport start 的调用进入 Finish。transport 前失败走 Abort，只释放 permit
   资源，不写 breaker、Provider evidence 或 Channel 评分样本。
3. 有有效协议 facts 的成功结果同时形成 Provider 与 Channel `eligible_success`。401、403、429、其他 4xx、
   客户取消和未分类本地错误对两层 breaker 均为 `ignored`。
4. HTTP 502/503/504、无状态 server error、发送/握手/响应头 timeout、连接重置、代理截断和同类 stream
   server error 直接形成 Provider `eligible_failure`。
5. HTTP 500、首 token timeout 和 body read timeout 先形成 Channel failure；每类错误分别收集 Provider 短窗
   evidence。只有同一 Provider 内同时满足至少两个不同 Channel 和两个不同模型时，本次 Finish 才额外形成
   Provider failure。不同证据类别不得拼接。
6. 401 使用 Channel、Channel config revision 与 Provider 双 revision 绑定的连续凭据闸门；429 写 Channel
   cooldown；403 暂停精确的 Channel、Model 与 revision 组合。三者不写 breaker 样本。
7. 默认 breaker 窗口、比例阈值、快速触发、half-open 双 permit success 和 open 退避沿用当前热更新 control。
   Provider 与 Channel generation 独立推进，未 stale 的作用域可以独立应用结果。
8. permit 固化 Provider/Channel breaker generation、Provider 双 revision/fence 和 Channel revision。归档、地址
   或状态变更使旧 Provider feedback 与 evidence 成为 stale/no-op；资源终结仍优先完成。
9. breaker reset 按实体分别执行。Provider reset 仅接受存在的 Provider，不得以 Redis key 存在性代替数据库
   身份；实体不存在返回 404。reset 不清除 Channel cooldown 或 permission pause。
10. Redis key 使用 Provider/Channel 当前命名空间；不读取、迁移或清理旧 Origin key，也不提供兼容代理。

## 影响

### 正面影响

- 公共故障域与 Provider 的唯一地址和生命周期一致。
- 删除 Origin key、ID 和运行态 join，归因与诊断链路更直接。
- reset 具有数据库实体护栏，不会为不存在对象制造运行态。

### 负面影响

- 官方服务和中转服务若地址或故障域不同，必须建成不同 Provider。
- 单 Provider 不能表达多个可独立熔断的地址。

### 中性影响或后续工作

- Channel TTFT 仍只使用 stream-only attempt 口径，并以独立分钟桶参与评分，不提升到 Provider 或 breaker。
- 公开错误继续隐藏 Provider、Channel、地址、breaker key 和内部归因码。

## 风险与缓解措施

| 风险 | 缓解措施 | 负责人 |
| --- | --- | --- |
| 单 Channel 故障误开 Provider breaker | 按类别隔离 evidence，并同时要求不同 Channel 与不同模型门槛 | 网关团队 |
| reset 为不存在实体造状态 | 先强读 Provider/Channel 身份，不存在统一返回 404 | 网关团队 |
| 迟到结果污染归档后状态 | Finish 校验双 revision、fence 与 generation，旧 feedback 为 stale/no-op | 网关团队 |

## 落地与验证

- breaker、evidence、permission、credential gate、proof 和 metrics 已全部切换到 Provider 作用域。
- 当前单元测试覆盖归因矩阵、隔离 evidence、half-open、reset、stale revision 和 Store 故障。
- 旧 Origin Redis key、combined routing Lua 和 Origin DTO 已从当前实现删除。

## 取代关系

- 取代：[ADR-0010：上游熔断归因](adr-0010-upstream-breaker-attribution.md)。
- 被取代：无。

## 参考资料

- [韧性与熔断器](../features/resilience-circuit-breakers.md)
- [路由负载均衡](../features/routing-load-balancing.md)
- [ADR-0013：Provider 运行态代际围栏](adr-0013-provider-runtime-fencing.md)
