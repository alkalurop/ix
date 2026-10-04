# Traktor Master Class Notes

David · Traktor Pro 4.5.x · Kontrol S8 · DDJ-FLX10 · BlackHole 16ch rig (`ix` / [blackhole](https://github.com/ixamal/blackhole))

Last updated: 2026-10-04 (Cursor session — Rekordbox sampler → disk, ix SAMPLES crates, metadata)

---

## High level — what this rig is for

- **Traktor S8** = mixer + deck control; **Track / Stem / Remix / Live Input** on four virtual decks.
- **BlackHole 16ch** = internal bus so **Maschine + KK S88** can land on **Channel D only** without stealing A/B/C (proven 2026-09-19). Details: `blackhole/docs/RUNBOOK.md`.
- **Remix decks** = live sample grids (64 cells) for loops/one-shots; **capture** from track decks or Loop Recorder — not a substitute for the STEMIT factory or Apple Music writes.
- **S8 hardware** = primary performance surface; some F1-only gestures (delete mode) are **not** on factory S8 mapping.

---

## Deck flavors (pick the right mode)

| Flavor | Use when |
|--------|----------|
| **Track Deck** | Normal files, loops, hotcues |
| **Stem Deck** | `.stem.m4a` / generated stems — four stem channels |
| **Remix Deck** | Sample grid, remix sets, capture |
| **Live Input** | External analog/digital **through** Traktor’s channel strip (not “play a file”) |

### Channel C — analog line in (S8)

- Deck **C** → **Live Input** (not Track Deck).
- **Input Routing → Input C** = S8 **analog pair** for channel C (not BlackHole 10/11 — that path is **D**).
- S8: channel **TRAKTOR** mode, **LINE** source, fader up.
- BlackHole routing does **not** affect analog C.

### Channel D — S88 / Maschine (BlackHole)

- Traktor **Input Deck D** = BlackHole **In 10 / In 11** (16ch graph).
- Maschine: internal tap **Record 7/8** → In 2; KK on Out 1 → 0/1; keys heard only on **S8 fader D** when A/B/C are down.

---

## Remix Deck — capture source (Pro 4 + S8)

### Where the control lives

- **Capture source** is in the **Remix deck header** (Deck Tempo row — often shows **“Loop Rec”** with a hover triangle). **Not** in the per-cell Advanced panel (that panel is sample-cell params: gain, sync, grid, loop/one-shot).
- If the menu is missing: increase deck size or use **Parallel Full** / **Advanced** layout so the full header is visible.

### S8 gesture (factory manual)

1. Hold **CAPTURE**, **touch Loop encoder** → capture UI.
2. Turn encoder → pick source (Deck A/B/C/D or Loop Rec).
3. Release CAPTURE, press an **unlit pad** (not only spin encoder).
4. **REMIX** mode on; pads show remix grid for that deck side.

### Capture source vs deck content (behavior you proved)

| Source deck state | Remix capture menu |
|-------------------|-------------------|
| Empty **Track** deck | **Deck A** (etc.) listed |
| **Stem** loaded on A | Often **Loop Rec only** — deck drops off list |
| Normal **single track** on A | **Deck A** works |

**Conclusion:** Remix **file-snippet capture** targets **Track Decks**, not **Stem Decks**. Not a BlackHole bug.

**Stem workaround:** capture via **Loop Recorder** (often **Cue** source) → drag into remix or capture from **Loop Rec** as source. Community: “Stem deck? That won’t work” (DJ TechTools / NI F1 docs say Track Decks only).

### Errors

- `Error loading sample slot from deck: Current active deck is not a track deck` — capture source was a **Live Input** or **Stem** deck treated as track capture.

---

## UI layout — Parallel Full + remix Advanced (same session)

### You do **not** need to choose Parallel *or* Advanced

- **Parallel Full** (manual) = **stacked A/B waveforms** + **full header** + **Advanced panel** + transport/tempo — it **includes** Advanced, not replaces it.
- Picking layout **Advanced alone** drops the parallel stack — that felt like either/or.

### How to set it

1. **Header layout dropdown** → a **Parallel** Traktor layout (custom “Pivote Traktor” is fine).
2. **Double-click deck header** on track decks until **Parallel Full** (cycles Micro → … → Parallel Full). Saved per layout.
3. **Preferences → Decks Layout → Size A & B / C & D** only lists Micro…**Advanced** — **Parallel Full is not in that dropdown**; use header double-click on Parallel layouts.
4. **Remix deck (e.g. B):** Size **Advanced** or **Full** in prefs → toggle **Advanced panel** open; **click sample name** to select which cell is edited.
5. **Preferences → Remix Decks:** **Show Volume Fader**, **Show Filter Fader**, **Permanently Show Slot Indicators** for more always-visible slot UI.

### Limits

- Advanced panel edits **one sample cell at a time**; four **slot columns** are the “whole deck” view.
- Parallel stack is built around the **A/B pair**; with **B = Remix**, stacked strip is mainly for track-side mixing; C/D use **Size C & D** separately.

---

## Clearing / replacing remix cells

### Right-click

- **No unload/delete** in context menu for cells (Pro 4).
- **Right-click Sample Trigger** = **color palette**, not delete.

### Software

- **Shift + click Sample Trigger** once = **stop**; **Shift + click again** = **unload** (S4 MK2 / same remix UI pattern — try on-screen trigger, not waveform).
- **Drag sample from Browser** onto occupied cell = **replaces** sample (official manual) — David’s working workaround.

### S8 hardware

- **SHIFT + CAPTURE + pad** = **F1 Delete mode**, **not** factory S8 clear.
- Factory S8 doc: **SHIFT + pad** = **stop** on remix; **does not document** pad unload.
- Try: **Deck focused**, **REMIX** on, **SHIFT + pad twice** (S4 pattern: stop then unload) — may be unmapped on S8.
- Optional mapping: [DJ TechTools — Kontrol S8 Sample Cell Delete](https://maps.djtechtools.com/mappings/9351) — hold **REMIX + pad**.
- **Controller Manager:** search **Slot Unload**, **Stop/Delete**, map to keyboard if needed.
- **Workaround:** capture on another **unlit pad** in the same slot column.

---

## Original BPM — no tempo stretch on samples

Traktor **time-stretches** remix samples when **Sync Type** is **on** and remix deck BPM ≠ sample **base tempo**.

### Per sample (required)

1. Remix deck **Advanced panel** open; **click sample name**.
2. **Sync Type OFF** (Advanced #10). Manual: *“When SYNC is off, the Sample will play at its original speed.”*
3. Or toggle **Sample Sync** on the cell / trigger row.
4. Repeat **per cell** — no global “all unsynced” pref; **save remix set** to persist.

### Deck level

- Remix **tempo fader** at **0%**; **double-click** header BPM → reset to **base tempo**.
- Deck **SYNC** to master changes **deck BPM**; **Sync-off** samples ignore deck and stay native speed.
- **Sync-on** samples still stretch to deck BPM.
- Wrong **Sample BPM** in Advanced → fix base tempo / grid even with sync off.

### Key Lock (slot)

- Hover slot → **Key Lock** decouples pitch from deck tempo for **synced** material; it does **not** replace **Sync Type off** for “no stretch.”

### After capture

- New captures often default **sync on** + loop; set **sync off** + **one-shot** if you want natural-length hits.

---

## Sync / quantize on remix deck (when you *want* lock)

- Header **Quantize** dot + value = when triggers align to remix deck internal timeline.
- **Preferences → Remix Decks:** **One-Shot Samples Ignore Quantize Mode** if one-shots should fire immediately.
- Remix deck can **SYNC** to Tempo Master like track decks; per-sample **Sync Type** still governs stretch.

---

## Rekordbox sampler — pads vs disk vs ix (`DDJ-FLX10`)

Rekordbox keeps **three different things**. Confusing them is why War Pig showed on **16 pads** but **`~/Music/PioneerDJ/Sampler/Capture` stayed empty** after quit.

| Layer | What it is | Survives quit? | ix tools see it? |
|-------|------------|----------------|------------------|
| **Sampler slots (pads)** | Live bank — same sample in many slots is still one idea, copied for performance | Session is **restored** when you reopen Rekordbox (library remembers *what* was loaded) | **No** — not a folder ingest |
| **Sampler → Capture** (browser tree) | Collection rows from **CAPTURE** (`title_capture`) | Yes, in collection + on disk when CAPTURE ran | **Yes** — after WAV lands in Capture |
| **`SAMPLES/Samplers` playlist** | Our crate in `rekordbox.xml` + Traktor NML from **Saved** archive | Yes | **Yes** — after `rekordbox-sample-crate` |

**Proved 2026-10-04:** Quitting Rekordbox **did not** write current pad contents into **`Sampler/Capture`** on disk. Filling all 16 slots with the same capture **does not** mint 16 WAV files. The **71** archived samples in **`SAMPLES/Samplers`** came from an earlier **CAPTURE** pass that **did** hit disk; new War Pig / mash work lived **only in slots** until CAPTURE (or export) runs again.

### Native Rekordbox way to get WAVs ix can pick up

**Goal:** files under **`~/Music/PioneerDJ/Sampler/Capture`** → `rekordbox-sample-crate` moves to **`Saved`** and syncs **`SAMPLES/Samplers`** (also NML). See `ix/docs/crate.md`, `docs/examples/rekordbox-sample-crate.sh`. Runs at end of **CRATER** / **STEMIT+CRATER**.

**CAPTURE (Performance mode — local files only, not streaming):**

1. Load **source track** (mash, vocal, etc.) on a deck.
2. Set a **loop** on the section you want.
3. **CAPTURE** (scissors on waveform) — loop range turns **blue**.
4. **Drag the blue loop** to an **empty sampler slot** (not only duplicating the same pad 16×).

Rekordbox then adds a collection row **`…_capture`**, lists it under **Sampler → Capture** in the tree, and writes WAVs to **`~/Music/PioneerDJ/Sampler/Capture`** (rekordbox 7 manual: *“stored at [Capture] in [Sampler] of [Media Browser]”*).

**Preferences → Controller → Sampler → SLOT:** if **Do not overwrite the loaded Slot** is on, use **empty** slots or turn it off before drag.

**After disk write:** quit Rekordbox + Traktor → `docs/examples/rekordbox-sample-crate.sh --execute` → reload xml (`<>`), **Don't ask again** + **No** on tag overwrite.

**Alternate — explicit file (EXPORT mode):** load track, set loop, waveform **⋮** → **Export Loop As WAV**. Standalone WAV for DAW/sampler; not the Capture-folder pipeline unless you import that file back through CAPTURE or drag into **Saved** manually.

**Browser hygiene:** **Sampler → All samples** lists anything ever loaded to a slot (useful for re-finding, tagging **Sample**). Only **Capture** + on-disk **`Capture/`** folder feeds **`rekordbox-sample-crate`** today.

### Traktor samples → Rekordbox (already wired)

- **Every remix set in Traktor NML** (factory ContentImport + yours) → **`SAMPLES/Remixes/<Set Name>/`** one playlist per set via `traktor-remix-crate`.
- **`~/Music/Traktor/Samples`** deck captures → **`SAMPLES/Remixes/Deck Captures`**.
- Ingest copies **artist, title, album, BPM, key, genre** from Traktor NML into `rekordbox.xml` and from xml into NML when the other app is missing the row (`dj_metadata.py`).

### Rekordbox → Traktor

- **`rekordbox-sample-crate`**: Saved/Capture WAVs → **`SAMPLES/Samplers`**; ingest uses xml/NML on-disk rows plus **library title match** for `_capture` names to fill artist/BPM/key when the source track is already in `rekordbox.xml`.

---

## Related repo pointers

| Topic | Where |
|-------|--------|
| 16ch Channel D, 11a Maschine tap | `github.com/ixamal/blackhole` RUNBOOK |
| CRATER / STEMIT / NML | `github.com/ixamal/ix` `docs/crate.md` |
| Rekordbox Capture → Saved + Samplers | `ix` `rekordbox-sample-crate`, `docs/examples/rekordbox-sample-crate.sh` |
| Traktor remix sets → `SAMPLES/Remixes/*` | `ix` `traktor-remix-crate`, `docs/examples/traktor-remix-crate.sh` |
| Alkalurop git mirror (not Drive) | `ix/docs/examples/alkalurop-bridge.sh` |
| S8 pads → S88 (TODO on hold) | `ix/docs/notes.md` |

---

## Manuals & links

- [Traktor Pro 4 Manual (PDF)](https://docs.native-instruments.com/pdf-guides/traktor/Traktor-Pro-4-Manual-English-170724.pdf) — Parallel Full, Remix Advanced panel, Sync Type.
- [Traktor Kontrol S8 Manual](https://docs.native-instruments.com/pdf-guides/TRAKTOR_KONTROL_S8_Manual_English_2014_10.pdf) — Remix mode, CAPTURE, SHIFT+pad stop.
- [F1 Delete mode](https://docs.native-instruments.com/pdf-guides/traktor/traktor_kontrol_f1_manual_english.pdf) — SHIFT+CAPTURE (DELETE), pad clear, encoder **UL** = unload whole remix deck.
- [S4 MK2 — unload sample](https://native-instruments.manymanuals.com/dj-controllers/traktor-kontrol-s4-mk2/technical-information-15193/54) — SHIFT + Sample Play twice.
- [Rekordbox 7 manual (PDF)](https://cdn.rekordbox.com/files/20241004105932/rekordbox7.0.4_manual_EN.pdf) — sampler deck (p.188), **CAPTURE** (p.200).
- [Rekordbox — sample from loop/slicer (video)](https://youtu.be/JCqhAH-rDYw) — CAPTURE drag to sampler slot.

---

## Open / on hold

- **TODO 13:** MIDI-map S8 pads → S88 samples (after Floor 10).
- Factory **S8 remix cell delete** may need DJTT mapping or Controller Manager **Slot Unload**.
- Document stem → Loop Rec → remix capture path in `blackhole` if we want git parity with this doc.
- **Git:** this file lives at `docs/examples/traktor-master-class-notes.md` in [ixamal/ix](https://github.com/ixamal/ix) — commit + push to appear on GitHub `main` (local-only until then).
- **Force-quit Rekordbox:** if hang > few minutes, quit from Activity Monitor; before CRATER/xml writes run `python3 -c "… require_xml …"` or reload only after confirming `rekordbox.xml` parses (backup: `rekordbox.xml.prune.bak`).
- **Rekordbox:** no documented “flush all pads to Capture folder on quit” — use **CAPTURE → drag to slot** (or Export Loop As WAV) as the native disk path for ix.

---

*Vibe coding: Cursor session distilled for alkalurop Google Drive. Git truth for routing remains `blackhole` + `ix` docs.*
