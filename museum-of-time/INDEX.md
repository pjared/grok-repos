# Museum of Time — archive

Long-term project: interactive website museum. Videos are exhibits hung in halls.

**Master layout (keep current):** [`layout.md`](layout.md) · floor plan [`assets/diagrams/museum-floor-plan.svg`](assets/diagrams/museum-floor-plan.svg)

## Halls
| Wing | Door label | Look |
|------|------------|------|
| Wheel of Travelers | Parable. Invented exhibits about people who changed a timeline. | Clean museum light |
| Surviving Books | Sourced retelling. Myth and history kept alive after the fires. | Firelight + paper |

Site rules: `site/rules.md`  
New exhibit: copy `templates/exhibit.md` → `exhibits/<slug>/README.md`, then update **`layout.md`**.

## Exhibits (see layout.md for canonical order)
| Slug | Title | Wing | Status |
|------|-------|------|--------|
| iole-uncopied-canvas | Iole of the Uncopied Canvas | Travelers · T1 | episode + 2 shorts done |
| already-seen | Already Seen | Travelers · T2 | locked concept (stills next) |
| *(Popol Vuh)* | Popol Vuh, Part 1 | Surviving Books · B1 | episode + 4 shorts done (Witness 1) |
| library-of-alexandria | What the Fire Took | Surviving Books · B2 | prompts + VO splits ready · next Witness 1 + packs |

## Asset folders
- `assets/stills/` — face locks, props, frames
- `assets/diagrams/` — wall SVGs + museum floor plan
- `assets/audio/` — ElevenLabs exports (`iole-01`, …)
- `assets/video/` — Flux packs (`F1`, …)

## Templates
- `templates/exhibit.md` — full exhibit folder starter (beat table + Science checklist)
- `templates/flux-cut-sheet.md` — ≤20s pack list sibling
- exhibits/a-day-in-meso/eras.md: pinned Mesoamerican eras reference
- exhibits/immortality-cyberpunk/idea.md: immortality / cured-aging cyberpunk idea (unplaced)
- exhibits/time-war/notes.md: consolidated Time War notes (2026-10-16)
