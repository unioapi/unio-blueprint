---
title: 运行控制与恢复
description: Gateway 运行态控制、代际围栏、凭据轮换与故障恢复的当前行为。
status: active
owner: 网关团队
last_updated: 2026-07-26
related:
  - ../glossary.md
  - admission-control.md
  - resilience-circuit-breakers.md
  - ../decisions/adr-0008-runtime-state-fencing.md
  - ../decisions/adr-0011-runtime-deployment-boundaries.md
---

# 功能设计：运行控制与恢复

## 摘要

Gateway 把 PostgreSQL 中的管理事实与 Redis 中的执行事实通过 revision、payload hash、durable operation 和
runtime state epoch 绑定。新请求只使用能够证明属于同一 ready epoch、当前 revision 且已提交的运行事实；
任何 pending、缺失、冲突或基础设施故障都 fail-closed。

已经取得 permit 并开始 transport 的调用不会因普通 control 或 Origin/Channel revision 更新被取消；usage、账务和
审计仍按实际结果处理，资源按 permit 固化的桶身份收口，旧 breaker/TTFT 结果可得到 stale disposition。
integrity epoch 换代是例外：它会在 Redis 调用前阻止旧 token/permit 的 Finalize、Finish 或 Abort，资源只能等待
租约或 TTL 过期。

## 当前事实层次

| 层次 | 当前权威 | 作用 |
| --- | --- | --- |
| 管理事实 | PostgreSQL 业务行与 durable operation | 保存配置值、revision、操作状态和恢复证据 |
| 执行事实 | Redis committed control、Origin/Channel state 和资源 key | 为多 Gateway 提供原子 Snapshot、Acquire、Finish 与限额状态 |
| 完整性身份 | `gateway.runtime_state_epoch` 的 epoch + revision | 证明整组执行事实属于当前恢复代际 |
| 故障锁 | Redis infrastructure fault latch + reconciliation proof | Store 故障后阻止仅凭一次健康探测恢复流量 |

普通 settings cache 和实例内 settings applier 不是关键准入的执行权威。关键执行 control 包括线路限流默认、
Channel 限流默认、全局并发默认、circuit breaker 与 routing balance；Channel 自身四维限额使用独立
`admission_limits_revision`。

## Revision 与围栏

| 事实 | 当前 revision / generation |
| --- | --- |
| Provider Origin Base URL | 独立、单调 `base_url_revision` 与 fence generation |
| Provider Origin 有效状态 | 独立、单调 `status_revision` 与 fence generation；Provider 状态批量变更也推进受影响 Origin |
| Channel 路由配置 | `config_revision`；Origin 绑定、状态、timeout、credential 或 credential validity 真变化时推进 |
| Channel 限额 | `admission_limits_revision`，不与 config revision 混用 |
| 关键 app setting | 每个 setting 独立 revision 与 active/pending control |
| breaker 状态 | Origin 和 Channel 各自 state generation |
| 整体运行态 | state epoch + epoch revision |

Channel 的 `protocol` 与 `adapter_key` 当前在创建后不通过普通更新接口修改。归档、恢复或 Provider 级联归档会推进
受影响 Channel 的 config revision。

## 普通运行控制发布

关键 app setting 与 Channel admission limits 使用同一可恢复发布顺序：

1. 在 PostgreSQL 创建不可变 token、目标、current/next revision 与 payload hash，operation 为 `preparing`。
2. Redis Prepare 校验 `next = current + 1`、payload hash 和现有 pending，建立 pending fence。
3. PostgreSQL CAS 将 operation 标为 `prepared`。
4. 在一个 PostgreSQL 事务中提交业务行及其 revision，并把 operation 标为 `db_committed`。
5. Redis Commit 将 pending 激活为 committed active control。
6. PostgreSQL 将 operation 标为 `committed`。

当前失败与恢复边界为：

- Redis Prepare 或 PostgreSQL 业务提交失败时，业务事实尚未提交，publisher 尝试 Redis Abort 并把 operation
  标为 `aborted`。
- 一旦 PostgreSQL 已是 `db_committed`，不能再 Abort。Redis Commit 失败、响应丢失或最终 operation 标记失败时，
  调用结果为 `runtime_sync_pending`。
- Reconciler 以 PostgreSQL operation 和当前业务行重建规范 payload：`db_committed` 只能恢复 committed，
  `preparing/prepared` 只能恢复 aborted。
- payload hash、pending revision、目标或业务事实冲突时，对账立即停止并保持 fail-closed；恢复流程不会猜测
  哪一侧正确，也不会覆盖冲突。
- runtime state epoch 使用专用恢复流程，普通 Reconciler 明确跳过它。

## Origin 路由事实发布

Provider Origin 的 Base URL、status、Base URL + status 组合更新，以及 Provider status 对所属 Origin 的批量更新，
使用独立 durable operation，但遵循相同的 prepare、业务提交、commit 和恢复原则。

