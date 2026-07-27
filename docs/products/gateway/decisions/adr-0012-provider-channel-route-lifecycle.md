---
title: "ADR-0012：Provider、Channel 与 Route 供给生命周期"
description: "定义 Origin 并入 Provider 后的供给关系、状态不变量以及编辑、启停、归档与恢复规则。"
status: proposed
owner: 网关团队
last_updated: 2026-07-27
related:
  - ../features/data-lifecycle.md
  - ../features/admission-control.md
  - ../features/routing-load-balancing.md
  - adr-0001-domain-terminology.md
  - adr-0008-runtime-state-fencing.md
  - adr-0010-upstream-breaker-attribution.md
  - ../../admin/decisions/adr-0002-provider-origin-management.md
  - ../../../templates/adr.md
---

# ADR-0012：Provider、Channel 与 Route 供给生命周期

## 背景

Gateway 当前使用 Provider、Provider Origin、Channel 与 Route 表达上游供给。目标改造把唯一上游根地址
`origin`、公共故障域和两条运行 revision 合并到 Provider，删除独立 Provider Origin 实体。合并后需要重新
明确 Provider、Channel 与 Route 的关系，以及三者编辑、启停、归档和恢复时是否影响其他实体。

当前实现事实仍以[数据生命周期](../features/data-lifecycle.md)为准；本 ADR 在被接受并完成实现验证前只记录
目标决策，不能用来宣称改造已经交付。

## 决策驱动因素

- 管理状态必须直接表达实体是否可用，避免 Channel 显示 `enabled`、实际却被 Provider 遮蔽。
- 停用应当是可逆的临时开关，不应静默改写下级状态或拓扑关系。
- 归档应当显式处理引用并保留历史，不应通过级联或自动替换隐藏影响范围。
- Route 的客户产品职责、Channel 的具体供给职责与 Provider 的上游总闸职责必须分离。

## 备选方案

### 方案：父级状态遮蔽子级状态

允许 Provider 停用时保留下属 `enabled` Channel，由路由在运行时叠加父子状态计算有效状态。

**优点**

- 停用和恢复 Provider 的操作步骤较少。

**缺点**

- Channel 的管理状态不能直接说明其是否可用，Admin 必须额外解释有效状态。
- 状态检查容易在路由、运行态同步和运营页面之间产生不同口径。

### 方案：显式状态不变量与分步生命周期（选中）

Provider 是上游总闸，Channel 是具体供给单元，Route 是面向客户的显式 Channel 池。状态转换必须保持父子
状态不变量；停用保留关系，归档前显式解除引用。

**优点**

- 每行状态含义直接、可检查，管理和路由口径一致。
- 所有影响拓扑或客户绑定的操作都可见，不存在静默级联。

**缺点**

- 停用或恢复一组供给时需要按依赖顺序执行多个操作。

## 决策

### 关系与路由资格

请求的供给链路为 `API Key → Route → Channel → Provider → 上游`：

- API Key 显式绑定一条 Route。
- Route 与 Channel 是多对多关系；Route 通过显式渠道池选择 Channel。
- 每个 Channel 恰好归属一个 Provider；Provider 与 Route 没有直接绑定。
- 每个 Provider 恰好保存一个 `origin`，不再存在独立 Provider Origin 实体。
- Channel 成为候选至少要求 Route、Channel、Provider 都为 `enabled`，且 Channel 仍在该 Route 渠道池中。

### 状态不变量

- `Channel.status = enabled` 蕴含 `Provider.status = enabled`。
- `route_channels` 可以保留 `disabled` Channel，但不得引用 `archived` Channel。
- `archived` Provider 下不得存在非归档 Channel。
- `disabled` 表示临时停止服务并保留配置和关系；`archived` 表示退出日常使用并保留历史。

### 编辑与启停

- Provider 创建时可以提交 `origin`；创建后的普通编辑只修改名称等普通资料，不接收 `origin` 或 `status`。
- 修改 `origin` 与修改 `status` 使用两个独立入口和 revision fence，不改 Channel 或 Route。
- 修改 `origin` 必须提交 `expected_origin_revision`。存在 enabled Channel 时还必须提交
  `confirm_enabled_channels=true`；这是请求内布尔字段，不签发或保存独立 token。服务端在锁定当前事实后
  重新校验 revision 和 enabled Channel。
- 停用 Provider 前必须先停用其下全部 enabled Channel；存在 enabled Channel 时返回 conflict，不自动级联。
- 启用 Provider 不自动启用 Channel。
- Provider 为 `disabled` 时允许创建或编辑 Channel，但 Channel 只能保存为 `disabled`；启用 Channel 必须先启用
  Provider。
- Provider 为 `archived` 时不允许创建、编辑或启用 Channel。
- 停用 Channel 保留其全部 Route 池成员关系；重新启用后可在仍启用的 Route 中恢复候选资格。
- Route 编辑只修改线路配置和显式 Channel 池，不修改 Channel 或 Provider 状态。
- 停用 Route 保留 API Key 绑定和 Channel 池；重新启用后继续使用原关系。

