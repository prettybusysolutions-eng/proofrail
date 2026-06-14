#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from proofrail.demo import run_github_merge_authority_demo


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="proofrail-demo")
    args = parser.parse_args()
    result = run_github_merge_authority_demo(Path(args.out_dir))
    print(result["transcript"])
    return 0 if result["valid"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
