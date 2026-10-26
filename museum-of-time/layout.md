# Museum of Time — master layout
**Keep this file current.** Update whenever an exhibit is added, moved, or retired.  
Social posts use this order and these labels, e.g. `Museum of Time · Surviving Books · Popol Vuh, Part 1`.

Floor plan: `assets/diagrams/museum-floor-plan.svg`

---

## Visitor path (canonical order)

1. **Entrance** — shared F1 dolly: dark wing → one lit pedestal  
2. Choose a **door** (epistemic status on the label — never skip)  
3. Walk the wing’s pedestals in the order below  
4. Exit / return to entrance for the other wing

---

## Entrance
| Field | Value |
|-------|--------|
| Shot | F1 — camera dollies down a dark wing toward one lit pedestal |
| Asset | `assets/video/F1.mp4` (when rendered) |
| Website | Walk-into-room transition for every exhibit |
| Look | Dark hall; only the far pedestal lit; halls diverge *after* this shot |

---

## Wing A — Wheel of Travelers
| Field | Value |
|-------|--------|
| Door label | Parable. Invented exhibits about people who changed a timeline. |
| Look past door | Clean museum light |
| Plaque voice | Parable / fiction cue (not a history) |
| Social prefix | `Museum of Time · Travelers · …` |

### Pedestals (order)
| # | Exhibit | Slug / source | Social label | Status |
|---|---------|---------------|--------------|--------|
| T1 | Iole of the Uncopied Canvas | `exhibits/iole-uncopied-canvas/` | Museum of Time · Travelers · Iole of the Uncopied Canvas | episode + 2 shorts done (`out/`); do not redo |
| T2 | Already Seen | `exhibits/already-seen/` | Museum of Time · Travelers · Already Seen | locked concept |

---

## Wing B — Surviving Books
| Field | Value |
|-------|--------|
| Door label | Sourced retelling. Myth and history kept alive after the fires. |
| Look past door | Firelight and paper texture |
| Plaque voice | Sourced retelling — never the Travelers register |
| Social prefix | `Museum of Time · Surviving Books · …` |

### Pedestals (order)
| # | Exhibit | Slug / source | Social label | Status |
|---|---------|---------------|--------------|--------|
| B1 | Popol Vuh, Part 1 | `/workspace/PopolVuh/` (First Book scripts) | Museum of Time · Surviving Books · Popol Vuh, Part 1 | episode + 4 shorts done (Witness 1); do not redo |
| B2 | What the Fire Took (Library of Alexandria) | `exhibits/library-of-alexandria/` | Museum of Time · Surviving Books · What the Fire Took | **title locked** · VO v2 · prompts + VO splits ready · next: Witness 1 + packs |

---


## Video & shorts standard (locked)
| Format | Spec |
|--------|------|
| Episode | 3–4 min widescreen YouTube |
| Shorts | Cut into 45–60 s vertical (TikTok, Reels, YouTube Shorts) |
| Each short | Ends on a **hook** |
| Social short label | `Museum of Time · [Wing] · [Exhibit] · Short N of M` |

Example: `Museum of Time · Surviving Books · Popol Vuh, Part 1 · Short 1 of 4`


## Narration voices (locked)
| Wing | Voice | Register | Audition over |
|------|-------|----------|---------------|
| Travelers | MoT Docent 3 (locked 2026-10-05) | warm guide, unhurried | F1 entrance |
| Surviving Books | MoT Witness 1 (locked 2026-10-05) | cooler, spare, holds silence | ash/harbor long take |

- Two voices — never share across doors.  
- No fake ethnic accents; correct names only.  
- No Professional Voice Cloning unless a real person consents.  
- Pick from ElevenLabs Voice Design samples over picture, not audio alone.

