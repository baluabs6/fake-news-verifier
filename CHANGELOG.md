# Changelog

## 0.3.0 - scheduled ingestion
- Added `ingest/`: daily fact-check ingestion from ClaimReview markup, with feed/sitemap auto-discovery, robots.txt
  compliance, same-site-only fetching, rate limiting, `--check-sources`, `--dry-run`, `--refresh`.
- Added rating normalisation (English, Hindi, Telugu wording) and `canonical` / `lang` columns on `fact_checks`
  (additive migration runs automatically at startup). The verdict prompt now sees the normalised rating.
- Revised ratings now overwrite stored ones (upsert) instead of being ignored.
- Added GitHub Actions: CI (tests) and a daily ingest workflow. Added `.fastapicloudignore`.
- README: overview, comparison with existing approaches, end-user benefits, tech stack table.
- README: architecture diagrams (system, request sequence, pipeline, data model, ingestion/CI/evaluation).
- 9 new tests (parsers, robots handling, collection logic, hostile XML).

## 0.2.1 - bug-fix release
- Fixed: language picker on the result page never changed (AngularJS `ng-if` child scope). Share message is now editable and the WhatsApp link follows the edited text.
- Fixed: re-check/fetch broke for article URLs containing long digit runs (the privacy redactor rewrote the URL). URLs are no longer redacted.
- Fixed: Hindi and Telugu words were split at vowel signs in search and de-duplication.
- Fixed: verdicts were matched to claims by position; now by `claim_index`. Skipped claims become Unverified instead of vanishing.
- Fixed: malformed model output (missing keys, wrong types, invented evidence ids) could crash a check; every field is now coerced.
- Fixed: a new HTTP client was created for every model call (resource leak); one cached client is reused.
- Fixed: Neon/Supabase pooled connections failed with prepared-statement errors; statement cache is disabled for pooler hosts.
- Fixed: rate limiter trusted the client-supplied first `X-Forwarded-For` entry (spoofable); now uses the entry added by your proxy (`TRUSTED_PROXY_HOPS`). Memory use is bounded.
- Fixed: stored fact-checks saved the review title instead of the claim text, weakening local search.
- Fixed: web search was restricted to news; now general.
- Fixed: tables were never created if the database was down at startup; creation now retries in the background.
- Added: 100 s pipeline timeout (504), concurrent-check cap, 3 MB page cap, stricter SSRF check (`is_global`), defence-in-depth tag stripping in the prompt builder.
- Added: tests for the verification pass (8 scenarios incl. garbage model output), Indic tokenising, proxy IP handling.
