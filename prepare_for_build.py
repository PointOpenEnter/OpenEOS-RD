"""Prepare a portable copy of OpenEOS for PyInstaller build."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    if not args.source.is_file():
        print(f"ERROR: source file not found: {args.source}")
        return 2

    # OpenEOS source already includes built-in standalone portability,
    # the ExifTool strict.pm fix, and the modern macOS interface.
    text = args.source.read_text(encoding="utf-8-sig")
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text(text, encoding="utf-8", newline="\n")
    print(f"Portable build source prepared: {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