### 归档与恢复

- 归档 Channel 前必须先从全部 Route 池移除；存在任一 Route 引用时返回 conflict，不自动拆线或替换。
- 归档 Provider 前必须先归档其下全部 Channel；存在非归档 Channel 时返回 conflict，不级联归档。
- Provider 仍有未完成的地址或状态变更时拒绝归档；归档流程不自动取消或接管该变更，须先由原操作或恢复
  流程进入终态。
- 归档 Route 前必须先迁移其绑定的 API Key；Route 自身的 Channel 池可以保留。
- Provider、Channel 与 Route 恢复后统一为 `disabled`，均不自动启用。
- 恢复 Provider 不恢复 Channel；恢复 Channel 不重新加入 Route；恢复 Route 不迁回归档时已迁走的 API Key。
- Provider 归档通过在 `origin` 末尾追加与自身 ID 绑定的后缀释放唯一地址；恢复只移除完全匹配当前 ID 的末尾
  后缀。原地址已被其他 Provider 占用时返回 conflict，不自动生成或改写地址。

### 在途请求

- Channel 或 Provider 归档提交后立即阻止新请求进入，但已经取得 permit 或已经开始 transport 的请求继续完成
  响应、usage、结算和资源收口。
- 归档可以立即清理 breaker、cooldown、permission 和新的准入 control，但不得立即删除在途 permit、Channel
  并发租约及 RPM/RPD/TPM 桶；这些资源由 `Finish` / `Abort` 收口，异常残留由 TTL 回收。
- 在途结果对已归档实体的 breaker 或 TTFT 更新应成为 stale/no-op；资源释放必须先于该结果判断完成。

## 影响

### 正面影响

- Provider、Channel 与 Route 的状态可以直接解释，不需要额外的父级有效状态标签。
- 供给停用、下线和恢复的影响范围可预测、可审计。
- Route 池可以在 Channel 临时维护期间保持稳定，避免把停用误当成拓扑删除。

### 负面影响

- 停用 Provider 需要先停用 Channel；恢复供给需要先启用 Provider，再显式启用 Channel。
- 归档操作需要调用方按 Route、Channel、Provider 的引用顺序完成多个步骤。

### 中性影响或后续工作

- Admin 需要按 conflict 返回引导正确的前置操作，但不能替代用户静默执行级联。
- Origin 并入 Provider 后的围栏、breaker 与运行态恢复由相关 superseding ADR 继续定义。
- 当前 active 功能文档只能在 Schema、代码和测试完成后改写为新实现事实。
- Gateway 与 Admin 在独立仓库完成并分别验证，作为同一发布批次切换；两边完成后最后回写 Blueprint 当前事实。

## 风险与缓解措施

| 风险 | 缓解措施 | 负责人 |
| --- | --- | --- |
| 部分入口绕过状态不变量 | 在 service 与数据库可表达的约束中共同校验，并覆盖创建、编辑、启停、归档和恢复测试 | 网关团队 |
| 多步操作中途停止 | 每一步保持合法终态，Admin 展示剩余前置条件并允许安全重试 | 网关团队、管理后台团队 |
| Route 池保留 disabled Channel 被误认为可用 | 路由继续按三层 `enabled` 条件过滤，Admin 分开展示池成员与当前候选资格 | 网关团队、管理后台团队 |
| 归档清理破坏在途请求收口 | 区分立即清理状态与 permit 绑定资源，并用长流和异常 TTL 场景验证 | 网关团队 |

## 落地与验证

- 先完成 Origin 并入 Provider 的 Schema、Gateway、Admin 与运行态改造，再更新 active 功能文档。
- 合同测试覆盖非法状态转换的 conflict，以及所有操作均不发生静默级联。
- 集成测试证明 Route 停用保留绑定和池、Channel 停用保留池、三类恢复都落入 `disabled`。
- 归档测试证明引用必须显式解除，未完成 Provider 变更会阻止归档，历史事实仍可读取。
- 长流与异常测试证明归档后不再接收新请求，同时已开始请求仍能完成资源、usage 和结算收口。
- Gateway 与 Admin 完成实现和各自验证后，最后更新 Blueprint active 功能文档；三个仓库分别正常提交和推送，
  不创建 PR。

## 取代关系

- 取代：实现并接受后，取代 [ADR-0001](adr-0001-domain-terminology.md) 中 Provider Origin 领域模型部分；
  Provider 围栏和 breaker 部分的取代关系由对应后续 ADR 明确。
- 被取代：无。

## 参考资料

- [数据生命周期](../features/data-lifecycle.md)
- [准入控制](../features/admission-control.md)
- [路由负载均衡](../features/routing-load-balancing.md)
- [Admin ADR-0002：Provider Origin 与供给管理](../../admin/decisions/adr-0002-provider-origin-management.md)
