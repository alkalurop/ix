# Tracker (GitHub)

Day-to-day work and the public queue live on **[ixamal](https://github.com/ixamal)**. Process that should last (how/why, commands, safety) stays in `docs/` in each repo. The [alkalurop](https://github.com/alkalurop) org gets a **git mirror** of those docs via `docs/examples/alkalurop-bridge.sh`. Issues, milestones, and labels are GitHub metadata — they do **not** copy through git. Look at ixamal for the live board; alkalurop for the mirrored code and docs.

Skip the repository **Agents** tab (GitHub Copilot cloud agent). Cursor / Codex rules stay in-repo (`.cursor/`, README).

`docs/TODO.md` is still the full ordered ledger. Milestones are the eras you can glance. Issues are the open leftovers (and one closed stamp per done era).

## Where to look

| Want | Place |
| --- | --- |
| What is open | [ixamal/ix issues](https://github.com/ixamal/ix/issues) |
| Eras / next | [ixamal/ix milestones](https://github.com/ixamal/ix/milestones?state=all) |
| Project board | [ixamal projects/2](https://github.com/users/ixamal/projects/2) (Now / Parked / Done) |
| How/why | `docs/crate.md`, `docs/security.md`, `docs/notes.md` |
| Ordered checklist | `docs/TODO.md` |
| STEMIT factory | [ixamal/stems](https://github.com/ixamal/stems) |
| Room / BlackHole | [ixamal/blackhole](https://github.com/ixamal/blackhole) |

## Milestones (ixamal/ix)

### Closed (shipped)

| Milestone | TODO rows |
| --- | --- |
| [Crate path-stable](https://github.com/ixamal/ix/milestone/1) | 1–3 |
| [Tagging cleanup](https://github.com/ixamal/ix/milestone/2) | 4–9 |
| [Music.app library hygiene](https://github.com/ixamal/ix/milestone/7) | 16, 18–22, 24–26 |
| [STEMIT prove + Afro House](https://github.com/ixamal/ix/milestone/11) | 14–16b |
| [STEMIT crates + IndustryStems](https://github.com/ixamal/ix/milestone/8) | 23, 27, 29–36, 39a |
| [Playlist bridge night](https://github.com/ixamal/ix/milestone/9) | 37–39 |
| [16ch Channel D live](https://github.com/ixamal/ix/milestone/10) | 11, 11a |

### Open

| Milestone | Meaning |
| --- | --- |
| [STEMIT factory live](https://github.com/ixamal/ix/milestone/3) | Leftovers: role titles [#7](https://github.com/ixamal/ix/issues/7), Alternative [#8](https://github.com/ixamal/ix/issues/8); Rock batch local |
| [Floor / Elysium](https://github.com/ixamal/ix/milestone/4) | **Next** — OSC → UE [#9](https://github.com/ixamal/ix/issues/9) |
| [Hardware leftover](https://github.com/ixamal/ix/milestone/5) | FLX10 CH2 / S8 pads parked |
| [Play history](https://github.com/ixamal/ix/milestone/6) | favorites + GENRES / ACAPELLAS reviews [#13](https://github.com/ixamal/ix/issues/13) |

Sibling: [stems STEMIT factory](https://github.com/ixamal/stems/milestone/1), [blackhole 16ch](https://github.com/ixamal/blackhole/milestone/1) (closed), [FLX10 digital parked](https://github.com/ixamal/blackhole/milestone/2).

## Labels

`crate` · `stemit` · `floor` · `hardware` · `parked` · `done-era`

## Project board

Public board: **[ixamal project — ix](https://github.com/users/ixamal/projects/2)** — columns **Now**, **Parked**, **Done**. Linked to `ix`, `stems`, and `blackhole`. (Project #1 was a first attempt and is closed.)

`TODO.md` remains the full ledger. This board is the glance view.

## Agents tab

Left alone. Entry for others: README + `.cursor/` + `schemas/mcp.example.json`.
