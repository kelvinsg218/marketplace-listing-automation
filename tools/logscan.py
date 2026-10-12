"""Compact, deterministic log digest (no LLM).

Prints level counts, then each distinct ERROR/WARNING/CRITICAL line and each
Python traceback once (deduplicated, with occurrence count). Use it instead of
reading whole logs into the conversation.

Usage:
    python tools/logscan.py <file> [--max 30]
    some_command 2>&1 | python tools/logscan.py -
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

LEVEL_RE = re.compile(r"\b(CRITICAL|ERROR|WARNING|WARN|INFO|DEBUG)\b")
TS_RE = re.compile(r"^\S+[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\s*")
INTERESTING = {"CRITICAL", "ERROR", "WARNING", "WARN"}


def digest(lines: list[str], max_items: int = 30) -> str:
    levels: Counter[str] = Counter()
    seen: Counter[str] = Counter()
    first_line: dict[str, int] = {}
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if line.startswith("Traceback (most recent call last)"):
            block = [line]
            i += 1
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                block.append(lines[i].rstrip())
                i += 1
            if i < len(lines):
                block.append(lines[i].rstrip())  # exception line
            key = "\n".join(b for b in block if b)
            levels["TRACEBACK"] += 1
            seen[key] += 1
            first_line.setdefault(key, i + 1)
            i += 1
            continue
        match = LEVEL_RE.search(line)
        if match:
            level = match.group(1)
            levels[level] += 1
            if level in INTERESTING:
                key = TS_RE.sub("", line)
                seen[key] += 1
                first_line.setdefault(key, i + 1)
        i += 1

    out = [f"{len(lines)} linhas | " + ", ".join(f"{k}={v}" for k, v in levels.most_common())]
    items = sorted(seen.items(), key=lambda kv: first_line[kv[0]])
    for key, count in items[:max_items]:
        prefix = f"L{first_line[key]}" + (f" (x{count})" if count > 1 else "")
        out.append(f"{prefix}: {key}")
    if len(items) > max_items:
        out.append(f"... +{len(items) - max_items} ocorrências distintas omitidas")
    if not items:
        out.append("Nenhum ERROR/WARNING/traceback encontrado.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="arquivo de log ou '-' para stdin")
    parser.add_argument("--max", type=int, default=30)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if args.source == "-":
        text = sys.stdin.read()
    else:
        text = Path(args.source).read_text(encoding="utf-8", errors="replace")
    print(digest(text.splitlines(), args.max))
    return 0


if __name__ == "__main__":
    sys.exit(main())
