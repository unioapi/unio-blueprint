---
title: "ADR-0008：运行态代际围栏"
description: "以 Provider Origin、Channel 与控制版本隔离迟到结果，并在恢复前拒绝新准入。"
status: superseded
owner: 网关团队
last_updated: 2026-07-27
related:
  - ../features/runtime-control-recovery.md
  - ../features/data-lifecycle.md
  - ../features/admission-control.md
  - adr-0007-atomic-admission-control.md
  - adr-0013-provider-runtime-fencing.md
---

# ADR-0008：运行态代际围栏

## 范围

本文记录当前 Gateway 的 Provider Origin、Channel、关键 control、runtime state epoch、凭据检测和迟到结果
围栏行为。

## 当前实现

1. Provider Origin 的 Base URL 真变化推进独立 `base_url_revision`。Origin 存储状态真变化时，只有有效状态
   随之变化才推进 `status_revision`；Provider 状态使变更前后有效状态相同时，只更新 Origin 存储状态而不推进
   status revision。同值更新不推进 revision。
2. Channel 的 Origin 绑定、状态或 timeout 真变化推进 `config_revision`；凭据真变化会保存新值、置
   `credential_valid=false`、清空旧凭据检测摘要并推进一次 config revision；credential validity 真变化也推进
   config revision。名称和 priority 更新不推进该 revision。`protocol` 与 `adapter_key` 创建后不通过普通更新接口
   修改。四维限额使用独立 `admission_limits_revision`。
3. 关键 app setting 与 Channel admission limits 使用 `runtime_control_operations` 和通用
   prepare/commit/abort/recovery Publisher。runtime state epoch 使用同一 operation 表但走专用 bootstrap 与
   maintenance 流程，非 bootstrap recovery 没有 Abort。Provider Origin Base URL/status 与 Provider status 批量更新
   使用独立的 `origin_routing_operations` 和 Origin 恢复流程。普通 Channel config 与 credential 更新不走这些
   durable 发布流程，而是依赖 PostgreSQL 单调 revision、Redis compare-and-rotate 与 CAS。
4. 每个 `AttemptPermit` 固化 runtime integrity、Origin Base URL/status revision 与 fence generation、Channel
   config revision、Origin/Channel breaker generation、half-open 权利和原始资源桶身份。lifecycle guard 通过且
   integrity epoch 仍匹配时，Finish 先释放 Channel 并发并处理 TPM，再判断结果能否写入当前运行态。
5. Origin Base URL/status fence stale 会同时阻止 Origin breaker、Origin 证据、Channel breaker 和 Channel TTFT
   写入；仅 Channel config stale 时，Channel breaker 与 TTFT 不写，但 Origin breaker 仍可应用。Origin 与 Channel
   breaker generation 分别判断，未 stale 的作用域可以独立应用。permit 资源仍按固化身份服从 first-terminal-wins
   收口。
6. integrity epoch 已换代时，request token owner 在 Redis 调用前拒绝 Finalize，permit owner 在 Redis 调用前拒绝
   Renew、Finish 或 Abort；旧运行资源不会由这些调用释放，只能等待租约或 TTL 过期。
7. 凭据轮换时，相同凭据且当前 valid 返回 `not_required`，不探测也不推进 revision；相同凭据但当前 invalid 会用
   当前 revision 探测。检测结果只有在 Channel config revision 与 Origin 两类 revision 仍匹配时才更新当前摘要或
   credential validity；stale 结果写检测日志但不覆盖当前状态。
8. Origin fence generation 在 Prepare 时推进；后续 Commit 或 Abort 都把对应 Origin breaker 重置为
   closed/no-sample。Channel config revision 变化后，由下一次 Acquire compare-and-rotate 出新的 closed/no-sample Channel
   generation；`SnapshotMany` 本身只读。独立 cooldown 和稳定限流桶不随这些 breaker/config rotation 清除。
