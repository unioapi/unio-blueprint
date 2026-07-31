---
title: 数据生命周期
description: Gateway 当前 Provider、Channel 与 Route 的状态、归档、恢复、硬删除和引用保护行为。
status: active
owner: 网关团队
last_updated: 2026-07-31
related:
  - ../glossary.md
  - routing-load-balancing.md
  - runtime-control-recovery.md
  - ../decisions/adr-0012-provider-channel-route-lifecycle.md
  - ../decisions/adr-0013-provider-runtime-fencing.md
---

# 数据生命周期

## 摘要

Gateway 对 Provider、Channel 和 Route 提供独立的状态、archive、restore 与受限硬删除操作。每个 Channel
直接归属一个 Provider；Provider 保存唯一 `origin`，不存在独立 Origin 生命周期。停用不改拓扑，归档前必须
显式解除引用，所有动作均不静默级联或自动替换。

归档改变当前供给状态和可路由资格，不删除 request、attempt、usage、ledger、价格/成本快照等历史事实。
已经取得 permit 或开始 transport 的调用继续完成业务和资源收口。

## 状态不变量

- `Channel.status = enabled` 蕴含 `Provider.status = enabled`。
- disabled Provider 下可以创建或编辑 Channel，但只能保存为 disabled；archived Provider 下禁止配置 Channel。
- `route_channels` 可以保留 disabled Channel，但不得保留 archived Channel。
- archived Provider 下不得存在非归档 Channel。
- disabled 表示临时停止服务并保留关系；archived 表示退出日常使用并保留历史。

## 行为总览

| 实体 | 停用 | 归档前置条件 | 恢复结果 | 硬删除 |
| --- | --- | --- | --- | --- |
| Provider | 存在 enabled Channel 时 conflict，不级联 | 无非归档 Channel、无非终态 provider routing operation | `disabled`，恢复原 `origin` | 仅已归档且无引用 |
| Channel | 保留全部 Route 池关系 | 不在任何 Route 池 | `disabled`，不恢复 Route 池 | 仅已归档且无历史引用 |
| Route | 保留 API Key 与 Channel 池 | 有 API Key 时必须原子迁移到 enabled Route | `disabled`，不迁回 API Key | 仅已归档且无历史引用 |

## Provider

### 创建、编辑与状态

Provider 创建时提交全局唯一、使用 `http` 或 `https` scheme 的 `origin`。普通编辑只修改名称等资料；地址和
状态使用独立入口与 expected revision。存在 enabled Channel 时修改地址需要调用方明确确认，但不修改 Channel
状态或 Route 池。

停用 Provider 前必须先停用其下全部 enabled Channel；存在 enabled Channel 时返回 conflict。启用 Provider
不自动启用任何 Channel。

### 归档与恢复

Provider 归档要求：

- 名下不存在非归档 Channel；
- 不存在 `preparing`、`prepared` 或 `db_committed` 的 provider routing operation；
- 当前对象尚未归档。

归档提交后，Provider 变为 archived，并在 `origin` 末尾追加精确 `__archived_<id>` 后缀，释放原 URL 的唯一
约束。归档不会中止或接管非终态 operation，也不会归档 Channel。

恢复只移除与当前 Provider ID 完全匹配的末尾后缀，并把状态置为 disabled。原 URL 已被其他 Provider 使用时
返回 conflict；服务不会生成新地址或剥离其他后缀。恢复后重新初始化 Provider 运行 control，不恢复 Channel。

### Redis 分层清理

归档立即删除 Provider breaker、evidence、origin/status control、permission 关联和已终态 routing operation 的
Redis 状态，阻止新准入。不得删除在途 permit 或任何 Channel 的资源；旧请求的运行反馈成为 stale/no-op，
资源仍按 permit 固化身份收口。

## Channel

### 配置与状态

Channel 只保存 `provider_id`，上游地址从 Provider 读取。创建、普通编辑和启用都在服务端检查 Provider 状态；
客户端过滤不能替代该护栏。停用 Channel 保留模型、成本、凭据和全部 Route 池关系，重新启用后可以在仍启用
Route 中恢复候选资格。

### 归档与恢复

Channel 仍在任意 Route 池时，归档返回 conflict；调用方必须先显式编辑所有 Route 移除该 Channel。归档不会
自动拆线、复制或添加替代 Channel。

归档成功后状态变为 archived，名称追加 `__archived_<id>`，并推进 Channel config revision。恢复要求父
Provider 未归档，结果为 disabled；归档前已经移除的 Route 关系不会自动恢复。

归档立即清理 Channel breaker、cooldown、capacity control、permission 和 recheck queue 成员；在途 permit 与
并发租约保留至 Finish/Abort 收口或 TTL 回收。Channel RPM/RPD/TPM 是独立观测桶，不是待收口的准入资源。

## Route

Route 有绑定 API Key 时不能直接归档；调用方必须指定另一条 enabled Route，服务在同一事务中迁移全部 Key
并归档原 Route。Route 归档保留 Channel 池，恢复为 disabled，已经迁走的 API Key 不自动迁回。

## 硬删除与历史保护

Provider、Channel 和 Route 的硬删除只接受已归档对象。Provider 删除会清理可删除的终态 provider routing
operation；非终态 operation、Channel、request、attempt、usage、账务或其他历史引用通过数据库约束阻止删除。
Channel 删除可以清理自身配置和检测日志，但不会为删除方便级联清理客户请求或账务事实。

归档与硬删除不改变已有 request、attempt、response facts、usage、settlement、ledger、价格快照或成本快照。

## 当前审计边界

实体状态、`archived_at`、名称/地址后缀、revision、routing operation 和引用关系可以证明技术结果，但当前
没有统一的 actor、reason 或 archive audit 字段。durable operation 记录运行控制发布与恢复技术事实，不替代
业务操作审计。

## 代码与测试证据

当前服务、数据库与故障测试覆盖 Provider/Channel 状态不变量、409 前置条件、无级联归档、Provider 地址后缀
释放与精确恢复、URL 冲突、非终态 operation 阻断、Redis 分层 purge、在途长流收口和历史引用保护。

## 相关决策

- [ADR-0012：Provider、Channel 与 Route 供给生命周期](../decisions/adr-0012-provider-channel-route-lifecycle.md)
- [ADR-0013：Provider 运行态代际围栏](../decisions/adr-0013-provider-runtime-fencing.md)
