#!/usr/bin/env python3
"""Compile Python source in memory without creating bytecode files."""
from __future__ import annotations

import argparse
from pathlib import Path


def compile_tree(root: Path) -> list[str]:
    failures = []
    for source in sorted(root.rglob("*.py")):
        try:
            compile(source.read_text(encoding="utf-8"), str(source), "exec")
        except (OSError, SyntaxError, UnicodeError) as exc:
            failures.append(f"{source}: {exc}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("src"))
    args = parser.parse_args()
    if not args.root.is_dir():
        print(f"Source root not found: {args.root}")
        return 2
    failures = compile_tree(args.root)
    if failures:
        print("Source compilation failed:")
        print("\n".join(failures))
        return 1
    print(f"Source compilation passed: {args.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
