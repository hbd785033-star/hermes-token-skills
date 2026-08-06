#!/usr/bin/env python3
"""Validate the structure and metadata of skills in this repository."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import yaml


NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", re.DOTALL)
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
SUPPORT_PATH_RE = re.compile(
    r"`((?:references|templates|scripts|assets)/[A-Za-z0-9._/-]+)`"
)
REQUIRED_FIELDS = ("name", "description", "version", "author", "license", "metadata")


@dataclass
class Skill:
    path: Path
    data: dict[str, Any]


def parse_frontmatter(path: Path, errors: list[str]) -> Skill | None:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"{path}: cannot read UTF-8 text: {exc}")
        return None

    if len(content) > 100_000:
        errors.append(f"{path}: file exceeds 100,000 characters")

    match = FRONTMATTER_RE.match(content)
    if not match:
        errors.append(f"{path}: expected frontmatter at byte 0 and a non-empty body")
        return None
    if not match.group(2).strip():
        errors.append(f"{path}: body must not be empty")

    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        errors.append(f"{path}: invalid YAML frontmatter: {exc}")
        return None
    if not isinstance(data, dict):
        errors.append(f"{path}: frontmatter must be a YAML mapping")
        return None

    for field in REQUIRED_FIELDS:
        if field not in data or data[field] in (None, ""):
            errors.append(f"{path}: missing required frontmatter field '{field}'")

    name = data.get("name")
    if not isinstance(name, str) or not NAME_RE.fullmatch(name) or len(name) > 64:
        errors.append(f"{path}: name must be kebab-case and at most 64 characters")
    elif path.parent.name != name:
        errors.append(f"{path}: directory name must match frontmatter name '{name}'")

    description = data.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append(f"{path}: description must be a non-empty string")
    elif len(description) > 60:
        errors.append(f"{path}: description exceeds 60 characters for the compact skill index")

    hermes = data.get("metadata", {}).get("hermes") if isinstance(data.get("metadata"), dict) else None
    if not isinstance(hermes, dict):
        errors.append(f"{path}: metadata.hermes must be a mapping")
    else:
        if not isinstance(hermes.get("tags"), list) or not hermes["tags"]:
            errors.append(f"{path}: metadata.hermes.tags must be a non-empty list")
        if not isinstance(hermes.get("related_skills"), list):
            errors.append(f"{path}: metadata.hermes.related_skills must be a list")

    return Skill(path=path, data=data)


def declared_external_skills(readme: Path, errors: list[str]) -> set[str]:
    if not readme.is_file():
        errors.append(f"{readme}: required for external related_skills declarations")
        return set()
    text = readme.read_text(encoding="utf-8")
    match = re.search(
        r"^## External `related_skills`\s*$\n(.*?)(?=^##\s|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        errors.append(f"{readme}: missing '## External `related_skills`' section")
        return set()
    return set(re.findall(r"`([a-z0-9]+(?:-[a-z0-9]+)*)`", match.group(1)))


def validate_directory_names(root: Path, paths: list[Path], errors: list[str]) -> None:
    checked: set[Path] = set()
    for skill_path in paths:
        relative_parts = skill_path.parent.relative_to(root).parts
        for index, part in enumerate(relative_parts):
            directory = root.joinpath(*relative_parts[: index + 1])
            if directory in checked:
                continue
            if not NAME_RE.fullmatch(part):
                errors.append(f"{directory}: directory names must use lowercase kebab-case")
            checked.add(directory)


def local_reference_targets(markdown: Path, skill_root: Path) -> set[Path]:
    text = markdown.read_text(encoding="utf-8")
    targets: set[Path] = set()
    for raw in MARKDOWN_LINK_RE.findall(text):
        target = raw.strip().split(maxsplit=1)[0].strip("<>")
        target = unquote(target.split("#", 1)[0])
        if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
            continue
        targets.add((markdown.parent / target).resolve())
    for target in SUPPORT_PATH_RE.findall(text):
        targets.add((skill_root / target).resolve())
    return targets


def validate_references(skill: Skill, errors: list[str]) -> None:
    skill_root = skill.path.parent
    for markdown in skill_root.rglob("*.md"):
        for target in sorted(local_reference_targets(markdown, skill_root)):
            if not target.exists():
                errors.append(f"{markdown}: referenced file does not exist: {target}")


def validate(root: Path) -> tuple[list[str], int]:
    root = root.resolve()
    errors: list[str] = []
    skill_paths = sorted(root.rglob("SKILL.md"))
    if not skill_paths:
        errors.append(f"{root}: no SKILL.md files found")
        return errors, 0

    validate_directory_names(root, skill_paths, errors)
    skills = [skill for path in skill_paths if (skill := parse_frontmatter(path, errors))]
    local_names = {
        skill.data["name"]
        for skill in skills
        if isinstance(skill.data.get("name"), str)
    }
    external_names = declared_external_skills(root / "README.md", errors)

    for skill in skills:
        hermes = skill.data.get("metadata", {}).get("hermes", {})
        related = hermes.get("related_skills", []) if isinstance(hermes, dict) else []
        if isinstance(related, list):
            for name in related:
                if not isinstance(name, str):
                    errors.append(f"{skill.path}: related_skills entries must be strings")
                elif name not in local_names and name not in external_names:
                    errors.append(
                        f"{skill.path}: external related_skill '{name}' is not declared in README.md"
                    )
        validate_references(skill, errors)

    return errors, len(skills)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to the parent of scripts/)",
    )
    args = parser.parse_args()
    errors, count = validate(args.root)
    if errors:
        print(f"Validation failed with {len(errors)} error(s):")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Validated {count} skill(s): OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
