---
title: "ADR-0004：模型能力声明与运行时能力分离"
description: "模型能力声明用于目录发现；真实请求能力由 Channel 协议和代码 Adapter registry 决定。"
status: active
owner: 网关团队
last_updated: 2026-07-27
related:
  - ../overview.md
  - ../features/model-capabilities-catalog.md
  - ../features/provider-adaptation.md
---

# ADR-0004：模型能力声明与运行时能力分离

## 背景

来源决策曾设计模型、渠道和运行证据三层能力体系。DEC-023 移除了 Channel 能力收紧层，
DEC-024 又移除了被动证据自动校正和请求能力闸门。当前代码仍保留能力字典、模型能力声明、
外部模型目录和 Adapter 画像，但这些数据与真实请求的可执行能力不在同一条判定链路中。

## 当前决策

Gateway 将“模型能力声明”和“运行时可执行能力”作为两个相互独立的事实集合：

- 模型能力声明用于 Admin 维护、目录展示和 `/v1/models` capability 筛选。
- 真实生成请求不读取模型能力声明；候选可执行性由 Channel 协议、候选拓扑和当前进程的代码
  Adapter registry 决定。
- 当前不存在 Channel capability override，也不存在从运行结果自动校正模型声明的链路。
- 模型声明与运行时能力可以不一致；capability tag 不是请求准入保证。

## 声明数据边界

### 能力字典

`capability_keys` 是 `model_capabilities.capability_key` 的外键字典，空库迁移当前写入 33 个 key。
每个 key 保存 domain、展示名称、说明、排序、`deprecated` 和 `protocol_scope`。

- `protocol_scope` 只允许 `shared`、`openai` 或 `anthropic`，当前只用于分类。
- `deprecated` 只是元数据；当前声明写入和 `/v1/models` 查询都不会因此拒绝或隐藏 key。
- 修改 scope 不检查或重写已有声明，也不校验模型关联的 Channel 协议。

### 模型能力声明

`model_capabilities` 以 `(model_id, capability_key)` 为主键，保存 `full`、`limited` 或
`unsupported`、可选 `limits`、时间戳和可空的 `updated_by`。表中没有声明来源和协议字段，
因此持久数据不能区分人工、目录采纳、目录刷新或 Adapter 画像写入。

## 当前写入路径

| 写入路径 | 当前行为 |
| --- | --- |
| Admin 模型声明 | HTTP 提供列表和批量 replace-all；批量写入先校验全部条目，再在一个事务内删除旧集合并重写。 |
| 目录采纳 | 在创建本地模型和 catalog link 的同一事务内，写入采纳请求携带的任意字典合法声明；不要求该集合等于目录提示。 |
| 目录刷新 service | 在一个事务内更新目录模型元数据，删除该模型全部声明，再按当前目录提示重写；当前没有注册刷新 HTTP 路由。 |
| Adapter 画像物化 | Admin 可列出并物化当前注册的 DeepSeek OpenAI、DeepSeek Anthropic 两份画像；画像逐 key upsert 并覆盖同 key 声明。 |

Adapter 画像物化没有包裹为一个事务。任一 key 写入失败时函数停止，之前成功的 key 不会回滚，
因此可能形成部分写入。画像本身的校验只检查 provider/protocol 非空、key 非空、支持级别、重复项，
以及非 `limited` 声明不得携带 limits；不校验 limits JSON 是否有效或其对象结构，也不预检数据库字典、
`protocol_scope` 或模型与 Channel 拓扑。字典不存在最终由外键在对应 upsert 时拒绝。

## 客户目录边界

OpenAI-compatible `/v1/models` 在 API Key 绑定 Route 的可见供给中聚合模型声明：

- `full` 和 `limited` 都折叠为同一个 capability tag，`unsupported` 不返回；
- `?capability=` 只读取第一个参数值，把其中逗号分隔的非空 key 按 AND 语义筛选；重复参数的
  后续值被忽略，未知 key 不报错但通常匹配不到模型；
- 响应只返回 capability key，不返回 support level 或 `limits`；
- 查询不读取 `deprecated`、`protocol_scope`、Channel protocol、Provider 状态或代码
  Adapter registry。

因此，一个模型出现在 `/v1/models` 中，只能证明当前目录 SQL 的 Route 供给等可见性条件成立；
模型可以没有任何声明并返回空 tag 数组。某个 tag 出现才额外证明存在一条非 `unsupported` 的模型声明。
两者都不能证明 OpenAI 请求一定存在协议匹配且已注册 Adapter 的候选。

## 运行时边界

真实生成请求按 ingress protocol 查询 Channel，并由代码 Adapter registry 检查 tokenizer、非流式、
流式、Responses 原生处理或 Chat bridge 等 operation capability。协议字段的 Pass、Adapt、Drop 和
Reject 也由具体协议 service 与 Adapter 代码执行。路由、授权、价格和结算均不读取
`model_capabilities`。

代码 Adapter operation capability 与模型 capability tag 是不同概念：前者决定当前进程能否发起
某类上游调用，后者是可由多条管理路径写入的目录声明。

## 当前行为与边界

- 目录声明不进入请求热路径，目录同步或声明变化不会直接改变真实请求准入。
- 多条写入路径共享同一无来源表，无法从存量行追溯写入类型。
- Adapter 画像可覆盖既有声明，且中途失败可留下部分画像。
- `protocol_scope` 和 `deprecated` 没有执行语义，跨 scope 声明可以保存并出现在客户目录。
- `/v1/models` 的目录可见性与真实请求候选可执行性可能不同。

## 代码与测试证据

当前代码、Schema 和测试覆盖以下事实：能力字典和声明表；Admin 已注册的字典、
replace-all、目录采纳和画像物化入口；目录刷新 service 的未注册状态；`/v1/models` 的 SQL 聚合与
AND 筛选；真实请求使用 Channel protocol 和代码 Adapter registry，而不读取模型声明。

## 来源谱系

| 原 DEC | 原始日期 | 原状态 | 当前迁移处理 |
| --- | --- | --- | --- |
| DEC-015 | 未记录；2026-06-23 部分取代 | 部分 superseded | 保留外部目录、模型级声明和代码 Adapter 画像；三层能力架构、运行时能力闸门和 Channel 收紧不作为当前事实。 |
| DEC-020 | 未记录；2026-06-23 取代 | superseded by DEC-024 | 仅保留历史：当前没有被动证据自动校正。 |
| DEC-022 | 未记录；2026-06-23 取代 | superseded by DEC-024 | 仅保留历史：当前没有能力证据闭环。 |
| DEC-023 | 未记录 | implemented | 保留当前事实：没有 Channel capability override 或渠道能力收紧层。 |
| DEC-024 | 2026-06-23 | accepted，来源标注待实施 | 保留已实现的能力字典、模型声明、移除自动校正和移除请求能力闸门；“只由人工写入”与当前多写入路径不符，不迁为现状。 |

## 取代关系

- 取代：无 Blueprint ADR。
- 被取代：无。

## 参考资料

- [模型能力与目录](../features/model-capabilities-catalog.md)
- [Provider 适配](../features/provider-adaptation.md)
