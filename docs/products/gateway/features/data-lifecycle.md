---
title: 数据生命周期
description: Gateway 当前 Provider、Provider Origin、Channel 与 Route 的归档、恢复和硬删除行为。
status: active
owner: 网关团队
last_updated: 2026-07-26
related:
  - ../glossary.md
  - routing-load-balancing.md
  - runtime-control-recovery.md
  - ../decisions/adr-0008-runtime-state-fencing.md
---

# 数据生命周期

## 摘要

Gateway 对 Provider、Channel 和 Route 提供独立的 archive、restore 与受限硬删除操作；Provider Origin
只通过通用状态更新在 `enabled`、`disabled` 和 `archived` 之间切换。四类实体没有一套统一归档协议，
其级联、替换、恢复、名称释放、引用保护和 revision 行为均不同。

归档改变当前供给状态和路由关系，不删除 request、attempt、usage、ledger、价格/成本快照等历史事实。
硬删除只对部分实体开放，并依赖数据库外键保护已被历史或运行操作引用的数据。

## 行为总览

| 实体 | 归档入口 | 恢复结果 | 硬删除入口 |
| --- | --- | --- | --- |
| Provider | 独立 archive，可级联 Origin/Channel，可带替代 Channel | Provider 变为 `disabled`；子 Origin/Channel 保持 `archived` | 有；仅允许已归档 Provider |
| Channel | 独立 archive，可带替代 Channel | Channel 变为 `disabled`；不自动回 Route 池 | 有；仅允许已归档 Channel |
| Route | 独立 archive；有 API Key 时必须原子迁移 | Route 变为 `disabled`；原候选池保留，API Key 不恢复 | 有；仅允许已归档 Route |
| Provider Origin | 通用 status 更新为 `archived` | 可从 `archived` 直接改为 `disabled` 或 `enabled` | 无专用入口 |

## Provider

### 归档

Provider 归档会把 Provider 置为 `archived`，级联归档其 Origin 和尚未归档的 Channel。被级联归档的
Channel 会从所有 Route 候选池移除，并在名称后追加 `__archived_<id>` 以释放原名称。

归档前检查所有 enabled Route。若移除该 Provider 的 Channel 会清空某条 enabled Route，且请求没有提供
替代 Channel，操作返回 conflict。调用方也可以提供另一 Provider 下的替代 Channel；替代对象必须 enabled、
凭据有效且配置完整，其 Provider 也必须 enabled。替换 Route 候选与归档在同一数据库操作中提交。

Provider 状态变更接入运行控制 fence。存在 fencer 时，归档通过 Provider/Origin operation 协调控制发布；
operation 保存的是技术恢复状态、token 和摘要，不是业务归档审计。

### 恢复与删除

Provider restore 只把 Provider 从 `archived` 改为 `disabled`。其 Origin 和 Channel 保持归档，需要分别处理；
Channel 也不会自动重新加入 Route。

Provider 硬删除只接受已归档对象。删除流程会清理可清理的终态 Origin operation 引用并删除 Provider
Origins；仍被 Channel、历史事实或在途 operation 引用时，数据库引用保护会使删除返回 conflict。

## Channel

### 归档

Channel 归档会：

- 将状态改为 `archived`；
- 从全部 `route_channels` 候选池移除；
- 名称追加 `__archived_<id>`；
- 推进 Channel 配置 revision。

若该 Channel 是某条 enabled Route 的最后候选，无替代对象时归档返回 conflict。替代 Channel 必须是不同
对象、enabled、凭据有效且配置完整，并且其 Provider enabled；替换和归档原子提交。替代 Channel 可以来自
另一 Provider。

### 恢复与删除

Channel restore 把状态改为 `disabled`，保留归档名称后缀，也不恢复任何 Route 绑定。父 Provider 仍为
`archived` 时，恢复会被拒绝。

Channel 硬删除只接受已归档对象。它会删除 Channel 自身配置子表，并通过外键级联删除对应检测日志；
request、attempt、账务历史或运行 operation 等引用可以阻止删除。被阻止时对象继续保持归档。

## Route

### 归档

Route 有绑定 API Key 时不能直接归档。调用方必须指定另一条 enabled Route；服务在同一事务中把全部
API Key 迁移到目标 Route，再归档原 Route。无绑定 API Key 时可以直接归档。

Route 归档会把名称追加 `__archived_<id>`，但保留 `route_channels` 候选池关系。归档完成后服务还会返回
其他“候选池为空但仍绑定 API Key”的非归档 Route 警告；该警告不回滚已经完成的归档。

### 恢复与删除

Route restore 把状态改为 `disabled`。原 `route_channels` 仍在，但归档时迁走的 API Key 不会自动迁回。

Route 硬删除只接受已归档对象。API Key、用户、routing trace 或其他外键引用可以阻止删除；服务将这类
外键冲突转换为保留归档对象的 conflict。

## Provider Origin

Provider Origin 没有独立 archive、restore 或 delete HTTP 路由。Admin 使用同一个 status 更新入口在
`enabled`、`disabled` 与 `archived` 间切换。

改为 `archived` 前，Origin 必须没有任何未归档 Channel；否则返回 conflict。Origin 名称不会追加归档
后缀。从 `archived` 可以直接改为 `disabled` 或 `enabled`，没有“只能先恢复为 disabled”的限制，也没有
硬删除入口。

Origin 状态更新使用有效状态 revision fence：

- 新状态与当前状态相同时幂等返回，不推进 revision；
- 若父 Provider 状态遮蔽了 Origin 变化，使有效状态不变，服务只更新数据库状态，不推进运行 revision；
- 有效状态真正变化时，通过运行控制发布推进 revision；fencer 未配置时状态更新失败。

## 历史与引用保护

Archive 操作不删除 request、attempt、response facts、usage、settlement、ledger、价格快照或成本快照。
这些历史行继续引用当时的 Provider、Channel、Route 和模型事实。硬删除是否可执行由显式状态闸门和数据库
外键共同决定，不会为了释放对象而级联删除账务或请求历史。

Channel 检测日志属于 Channel 自身配置生命周期，硬删除 Channel 时可以级联清理；它与请求、usage 和
账务历史的保留边界不同。

## 当前审计事实

Provider、Provider Origin、Channel、Route 及其归档请求当前没有统一的 actor、reason 或 archive audit
字段。实体状态、`archived_at`（存在该列的实体）、名称后缀、revision 和引用关系可以证明技术结果，
但不能回答由谁、为何发起归档或恢复。

Provider/Origin operation 表记录运行控制发布、恢复 token、状态和技术摘要，不记录业务操作者或归档理由。

## 当前边界

- 四类实体的 API、级联、替代和恢复语义不同；Provider Origin 没有独立恢复或硬删除入口。
- 恢复不会重建归档前的完整拓扑：Provider 子对象、Channel Route 绑定和 Route API Key 均不会自动恢复。
- Route 归档保留候选池，而 Channel/Provider 归档会移除候选；不能把三者解释为同一种操作。
- 硬删除依赖外键现状，已有历史或在途引用时只能继续归档保留。
- Channel archive 和 hard delete 的当前服务路径不调用 Redis Channel state、admission control 或其他运行 key 清理。
- 当前没有统一记录 actor、reason 和归档/恢复事件的业务审计事实。

## 状态说明

本文于 2026-07-26 按当前 Gateway 代码、Schema 和现有测试接收为 `active`。
