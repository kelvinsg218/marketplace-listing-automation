# Tools inventory — verified 2026-10-12

Status: **Ativo** (installed and validated) · **Dormente** (in `tools/skills-catalog/`, zero context cost) ·
**Configurado** (installed, awaiting a step) · **Não instalado** (evaluated, rejected; see DECISIONS.md).

## Base environment
| Tool | Version | Check |
|---|---|---|
| Node.js / npm | 24.19.0 / 11.17.0 | `node --version` |
| Git | 2.49.0.windows.1 | `git --version` |
| Claude Code | 2.1.278 | `claude --version` |
| Python | 3.13.5 (project venv `.venv`) | `.venv\Scripts\python --version` |
| Ollama | 0.40.3, API on 127.0.0.1:11434 | `ollama list` |

## Skills and plugins (by function)
| Name | Source @ commit | Type / location | Function | Status |
|---|---|---|---|---|
| frontend-design | anthropics/claude-code @3deb873 (plugins/frontend-design) | skill, `.claude/skills/` | Design/UX | Ativo |
| pyside6-design | own | skill, `.claude/skills/` | Design/UX (Qt tokens, pitfalls, review loop) | Ativo |
| webapp-testing | anthropics/skills @dbd4588 | skill + `scripts/with_server.py` (inspected) | Testes/Automação | Ativo |
| systematic-debugging | obra/superpowers v7.0.0 @bb92a77 | skill (4 files) | Depuração | Ativo |
| test-driven-development | obra/superpowers @bb92a77 | skill | Testes | Ativo |
| verification-before-completion | obra/superpowers @bb92a77 | skill | Revisão/validação | Ativo |
| python-testing | affaan-m/ECC @b92f181 | skill | Testes | Ativo |
| strategic-compact | affaan-m/ECC @b92f181 | skill | Otimização de tokens | Ativo |
| token-economy | own | skill, `~/.claude/skills/` (user scope, reusable) | Otimização de tokens | Ativo |
| writing-plans | obra/superpowers @bb92a77 | skill | Planejamento | Dormente |
| python-patterns | affaan-m/ECC @b92f181 | skill | Programação | Dormente |
| windows-desktop-e2e | affaan-m/ECC @b92f181 | skill | Testes E2E Qt (fase 7) | Dormente |
| generating-python-installer | affaan-m/ECC @b92f181 | skill | Distribuição (fase 7) | Dormente |
| Superpowers plugin (full) | obra/superpowers | plugin + SessionStart hook | — | Não instalado (D-001) |
| ECC (full) | affaan-m/ECC (renamed from everything-claude-code) | 311 skills, 71 agents, hooks | — | Não instalado (D-001) |
| awesome-claude-skills | ComposioHQ | catalog | Descoberta | Não instalado (consulta) |
| superpowers-developing-for-claude-code | obra @74afe93 (last push 2025-12-03) | docs snapshot | — | Não instalado: desatualizado, redundante com `claude-code-guide` |
| frontend-ai-skills | JustineBijuPaul @f52d23c | 70 web skills | — | Não instalado (D-002) |
| frontend-skills | eghamat24 @0edb0bc | Vue/React conventions | — | Não instalado (D-002) |
| shadcn/ui | shadcn-ui/ui | web components | Referência visual | Não instalado (referência) |

Verify skills: `python tools/skills_catalog.py list`. Licenses: MIT/Apache copies kept beside each skill.

## MCP, automation, local AI
| Name | Version | Location | Function | Status | Check |
|---|---|---|---|---|---|
| chrome-devtools-mcp | 1.10.1 (pinned) | `.mcp.json` (project) | Inspect real forms (phase 4) | Configurado: aguarda aprovação no `claude` | `claude mcp get chrome-devtools` |
| MCP reference servers | — | — | — | Não instalado (D-004) | — |
| Playwright for Python | 1.63.0 | `.venv` | Browser automation (system Edge) | Ativo, 5 browser tests | `pytest -m browser` |
| Playwright JS | — | — | — | Não instalado (Python is used) | — |
| Ollama model qwen2.5-coder:1.5b | 986 MB, 1.2 GB loaded | Ollama store | Error-triage hints only | Ativo (limited, D-003) | `python tools/ollama_assist.py stats` |
| Aider | 0.86.2 | — | — | Não instalado: requires Python <3.13 | — |
| OpenCode | anomalyco/opencode (was sst/opencode), npm opencode-ai 1.19.0 | — | — | Não instalado (D-003) | — |
| PyInstaller | 6.22.3 | `.venv` (build extra) | Windows build | Ativo, build validated | `dist\MLA\MLA.exe --self-test` |

## Project tools (`tools/`)
`logscan.py` (deterministic log digest) · `ollama_assist.py` (local LLM + real metrics in `tools/.metrics/`) ·
`skills_catalog.py` (activate/deactivate skills) · `ui_snapshots.py` (render pages to PNG with sample data in a temp
folder) · `make_icon.py` (app icon).
