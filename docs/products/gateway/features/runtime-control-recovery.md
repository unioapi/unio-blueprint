---
title: 运行控制与恢复
description: Gateway 的 Provider 双 revision、Channel 控制、运行态代际围栏和故障恢复当前行为。
status: active
owner: 网关团队
last_updated: 2026-07-31
related:
  - ../glossary.md
  - admission-control.md
  - resilience-circuit-breakers.md
  - ../decisions/adr-0013-provider-runtime-fencing.md
  - ../decisions/adr-0011-runtime-deployment-boundaries.md
---

# 功能设计：运行控制与恢复

## 摘要

Gateway 通过 revision、payload hash、durable operation 和 runtime state epoch，把 PostgreSQL 管理事实与 Redis
执行事实绑定。新请求只使用属于同一 ready epoch、revision 当前且已提交的运行事实；pending、缺失、冲突或
基础设施故障均 fail closed。

已经取得 permit 并开始 transport 的调用不会因普通 control、Provider 或 Channel revision 更新而取消；usage、
账务和审计继续，资源按 permit 固化身份收口，旧 breaker/evidence 反馈成为 stale。integrity epoch 换代
会阻止旧 token/permit 的主动终结，资源只能等待租约或 TTL。

## 当前事实层次

| 层次 | 当前权威 | 作用 |
| --- | --- | --- |
| 管理事实 | PostgreSQL Provider/Channel/control 行与 durable operation | 保存配置、revision、operation 状态和恢复证据 |
| 执行事实 | Redis committed control、Provider/Channel state 和资源 key | 多 Gateway 原子 Snapshot、Acquire、Finish 与限额 |
| 完整性身份 | runtime state epoch + revision | 证明整组执行事实属于当前恢复代际 |
| 故障锁 | Redis infrastructure fault latch + reconciliation proof | Store 故障后阻止仅凭健康探测恢复流量 |

## Revision 与 generation

| 事实 | 当前 revision / generation |
| --- | --- |
| Provider origin | 独立单调 `origin_revision` 与 origin fence generation |
| Provider 状态 | 独立单调 `status_revision` 与 status fence generation |
| Channel 路由配置 | `config_revision`；状态、timeout、credential 或 credential validity 真变化时推进 |
| Channel 并发容量 | 独立 `capacity_revision` |
| 关键 app setting | 每项独立 revision 与 active/pending control |
| breaker | Provider 与 Channel 各自 state generation |
| 整体运行态 | state epoch + epoch revision |

Provider 地址和状态的 revision、pending 与 fence 互相独立；普通 Provider 资料不推进两条 revision。Channel
只保存 `provider_id`，Provider 变化不改写 Channel revision。

## 普通运行控制发布

四个关键 app setting 与 Channel capacity 通过 `runtime_control_operations` 发布：

1. PostgreSQL 创建不可变 token、目标、current/next revision 和 payload hash，operation 为 preparing。
2. Redis Prepare 校验单调 revision、payload hash 和当前 pending，建立 pending fence。
3. PostgreSQL CAS 标记 prepared，在事务中提交业务事实与 revision，标记 db_committed。
4. Redis Commit 激活 committed control，PostgreSQL 最终标记 committed。

Prepare 或数据库提交前失败可以 Abort；db_committed 后只能恢复 Commit。Reconciler 以 PostgreSQL operation 和
当前业务行重建规范 payload，任何 hash、pending、目标或业务事实冲突都停止恢复并保持 fail closed。

Gateway 与 Admin 的首次启动协调运行在停机重启模型下：先收口 PostgreSQL 中未终结的 durable operation，再以
PostgreSQL 当前稳定事实为权威，原子重建缺失或漂移的四个关键 app setting 与 Channel capacity control。启动重建
会覆盖 Redis 中落后、超前、payload 不同或残留 pending 的单个 control，并清除该 control 的 pending 字段；
不会清除请求层限流桶、并发租约、request token、Sticky、breaker 或其他运行态 key。进程启动后的周期
Reconciler 不使用权威覆盖，仍只补缺失并严格拒绝已有冲突，避免干扰运行中的 Admin 发布。

## Provider 路由事实发布

Provider origin 与 status 使用独立 `provider_routing_operations`，kind 只允许 `origin` 或 `status`：

- 单次操作锁定 Provider 与 operation，不存在 Origin ID 扇出、批量 status 或 combined 更新。
- origin/status 分别推进对应 revision 与 fence；一个操作不改另一条 revision。
- 未提交操作恢复 aborted，db_committed 操作只恢复 committed。
- 首次启动协调在收口未终结 Provider operation 后，以 PostgreSQL 当前双 revision 和 status 校正 Redis Provider
  control。正常 Hash 只改控制字段、清除 pending 并推进 fence generation，保留 breaker 窗口与状态；错误类型
  的单个 Provider key 会重建。周期 Reconciler 仍只补缺失，已存在冲突不会被运行期覆盖。
- 地址正文不进入 revision transition 摘要，durable payload hash 仍绑定规范化完整目标。

Provider 归档遇非终态 operation 返回 conflict，不自动 Abort 或接管。归档后清除已终态 operation 的 Redis
记录和 Provider control；恢复后从 PostgreSQL 当前双 revision 重新初始化 control。

