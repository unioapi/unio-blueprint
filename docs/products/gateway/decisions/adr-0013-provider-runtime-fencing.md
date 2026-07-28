---
title: "ADR-0013：Provider 运行态代际围栏"
description: "以 Provider 的独立 origin/status revision、Channel revision 与整体运行态代际隔离迟到结果。"
status: active
owner: 网关团队
last_updated: 2026-07-28
related:
  - ../features/runtime-control-recovery.md
  - ../features/data-lifecycle.md
  - ../features/admission-control.md
  - adr-0007-atomic-admission-control.md
  - adr-0008-runtime-state-fencing.md
  - adr-0012-provider-channel-route-lifecycle.md
---

# ADR-0013：Provider 运行态代际围栏

## 背景

[ADR-0012](adr-0012-provider-channel-route-lifecycle.md) 将上游根地址、有效状态和公共故障域并入
Provider，删除独立 Provider Origin。原 [ADR-0008](adr-0008-runtime-state-fencing.md) 的多代隔离原则仍然
成立，但其实体、operation、锁序和 revision 归属已经变化，需要由当前两层供给模型重新定义。

## 决策驱动因素

- 地址变更和状态变更必须独立推进、独立恢复，不能互相制造虚假冲突。
- 已开始 transport 的请求必须完成业务与资源收口，但不能以旧事实污染新运行态。
- PostgreSQL、Redis 或发布 operation 不一致时必须 fail closed，恢复流程不得猜测正确值。
- Provider 归档必须立即阻止新准入，同时保留 permit 固化资源直至在途调用终结。

## 备选方案

### 方案：Provider 使用单一配置 revision

地址、状态和普通资料共享一个 revision。

**优点**

- 字段和比较逻辑较少。

**缺点**

- 名称等普通编辑会无意义地使运行态失效。
- 地址和状态不能独立发布、诊断与恢复。

### 方案：Provider 双 revision 与独立围栏（选中）

Provider 的 `origin` 和 `status` 分别维护单调 revision、pending 状态与 fence generation；Channel 和全局
control 继续维护各自 revision，permit 固化本次调用需要的全部身份。

**优点**

- 地址与状态变更互不干扰，冲突和恢复原因可解释。
- 迟到结果可以精确判断 stale，同时不妨碍资源收口。

**缺点**

- 运行态快照、operation 恢复和诊断必须同时呈现两条 revision。

## 决策

1. Provider 保存唯一 `origin`、`origin_revision`、`status_revision`。两条 revision 只在对应事实真变化时单调
   推进；同值更新不推进。
2. Provider 地址和状态分别使用 `provider_routing_operations` 中 `origin`、`status` 两类 durable operation。
   operation 只归属 `provider_id`；并发修改按 Provider、operation 的顺序锁定，不存在 Origin 扇出或组合更新。
3. Redis 分别维护 Provider 当前 origin/status revision、active/pending 状态、各自 fence generation 和 Provider
   breaker generation。地址或状态 Prepare 推进对应 fence；Commit/Abort 只处理该变更的 pending 状态。
4. Channel 保存 `provider_id`、自身 config/admission revision、凭据和调度配置。Provider 地址或状态变化不改写
   Channel revision；Channel 配置变化也不推进 Provider revision。
5. 候选快照和每次 `AttemptPermit` Acquire 都校验 ready runtime epoch、Provider 双 revision/pending、Channel
   revision、关键 control 与相应 generation。地址不匹配返回 `stale_revision`，状态不匹配返回
   `stale_status_revision`。
6. permit 固化 Provider 双 revision、双 fence generation、Provider/Channel breaker generation 和原始资源桶
   身份。普通 revision 或 generation 变化后，Finish/Abort 仍先完成并发、限额、usage 和终态收口，再将旧
   breaker、evidence 或 TTFT 写入判为 stale/no-op。
7. runtime epoch 换代仍是例外：旧 token/permit 的主动 Finalize、Finish 或 Abort 在 Redis 调用前被拒绝，
   资源依赖租约或 TTL 回收。
8. Provider 归档立即清理 breaker、cooldown、control、permission 和 evidence，阻止新准入；不得清理在途
   permit、并发租约和计数桶。归档后迟到的运行反馈为 stale/no-op，但资源必须完成收口。
9. 启动 Reconciler 先收口 PostgreSQL durable operation，再以 PostgreSQL 当前 Provider/Channel/control 稳定事实
   为权威修复缺失或漂移的 Redis control；Provider 正常 Hash 保留 breaker 状态，只校正双 revision、status、
   pending 与 fence。运行期周期 Reconciler 仍只补缺失；已存在状态若 revision、pending、payload hash 或业务
   事实冲突，停止恢复并保持 fail closed。
10. readiness 核验 Provider routing operation、关键 control、runtime epoch、Redis server identity、完整对账
    proof 与故障锁；普通健康探针不创建或修复运行态。

## 影响

### 正面影响

- Provider 地址与状态可以独立更新、诊断和恢复。
- 在途请求与新运行事实明确隔离，归档不会破坏资源和账务收口。
- 删除 Origin 批量发布、组合 Lua 和三层锁序，恢复面更小。

### 负面影响

- 所有运行态 DTO、trace、检测日志和诊断视图都必须携带 Provider 双 revision。
- Redis 全量丢失后仍需要受控的 epoch 恢复、完整对账和 post-commit release。

### 中性影响或后续工作

- breaker 的归因、证据与 reset 语义由 [ADR-0014](adr-0014-provider-breaker-attribution.md) 定义。
- Provider、Channel 与 Route 的状态和归档护栏由 [ADR-0012](adr-0012-provider-channel-route-lifecycle.md) 定义。

## 风险与缓解措施

| 风险 | 缓解措施 | 负责人 |
| --- | --- | --- |
| 地址和状态 pending 被错误合并 | operation kind、revision 和 Redis pending 分开建模并覆盖交错操作测试 | 网关团队 |
| 归档误删在途资源 | purge 按立即阻断事实与 permit 绑定资源分层，覆盖长流和异常 TTL 测试 | 网关团队 |
| 启动修复误清业务运行态 | 只重建目标 control/marker；Provider 正常 Hash 保留 breaker，其他资源使用独立 key | 网关团队 |

## 落地与验证

- Gateway Schema、publisher、reconciler、readiness、permit、凭据检测和运行诊断已经切换为 Provider 双 revision。
- 隔离 PostgreSQL 已重放全部迁移、seed、down/up；隔离 Redis 已验证全新初始化和完整状态丢失恢复。
- breakerstore、runtimecontrol、Admin 合同、全量 Go 测试、构建、长流与完整状态丢失 E2E 均已通过。

## 取代关系

- 取代：[ADR-0008：运行态代际围栏](adr-0008-runtime-state-fencing.md)。
- 被取代：无。

## 参考资料

- [运行控制与恢复](../features/runtime-control-recovery.md)
- [准入控制](../features/admission-control.md)
- [数据生命周期](../features/data-lifecycle.md)