- 单 Origin 操作锁定 Provider、目标 Origin 和 operation；批量操作按 Origin ID 稳定顺序锁定全部目标。
- Base URL 和 status 分属独立 revision；组合更新在同一 operation 中同时推进，批量 Provider status 更新原子处理
  受影响的 Origin status revisions。
- 未提交操作恢复为 aborted，`db_committed` 操作只恢复 committed。
- Reconciler 可在完整 PostgreSQL 事实已锁定且 Redis Origin control 完全缺失时恢复该 control。
- 已存在的 Redis control 若 revision、有效状态、pending 或业务事实不一致，不会被覆盖；整轮对账停止并继续
  fail-closed。

Origin 地址正文不进入 revision transition 摘要；durable payload hash 仍绑定规范化的完整目标 payload。

## 请求热路径

### 候选快照

候选计划使用 PostgreSQL 当前业务事实和 revision 构造 `SnapshotMany` 输入。一次 Redis Lua 线性化读取会校验：

- ready integrity epoch 与 revision；
- Channel rate、global concurrency、circuit breaker、routing balance 等当前 control；
- 每个 Origin Base URL/status revision、有效状态和 pending fence；
- 每个 Channel config/admission revision、breaker、429 cooldown、Channel-Model permission 与容量 key。

任一 control 缺失、pending、payload 不合法、revision stale、stable resource 类型错误或 fault latch 未恢复都会使
整批失败。正常生成路径在请求 TPM Reserve、账务授权和 attempt 创建前完成该快照，因此失败不会产生上游调用。

### 候选 Acquire 与 Finish

快照只用于过滤和排序。每个真实 transport 前仍会：

1. 从 PostgreSQL 强读 admission 与 routing revisions，并确认两组 revision 属于同一 integrity epoch；
2. 以新的 permit ID 调用 Redis 原子 Acquire；
3. 同时校验当前 Origin/Channel 围栏、breaker、permission、cooldown、限额与资源；
4. 全部通过后才创建 `AttemptPermit` 并调用上游。

PostgreSQL 强读失败、Breaker Store 调用错误或 `breaker_store_unavailable` 会立即终止 fallback。Redis 正常返回的
拒绝结果则只跳过当前候选；这既包括容量、breaker 和权限等业务拒绝，也包括 `runtime_sync_required`、
`runtime_state_lost`、integrity stale 及 revision/control pending 或 stale 等 fail-closed 拒绝。后者当前会继续检查
下一候选，全部候选均被拒绝时再收口为无可用候选，而不是把具体 control 原因直接返回给客户。

Finish/Abort 在写入前再次要求 permit 的 integrity epoch 仍是 PostgreSQL 当前身份。若 epoch 已换代，Manager
在调用 Redis 前返回错误，permit 资源只能依赖租约或 TTL 过期；request Finalize 具有相同边界。epoch 仍匹配时，
Redis 才用 permit 中固化的 revision、fence generation 和 breaker generation 决定 applied 或 stale disposition，
并按 first-terminal-wins 终结资源。

## Runtime State Epoch

State epoch 有 `recovering` 与 `ready` 两种 PostgreSQL 状态，reason 为 `bootstrap`、`state_loss` 或 `restore`。
每次新 epoch 使用新的 128-bit 随机身份和单调 revision。

### 首次 bootstrap

首次启动原子创建 recovering epoch 与 durable operation，经 Redis pending fence、PostgreSQL `db_committed`、
Redis Commit 后自动把 PostgreSQL epoch 标为 ready，并将 operation 标为 committed。相同 operation 的响应丢失或
重启可幂等恢复；后续启动不会生成新的 bootstrap epoch。

### state loss / restore

非 bootstrap 恢复只能通过维护命令开始，并要求：

- 当前 epoch 是 ready，调用方给出的 current revision 匹配；
- reason 是 `state_loss` 或 `restore`，且明确确认运行态已丢失；
- 明确确认外部入口已经阻断；
- recovery ID、operator reference、detected time 与 not-before 合法，not-before 不晚于检测后 24 小时。

BeginRecovery 建立唯一 durable operation 和 Redis pending fence，并把 PostgreSQL 推进到新的 recovering epoch。
该流程没有 Abort；启动协调器只恢复 pending/db-committed 状态，不会自行 Commit 非 bootstrap epoch。

CommitRecovery 只接受绑定同一 recovery、旧 revision、reason 与时间窗口的 `approved` 证据。当前固定门禁为：
入口阻断、在途排空、等待窗口、breaker/cooldown、permission、control、离线脚本和 maintenance probe；每项必须
带 passed、检查时间和 SHA-256 摘要。证据和入口阻断检查的有效期均为 15 分钟。

证据通过后，CommitRecovery 激活 Redis 新 marker，并把 PostgreSQL epoch 标为 ready，但 durable operation 进入
`awaiting_release`，而不是 committed。

### Post-commit release

