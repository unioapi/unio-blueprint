---
title: AI 协作规则
description: AI 工具参与维护 UnioAPI 蓝图时必须遵守的仓库规则。
status: active
owner: 平台团队
last_updated: 2026-07-21
related:
  - README.md
  - CONTRIBUTING.md
  - docs/specifications/documentation.md
---

# AI 协作规则

## 工作规则

1. 编辑目录前先阅读距离最近的 `README.md`。
2. 新建文档前先搜索已有的权威位置。
3. 严格区分架构依据、共享规范、产品领域知识和具体实现细节。
4. 不得从占位文档推断已经确定的产品行为。
5. 新建文档时使用 `docs/templates/` 中的对应模板。
6. 使用相对 Markdown 链接指向相关权威文档。
7. 保持所有文档的 Front Matter 合法且完整。
8. 不得添加密钥、生产数据、生成产物，或从实现仓库复制大段源码。
9. 默认使用简体中文撰写正文；只有产品专名、路径、字段和代码标识符保留英文。

## 变更范围

优先进行能够建立单一权威来源的最小变更。请求与已接受决策冲突时，必须明确指出
冲突，不能静默改写历史。
