---
title: Provider Origin 与 Channel 管理
description: 运营人员维护供应商、上游源站、渠道、凭据与归档生命周期的页面设计。
status: draft
owner: 管理后台团队
last_updated: 2026-07-25
related:
  - ../glossary.md
  - ../features/operations-management.md
  - ../decisions/adr-0002-provider-origin-management.md
  - ../../../templates/page-design.md
---

# 页面设计：Provider Origin 与 Channel 管理

## 目的

让运营人员在一个清晰的层级中检查和维护 Provider、Provider Origin 与 Channel，并安全完成检测、凭据轮换、归档、恢复和线路绑定迁移。

## 用户与入口

| 用户 | 入口 | 预期上下文 |
| --- | --- | --- |
| 运营人员 | 运营导航中的 Provider 列表 | 需要快速判断供应商是否已配置 Origin，或开始维护供给。 |
| 运营人员 | Provider、Origin 或 Channel 详情 | 正在处理配置、凭据、路由可用性或归档。 |

## 目标

- 展示 Provider 与 Provider Origin 的稳定业务关系，并把 Channel 作为源站下的账号级配置。
- 让敏感凭据操作可理解、可确认且不泄露内容。
- 用受控的归档和恢复替代误删除。

## 非目标

- 呈现客户可见的 API Endpoint、内部技术类型名或凭据内容。
- 在 Provider 列表轮询每个 Origin 的实时运行态。

## 信息层级

1. Provider 列表显示名称、业务状态和 Origin 摘要。摘要显示名称、规范化地址和业务状态；零 Origin 必须明确为空，多个 Origin 可紧凑展示并可展开。
2. 非归档 Provider 的行级操作提供“新建上游源站”；归档 Provider 不提供创建入口。
3. Provider 与 Origin 详情按 Channel 列出协议、适配器、凭据有效性、最近检测摘要、归档状态和必要的客观运行事实链接。
4. Channel 详情提供检测、凭据轮换、归档/恢复和模型或线路成员关系管理；凭据永不显示。

## 数据与权限

| 数据或操作 | 权威位置 | 可见性或权限 | 新鲜度 |
| --- | --- | --- | --- |
| Provider 与 Origin 业务摘要 | [运营管理](../features/operations-management.md) | 授权运营人员 | 列表查询时 |
| Channel 凭据状态和检测历史 | 运营管理 | 授权运营人员；无凭据内容 | 当前状态与历史分开 |
| Origin/Channel 运行态 | [运营可观测性](../features/operations-observability.md) | 授权运营人员 | 明示数据新鲜度 |
| 归档、恢复、绑定迁移 | 运营管理 | 授权运营人员；破坏性动作需确认 | 动作完成后刷新 |

## 交互

- 新建 Origin 复用统一表单；成功后刷新 Provider 列表、Origin 与 Channel 查询。
- 手动检测显示安全的成功、失败和延迟摘要；明确检测会发出真实上游请求但不计入客户账单。
- 轮换凭据后显示“已保存”与验证结果两个独立状态。`passed`、`failed`、`stale`、`execution_failed` 和 `not_required` 必须有不同文案，不能把未检测或失败说成通过。
- 归档前说明受影响的线路或 API Key；有绑定 API Key 的线路必须先迁移。恢复后显示其已处于 disabled，并提示需要的重新绑定或启用动作。

## 页面状态

| 状态 | 必备表现 | 可用操作 |
| --- | --- | --- |
| 加载 | 固定结构与加载提示，不显示旧运行态冒充当前值 | 返回列表或详情 |
| 空状态 | 明确“尚无上游源站”或“尚无渠道” | 非归档 Provider 可创建 Origin |
| 无 Origin | Provider 行明确为空 | 查看或创建 Origin |
| 凭据检测中 | 显示保存与验证分别进行 | 等待结果；不得重复伪造状态 |
| 检测失败 | 显示安全原因与不可路由状态 | 修复后重新检测 |
| 已归档 | 显示归档时间和历史提示 | 恢复；符合条件时删除 |
| 基础设施故障 | 链接客观运行态并说明准入已拒绝 | 诊断运行态，不给出健康标签 |

## 无障碍

表格操作必须有名称和键盘焦点；状态以文字而非颜色独自表达；确认对话框在打开时获得焦点、关闭后返回触发控件；异步检测结果通过状态区域播报。

## 验收标准

- [ ] 列表在同一业务查询中获得 Origin 摘要，不逐行读取运行态。
- [ ] 所有用户可见文案使用“上游源站”，不使用旧 `ProviderEndpoint` 或含混的“端点”。
- [ ] 凭据从不出现在响应、页面或检测历史中。
- [ ] 归档 Provider 不可新建 Origin；恢复对象明确为 disabled 并提示后续操作。