`awaiting_release` 期间，完整 Origin、Channel、关键 control 和 durable operation 对账可以提交绑定 Redis server
identity/run ID 与 reconciliation generation 的 proof，从而清除 infrastructure fault latch，允许外部入口隔离的
maintenance smoke。普通 `/readyz` 仍返回未就绪，因为 durable operation 尚未 release。

`ReleaseRecovery` 只接受在新 epoch activated time 之后生成、与 recovery ID 和新 revision 精确绑定、状态为 passed
且不超过 15 分钟的 post-commit Gateway smoke 证据。Release 成功后 operation 才变为 committed，普通 readiness
才可在其他门禁都通过时恢复。

## Readiness 与故障锁

普通 `/readyz` 是只读检查，不创建 marker、不恢复 control，也不清 infrastructure fault latch。它同时要求：

- PostgreSQL epoch 为 ready，五项关键 control revision 有效；
- 没有阻断 readiness 的 durable operation；
- Redis marker、epoch、control revisions、payload 与 stable resource integrity 匹配；
- Store fault latch 已由完整 reconciliation proof 清除。

Redis/BreakerStore 操作失败会使新准入 fail-closed，并留下 fault latch。Redis 恢复可连接并不足以重新放流；只有
后台 Reconciler 完整核对 PostgreSQL 与 Redis 后才能调用清锁接口。普通健康探针不会产生该副作用。

## 凭据失效、轮换与检测

### 连续 401

连续 401 计数是每个 Gateway 实例内存中的 map，key 包含 Channel ID、Channel config revision 与 Origin 的
Base URL/status revision，不是 Redis 全局计数。默认阈值为 3，并可热更新：

- 同一 revision 的上游成功清零；
- 401 累加，达到阈值后删除本机计数并触发一次 invalidator；
- timeout、5xx、403、429、客户取消和未分类错误既不增加也不清零。

生产 invalidator 使用独立 goroutine 和 5 秒 background timeout 执行 PostgreSQL CAS。只有三类
revision 仍匹配且 `credential_valid=true` 时才置为 false 并推进 config revision；无论是否发生状态变化，当前
Channel 仍存在时都会写带 tested revisions 与 `state_change_applied` 的 `runtime_401` 审计。

异步数据库写失败只记录日志，不阻断已完成请求，也没有持久重试；不同 Gateway 的连续计数不会合并。

### 凭据轮换

Admin 凭据更新先在单个数据库写中比较规范化后的新值：

- credential 真变化时，立即保存新值、把 `credential_valid` 置为 false、清空旧 credential 的最近检测摘要，
  并推进一次 config revision；随后用该 revision 与 Origin 两类 revision 的冻结快照执行独立有界探测。
- credential 未变化且当前 valid 时，不探测、不推进 revision，返回 `not_required`。
- credential 未变化但当前 invalid 时，使用当前 revision 重新探测。
- 探测成功且三类 revision 仍匹配时恢复 valid，并因状态真变化再推进 config revision。
- credential-invalid 探测失败维持 invalid；其他探测失败或检测编排异常也不会恢复 valid。
- 探测期间任一 revision 变化时，结果只写 `state_change_applied=false` 审计，不覆盖当前摘要或凭据状态。

保存已成功但检测失败、stale 或执行异常时，服务仍返回“credential 已保存”的组合结果，并以 `failed`、`stale`
或 `execution_failed` 表达验证结果，不把已提交保存伪装为可回滚失败。

普通 Channel 主动检测同样按三类 revision 应用结果：成功可恢复 credential validity，明确 credential-invalid
结果可置 invalid，其他失败只更新检测摘要。403 permission recheck 使用精确 Channel-Model-revision 绑定并只写
专用审计，不调用整个 Channel 的 credential validity 更新。

## 安全与可观测性

公开 API 不返回 credential、permit、epoch、fence、payload hash、Origin 地址或内部 revision。恢复证据的固定
Schema 只保存分类、时间和摘要，不允许 URL、credential、请求/响应正文或 Redis operation identifier。

内部可观测事实包括 durable operation state、同步结果、epoch/integrity、reconciliation generation、fault latch、
revision mismatch 与 Finish disposition。凭据检测日志保存稳定分类、状态码、延迟、模型、tested revisions 和
state change 结果；permission recheck 不保存上游响应 body。

## 代码与测试证据

普通 control publisher/reconciler、Origin 单项/组合/批量 publisher、缺失 Origin control 恢复、state epoch
bootstrap、response loss、maintenance evidence、awaiting-release、concurrent command、readiness、401 gate、
凭据 CAS 和 permission recheck 均有分层单元或数据库集成测试。

## 状态说明

本文于 2026-07-26 按当前 Gateway 代码、Schema 与现有测试接收为 `active`。

## 相关决策

- [ADR-0008：运行态代际围栏](../decisions/adr-0008-runtime-state-fencing.md)
- [ADR-0011：运行时部署边界](../decisions/adr-0011-runtime-deployment-boundaries.md)
