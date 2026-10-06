# Code audit — 2026-10-06

Baseline: `aa77b1052caa01cb8b346a0a94e3a73a84d0e8a4`, `reboot-2026-10`, Draft PR #2.

Drive v2.0.2 source was byte-compared with the recovered branch. The patched ReviewCenter was the intentional difference; `models.py` was absent from GitHub and has been restored with dataclasses so the filename builder imports successfully. The source PDF has 552 image-only pages. The reference Sheet has 20 seed songs, all marked awaiting human review, plus Themes / Flow / Bible / Relations / Sets / Community / Books / Dashboard.

## Findings and resolutions

| Severity | Finding | Resolution |
| --- | --- | --- |
| Critical | Review uses `wgdb_v2` while Collection/editor uses incompatible `db.py` tables. | One WGDB and transactional migrations; old v2 is an API adapter. Canonical `score_variants`; `scores` is a read-only compatibility view. |
| Critical | Code/CWD-dependent data paths can select different DBs or lose data after replacing folders. | Stable per-user storage; preserve original legacy databases; copy/adopt only an unambiguous old DB. |
| High | Blank source path after restart can collide with another PDF/page and overwrite it. | SHA-256 source identity, managed source copies, persisted jobs/pages and source IDs. |
| High | Approval commits Song, Arrangement and score independently. | Atomic approval + review history + correction memory; rollback on failure. |
| High | Key candidate is prefilled and can silently become approved value. | Candidate/evidence separate from confirmed Key; manual application; unknown and conflict states remain unknown. |
| High | Raw title uses corrected CSV field; reapproval/re-OCR may replace evidence. | Raw observations retained per engine; score raw title remains immutable; corrections and review events separate. |
| High | PDF export silently skips missing items and can replace a prior valid output with an incomplete book. | Strict validation by default, atomic replacement; original input cannot be used as output. |
| High | Collection references can select/delete the wrong score or lose order. | Specific variant IDs, preserved ID mapping on mixed-schema migration, referential integrity, ordered rendering checks. |
| Medium | Old widget workers read Tk variables and call `after` from background threads. | Capture values on UI thread, Queue-based progress, thread-local SQLite connection, checkpointed cancellation. |
| Medium | Arrow keys navigate pages while typing. | Entry/Text caret preserved; Ctrl+arrows navigate. |
| Medium | OCR title scoring overweights lyric/chord width. | Prefer title typography/upper position; exclude chord clutter; human review remains required. |
| Medium | Tesseract custom tessdata folder may lack the `tsv` config. | Explicit TSV variables plus output format validation. |
| Medium | No cover, Korean TOC, sections, metadata, transition notes. | Guidebook and setlist PDF modes with embedded CJK font, links/bookmarks and original score pages. |
| Medium | Hardcoded `C:\wge-venv` shortcuts, several UIs/launchers. | All launchers forward to one app; per-checkout environment; one-time setup and branch updates. |

## Verification scope

Original tests: **3 passed**, but they did not test the active v2 review flow, schema mixing, restart, actual OCR or desktop integration. New automated tests include the three original tests plus legacy/mixed/failure migrations, stable source identity, 20-page synthetic pipeline, cancellation, review rollback, manual key precedence, exact Collection/PDF order, Korean output, master data preservation and real Tk widgets. Actual scan OCR is recorded separately in the progress report.

The user's original DB on Windows was not provided. Migration compatibility is tested against both recovered schema fixtures and mixed ID collisions; this is not a claim to have inspected that particular live database. Windows-native execution and packaging require their own validation.
