# Changelog

## 0.1.2 (2026-10-05) — laya-seo fork

Cascade: local Laya discriminative model as a confidence gate in front of Jev.

- Added `--cascade {laya-first,jev-first,offline}`. `laya-first` (default) asks Laya
  first and only escalates a page to Jev when the page-weighted confidence misses
  `--laya-page-accept` (default 0.80). Judgment results keep the upstream shape, so
  score / report / xlsx / md layers are unchanged.
- Only `choice` primitives count toward acceptance. `score` and `noul` confidence was
  measured to be inconsistent with Laya's actual answer (a `noul=0.297` "no" reported
  confidence 0.703), and including them pinned the savings rate at 0%.
- Page state sent to Laya is trimmed to 1800 chars of body text, 12 outline items and
  8 CTAs (`cli.py:_shrink_for_laya`); `STATE_TOKEN_LIMIT` raised 900 to 2000. Chinese
  pages measured 1000-1546 tokens at 6000 chars and were all blocked before this.
- Jev client now batches 2 questions per request, serially with a 1.1s pause, at page
  concurrency 2, with a `TEXT_STEPS` retry ladder. Needed because relay providers return
  `HTTP 422 token_budget_exceeded` against an account-cumulative quota: `counted_tokens`
  was constant regardless of how many questions were sent.
- Jev refusals fall back to Laya's raw answers tagged `laya_fallback=True`, so a page is
  never silently missing.
- Relay endpoints are configurable: `JEV_API_BASE` and `JEV_MODEL` override the official
  `https://api.typesafe.ai/v1/systemone` + `jev-latest`.
- Reports can be rendered in Chinese from one `audit.json`: `--lang {en,zh,both}`.
  Translation happens in the render layer, so both languages share every number.
  `jevseo/i18n.py` holds 74/74 rule translations and 228 vocabulary entries.
  Workbook sheet names stay English because Chinese names break `COUNTIF` references silently.
- Added an `Engine` column to the workbook's `Semantic judgments` sheet and an engine
  disclosure section to the Markdown report, so every judgment can be traced to
  `Jev cloud` / `Laya local` / `Laya (fallback)` / `Rule` / `code`.
- `jev_api` failures and request counts are now surfaced in `digest.md` instead of being lost.
- Added `docs/USER-MANUAL.md` and rewrote `README.md` as its index.
- Tests: 55 offline cascade cases added (`tests/test_cascade.py`); no weights, keys or spend.
- Fixed: `doctor` no longer crashes when WeasyPrint is installed but its Pango DLLs are missing. It reports `broken (OSError: ...)` plus `pdf: unavailable` instead of dying.

## 0.1.1 (2026-09-22)

Found by a clean-machine test (fresh clone, empty home folder, no keys):

- Fixed: the workbook crashed when a sheet had no rows, for example the Jev sheet when no TypeSafe key is set. Every formatting range now skips empty sheets.
- An audit without Jev or PageSpeed is now labelled a partial audit on the cover, gauge, scorecard, workbook, Markdown and digest, with the reason.
- Keys can come from `$JEVSEO_ENV_FILE`, `./.env` or the repository's `.env` (template `.env.example`), not only the environment.
- Inter and JetBrains Mono are bundled (SIL OFL) and loaded by the PDF and charts, so reports look the same on machines without the fonts installed.
- The automatic summary keeps acronyms such as AI in running text.
- `requirements.txt`, WeasyPrint system library notes and optional Playwright setup in the README; CI runs on Python 3.10, 3.12 and 3.13; the checks badge uses GitHub's own workflow badge so it works on a private repository.

## 0.1.0 (2026-09-22)

First release.

- Live crawl from a homepage: robots.txt and Crawl-delay, sitemaps, internal links, redirects kept separate from pages, JavaScript rendering for script-only pages, a private-network guard on every hop, charset-safe decoding.
- 52 deterministic rules tied to Google Search Central and web standards, including structured-data properties Google requires for rich results. Heuristics are labelled.
- Jev (TypeSafe System One) judgments batched per page and per site, plus competing page pairs. Question wording and the decisiveness measure were chosen by A/B tests against blind labels; see `references/evaluation.md`.
- PageSpeed Insights: Chrome UX Report field data and Lighthouse lab scores.
- Optional `--full` mode with DataForSEO: rankings, keywords, competitors, referring domains, live SERPs, AI answer mentions, filtered by Jev relevance and mapped to pages. Hard budget caps and per-call cost ledgers for Jev and DataForSEO. `--reuse-dfs` avoids paying twice.
- Reports: designed PDF, Excel action tracker, Markdown with charts, all from one `audit.json`. The narrative is checked for unknown action IDs, numbers the audit does not contain and mismatched effort bands.
- `rescore` rebuilds findings offline. 37 offline tests.
