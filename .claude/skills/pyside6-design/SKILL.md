---
name: pyside6-design
description: Use when creating or changing any MLA screen, widget, dialog or stylesheet (PySide6/Qt). Holds the project's design tokens, component rules, Qt styling pitfalls and the visual review loop.
---

# MLA design system (PySide6)

Principles adapted from Anthropic's `frontend-design` skill and shadcn/ui's component model, translated to Qt.

## Direction
Operations console for marketplace sellers. Dark, graphite and violet (fixed by the brief). Products move through a
pipeline (draft → ready → queue → review → published); the dashboard's `PipelineRail` is the ONE bold element —
keep everything else quiet. Avoid the SaaS-card kit: no drop shadows, no gradients as decoration, tonal layers +
1px borders instead. No ALL-CAPS labels, no middle-dot meta strings, no "→" in buttons.

## Tokens (only source: `src/mla/ui/theme.py`, class `T`)
- Layers: canvas `#0C0B10` < sidebar < surface `#16151C` < raised `#1E1C26`; lines `#2A2733`/`#3B3747`.
- Text: `text`, `text_2` (secondary), `text_3` (hints). Brand: `violet #7B5CFF`, `violet_hi`, `violet_wash`.
- Semantic tones (`TONES`): neutral, violet, active, warning, success, danger, muted. Status → tone in `STATUS_TONE`.
- Type: Manrope (display: titles/numbers, `display_font()`), Segoe UI Variable (body 13px). Scale 11/12/13/15/24/28.
- Radii by hierarchy: panels 10, controls 6, chips pill.

## Components (`src/mla/ui/widgets/common.py`)
`button(text, variant)` primary|secondary|ghost|danger|success · `icon_button` · `StatusChip` · `StatusDelegate(enum_cls)`
for table cells · `PageHeader` · `Panel` · `EmptyState` · `show_toast` · `confirm`/`inform` · `thumbnail` ·
`clear_layout` · `format_when` · `plural`. Icons: Lucide via `ui/icons.py` (`icon(name, color)`).

## Qt pitfalls (all hit in this project)
- A widget-level `setStyleSheet("background: …")` without a selector cascades to ALL children → always scope:
  `QFrame#name { … }` with `setObjectName`.
- Dynamic properties (`variant`, `invalid`) need re-polish → use `set_prop()`.
- `QComboBox`/`QTableWidgetItem` turn `StrEnum` into plain `str` → convert back (`StatusDelegate(enum_cls)`).
- `deleteLater()` leaves widgets painted until the loop turns → use `clear_layout()`.
- Enabling sorting on a view emits `sort()` immediately → connect sort handlers after the page is built.
- `QSplitter.setSizes` before show is ignored → prefer layouts/stretch or max heights.

## Copy (PT-BR)
Sentence case, active verbs, same word through a flow (Executar → "Na fila"; Publicar → "Publicado"). Errors say what
happened and how to fix it; empty states invite an action. Correct plurals with `plural()`. Dates via `format_when()`.

## Review loop (required for visual changes)
1. `.venv\Scripts\python tools/ui_snapshots.py <scratch_dir>` (seeds sample data in a temp folder only).
2. Read the PNGs; check overflow/elision, empty columns, ghosting, alignment, contrast, focus states.
3. Fix, re-render, re-check. Add/adjust pytest-qt tests in `tests/ui/`.
