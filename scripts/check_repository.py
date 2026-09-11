from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".env",
    ".js",
    ".lock",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
BLOCKED = {
    "personal absolute path": re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    "credential-like assignment": re.compile(
        r"(?i)(api[_-]?key|secret|password|bearer[_-]?token)\s*=\s*[\"'][^<][^\"']+[\"']"
    ),
}


def main() -> int:
    failures: list[str] = []
    for path in ROOT.rglob("*"):
        if (
            not path.is_file()
            or ".git" in path.parts
            or ".venv" in path.parts
            or (path.suffix not in TEXT_SUFFIXES and path.name != ".env")
        ):
            continue
        text = path.read_text(encoding="utf-8")
        for label, pattern in BLOCKED.items():
            if pattern.search(text):
                failures.append(f"{path.relative_to(ROOT)}: {label}")
    if failures:
        print("Repository safety check failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print("repository_safety_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