9. 已开始 transport 的调用不会因普通 Origin/Channel 配置变化被主动取消，业务响应、usage、账务和审计继续按
   实际路径处理。归档和恢复推进相应状态或 config revision，不删除历史 request、attempt、usage、ledger、价格
   或成本快照；当前 Channel archive 与 hard delete 也不清理 Redis Channel state、admission control 或其他运行
   key。Provider、Channel、Route 与 Provider Origin 的具体归档、恢复和硬删除行为见[数据生命周期](../features/data-lifecycle.md)。
10. runtime state epoch 保存随机 epoch 身份、单调 revision 和 `recovering`/`ready` 状态。bootstrap、state loss 与
   restore 使用 durable operation；普通新准入只接受当前 ready epoch。非 bootstrap recovery 在 commit 后进入
   `awaiting_release`，Release 完成前普通 readiness 仍不通过。

## 代码与测试证据

当前代码和测试覆盖 Origin Base URL/status 单项与组合发布、Provider 状态批量发布、Channel config 与 admission
revision、凭据轮换及 stale CAS、按作用域区分的 permit stale disposition、integrity epoch mismatch、Origin fence
commit/abort rotation、Channel Acquire rotation、state epoch bootstrap、响应丢失恢复、maintenance
commit/release、归档与恢复的 revision 变化，以及 Channel archive/hard delete 不清理 Redis 运行 key 的服务路径。

## 来源谱系

| 原 DEC | 原始日期 | 原状态 | 当前处理与修订关系 |
| --- | --- | --- | --- |
| DEC-032 | 2026-07-20 | accepted，来源标注待实现 | 保留 Base URL 与公共故障域同属一实体；正文按 ADR-0001 使用 Provider Origin，旧 `ProviderEndpoint` 仅为来源名。 |
| DEC-033 | 2026-07-20 | accepted，来源标注待实现 | Permit、generation 与迟到结果 no-op 的主要来源；普通 revision stale 时资源仍收口，integrity epoch 换代时主动收口被阻断。 |
| DEC-036 | 2026-07-21 | accepted，来源标注待实现 | Channel config revision 隔离迟到结果；限额 revision 独立。 |
| DEC-037 | 2026-07-21 | accepted，来源标注待实现 | 当前 invalid 凭据可用相同凭据重新检测；不同凭据保存后先置 invalid 再检测。 |
| DEC-038 | 2026-07-21 | accepted，来源标注待实现 | Provider Origin status revision、围栏和全局准入边界；术语按 ADR-0001 修订。 |
| DEC-039 | 2026-07-21 | accepted，来源标注待实现 | 不同凭据替换当前有效凭据时，保存动作先置 invalid，检测成功且 revision 仍匹配后恢复 valid。 |
| DEC-040 | 2026-07-21 | accepted，来源标注待实现 | Store/control 故障统一 fail-closed，恢复需完整性门禁。 |
| DEC-041 | 2026-07-21 | accepted，来源标注待实现 | permit 固化候选资源身份；普通 revision stale 时按固化身份终结，integrity epoch 换代时依赖租约或 TTL。 |
| DEC-043 | 2026-07-21 | accepted，来源称已实现，部分修订 | Redis control/revision、durable 发布和恢复有效；共享 rate-control 范围由 DEC-054 修订。 |
| DEC-052 | 2026-07-23 | accepted，来源称已实现 | 仅保留 Provider/Origin 管理信息架构来源；术语改为 Provider Origin。 |

## 取代关系

- 取代：无 Blueprint ADR；这是对上述来源的合并记录。
- 被取代：[ADR-0013：Provider 运行态代际围栏](adr-0013-provider-runtime-fencing.md)。

## 状态说明

本文于 2026-07-26 按当时 Gateway 代码、Schema 与测试接收；2026-07-27 因 Origin 并入 Provider 被
[ADR-0013](adr-0013-provider-runtime-fencing.md) 取代，保留为决策谱系。

## 参考资料

- [运行控制与恢复](../features/runtime-control-recovery.md)
- [数据生命周期](../features/data-lifecycle.md)
- [ADR-0001：统一领域术语](adr-0001-domain-terminology.md)
