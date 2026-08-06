---
title: 运营管理
description: 管理后台对供给、凭据、检测和归档生命周期的受控运营设计。
status: draft
owner: 管理后台团队
last_updated: 2026-08-06
related:
  - ../overview.md
  - ../glossary.md
  - ../quality.md
  - ../pages/provider-channel-management.md
  - ../decisions/adr-0002-provider-origin-management.md
---

# 功能设计：运营管理

## 摘要

运营管理让内部运营人员安全维护 Provider、Channel 和 Route：Provider 内嵌唯一 API Root 与独立运行
revision，Channel 承载账号级配置和凭据；Provider 还拥有只用于内部观察的 USD 余额和不可变账本。配置可变更、
凭据可轮换并检测、不再使用的实体可归档，同时不破坏客户路由边界和历史解释。

## 用户与任务

| 用户 | 任务 | 当前问题 |
| --- | --- | --- |
| 运营人员 | 创建和维护 Provider 与 Channel | Provider 的唯一地址、公共故障域和账号级配置必须清晰分层。 |
| 运营人员 | 轮换凭据并确认新配置可用 | 不能让真实客户请求承担未验证凭据的试错。 |
| 运营人员 | 下线或恢复供给 | 必须保留历史请求和账务关联，并防止恢复后意外进入路由。 |

## 目标

- 使用 Provider 的 `origin` 作为唯一上游根地址和公共故障域，不恢复独立 Origin 实体。
- 将凭据保存、真实检测和恢复可路由状态组织为一个受控工作流。
- 用归档替代常规删除，保留历史事实并明确恢复后的操作。
- 允许运营人员调整 Provider 内部余额并查看与请求关联的成本流水，但不把它当作上游真实余额或路由闸门。

## 非目标

- 把 Channel 凭据、上游正文或内部错误详情展示给运营人员。
- 将模型能力声明、渠道 override 或历史健康分桶作为路由闸门。
- 在 Admin 中重新实现 Gateway 的候选选择、熔断或结算。

## 使用体验

1. 运营人员在 Provider 列表查看唯一 API Root、地址 revision、状态 revision 和供给规模。
2. 在 Provider 下管理 Channel；Channel 保存协议、适配器、凭据、模型绑定及账号级运行配置。
3. 运营人员可手动触发渠道检测。检测向真实上游发最小请求，并清楚区分连通性、凭据、模型、协议、限额和超时等结果。
4. 轮换凭据时，系统持久化新值并暂时使该 Channel 不可参与新请求；仅当前配置版本的检测成功才恢复。检测失败、执行失败或 stale 结果保留不可路由状态。
5. 运营人员将不再使用的 Provider、Channel 或 Route 归档；遇到依赖冲突时按 Route → Channel → Provider
   处理，需要重新使用时先恢复为 disabled，再显式完成启用和必要的重新绑定。
6. 在 Provider 列表和详情查看当前 USD 余额；低于 10 USD 或为负数时显示明确提醒。详情中可直接填写核对后的
   最终余额，并在账本中查看请求消费、模型探测消费与手工调额。
7. 在 Provider 详情查看待对账成本风险。风险来自无可靠 usage 的失败、断点请求，或已收到 2xx 但 usage 不完整的模型
   探测；它只辅助人工核对，不自动扣余额。最终余额调额提交后，调额前同币种风险标记为已对账。

## 需求

### 功能需求

- Provider 表示供应商、唯一上游根地址和公共故障域；Channel 直接归属于 Provider。
- Provider 列表直接展示规范化 `origin`、`origin_revision` 和 `status_revision`。详细运行态只在详情读取，
  列表不能逐行轮询。
- 普通 Provider 编辑不接收地址或状态。地址和状态各自使用 expected revision；enabled Channel 下改址的
  409 需要运营人员明确二次确认，revision 冲突必须刷新事实后重试。
- 只有 enabled Provider 下的 Channel 才能启用；disabled Provider 下只能保存 disabled Channel；archived
  Provider 下禁止配置 Channel。
