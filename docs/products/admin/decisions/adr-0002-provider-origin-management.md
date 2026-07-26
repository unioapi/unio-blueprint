---
title: "ADR-0002：Provider Origin 与供给管理"
description: "以 Provider Origin 管理上游故障域，并采用检测优先的凭据与归档生命周期。"
status: proposed
owner: 管理后台团队
last_updated: 2026-07-25
related:
  - ../overview.md
  - ../glossary.md
  - ../features/operations-management.md
  - ../pages/provider-origin-channel-management.md
  - ../../gateway/decisions/adr-0001-domain-terminology.md
  - ../../../templates/adr.md
---

# ADR-0002：Provider Origin 与供给管理

## 背景

运营人员需要管理供应商、上游地址、账号级 Channel、凭据和下线供给。历史来源将上游根地址称为 `ProviderEndpoint` 或“端点”，但 Blueprint 已接受的 Gateway ADR-0001 将其定义为 Provider Origin；管理后台必须服从该术语。来源同时记录了凭据轮换检测、归档生命周期和 Provider 列表 Origin 摘要的长期行为。

## 决策驱动因素

- 上游根地址必须与供应商身份和账号级 Channel 配置分离，且故障域可解释。
- 未经验证的新凭据不能由客户请求试错。
- 下线供给必须保留历史、账务和路由解释。

## 备选方案

### 方案：将上游地址留在 Channel 并直接启用新凭据

每条 Channel 单独保存根地址，保存凭据后立即参与路由。

**优点**

- 初始配置流程较短。

**缺点**

- 同一故障域会分散，且新凭据可能先影响真实客户请求。

### 方案：Provider Origin 分层、检测优先与归档生命周期（选中）

Provider 表示供应商与记账主体，Provider Origin 表示一个上游根地址和公共故障域，Channel 在 Origin 下承载账号级配置；凭据先检测后恢复，供给通过归档管理。

**优点**

- 故障域、配置和运营责任清晰。
- 凭据安全与历史解释更可靠。

**缺点**

- 凭据轮换会在检测期间暂时摘除 Channel，恢复后可能需要人工重新绑定或启用实体。

## 决策

- Admin 使用 Provider、Provider Origin 和 Channel 三层模型。Provider Origin 是上游 `base_url`/host 与公共故障域，遵循 Gateway ADR-0001，不使用旧 `ProviderEndpoint` 术语。
- Provider 列表直接显示 Provider Origin 业务摘要，并在非归档 Provider 行提供创建入口；列表不逐 Origin 读取运行态。
- 凭据真实变化时，先保存新值并将 Channel 暂停参与新请求；仅对当前版本的真实渠道检测成功才恢复。失败、执行失败或 stale 不恢复，响应安全地区分保存与验证结果。
- Provider、Provider Origin、Channel 和线路使用归档而非常规删除。归档保留历史并使实体不参与新路由；恢复统一为 disabled。线路归档前必须迁移绑定 API Key，硬删除仅适用于已归档且无历史引用的实体。

本 ADR 不把来源中的“已实现”视为已完成的 Blueprint 承诺；实现状态须单独核验。

## 影响

### 正面影响

- 运营界面和 Gateway 以一致术语解释上游故障域。
- 凭据检测结果不会被旧配置或并发轮换覆盖。
- 归档不破坏历史请求、账务和经营统计。

### 负面影响

- 新凭据正确时也有短暂不可路由窗口。
- 归档/恢复需要额外确认、迁移和重新启用操作。

### 中性影响或后续工作

- 配置代际、运行态围栏和自动检测的实现需跨 Admin 与 Gateway 核验。
- 删除与历史数据保留策略属于独立的合规与数据生命周期决策。

## 风险与缓解措施

| 风险 | 缓解措施 | 负责人 |
| --- | --- | --- |
| 新凭据错误影响客户 | 检测前保持不可路由，检测使用独立有界执行 | 管理后台团队、网关团队 |
| 迟到检测覆盖较新配置 | 用当前配置版本核验；stale 只记录历史 | 网关团队 |
| 归档线路导致 Key 无路由 | 归档前迁移绑定 Key，并在页面给出影响提示 | 管理后台团队 |
| 术语回退 | 所有产品文案链接 Gateway ADR-0001 | 管理后台团队 |

## 落地与验证

验证 Provider 列表能展示 Origin 摘要且不产生运行态 N+1；凭据不回显、未验证不路由、stale 不改当前状态；归档保留历史且恢复为 disabled。参照[路线图](../roadmap.md)记录实施核验。

## 来源谱系

| 原 DEC | 原始日期 | 原状态 | 当前处理与修订关系 |
| --- | --- | --- | --- |
| DEC-037 | 2026-07-21 | accepted，来源标注待实现 | 原本无效凭据轮换后的即时真实检测；由 DEC-039 扩展。 |
| DEC-039 | 2026-07-21 | accepted，来源标注待实现 | 当前凭据真实变化时先暂停、检测成功且版本匹配才恢复；修订并补充 DEC-037。 |
| DEC-052 | 2026-07-23 | accepted，来源称已实现 | Provider 列表显示 Origin 摘要与行级创建入口；正文采用 Provider Origin 术语，修订来源旧称。 |
| `PLAN-archive-lifecycle-2026-07`（非 DEC） | 2026-07 | 已定方案 | 归档、恢复、线路绑定迁移与硬删除护栏；实现状态须核验，未记录取代关系。 |

## 取代关系

- 取代：无 Blueprint ADR。
- 被取代：无。

## 参考资料

- [Gateway ADR-0001：统一领域术语](../../gateway/decisions/adr-0001-domain-terminology.md)
- [运营管理](../features/operations-management.md)
- [Provider Origin 与 Channel 管理](../pages/provider-origin-channel-management.md)