## How to add an exhibit
1. Copy `templates/exhibit.md` → `exhibits/<slug>/README.md` (clear beat table + Science checklist).  
2. Add a row to the correct wing table above (**next free #**).  
3. Update `INDEX.md` exhibits list.  
4. Refresh `assets/diagrams/museum-floor-plan.svg` pedestal labels if the floor plan is used in posts.  
5. Use the **Social label** column verbatim for posts.

## How to move an exhibit
1. Change wing / # in this file.  
2. Update social label prefix if the wing changed.  
3. Update INDEX + floor-plan SVG.

---

## Related
- Site rules: `site/rules.md`  
- Archive index: `INDEX.md`
- A Day in Meso (dramatized history, wing TBD): see exhibits/a-day-in-meso/outline.md

## Frame (the director, 2026-10-11)
The museum sits "At the End of Time": a future where aging is cured and shared with all humanity; every exhibit is the past the immortals look back on. Title family: "The ___ at the End of Time" (The Museum at the End of Time, ...). The F1 dolly down the dark wing is the immortals walking back through their own past. Source: exhibits/immortality-cyberpunk/idea.md

## Pitches 2026-10-15 (the director)
- Time War: winners rewrite history, plaques change by who reads them. The losing side leaves one plaque unrewritten on purpose, as a trap; the curtain drops when time travel is invented and someone reads it.
- 2000s hall (both standalone and a time-war front): invented governor (parable, not a real official) takes a cut to let the ultrawealthy run a quiet, Looper-style illegal time travel operation on a small plot in Salt Lake City. The 2000s are setup only; the reveal comes later.
- Animation pitches on hold.
- Invention era (curtain drop): Warhammer 40K-style grim futurism; humans control their genome, nearly everything is invented, time travel is the last great invention and the prize worth a war. (the director: "Exactly.")
- 2020s chapter: the Salt Lake operation has grown and hides in plain sight as a normal-looking business; only the time travel is secret.
  - Front #1 (locked): 24-hour storage-unit place in Salt Lake; lights never go off. More fronts to come.
- Meso tie (good start per the director): a Salt Lake traveler goes back to the Triple Alliance years and backs the red king, which is why red wins; stolen codices end up in the storage units.
- Time War is one good-vs-evil war across every hall; WWII is one front (big picture, not one character). Evil side = same side behind Salt Lake operation and red king. Holocaust/documented atrocities stay on fixed sourced plaques.
- Timeline tool (the director is building, Grok Bot offered): one master timeline plus multiple in-depth cuts of the major action; each entry tagged documented/reconstructed/invented.
  - ComfyUI-style node canvas: events as nodes, wires as cause/effect, time jumps as backward wires, expandable groups for in-depth cuts, thumbnail per node (storyboard). Shared tool to build and edit scenes together.
- Big picture (2026-10-16): interactive website where visitors pitch changes, people vote, AI drafts the edit/plaque (democratic canon). Invented parts are votable; documented history stays locked to sources. Open: who gets a vote.
  - The director: vote covers all of it (fiction halls and time war outcome). First vote cast: green.
- Daily news plaques: ON HOLD (too many plaques); keep real news for the larger rooms only.
- Red simian species (the director, 2026-10-16): intergalactic evolved apes, Gears of War-style, red side army. Optional invented link to Popol Vuh monkeys (wooden people / hero twins half-brothers) must be plaqued as our invention; Popol Vuh is K'iche' Maya, red side is Triple Alliance. Hall of Dead Timelines door: "Every future that lost a vote."
  - UPDATED (the director, 2026-10-16, Qwen #4): red simians are mutated human time travelers stranded in the far future, which supersedes "intergalactic evolved apes" above. The time war is a civil war among humans, and the red side has a sympathetic reason to fight. Popol Vuh monkey link stays cited as documented myth; the mutation twist is labeled invented.
- New item (2026-10-16): corpo gift to the richest man's wife (invented corpo dynasty couple, not real people). Draft plaque (Writing Bot): "A gift for the woman who had everything. It came from a year that hadn't happened yet." Gift itself TBD.
  - Gift = string of pearls, each pearl an era of human history. Plaque option (Writing Bot): "A string of pearls, one for every age of humanity. She wore all of history around her neck and never asked what it cost." Ideas: each wing gets a pearl (necklace = map of museum); one pearl missing, stolen through time. Real legends (e.g., Cleopatra pearl, from Pliny) labeled legend.
  - The wife (red side, invented): luxury tourist of all history, travels any point in time; cruel, treats eras as her resort. Pearls are her souvenirs; each cost someone in that era. Possible tie: Salt Lake storage units book her trips / store luggage.
- 2026-10-24: Mesoamerican material on hold (the director).
- 2026-10-24: Time War theme locked: the body in the storage unit.

## Online navigation vote (2026-10-25)
Three votes for era-shifting nav with a 2000s retro lobby (Curator, Grok Bot, Writing Bot). Two for straight 2000s retro (Scene Checkpoint, and Science Checkpoint with a timeline scrubber and tags on the menu). PASSED by the director: era-shifting nav with a 2000s retro lobby is LOCKED.
