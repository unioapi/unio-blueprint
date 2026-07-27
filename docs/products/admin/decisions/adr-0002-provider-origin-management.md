---
title: "ADR-0002：Provider 与 Channel 供给管理"
description: "在 Provider 内嵌上游地址和运行态，并以显式状态护栏管理 Channel、凭据与归档生命周期。"
status: proposed
owner: 管理后台团队
last_updated: 2026-07-27
related:
  - ../overview.md
  - ../glossary.md
  - ../features/operations-management.md
  - ../pages/provider-channel-management.md
  - ../../gateway/decisions/adr-0012-provider-channel-route-lifecycle.md
  - ../../../templates/adr.md
---

# ADR-0002：Provider 与 Channel 供给管理

## 背景

运营人员需要管理供应商、上游地址、账号级 Channel、凭据和下线供给。Gateway 已按
[ADR-0012](../../gateway/decisions/adr-0012-provider-channel-route-lifecycle.md) 删除独立 Provider Origin，
每个 Provider 直接保存唯一 `origin`、独立地址/状态 revision 和公共故障域。Admin 必须使用相同的
Provider → Channel 两层模型，并把有依赖的停用、改址和归档操作组织为显式工作流。

## 决策驱动因素

- 上游根地址必须与 Provider 身份保持一一对应，且公共故障域可解释。
- 未经验证的新凭据不能由客户请求试错。
- 状态和归档操作不能静默级联或替换 Route 拓扑。

## 备选方案

### 方案：保留独立 Origin 页面和兼容入口

Admin 继续展示 Provider、Origin、Channel 三层页面，并在客户端适配新 Gateway。

**优点**

- 历史操作路径变化较小。

**缺点**

- 页面会展示不存在的领域实体，状态、revision 和 breaker 归属无法解释。
- 兼容 DTO 会掩盖 Gateway 已完成的一次切换。

### 方案：Provider 内嵌 origin、检测优先与显式生命周期（选中）

Provider 同时表示供应商、唯一 API Root 和公共故障域，Channel 承载账号级凭据与调度配置。Provider 地址与
状态独立修改，凭据先检测后恢复，停用和归档按 Route → Channel → Provider 的依赖顺序显式完成。

**优点**

- Provider 与 Channel 的故障域、配置和运营责任清晰。
- 凭据安全与历史解释更可靠。

**缺点**

- 改址、停用和归档在存在依赖时需要确认或分步处理。

## 决策

- Admin 使用 Provider → Channel 两层模型，不提供独立 Origin 页面、Tab、选择器、API client 或兼容 DTO。
- Provider 创建表单接收唯一 API Root。Provider 列表直接显示 `origin` 和双 revision；详细 breaker、pending、
  generation 与同步状态只在 Provider 详情读取。
- 普通 Provider 编辑只修改名称等资料。地址修改提交 `expected_origin_revision`；服务端因 enabled Channel 返回
  conflict 时，页面展示影响并由用户二次确认后提交 `confirm_enabled_channels=true`。状态修改使用独立
  `expected_status_revision`。
- Channel 表单只选择 Provider。只有 enabled Provider 下的 Channel 才能启用；disabled Provider 下只能保存
  disabled Channel；archived Provider 禁止配置 Channel。
- 凭据真实变化时先保存新值并暂停 Channel；只有绑定当前 Provider 双 revision 和 Channel revision 的真实
  检测成功才恢复。失败、执行失败或 stale 不恢复，页面分别呈现保存与验证结果。
- Provider 停用、Provider/Channel 归档和 Route 引用冲突均不静默级联、复制或替换。409 提示运营人员按
  Route → Channel → Provider 顺序处理前置条件。
- Provider、Channel 和 Route 的恢复结果为 disabled；历史请求、账务和经营事实继续保留。

本 ADR 仍为 `proposed`，实现与测试结果只作为评审证据，不替代产品负责人批准。

## 影响

### 正面影响

- 运营界面和 Gateway 以一致的两层模型解释上游故障域。
- 凭据检测结果不会被旧配置或并发轮换覆盖。
- 归档不破坏历史请求、账务和经营统计。

### 负面影响

- 新凭据正确时也有短暂不可路由窗口。
- 改址、归档和恢复需要额外确认、解除引用和重新启用操作。

### 中性影响或后续工作

- Provider 双 revision、运行态围栏和自动检测继续由 Gateway 提供事实。
- 删除与历史数据保留策略属于独立的合规与数据生命周期决策。

## 风险与缓解措施

| 风险 | 缓解措施 | 负责人 |
| --- | --- | --- |
| 新凭据错误影响客户 | 检测前保持不可路由，检测使用独立有界执行 | 管理后台团队、网关团队 |
| 迟到检测覆盖较新配置 | 用当前配置版本核验；stale 只记录历史 | 网关团队 |
| 归档线路导致 Key 无路由 | 归档前迁移绑定 Key，并在页面给出影响提示 | 管理后台团队 |
| 旧 Origin 实体回流 | 合同测试和 E2E 禁止旧路由、字段、页面与选择器 | 管理后台团队 |
| 409 被客户端静默处理 | 明示依赖顺序；只有改址具有用户确认后的第二次请求 | 管理后台团队 |

## 落地与验证

Provider 列表、详情、地址 revision 冲突与 enabled Channel 二次确认、Channel 状态限制、409 依赖提示、凭据
检测和运行态 DTO 已通过 Admin 单元、合同、lint、构建与 E2E 验证。Gateway 合同保证旧 Origin API 不存在、
归档保留历史且恢复为 disabled。

## 来源谱系

| 原 DEC | 原始日期 | 原状态 | 当前处理与修订关系 |
| --- | --- | --- | --- |
| DEC-037 | 2026-07-21 | accepted，来源标注待实现 | 原本无效凭据轮换后的即时真实检测；由 DEC-039 扩展。 |
| DEC-039 | 2026-07-21 | accepted，来源标注待实现 | 当前凭据真实变化时先暂停、检测成功且版本匹配才恢复；修订并补充 DEC-037。 |
| DEC-052 | 2026-07-23 | accepted，来源称已实现 | 仅保留 Provider 列表呈现供给摘要的目标；独立 Origin 行级创建入口被当前两层模型取代。 |
| `PLAN-archive-lifecycle-2026-07`（非 DEC） | 2026-07 | 已定方案 | 保留历史与恢复为 disabled；级联、替代和 Origin 生命周期由 ADR-0012 修订。 |

## 取代关系

- 取代：无 Blueprint ADR。
- 被取代：无。

## 参考资料

- [Gateway ADR-0012：Provider、Channel 与 Route 供给生命周期](../../gateway/decisions/adr-0012-provider-channel-route-lifecycle.md)
- [运营管理](../features/operations-management.md)
- [Provider 与 Channel 管理](../pages/provider-channel-management.md)
