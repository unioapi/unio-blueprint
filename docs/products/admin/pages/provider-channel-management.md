---
title: Provider 与 Channel 管理
description: 运营人员维护 Provider API Root、Channel、凭据、运行态与显式归档生命周期的页面设计。
status: draft
owner: 管理后台团队
last_updated: 2026-07-28
related:
  - ../glossary.md
  - ../features/operations-management.md
  - ../decisions/adr-0002-provider-origin-management.md
  - ../../gateway/decisions/adr-0015-deterministic-cost-aware-routing.md
  - ../../../templates/page-design.md
---

# 页面设计：Provider 与 Channel 管理

## 目的

让运营人员按 Provider → Channel 两层结构维护唯一 API Root、凭据与运行状态，并安全完成检测、地址切换、
状态变更、归档和恢复。

## 用户与入口

| 用户 | 入口 | 预期上下文 |
| --- | --- | --- |
| 运营人员 | 运营导航中的 Provider 列表 | 需要查看供应商、API Root、双 revision 和供给规模。 |
| 运营人员 | Provider 或 Channel 详情 | 正在处理配置、凭据、运行态、路由可用性或归档。 |

## 目标

- 展示 Provider 与唯一 API Root，并把 Channel 作为 Provider 下的账号级配置。
- 让敏感凭据操作可理解、可确认且不泄露内容。
- 用受控的归档和恢复替代误删除。

## 非目标

- 呈现客户可见的 API Endpoint、内部技术类型名或凭据内容。
- 在 Provider 列表逐行轮询实时运行态。

## 信息层级

1. Provider 列表显示名称、状态、唯一 API Root、`origin_revision`、`status_revision`、Channel/Model/Route 数量。
2. Provider 详情内嵌 API Root 编辑、双 revision、pending/sync 状态、Provider breaker 与 reset；不存在的
   Provider reset 必须显示 404，不创建运行态。
3. 修改 API Root 首次因 enabled Channel 返回 409 时，弹窗明确影响范围并要求用户确认；第二次请求携带确认
   字段但仍使用原 expected revision，服务端重新校验。
4. Channel 表单只选择 Provider，并展示只读 API Root。Provider disabled 时自动限制 Channel 为 disabled；
   Provider archived 时禁止保存。Priority 使用 `0,10,...,100` 固定选项；Sticky 使用“系统默认、开启、关闭”
   三态，选择开启时必须填写该 Channel 的 TTL。
5. Channel 详情提供检测、凭据轮换、归档/恢复和模型或 Route 成员关系管理；凭据永不显示。

## 数据与权限

| 数据或操作 | 权威位置 | 可见性或权限 | 新鲜度 |
| --- | --- | --- | --- |
| Provider 业务摘要和双 revision | [运营管理](../features/operations-management.md) | 授权运营人员 | 列表查询时 |
| Channel 凭据状态和检测历史 | 运营管理 | 授权运营人员；无凭据内容 | 当前状态与历史分开 |
| Provider/Channel 运行态 | [运营可观测性](../features/operations-observability.md) | 授权运营人员 | 明示数据新鲜度 |
| 归档、恢复、绑定迁移 | 运营管理 | 授权运营人员；破坏性动作需确认 | 动作完成后刷新 |

## 交互

- 新建 Provider 时填写 API Root；普通编辑不混入地址或状态更新。
- 地址 revision conflict 要求刷新当前事实；enabled Channel conflict 提供一次明确的二次确认。
- 手动检测显示安全的成功、失败和延迟摘要；明确检测会发出真实上游请求但不计入客户账单。
- 轮换凭据后显示“已保存”与验证结果两个独立状态。`passed`、`failed`、`stale`、`execution_failed` 和 `not_required` 必须有不同文案，不能把未检测或失败说成通过。
- Channel Sticky 选择“系统默认”或“关闭”时不显示自定义 TTL；选择“开启”时使用带单位的时长输入，
  Priority 不接受固定选项以外的自由数值。
- 生命周期 conflict 提示按 Route → Channel → Provider 解除引用和状态依赖，不提供级联、复制或替代动作。
- 恢复后显示对象已处于 disabled，并提示需要的重新绑定或启用动作。

## 页面状态

| 状态 | 必备表现 | 可用操作 |
| --- | --- | --- |
| 加载 | 固定结构与加载提示，不显示旧运行态冒充当前值 | 返回列表或详情 |
| 空状态 | 明确“尚无 Provider”或“尚无 Channel” | 创建 Provider 或 Channel |
| 地址 revision conflict | 显示当前事实已变化 | 刷新后重新编辑 |
| enabled Channel conflict | 显示地址切换会影响已启用 Channel | 明确确认或取消 |
| 凭据检测中 | 显示保存与验证分别进行 | 等待结果；不得重复伪造状态 |
| 检测失败 | 显示安全原因与不可路由状态 | 修复后重新检测 |
| 已归档 | 显示归档时间和历史提示 | 恢复；符合条件时删除 |
| 基础设施故障 | 链接客观运行态并说明准入已拒绝 | 诊断运行态，不给出健康标签 |

## 无障碍

表格操作必须有名称和键盘焦点；状态以文字而非颜色独自表达；确认对话框在打开时获得焦点、关闭后返回触发控件；异步检测结果通过状态区域播报。

## 验收标准

- [ ] 列表在同一业务查询中获得 Provider 地址和双 revision，不逐行读取运行态。
- [ ] 页面不存在独立 Origin 页面、Tab、选择器、复制或替代对话框。
- [ ] 凭据从不出现在响应、页面或检测历史中。
- [ ] 地址更新覆盖 revision conflict 和 enabled Channel 二次确认。
- [ ] 409 引导 Route → Channel → Provider；恢复对象明确为 disabled 并提示后续操作。
- [ ] Channel Priority 只能选择 `0,10,...,100`；Sticky 三态与 TTL 校验和 Gateway 契约一致。
