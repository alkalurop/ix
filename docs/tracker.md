# Tracker (GitHub)

Day-to-day work and the public queue live on **[ixamal](https://github.com/ixamal)**. Process that should last (how/why, commands, safety) stays in `docs/` in each repo. The [alkalurop](https://github.com/alkalurop) org gets a **git mirror** of those docs via `docs/examples/alkalurop-bridge.sh`. Issues, milestones, and labels are GitHub metadata — they do **not** copy through git. Look at ixamal for the live board; alkalurop for the mirrored code and docs.

Skip the repository **Agents** tab (GitHub Copilot cloud agent). Cursor / Codex rules stay in-repo (`.cursor/`, README).

## Where to look

| Want | Place |
| --- | --- |
| What is open | [ixamal/ix issues](https://github.com/ixamal/ix/issues) |
| Eras / next | [ixamal/ix milestones](https://github.com/ixamal/ix/milestones?state=all) |
| How/why | `docs/crate.md`, `docs/security.md`, `docs/notes.md` |
| Ordered checklist | `docs/TODO.md` (links to issues; detail stays here) |
| STEMIT factory | [ixamal/stems](https://github.com/ixamal/stems) |
| Room / BlackHole | [ixamal/blackhole](https://github.com/ixamal/blackhole) |

## Milestones (ixamal/ix)

| Milestone | State | Meaning |
| --- | --- | --- |
| [Crate path-stable](https://github.com/ixamal/ix/milestone/1) | closed | Music / Traktor / Rekordbox same files |
| [Tagging cleanup](https://github.com/ixamal/ix/milestone/2) | closed | EDM / House / Hip Hop passes |
| [STEMIT factory live](https://github.com/ixamal/ix/milestone/3) | open | Proven path; Rock batch + leftovers |
| [Floor / Elysium](https://github.com/ixamal/ix/milestone/4) | open | **Next** — OSC → UE |
| [Hardware leftover](https://github.com/ixamal/ix/milestone/5) | open | FLX10 CH2 / S8 pads parked |
| [Play history](https://github.com/ixamal/ix/milestone/6) | open | favorites + GENRES / ACAPELLAS reviews |

Sibling stamps: [stems STEMIT factory](https://github.com/ixamal/stems/milestone/1), [blackhole 16ch Channel D](https://github.com/ixamal/blackhole/milestone/1) (closed), [FLX10 digital parked](https://github.com/ixamal/blackhole/milestone/2).

## Labels

`crate` · `stemit` · `floor` · `hardware` · `parked` · `done-era`

## Project board

A GitHub Project (column board) needs `project` token scope (`gh auth refresh -s read:project,project`). Until that is granted, **milestones + issues** are the queue. Optional later: one ixamal org project with Now / Parked / Done.

## Agents tab

Left alone. It is Copilot’s session console, not an open-source agent manifesto. Entry for others: README + `.cursor/` + `schemas/mcp.example.json`.
