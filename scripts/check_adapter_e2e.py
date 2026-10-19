#!/usr/bin/env python3
"""CI rule: every production adapter declares real-component end-to-end tests.

An adapter is any non-Protocol class under proofrail/ or integrations/ that
defines execute() or observe(). Each must appear in tests/adapter_e2e_registry.json
with a named real component and at least one test that exists and references
the adapter, or be explicitly excluded with a reason. A new adapter with no
declaration fails CI.

Static checks cannot prove a test exercises the real component; the registry
makes the claim explicit and reviewable, and keeps the test it names alive.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "tests" / "adapter_e2e_registry.json"
SOURCE_DIRS = ("proofrail", "integrations")
ADAPTER_METHODS = {"execute", "observe"}


def discover_adapters(root: Path = ROOT) -> set[str]:
    found = set()
    for directory in SOURCE_DIRS:
        for path in sorted((root / directory).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if not isinstance(node, ast.ClassDef):
                    continue
                bases = {ast.unparse(base) for base in node.bases}
                if any(base.split(".")[-1] == "Protocol" for base in bases):
                    continue
                methods = {item.name for item in node.body if isinstance(item, ast.FunctionDef)}
                if methods & ADAPTER_METHODS:
                    found.add(f"{path.relative_to(root).as_posix()}:{node.name}")
    return found


def _test_exists(root: Path, test_id: str) -> str | None:
    """Return an error string, or None if file::Class::method exists."""
    try:
        file_part, class_name, method = test_id.split("::")
    except ValueError:
        return f"malformed test id {test_id!r} (want file::Class::method)"
    path = root / file_part
    if not path.is_file():
        return f"test file missing: {file_part}"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            if any(isinstance(m, ast.FunctionDef) and m.name == method for m in node.body):
                return None
            return f"test method missing: {test_id}"
    return f"test class missing: {file_part}::{class_name}"


def check(root: Path = ROOT, registry_path: Path | None = None) -> list[str]:
    registry = json.loads((registry_path or root / "tests" / "adapter_e2e_registry.json").read_text())
    declared = registry.get("adapters", {})
    excluded = registry.get("excluded", {})
    errors: list[str] = []
    discovered = discover_adapters(root)
    for adapter in sorted(discovered):
        if adapter in excluded:
            if not str(excluded[adapter]).strip():
                errors.append(f"{adapter}: excluded without a reason")
            continue
        entry = declared.get(adapter)
        if entry is None:
            errors.append(f"{adapter}: undeclared adapter; add real-component end-to-end tests "
                          f"to tests/adapter_e2e_registry.json")
            continue
        if not str(entry.get("real_component", "")).strip():
            errors.append(f"{adapter}: real_component is not named")
        tests = entry.get("tests") or []
        if not tests:
            errors.append(f"{adapter}: no end-to-end tests declared")
        class_name = adapter.split(":")[1]
        for test_id in tests:
            problem = _test_exists(root, test_id)
            if problem:
                errors.append(f"{adapter}: {problem}")
                continue
            if class_name not in (root / test_id.split("::")[0]).read_text(encoding="utf-8"):
                errors.append(f"{adapter}: {test_id.split('::')[0]} never references {class_name}")
    for adapter in sorted(set(declared) | set(excluded)):
        if adapter not in discovered:
            errors.append(f"{adapter}: declared in registry but no longer exists")
    return errors


def main() -> int:
    errors = check()
    if errors:
        print("Adapter end-to-end rule FAILED:", *errors, sep="\n  ", file=sys.stderr)
        return 1
    print(f"Adapter end-to-end rule: {len(discover_adapters())} adapters checked, OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