- 凭据是只写敏感信息。所有响应、日志和检测记录不得回显明文或密文。
- 凭据发生真实变化时，必须先暂停新配置参与路由，清除旧的当前检测摘要，并立即执行独立、有界的真实检测；同值且当前有效的请求是幂等的，不伪造新的检测成功。
- 检测成功只有在 Provider 双 revision 与 Channel 配置版本仍匹配时才可恢复凭据有效性；迟到结果只可留
  历史，不得覆盖当前状态。
- 归档为可恢复生命周期：归档实体默认不在在用列表显示且不参与新路由；恢复统一落入 `disabled`，必须显式启用。
- Provider 停用遇 enabled Channel 返回 conflict；Provider 归档遇非归档 Channel 或非终态 operation 返回
  conflict。Channel 归档遇任意 Route 池引用返回 conflict；所有动作均不级联、不自动替换。
- Provider、Channel 与 Route 恢复为 disabled，不自动恢复子对象、Route 池或 API Key 绑定。
- 归档线路前必须迁移其绑定 API Key；归档后的硬删除只适用于已归档且无历史引用的实体。
- 归档实体的历史请求、账务和经营统计仍按事实保留；自动渠道检测跳过归档 Channel。
- Provider、Model 和 Route Channel 选择器必须读取服务端分页的全部结果，不得把单页 100 条静默当成全集。
- Provider 余额没有记录时显示“未设置”；状态分为“正常”“余额较低”“负余额”，余额可以为负。
- Provider 账本只允许新增流水：可靠请求成本关联请求、最终 attempt、成本快照、Channel 和上游模型；可靠探测
  成本关联独立探测记录；手工调额不关联请求。调额不记录操作人，由服务端根据最终目标余额计算差额。
- partial estimate、失败 attempt 或已收到 2xx 的探测没有可靠 usage 时不产生自动消费流水，只新增待对账成本风险；
  明确失败的探测只保留探测事实，不新增成本风险。风险中的估算金额不参与余额、路由或经营利润。
- 余额不参与路由、fallback、breaker、Provider/Channel 状态，也不因 403 自动冻结 Provider 或整个 Channel 账号；
  403 继续按精确 Channel-Model permission pause 处理。

### 质量需求

- 检测应与客户请求、客户用量和成功率统计隔离；它可能消耗上游额度，可靠 usage 进入 Provider 账本，但不产生客户账单。
- 凭据轮换的保存、检测和恢复结果必须可审计，并明确区分“已保存”与“已验证”。

## 状态与边界情况

| 状态或条件 | 预期行为 | 恢复方式 |
| --- | --- | --- |
| 新凭据检测成功且版本匹配 | 恢复 Channel 参与新请求 | 记录检测事实。 |
| 检测失败或执行失败 | 新凭据已保存但 Channel 保持不可路由 | 修复配置后手动或周期检测。 |
| 检测结果 stale | 记录历史，不改当前状态或摘要 | 对当前版本重新检测。 |
| Channel 已归档 | 不参与路由和自动检测 | 恢复为 disabled，重新绑定并显式启用。 |
| 线路仍有绑定 API Key | 阻止归档线路，并要求先迁移绑定 | 迁移后重新归档。 |

## 权限、安全与隐私

仅授权内部运营人员可执行管理和检测动作。凭据永不回显；检测和错误提示只提供安全摘要。多管理员的授权模型与操作审计尚待单独决策，不能由当前单一运营入口隐含替代。

## 可观测性

管理操作应留下不含凭据的状态变更和检测事实。页面显示的运行事实及其解释范围见[运营可观测性](operations-observability.md)。

## 发布与迁移

Provider→Channel 管理模型、双 revision、凭据围栏、状态限制、显式归档与页面合同已经过 Admin 和 Gateway
测试核验；后续变化必须同步更新 Gateway 决策与本设计。

## 验收标准

- [x] 页面只使用 Provider→Channel 模型，Provider 表单和详情内嵌唯一 API Root 与双 revision。
- [x] 新凭据在检测成功且版本匹配前不参与新请求，且任何结果不回显凭据。
- [x] 生命周期 409 引导 Route → Channel → Provider，不静默级联或替换。
- [x] 归档与恢复保留历史关联，恢复结果为 disabled。
- [x] 渠道检测结果不污染客户用量、账务或成功率统计。
- [x] Provider、Model 和 Route Channel 选择器不会因单页大小限制而隐藏后续选项。
