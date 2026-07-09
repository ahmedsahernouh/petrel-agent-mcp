#!/usr/bin/env python3
"""Validate minimal Google OKF v0.1 rules for the Petrel Markdown bundle."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except Exception:
    yaml = None


FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


def parse_frontmatter(text: str) -> dict[str, object] | None:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None
    raw = match.group(1)
    if yaml is not None:
        data = yaml.safe_load(raw) or {}
        return data if isinstance(data, dict) else {}
    data: dict[str, object] = {}
    for line in raw.splitlines():
        if ":" not in line or line.startswith((" ", "\t", "-")):
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def has_frontmatter(text: str) -> bool:
    return FRONTMATTER_RE.match(text) is not None


def validate_bundle(bundle_root: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    root_index = bundle_root / "index.md"
    root_log = bundle_root / "log.md"

    if not root_index.exists():
        warnings.append("missing root index.md")
    else:
        meta = parse_frontmatter(root_index.read_text(encoding="utf-8", errors="replace"))
        if meta is None:
            warnings.append("root index.md does not declare okf_version")
        elif str(meta.get("okf_version", "")).strip() != "0.1":
            warnings.append("root index.md frontmatter does not declare okf_version: \"0.1\"")

    if not root_log.exists():
        warnings.append("missing root log.md")

    for path in sorted(bundle_root.rglob("*.md")):
        rel = path.relative_to(bundle_root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.name == "index.md":
            if path != root_index and has_frontmatter(text):
                errors.append(f"{rel}: non-root index.md must not have frontmatter")
            continue
        if path.name == "log.md":
            if has_frontmatter(text):
                errors.append(f"{rel}: log.md must not have frontmatter")
            if not re.search(r"(?m)^##\s+\d{4}-\d{2}-\d{2}\b", text):
                warnings.append(f"{rel}: no ISO date heading found")
            continue
        meta = parse_frontmatter(text)
        if meta is None:
            errors.append(f"{rel}: missing parseable YAML frontmatter")
            continue
        if not str(meta.get("type", "")).strip():
            errors.append(f"{rel}: missing non-empty type field")
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate minimal OKF v0.1 bundle conformance.")
    parser.add_argument(
        "bundle_root",
        nargs="?",
        default=str(Path(__file__).resolve().parents[1] / "vault" / "Petrel Knowledge Wiki"),
        help="Path to the OKF bundle root directory.",
    )
    args = parser.parse_args()
    bundle_root = Path(args.bundle_root).expanduser().resolve()
    if not bundle_root.exists() or not bundle_root.is_dir():
        print(f"Bundle root does not exist or is not a directory: {bundle_root}", file=sys.stderr)
        return 2
    errors, warnings = validate_bundle(bundle_root)
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        print(f"OKF validation failed: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"OKF validation passed: {bundle_root} ({len(warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
