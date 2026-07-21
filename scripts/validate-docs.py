#!/usr/bin/env python3
"""校验 UnioAPI 蓝图的结构约定。"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
EXCLUDED_PARTS = {".git", ".claudian", ".obsidian"}
REQUIRED_FIELDS = {
    "title",
    "description",
    "status",
    "owner",
    "last_updated",
    "related",
}
VALID_STATUSES = {
    "draft",
    "proposed",
    "active",
    "deprecated",
    "superseded",
    "archived",
}
README_SECTIONS = (
    "## 目的",
    "## 范围",
    "## 职责",
    "## 适合存放的内容",
    "## 不应存放的内容",
)
TOP_LEVEL_DOC_DIRECTORIES = {
    "architecture",
    "specifications",
    "website",
    "docs-site",
    "console",
    "admin",
    "gateway",
    "sdk",
    "roadmap",
    "decisions",
    "templates",
    "assets",
}
PRODUCT_DOMAINS = ("website", "docs-site", "console", "admin", "gateway", "sdk")
DOMAIN_PATHS = {
    "README.md",
    "overview.md",
    "roadmap.md",
    "glossary.md",
    "quality.md",
    "decisions/README.md",
    "pages/README.md",
    "diagrams/README.md",
    "assets/README.md",
}
KEBAB_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FIELD = re.compile(r"^([a-z][a-z0-9_]*):(?:\s*(.*))$")
LOCAL_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def is_included(path: Path) -> bool:
    return not EXCLUDED_PARTS.intersection(path.relative_to(ROOT).parts)


def display(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def unquote_yaml(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_front_matter(path: Path, errors: list[str]) -> tuple[dict[str, str], list[str], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        errors.append(f"{display(path)}：缺少 YAML Front Matter 起始分隔符")
        return {}, [], text

    try:
        end = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        errors.append(f"{display(path)}：缺少 YAML Front Matter 结束分隔符")
        return {}, [], text

    fields: dict[str, str] = {}
    related: list[str] = []
    current_field = ""
    for line in lines[1:end]:
        match = FIELD.match(line)
        if match:
            current_field = match.group(1)
            if current_field in fields:
                errors.append(f"{display(path)}：Front Matter 字段 '{current_field}' 重复")
            fields[current_field] = match.group(2).strip()
            continue
        if current_field == "related" and re.match(r"^\s+-\s+", line):
            related.append(unquote_yaml(re.sub(r"^\s+-\s+", "", line).strip()))

    missing = REQUIRED_FIELDS - fields.keys()
    for name in sorted(missing):
        errors.append(f"{display(path)}：缺少 Front Matter 字段 '{name}'")

    for name in REQUIRED_FIELDS - {"related"}:
        if name in fields and not unquote_yaml(fields[name]):
            errors.append(f"{display(path)}：Front Matter 字段 '{name}' 不能为空")

    if "status" in fields:
        status = unquote_yaml(fields["status"])
        if status not in VALID_STATUSES:
            errors.append(f"{display(path)}：不支持的状态值 '{status}'")

    if "last_updated" in fields:
        updated = unquote_yaml(fields["last_updated"])
        if updated != "YYYY-MM-DD" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", updated):
            errors.append(f"{display(path)}：last_updated 必须使用 YYYY-MM-DD 格式")

    if "related" in fields:
        inline_related = fields["related"]
        if inline_related == "[]":
            if related:
                errors.append(f"{display(path)}：related 不能同时使用空列表和列表项")
        elif inline_related:
            errors.append(f"{display(path)}：related 必须是缩进的 YAML 列表或 []")

    return fields, related, text


def validate_related(path: Path, related: list[str], errors: list[str]) -> None:
    for target in related:
        if not target:
            errors.append(f"{display(path)}：related 包含空项目")
            continue
        if "://" in target or target.startswith(("mailto:", "#")):
            errors.append(f"{display(path)}：related 只能包含仓库相对路径：{target}")
            continue
        clean_target = unquote(target.split("#", 1)[0])
        resolved = (path.parent / clean_target).resolve()
        if not resolved.is_relative_to(ROOT) or not resolved.exists():
            errors.append(f"{display(path)}：related 目标不存在：{target}")


def without_fenced_code(text: str) -> str:
    lines: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append(line)
    return "\n".join(lines)


def validate_markdown_links(path: Path, text: str, errors: list[str]) -> None:
    for match in LOCAL_LINK.finditer(without_fenced_code(text)):
        target = match.group(1).strip()
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1]
        target = target.split(" ", 1)[0]
        clean_target = unquote(target.split("#", 1)[0])
        if not clean_target:
            continue
        resolved = (path.parent / clean_target).resolve()
        if not resolved.is_relative_to(ROOT) or not resolved.exists():
            errors.append(f"{display(path)}：本地 Markdown 链接不存在：{target}")


def validate_names(errors: list[str]) -> None:
    for path in sorted(DOCS.rglob("*")):
        if path.is_dir():
            if not KEBAB_NAME.fullmatch(path.name):
                errors.append(f"{display(path)}：目录名不是小写 kebab-case")
            continue
        if path.name == "README.md":
            continue
        if not KEBAB_NAME.fullmatch(path.stem):
            errors.append(f"{display(path)}：文件名不是小写 kebab-case")


def validate_directories(errors: list[str]) -> None:
    actual = {path.name for path in DOCS.iterdir() if path.is_dir()}
    for name in sorted(TOP_LEVEL_DOC_DIRECTORIES - actual):
        errors.append(f"docs/{name}：缺少规定的顶级目录")

    for directory in [DOCS, *sorted(path for path in DOCS.rglob("*") if path.is_dir())]:
        readme = directory / "README.md"
        if not readme.is_file():
            errors.append(f"{display(directory)}：目录缺少 README.md")
            continue
        text = readme.read_text(encoding="utf-8")
        for heading in README_SECTIONS:
            if heading not in text:
                errors.append(f"{display(readme)}：缺少规定章节 '{heading}'")

    for domain in PRODUCT_DOMAINS:
        domain_root = DOCS / domain
        actual_paths = {
            path.relative_to(domain_root).as_posix()
            for path in domain_root.rglob("*.md")
        }
        for missing in sorted(DOMAIN_PATHS - actual_paths):
            errors.append(f"docs/{domain}/{missing}：缺少规定的领域文档")


def main() -> int:
    errors: list[str] = []
    markdown_files = sorted(path for path in ROOT.rglob("*.md") if is_included(path))

    validate_directories(errors)
    validate_names(errors)

    for path in markdown_files:
        _, related, content = parse_front_matter(path, errors)
        validate_related(path, related, errors)
        validate_markdown_links(path, content, errors)

    if errors:
        for error in errors:
            print(f"错误：{error}")
        print(f"\n校验失败，共 {len(errors)} 个错误。")
        return 1

    directory_count = sum(1 for path in DOCS.rglob("*") if path.is_dir()) + 1
    print(
        f"校验通过：{len(markdown_files)} 个 Markdown 文件，"
        f"覆盖 {directory_count} 个文档目录。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
