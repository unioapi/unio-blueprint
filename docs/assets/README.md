---
title: Assets（共享资源）
description: UnioAPI 跨领域视觉资源的所有权与存放规则。
status: active
owner: 设计团队
last_updated: 2026-07-21
related:
  - ../README.md
  - ../specifications/colors.md
  - ../specifications/icons.md
---

# Assets（共享资源）

## 目的

存放由多个 UnioAPI 产品领域共同使用的权威视觉源文件和渲染结果。

## 范围

共享 Logo、图标、架构图、Mermaid、Excalidraw 和图片。

## 职责

- 需要后续编辑时，同时保留源文件与渲染结果。
- 记录资源所有者、来源、授权方式和用途。
- 使用描述性的小写 kebab-case 文件名。
- 在引用资源的文档附近提供替代文字或图示说明。

## 适合存放的内容

- 多个产品使用的品牌资源。
- 平台级架构图。
- 只应存在一个权威版本的共享视觉源文件。

## 不应存放的内容

- 只属于单一产品的资源；这类内容放入对应领域的 `assets/`。
- 构建生成文件或优化后的应用资源包。
- 未经授权的第三方媒体或没有说明的截图。

## 新增资源

如果仅靠引用文档无法理解资源的所有权、授权、变体或用法，应增加配套 Markdown
说明。通过链接引用资源，不要复制到多个领域。
