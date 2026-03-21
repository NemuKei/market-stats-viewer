#!/usr/bin/env python3
"""
Basic validator for repo-local skill folders.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

MAX_SKILL_NAME_LENGTH = 64
ALLOWED_FRONTMATTER_KEYS = {"name", "description", "license", "allowed-tools", "metadata"}


def validate_skill(skill_path: str) -> tuple[bool, str]:
    skill_dir = Path(skill_path)
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return False, "SKILL.md not found"

    content = skill_md.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return False, "No YAML frontmatter found"

    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format"

    frontmatter_text = match.group(1)
    try:
        frontmatter = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as exc:
        return False, f"Invalid YAML in frontmatter: {exc}"

    if not isinstance(frontmatter, dict):
        return False, "Frontmatter must be a YAML dictionary"

    unexpected_keys = set(frontmatter.keys()) - ALLOWED_FRONTMATTER_KEYS
    if unexpected_keys:
        allowed = ", ".join(sorted(ALLOWED_FRONTMATTER_KEYS))
        unexpected = ", ".join(sorted(unexpected_keys))
        return (
            False,
            f"Unexpected key(s) in SKILL.md frontmatter: {unexpected}. Allowed properties are: {allowed}",
        )

    if "name" not in frontmatter:
        return False, "Missing 'name' in frontmatter"
    if "description" not in frontmatter:
        return False, "Missing 'description' in frontmatter"

    name = str(frontmatter.get("name", "")).strip()
    if name:
        if not re.match(r"^[a-z0-9-]+$", name):
            return (
                False,
                f"Name '{name}' should be hyphen-case (lowercase letters, digits, and hyphens only)",
            )
        if name.startswith("-") or name.endswith("-") or "--" in name:
            return (
                False,
                f"Name '{name}' cannot start/end with hyphen or contain consecutive hyphens",
            )
        if len(name) > MAX_SKILL_NAME_LENGTH:
            return (
                False,
                f"Name is too long ({len(name)} characters). Maximum is {MAX_SKILL_NAME_LENGTH} characters.",
            )

    description = str(frontmatter.get("description", "")).strip()
    if "<" in description or ">" in description:
        return False, "Description cannot contain angle brackets (< or >)"
    if len(description) > 1024:
        return (
            False,
            f"Description is too long ({len(description)} characters). Maximum is 1024 characters.",
        )

    return True, "Skill is valid!"


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python quick_validate_skill.py <skill_directory>")
        return 1

    valid, message = validate_skill(sys.argv[1])
    print(message)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