## 候选快照与 Acquire

候选计划使用 PostgreSQL 当前 Provider、Channel、Model、价格和 revision 构造 `SnapshotMany`。一次 Redis
线性化读取校验：

- ready epoch/revision、Redis server identity 和故障锁；
- Provider origin/status revision、active/pending fence、Provider breaker/evidence；
- Channel config/capacity revision、breaker、cooldown、permission 与并发容量；
- RouteRate、GlobalConcurrency、CircuitBreaker 和 RoutingBalance 当前 control。

任一关键 control 缺失、pending、payload 非法或 revision stale 会使整批失败，并发生在请求 TPM Reserve、账务
授权和 attempt 创建前。正常业务不可用状态只过滤相应候选。

每个真实 transport 前仍以新 permit ID 执行 Acquire，强读当前 control revision 并再次校验 Provider/Channel
围栏、breaker、permission、cooldown 与 Channel 并发。地址不匹配是 `stale_revision`，状态不匹配是
`stale_status_revision`。Store 错误或 `breaker_store_unavailable` 终止 fallback；普通 denial 可检查下一候选。

Finish/Abort 在 epoch 匹配时先按 permit 固化身份收口资源，再根据 revision、fence 与 generation 应用或拒绝
运行反馈。epoch 已换代时 Manager 在调用 Redis 前失败，资源依赖租约或 TTL。

## Runtime State Epoch

epoch 保存随机身份、单调 revision 和 recovering/ready 状态，reason 为 bootstrap、state_loss 或 restore。

- 首次 bootstrap 建立 durable operation，经 Redis pending、PostgreSQL db_committed、Redis Commit 后自动 ready。
- PostgreSQL 已是 ready 且没有未终结 epoch operation 时，Gateway 启动会按 DB 当前 epoch/revision 原子重建
  缺失或不匹配的 Redis marker；不会清除其他 Redis 运行态 key。
- state loss/restore 只能由 maintenance 命令开始，要求明确确认入口阻断、运行态丢失和合法 recovery 身份。
- Commit 需要入口阻断、在途排空、等待窗口、breaker/cooldown、permission、control、离线脚本和 maintenance
  probe 的限时摘要证据；随后进入 awaiting_release。
- awaiting_release 期间必须完成 Provider、Channel、关键 control 和 durable operation 全量对账，提交绑定
  Redis server identity 与 reconciliation generation 的 proof，再以 post-commit smoke 证据 Release。
- Release 后 operation 才 committed，普通 readiness 才可恢复。

## Readiness 与故障锁

`/readyz` 是只读检查，不创建 marker、恢复 control 或清 fault latch。它要求 PostgreSQL ready epoch、四个关键
control、无阻断 operation、Redis marker/epoch/control/payload、Provider routing operation 终态、server identity、
reconciliation proof 和 fault latch 全部一致。

Redis/BreakerStore 操作失败会使新准入 fail closed 并留下 fault latch。Redis 恢复连接不足以重新放流；后台
Reconciler 完整核对 PostgreSQL 与 Redis 后才能清锁。

## 凭据失效、轮换与检测

连续 401 key 包含 Channel ID、Channel config revision 与 Provider 的 origin/status revision。相同 revision 的
成功清零；达到阈值后异步 PostgreSQL CAS，仅在三条 revision 匹配且 credential 当前 valid 时置 invalid。

凭据更新遵循：

- 真变化时保存新值、置 invalid、清旧摘要、推进 config revision，并用 Channel + Provider 双 revision 冻结
  快照执行独立有界探测；
- 同值且 valid 返回 not_required；同值但 invalid 使用当前 revision 重测；
- 成功且三条 revision 仍匹配时恢复 valid 并推进 config revision；
- failed、execution_failed 或 stale 不恢复，保存结果仍明确为已提交；
- 403 permission recheck 使用精确 Channel-Model-revision 绑定，不修改整个 Channel credential validity。

## 归档与在途收口

Provider/Channel 归档立即清除阻止新请求所需的 breaker、cooldown/control、permission 和 evidence，但保留
permit 与并发租约。已开始调用继续响应、usage、账务与审计；其运行反馈因生命周期或 revision 变化
成为 stale/no-op。异常残留由租约和 TTL 回收。

## 安全与可观测性

公开 API 不返回 credential、permit、epoch、fence、payload hash、Provider origin 或内部 revision。内部事实包括
双 revision active/pending、operation state、epoch/integrity、reconciliation generation、fault latch、revision
mismatch、Finish disposition 和凭据检测摘要。

## 代码与测试证据

当前测试覆盖普通 control、Provider origin/status publisher/reconciler、启动时 DB 权威修复高低 revision、payload
漂移、pending、错误 key 类型和 ready marker 丢失，周期严格协调不覆盖冲突，以及 state epoch bootstrap、响应
丢失、maintenance evidence、awaiting release、readiness、401、凭据 CAS、permission recheck、归档分层 purge、
完整状态丢失和长流 revision fence。

## 相关决策

- [ADR-0013：Provider 运行态代际围栏](../decisions/adr-0013-provider-runtime-fencing.md)
- [ADR-0011：运行时部署边界](../decisions/adr-0011-runtime-deployment-boundaries.md)
