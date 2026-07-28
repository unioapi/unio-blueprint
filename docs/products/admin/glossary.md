---
title: Admin（管理后台）词汇表
description: 管理后台领域专用术语的权威定义。
status: draft
owner: 管理后台团队
last_updated: 2026-07-28
related:
  - README.md
  - ../../architecture/glossary.md
  - ../gateway/glossary.md
  - ../gateway/decisions/adr-0001-domain-terminology.md
---

# Admin（管理后台）词汇表

Provider、Channel 与 Route 的定义属于
[Gateway 词汇表](../gateway/glossary.md)和已接受的
[Gateway ADR-0012](../gateway/decisions/adr-0012-provider-channel-route-lifecycle.md)。本表只定义 Admin
在这些共享对象之上的运营概念。

## 领域术语

| 术语 | 定义 |
| --- | --- |
| 渠道检测 | 使用渠道自身配置向真实上游发起最小探测，以验证连通性、凭据、模型和协议，并返回可解释的客观结果。 |
| 凭据有效性 | 与管理员启停状态正交的渠道事实；无效凭据使渠道不进入新请求候选，只有符合当前配置版本的检测成功才能恢复。 |
| 客观运行事实 | 可直接追溯到当前硬门禁、检测、运行态或历史记录的事实，例如 breaker、错误率、流式 TTFT、容量、路由组成分与最终得分；不是主观健康分桶。 |
| 经营驾驶舱 | 面向内部运营的分层经营视图：决策层、分析中心和实时监控页。 |
| API Root 修改确认 | Provider 已有 enabled Channel 时，运营人员对地址切换影响作出的请求内二次确认；不跳过 expected revision 检查。 |
| 归档 | 将 Provider、Channel 或 Route 转为保留历史关联、默认不在在用列表显示的状态；不是硬删除，也不静默级联。 |

## 维护规则

这里只定义管理后台独有术语。平台通用术语属于
[平台词汇表](../../architecture/glossary.md)，Gateway 领域对象属于
[Gateway 词汇表](../gateway/glossary.md)；应通过链接引用，不得重复定义。
