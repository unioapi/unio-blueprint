---
title: Admin（管理后台）路线图
description: 管理后台运营能力、客观可观测性与经营驾驶舱的结果导向规划。
status: draft
owner: 管理后台团队
last_updated: 2026-07-27
related:
  - README.md
  - overview.md
  - features/operations-management.md
  - features/operations-observability.md
  - pages/operations-dashboard.md
  - ../../roadmap/README.md
---

# Admin（管理后台）路线图

## 目的与规划周期

本路线图记录迁移时已知的产品差异和待核验项。它不以来源中的完成日志或百分比宣称交付状态；由管理后台团队按季度复审。

## 当前

| 结果 | 指标 | 负责人 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| Provider→Channel 管理模型符合 ADR-0002 | 独立 Origin 页面/API/DTO 消失；地址双 revision 与 Channel 状态护栏通过合同和 E2E | 管理后台团队、网关团队 | [ADR-0002](decisions/adr-0002-provider-origin-management.md) | 已完成 |
| 以客观运行事实替换早期健康分桶 | 无 `healthy/degraded/unhealthy/no_data` 主观标签、筛选或阈值 | 管理后台团队 | [ADR-0001](decisions/adr-0001-objective-operational-facts.md) | 待核验 |
| 核验凭据轮换保护 | 新凭据未经当前版本检测成功不参与新请求 | 管理后台团队、网关团队 | [运营管理](features/operations-management.md) | 待核验 |

## 下一步

| 结果 | 指标 | 负责人 | 依赖 | 决策门槛 |
| --- | --- | --- | --- | --- |
| 完善多步生命周期的影响预览 | 409 在执行前列出具体 Route/Channel 依赖，不增加静默级联 | 管理后台团队 | [运营管理](features/operations-management.md) | Gateway 提供结构化冲突详情 |
| 建成经营驾驶舱的二级分析中心与 rollup | 可按利润、渠道、模型、缓存、用户和异常下钻；数据保留规则经确认 | 管理后台团队、财务负责人 | [运营可观测性](features/operations-observability.md) | 数据口径与保留策略评审 |
| 建成独立实时监控页 | 运行时指标与经营聚合明确分离 | 管理后台团队、网关团队 | [经营驾驶舱](pages/operations-dashboard.md) | 指标数据源与告警责任确认 |

## 未来

| 可选方向 | 潜在价值 | 所需证据 | 负责人 |
| --- | --- | --- | --- |
| 多管理员身份、授权与操作审计 | 扩大运营协作时维持最小权限与可追溯性 | 角色模型、审计保留要求与安全评审 | 管理后台团队、安全负责人 |
| AI 经营摘要 | 降低从分析事实到行动的时间 | 二级聚合、调用成本、缓存和安全边界方案 | 产品负责人 |

## 明确不计划

- 恢复已被 DEC-024 取代的能力自动校正、请求能力闸门或渠道能力收紧。
- 恢复以阈值派生的渠道健康分桶。

## 变更记录

| 日期 | 变更 | 原因 |
| --- | --- | --- |
| 2026-07-25 | 从 Gateway 来源迁入运营长期事实并登记核验差异 | 迁移资料不能将实现状态自动升级为产品承诺。 |
| 2026-07-27 | Provider Origin 并入 Provider，完成 Admin 两层供给模型 | Gateway 与 Admin 已完成一次切换并通过合同、构建和 E2E。 |
