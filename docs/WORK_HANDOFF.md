# Worship Guide — Work Handoff (2026-10-06)

## Goal
Complete a stable Worship Guide MVP this year without continuing the old cycle of downloading a new ZIP for every small fix.

The product goal is:

PDF / image import
→ OCR
→ human review
→ Song / Arrangement / Score Variant WGDB
→ metadata + multi-filter search
→ Collection / songbook builder
→ PDF export
→ setlist
→ later AI recommendations + web/mobile

## Canonical working branch
- Repository: byounheeyoung-arch/worship-guide
- Branch: `reboot-2026-10`
- Do NOT work from the old scattered ZIP folders as the primary source.
- Do NOT overwrite user data during code updates.

## What was recovered
The repository default branch only contained a minimal README, .gitignore, and LICENSE.
The latest working desktop prototype was preserved in Google Drive under the Worship Guide folder as:
- `worship-guide-v2.0.2`
- `worship-guide-v2.0.2.zip`
- original merged score PDF: `pdf24_merged.pdf`
- master metadata sheet: `WGDB Master 구글시트`

The v2.0.2 source has been imported into `reboot-2026-10`.

## Important product decisions already made

### Data model
A song and a score are not the same thing.

```
Song
  └─ Arrangement
       └─ Score Variant
            ├─ Key
            ├─ source PDF
            ├─ page range
            ├─ score image/file
            ├─ raw OCR title
            ├─ OCR confidence
            └─ review status
```

Example:
```
예수 닮기를
├─ Original / E / page 1
├─ Original / F / page 2
└─ Original / G / page 3
```

The same song may have several pages because each page is a different key. Never collapse those score variants.

### Human review philosophy
- OCR output is a candidate, never the final truth.
- Preserve the raw OCR text.
- Preserve the human-corrected title separately.
- Preserve review history.
- Reuse previous corrections as future title suggestions.
- User editing and community recommendations must remain possible.

### Collection / songbook
Users must be able to build collections using multiple simultaneous filters:
- theme
- mood
- key
- scripture
- flow
- difficulty
- custom tags

A CollectionItem must point to a specific Score Variant, not only to a Song.
This allows one collection to use G key while another uses E key for the same song.

### PDF output
Support:
1. simple merged score PDF
2. guidebook PDF with cover + TOC + sections + metadata
3. setlist pack with order / notes / selected score variants

## Existing master metadata
The connected Google Sheet already has these tabs:
- Songs
- Themes
- Flow
- Bible
- Relations
- Sets
- Community
- Books
- Dashboard

The Songs sheet already contains a small gold-standard seed set with WGIDs and metadata.
Treat this as valuable seed data, not disposable test data.

## Known issues / technical debt

### 1. Review Center bug found and patched
In the imported v2.0.2 source, `_detect_key_candidate` was accidentally dedented outside the `ReviewCenter` class, while `approve`, `prev`, and `next` were nested underneath it. This can break review behavior.

A fix has already been committed on `reboot-2026-10`:
- place `_detect_key_candidate` inside `ReviewCenter`
- keep `approve`, `prev`, and `next` as sibling methods
- reset stale key candidate state when moving between pages

Review this file first before any new feature work.

### 2. Key detection is not reliable enough
Current heuristic OCRs the top region, extracts chord roots, and guesses the tonic.
This is only a candidate and must never silently become authoritative.
Improve it using:
- explicit printed key markings when present
- chord-sequence heuristics
- first/last cadence clues
- confidence threshold
- easy manual override
- store raw evidence used for the guess

### 3. OCR title quality
EasyOCR works, but Korean score titles have errors such as:
- 예수 닭기틀 → 예수 닮기를

Desired behavior:
- fuzzy match against WGDB title/alias lexicon
- use previous human corrections
- show 1 best recommendation + alternatives
- do not auto-commit low-confidence matches

### 4. DB duplication
Older prototypes contain both `db.py` and `wgdb_v2.py`.
Consolidate to one canonical database layer with migrations.
Do not leave two competing schemas.

### 5. Packaging / version sprawl
Old workflow created v0.x/v1.x/v2.x folders and ZIPs.
Stop doing that.
Use:
- one repository
- one main application
- semantic releases/tags only when meaningful
- migrations for data changes

### 6. Data must survive upgrades
Store user data outside replaceable package code.
Recommended:
```
data/
  wgdb.sqlite3
  source/
  work/
  exports/
```
Never delete or recreate the DB automatically on upgrade.

## Required MVP before moving to AI/web

### Phase A — stable desktop core
- [ ] one canonical package / launcher
- [ ] clean DB migration layer
- [ ] PDF import
- [ ] page rendering
- [ ] title OCR
- [ ] key candidate extraction
- [ ] review center with score preview
- [ ] keyboard review flow
- [ ] Song / Arrangement / Score Variant persistence
- [ ] reopen app and verify persistence
- [ ] 20-page end-to-end smoke test
- [ ] only then process full 552-page PDF

### Phase B — metadata/search
- [ ] title / alias / lyricist / composer
- [ ] theme
- [ ] mood
- [ ] worship flow
- [ ] scripture
- [ ] BPM / meter
- [ ] difficulty
- [ ] user-defined tags
- [ ] multi-filter search (AND across fields, OR within same field)

### Phase C — Collections
- [ ] create/edit/delete collection
- [ ] filtered candidate search
- [ ] choose Score Variant per song
- [ ] reorder items
- [ ] sections
- [ ] saved filters + chosen items
- [ ] update suggestions when DB gains matching songs

### Phase D — PDF export
- [ ] simple merge
- [ ] cover
- [ ] TOC
- [ ] section dividers
- [ ] title / key / theme / scripture metadata
- [ ] page ordering verification
- [ ] Korean font handling

### Phase E — Setlist
- [ ] worship-date/service metadata
- [ ] ordered songs
- [ ] selected score variant
- [ ] transition notes
- [ ] PDF pack

## Acceptance test before calling the MVP stable
Use a 20-page slice containing:
- a song repeated in multiple keys
- at least one OCR title error
- at least one page with a readable key marking
- at least one page where key detection should remain unknown

Verify:
1. no duplicate Song is created for key variants
2. every page remains available as a distinct Score Variant
3. corrected title is remembered as a future suggestion
4. wrong/low-confidence key does not silently overwrite human choice
5. closing and reopening retains all reviewed data
6. collection selects the intended score variant
7. exported PDF pages match the collection order

## Working style
Do not stop for minor implementation decisions. Make reasonable choices, document them, and keep moving.
Prefer tests and migrations over one-off manual fixes.
Do not create a new ZIP per bug.
Do not ask the user to run a terminal command after every small code change.
Produce a testable checkpoint only after a coherent feature slice is stable.
