"""Activate/deactivate project skills to keep the always-loaded context small.

Active skills live in .claude/skills/ (their descriptions are loaded every
session). Dormant skills live in tools/skills-catalog/ and cost nothing.

Usage:
    python tools/skills_catalog.py list
    python tools/skills_catalog.py activate <name>
    python tools/skills_catalog.py deactivate <name>
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACTIVE = ROOT / ".claude" / "skills"
DORMANT = ROOT / "tools" / "skills-catalog"
DESC_RE = re.compile(r"^description:\s*(.+)$", re.MULTILINE)


def _describe(skill_dir: Path) -> str:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    match = DESC_RE.search(text)
    return (match.group(1).strip().strip('"') if match else "")[:110]


def _skills(base: Path) -> list[Path]:
    return sorted(p for p in base.iterdir() if (p / "SKILL.md").exists()) if base.exists() else []


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if not argv or argv[0] == "list":
        for label, base in (("ATIVAS", ACTIVE), ("CATÁLOGO (dormentes)", DORMANT)):
            print(f"{label}:")
            for skill in _skills(base):
                print(f"  {skill.name:32} {_describe(skill)}")
        return 0
    if len(argv) != 2 or argv[0] not in {"activate", "deactivate"}:
        print(__doc__)
        return 1
    src_base, dst_base = (DORMANT, ACTIVE) if argv[0] == "activate" else (ACTIVE, DORMANT)
    src, dst = src_base / argv[1], dst_base / argv[1]
    if not (src / "SKILL.md").exists():
        print(f"Skill '{argv[1]}' não encontrada em {src_base.relative_to(ROOT)}")
        return 1
    if dst.exists():
        print(f"Destino já existe: {dst.relative_to(ROOT)}")
        return 1
    shutil.move(str(src), str(dst))
    print(f"{argv[0]}: {argv[1]} -> {dst.relative_to(ROOT)} (vale a partir da próxima sessão)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
