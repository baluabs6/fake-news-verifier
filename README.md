# Fake News Verifier

> Evidence-based checking for claims, headlines, WhatsApp forwards and article links. It does not guess "real or fake"
> from writing style. It finds what trustworthy sources have said, shows that evidence, and tells you how strong it is.

**Contents:** [What it is](#what-is-this-application-about) ·
[How it is different](#why-is-this-application-different-from-existing-applications) ·
[How it helps users](#why-and-how-does-it-help-end-users) · [Stack](#application-stack) ·
[Architecture](#architecture) · [Run locally](#run-locally) · [Deploy](#deploy-to-fastapi-cloud)

## What is this application about?

Misinformation mostly travels as forwards: a scary message, a doctored screenshot, an old news story shared as if
it were new. Fact-checks usually exist somewhere, but they are scattered across many sites, often only in English, and
hard to find when you are holding a message on your phone.

Fake News Verifier is a website (installable as a phone app) where you paste a claim or an article link and get back:

- a **verdict**: True, False, Misleading or Unverified (or Not Checkable for opinions and satire);
- an **evidence strength** score and a breakdown of how it was calculated;
- the **sources**, grouped into those that support the claim and those that contradict it, each with a reliability score;
- a **reply-ready message** (English, Hindi or Telugu) you can send back to the person who forwarded it.

The key design rule: **the AI is not allowed to answer from its own memory.** The app first retrieves evidence
(a database of published fact-checks, the Google Fact Check API, and live web search), and Claude may only reason over
that evidence. A second pass then checks that every conclusion is backed by a cited source and downgrades the verdict
to Unverified when it is not. "We could not verify this" is a normal, first-class answer.

```mermaid
flowchart LR
  A["Paste claim<br/>or link"] --> B["Extract the<br/>checkable claims"] --> C["Retrieve evidence<br/>fact-checks, news"] --> D["Verdict from<br/>evidence only"] --> E["Verification pass<br/>every claim needs a source"] --> F["Result, sources,<br/>share message"]
```

It is also a portfolio project that demonstrates agentic retrieval-augmented generation (RAG), multi-source retrieval,
structured model output, evaluation, and a full-stack deployment.

## Why is this application different from existing applications?

| Typical approach | Where it falls short | What this application does instead |
|---|---|---|
| **Fact-check websites** | They only cover claims someone already investigated, and you must search each site yourself. | Searches many fact-checkers and live news at once, keeps a growing local database of fact-checks, and says Unverified when nothing reliable exists. |
| **Asking a general chatbot "is this true?"** | The answer comes from the model's memory: no sources, can be confidently wrong, can be out of date. | The model may only use retrieved evidence. Every verdict must cite sources, and a verification pass downgrades unsupported ones. Results carry an expiry date and a re-check button. |
| **Platform warning labels** | Opaque: you see a label, not the reasoning. | Shows the evidence, which sources support or contradict, each source's reliability, and exactly how the strength score was computed. |
| **"Fake probability" classifiers** | Judge writing style, not facts, and give a bare number. | No style guessing. Verdicts come from evidence, and the app abstains when evidence is thin. |
| **English-only tools** | Miss most Indian forwards. | Accepts Hindi and Telugu claims, produces replies in three languages, weights Indian fact-checkers, and installs as an app that appears in the Android Share menu. |

**Design principles**
- **Evidence first, abstain when unsure.** Unverified is a verdict, not a failure.
- **Transparent.** Sources, stances, reliability and the strength calculation are all visible. Copies of the same story count as one source.
- **Measurable.** An evaluation module reports accuracy, calibration and the rate of confident wrong answers, and compares the app against a plain-LLM baseline.
- **Safe by design.** Personal data (phone, email, Aadhaar, PAN, UPI) is redacted before storage or model use; fetched pages are treated as untrusted (prompt-injection hardening); URL fetching is guarded against internal-network access.
- **Human in the loop.** Users can flag a verdict, and reviewers can correct it. Their labels feed the evaluation set.

**Honest limits.** This is decision support, not an oracle. It can be wrong, and it does not replace professional
fact-checkers. It does not detect AI-generated images. Retrieval works best for English-language claims today. See
[Known limits](#known-limits).

## Why and how does it help end users?

| What the person needs | How the app helps |
|---|---|
| "I got a scary forward. Is it real?" | Paste it, or share it straight from WhatsApp to the installed app (Android). A verdict with sources typically comes back in well under a minute. |
| "Why should I trust the answer?" | Sources are split into *supports* and *contradicts*, each with a reliability score and a "how is this calculated?" breakdown, so you can judge for yourself. |
| "What if nobody has checked this yet?" | You get an honest Unverified instead of a guess. Old results are marked out of date and can be re-checked. |
| "How do I tell my family it is false?" | One tap creates a short message in English, Hindi or Telugu with the verdict, a source and a link, ready to send on WhatsApp. |
| "Is this message a scam?" | Warning signs are flagged: KYC or lottery bait, shortened links, look-alike bank domains. These are warnings, not verdicts. |
| "Is it safe to paste private messages?" | Personal identifiers are removed first, and there is a "don't save this check" option. |
| "I think the verdict is wrong." | Report it. A human reviewer looks at flagged and low-confidence results. |
| "What is going around right now?" | A Trending page lists claims that several different people checked this week. |

**How to use it:** 1) paste a claim or link, or share to the app, 2) wait while it searches and verifies,
3) read the verdict, the sources and the strength breakdown, 4) copy the reply message or the result link.

**What the results mean**

| Verdict | Meaning |
|---|---|
| **True** | Reliable sources back the claim. |
| **False** | Reliable sources contradict the claim. |
| **Misleading** | Partly right, missing context, or exaggerated. |
| **Unverified** | Not enough reliable evidence to decide either way. |
| **Not Checkable** | An opinion, question or satire, not a factual claim. |

*Evidence strength* is not "the probability the claim is true." It measures how strong the evidence behind the verdict
is: how many independent sources agree, how reliable the best one is, whether a published fact-check backs it, and
whether other sources conflict.

## Application stack

| Layer | Technology | Role |
|---|---|---|
| **Frontend** | AngularJS 1.8 with ngRoute, plain CSS, Google Fonts (Newsreader, Public Sans) | Single-page app: check form, result page, history, trending, reviewer queue |
| **Mobile / PWA** | Web App Manifest, service worker, Web Share Target | Installable; appears in the Android Share menu |
| **Backend** | Python 3.11+, FastAPI, Pydantic v2, pydantic-settings, httpx | JSON API, validation, rate limiting, static file hosting |
| **Orchestration** | LangGraph | The verification pipeline: extract, retrieve, verdict, verify |
| **AI** | Claude (Anthropic API) with forced tool-use for structured JSON | Claim extraction, verdicts with stances, independent verification pass |
| **Retrieval** | Google Fact Check Tools API, Tavily web search, PostgreSQL full-text search | Evidence from fact-checkers, fresh news, and the stored corpus |
| **Content extraction** | trafilatura, SSRF-guarded fetcher | Turns article URLs into clean text safely |
| **Database** | PostgreSQL (SQLAlchemy 2 async, asyncpg, JSONB, GIN full-text index) | Fact-check corpus, saved checks, flags, reviews |
| **Hosting** | FastAPI Cloud, hosted Postgres (Neon or Supabase) | One deployable app plus a managed database |
| **CI/CD & jobs** | GitHub Actions | Tests on every push, daily fact-check ingestion, optional auto-deploy |
| **Quality** | pytest, built-in evaluation runner | Unit tests, ablation reports (baseline vs retrieval vs full pipeline) |
| **Local dev** | uv or pip, Docker Compose (Postgres) | `fastapi dev` with a local database |

## Architecture

Diagrams use [Mermaid](https://mermaid.js.org/); GitHub, GitLab and VS Code (with a Mermaid extension) render them.

### 1. System overview
One deployable app: FastAPI serves both the JSON API and the AngularJS single-page app.

```mermaid
flowchart LR
  subgraph Client["Browser or phone"]
    UI["AngularJS 1.8 SPA"]
    PWA["PWA: service worker<br/>and Android share target"]
  end

  subgraph Cloud["FastAPI Cloud: one app"]
    STATIC["Static files<br/>index.html, views, app.js"]
    GUARD["Guards: rate limit,<br/>input caps, CORS"]
    API["Public API<br/>/api/check, /api/checks,<br/>/api/trending, /share"]
    ADMIN["Reviewer API<br/>/api/admin/*<br/>needs X-Admin-Key"]
    SVC["Services: URL fetch with SSRF guard,<br/>PII redaction, scam signals,<br/>share cards in en, hi, te"]
    GRAPH["LangGraph<br/>verification pipeline"]
  end

  subgraph External["External services"]
    CLAUDE["Anthropic Claude API"]
    GFC["Google Fact Check<br/>Tools API"]
    WEB["Tavily web search"]
  end

  PG[("PostgreSQL<br/>Neon or Supabase")]

  UI -->|"HTML, JS, CSS"| STATIC
  UI -->|"HTTPS JSON"| GUARD
  PWA -.->|"installs and shares into"| UI
  GUARD --> API
  GUARD --> ADMIN
  API --> SVC
  SVC --> GRAPH
  GRAPH -->|"structured output"| CLAUDE
  GRAPH --> GFC
  GRAPH --> WEB
  GRAPH <-->|"full-text search, store fact-checks"| PG
  API -->|"save checks, flags"| PG
  ADMIN -->|"queue, reviews, stats, export"| PG
```

### 2. What happens on `POST /api/check`
```mermaid
sequenceDiagram
  autonumber
  actor U as User
  participant FE as AngularJS app
  participant API as FastAPI
  participant G as LangGraph pipeline
  participant LLM as Claude
  participant DB as PostgreSQL
  participant EXT as Fact Check API and web search

  U->>FE: Paste claim or article link
  FE->>API: POST /api/check
  API->>API: Rate limit, redact personal data, fetch article if URL
  API->>G: run_pipeline
  G->>LLM: Extract checkable claims
  alt No checkable claim (opinion, satire)
    G-->>API: Not Checkable
  else Claims found
    par Local corpus
      G->>DB: Full-text search of stored fact-checks
    and Live sources
      G->>EXT: Fact-checks and news for each claim
      G->>DB: Store new fact-checks
    end
    G->>G: Score source credibility, group duplicate sources
    G->>LLM: Verdict, stance of every source, citations
    G->>LLM: Verification pass on the cited evidence
    G->>G: Downgrade unsupported verdicts, compute evidence strength
    G-->>API: Result
  end
  API->>DB: Save check
  API-->>FE: Result JSON
  FE-->>U: Verdict, sources, share message
```

### 3. Verification pipeline (LangGraph)
The model never decides from memory: it only reasons over retrieved evidence, and a second pass can overrule it.

```mermaid
flowchart TD
  IN(["Claim, post or article text"]) --> EXTRACT["extract: up to 3 atomic claims"]
  EXTRACT --> Q{"Any checkable claims?"}
  Q -->|"no"| NC["Result: Not Checkable"]
  Q -->|"yes"| RET

  subgraph RET["retrieve: runs in parallel for each claim"]
    direction LR
    R1["Stored fact-checks<br/>Postgres full-text"]
    R2["Google Fact Check API"]
    R3["Tavily web search"]
  end

  RET --> RANK["Rank by source credibility and recency,<br/>group syndicated copies into one source"]
  RANK --> VERDICT["verdict: Claude returns verdict,<br/>stance per source, citations"]
  VERDICT --> VERIFY

  subgraph VERIFY["verify: second pass"]
    direction TB
    V1["Drop invented citation ids"] --> V2["Does a cited source's stance<br/>back the verdict?"]
    V2 --> V3["Independent Claude check:<br/>is the reasoning in the sources?"]
    V3 --> V4["Compute evidence strength:<br/>independent sources, reliability,<br/>fact-checker backing, conflicts"]
  end

  VERIFY --> OUT(["Result: verdict, strength, cited sources,<br/>expiry date, token usage"])
  NC --> OUT
```

### 4. Data model
```mermaid
erDiagram
  CHECKS ||--o{ FLAGS : "flagged by users"
  CHECKS ||--o| REVIEWS : "reviewed by a person"

  CHECKS {
    string id PK
    string client_id
    string input_type
    text input_text
    string verdict
    float confidence
    jsonb result
    datetime created_at
  }
  FLAGS {
    int id PK
    string check_id FK
    string reason
    text note
    string status
    datetime created_at
  }
  REVIEWS {
    string check_id PK, FK
    string verdict
    text note
    datetime reviewed_at
  }
  FACT_CHECKS {
    int id PK
    text claim
    string rating
    string canonical
    string publisher
    text url UK
    string reviewed_at
    string lang
    datetime created_at
  }
```
`fact_checks` is the retrieval corpus (filled by the ingester and by every Fact Check API lookup). The other three tables hold user activity.

### 5. Data ingestion, CI/CD and evaluation (outside the request path)
```mermaid
flowchart LR
  CRON["GitHub Actions<br/>daily schedule"] --> ING["python -m ingest.run"]
  ING -->|"robots.txt, feeds or sitemaps"| SITES["Fact-check sites<br/>Alt News, BOOM, Factly, ..."]
  SITES -->|"ClaimReview JSON-LD"| ING
  ING -->|"upsert with normalised rating"| FC[("fact_checks")]

  DEV["git push"] --> CI["CI: pytest"]
  CI --> DEPLOY["fastapi deploy<br/>(workflow from fastapi cloud setup-ci)"]
  DEPLOY --> APP["FastAPI Cloud app"]

  EVAL["python -m eval.run_eval"] -->|"labelled claims, 3 ablation modes"| PIPE["Same LangGraph pipeline"]
  EVAL --> REPORT["Markdown report:<br/>accuracy, calibration,<br/>high-confidence-wrong rate"]
  REV["Reviewer export<br/>/api/admin/export"] -->|"JSONL labels"| EVAL
```

### Project layout
```text
app/
  main.py            FastAPI app, /share target, static mount, DB init with retry
  config.py db.py models.py schemas.py
  api/               routes.py (public), admin.py (reviewers), deps.py (rate limit, admin key)
  services/
    verify.py        LangGraph pipeline: extract, retrieve, verdict, verify
    evidence.py      Postgres full-text + Google Fact Check + Tavily retrieval
    quality.py       independent-source clustering, computed confidence
    credibility.py   domain reliability table, recency
    ratings.py       normalise fact-checker wording to True/False/Misleading/Unverified
    ingest.py        safe article fetch (SSRF guard, trafilatura)
    privacy.py scam.py sanitize.py cards.py llm.py
  static/            AngularJS app, views/, PWA manifest, service worker
ingest/              daily fact-check ingester (ClaimReview parsing, robots-aware fetching)
eval/                evaluation runner, metrics, datasets
tests/               unit tests (pure logic, verification pass, ingester, API smoke)
.github/workflows/   ci.yml, ingest.yml
```

## Run locally
```bash
docker compose up -d db                 # local Postgres
cp .env.example .env                    # add ANTHROPIC_API_KEY (+ optional GOOGLE_FACTCHECK_API_KEY, TAVILY_API_KEY)
uv sync                                 # or: python -m venv .venv && pip install -r requirements.txt
uv run fastapi dev                      # http://127.0.0.1:8000  (docs at /docs, health at /api/health)
uv run pytest
```

## Deploy to FastAPI Cloud
1. Create a hosted Postgres. FastAPI Cloud has Neon and Supabase integrations that set `DATABASE_URL` for you
   (check your dashboard); otherwise use any hosted Postgres and copy its connection string.
2. `fastapi login`  (opens your browser)
3. Set configuration (secrets are write-only):
```bash
fastapi cloud env set --secret DATABASE_URL "postgresql://USER:PASS@HOST/DB?sslmode=require"
fastapi cloud env set --secret ANTHROPIC_API_KEY "sk-ant-..."
fastapi cloud env set --secret GOOGLE_FACTCHECK_API_KEY "..."
fastapi cloud env set --secret TAVILY_API_KEY "..."
fastapi cloud env set ENVIRONMENT "production"
```
4. `fastapi deploy`  (reads `[tool.fastapi] entrypoint` from pyproject.toml)
5. Open the URL it prints, then check `/api/health`: `database`, `anthropic_configured` must be `true`.

If `env set` complains the app does not exist yet, run `fastapi deploy` once, set the variables, deploy again.

## API
| Method | Path | Purpose |
|---|---|---|
| POST | /api/check | `{"text": "..."}` or `{"url": "..."}` -> verdict |
| GET | /api/checks/{id} | Shareable result |
| GET | /api/checks | Your history (header `X-Client-Id`) |
| POST | /api/checks/{id}/recheck | Re-run a stale check |
| GET | /api/checks/{id}/card?lang=en\|hi\|te | Reply-ready message |
| POST | /api/checks/{id}/flag | Report a wrong verdict |
| GET | /api/trending | Claims checked by 3+ people this week |
| GET | /api/health | Config + DB status |
| GET/POST | /api/admin/queue, /stats, /export, /review/{id} | Reviewer tools (header `X-Admin-Key`) |

## Features added in v0.2
- **Independent sources:** syndicated copies and same-site items count once. **Stance per source** (supports / contradicts).
- **Computed evidence strength** instead of the model's own confidence (weights live in `app/services/quality.py`; tune them with the eval report).
- **Verdict expiry:** results carry `stale_after`; stale ones offer a re-check.
- **Reply card** in English, Hindi, Telugu (have a native speaker review the wording) + WhatsApp link.
- **PWA:** installable; on Android Chrome the installed app appears in the Share sheet (`/share` target). iOS does not support this, paste still works.
- **Review queue:** users flag verdicts, reviewers use `/#!/admin` (set `ADMIN_KEY`), `/api/admin/export` produces labelled JSONL for the eval runner.
- **Privacy:** phone, email, Aadhaar, PAN, UPI and card numbers are redacted before storage and before the model sees them; "don't save" option.
- **Scam signals:** heuristic warnings (shorteners, look-alike bank domains, KYC/lottery bait). Warnings, not verdicts.
- **Prompt-injection hardening:** tag stripping on all untrusted text; `tests/test_injection_live.py` (needs `ANTHROPIC_API_KEY`).
- **Usage tracking:** tokens per check in results, `/api/admin/stats`, and an "Avg tokens" column in eval reports.

## Scheduled ingestion (grows the fact-check database daily)
```bash
python -m ingest.run --check-sources            # what feed/sitemap does each site in ingest/sources.json resolve to?
python -m ingest.run --dry-run --since-days 3   # fetch + parse, print rows, write nothing
python -m ingest.run --since-days 3             # upsert into DATABASE_URL
```
- Reads schema.org `ClaimReview` markup from each fact-check page; stores only claim, rating, publisher, date and link.
- Finds feeds automatically (`<link rel="alternate">`), falls back to `robots.txt` sitemaps. Add `"feeds": [...]`,
  `"sitemaps": [...]` or `"url_contains": "fact-check"` to a source in `ingest/sources.json` to override or narrow it.
- Polite by design: obeys robots.txt, same-site URLs only, 1 s between requests per host, 25 pages per source per run.
  Set `INGEST_USER_AGENT` to something that includes your contact URL, and read each site's terms before enabling it.
- Ratings are normalised to True / False / Misleading / Unverified (`app/services/ratings.py`); the raw wording is kept.
- Revised fact-checks: run with `--refresh` (or the manual workflow's "refresh" option) to overwrite stored ratings.
- `.github/workflows/ingest.yml` runs it daily. Add repository secret `DATABASE_URL` (and optionally variable
  `INGEST_USER_AGENT`). GitHub pauses scheduled workflows after 60 days without repo activity.
- **Run `--check-sources` before the first scheduled run.** I could not verify these sites' current feed URLs from my
  environment, and some sites do not publish ClaimReview markup; the summary table shows which ones yield rows.

## CI/CD
`.github/workflows/ci.yml` runs the tests on every push. For auto-deploy, let FastAPI Cloud write the workflow and
secrets for you: run `fastapi cloud setup-ci` (the command name differs between CLI versions, so check `fastapi cloud --help`).
It sets `FASTAPI_CLOUD_TOKEN` and `FASTAPI_CLOUD_APP_ID` as GitHub secrets.

## Evaluation
```bash
python -m eval.run_eval --data eval/sample_claims.jsonl --modes baseline rag full          # 4-claim smoke test only
python -m eval.run_eval --data data/liar/test.tsv --format liar --limit 100 \
    --modes baseline rag full --exclude-domain politifact.com
```
Modes are ablations: `baseline` (Claude alone), `rag` (retrieval, no verification), `full` (shipped pipeline).
Reports (summary, confusion matrix, calibration, high-confidence-wrong rate) land in `eval/reports/`.
Run once with `--exclude-domain` (no answer leakage) and once without, and report both.
`eval/sample_claims.jsonl` is a smoke test with famous claims, not a benchmark. Download LIAR separately and
hand-label 50-100 Indian claims in the same jsonl format.

## Known limits
- Rate limiting is in-memory and per instance (resets on restart). Use Redis for a shared limit.
- URL fetching checks the resolved IP before connecting, but DNS rebinding is not fully closed. Put the app behind an egress allowlist if you open it to the public.
- Computed-strength weights (`app/services/quality.py`) and the scam heuristics are starting points, not calibrated values.
- Hindi/Telugu card wording needs a native-speaker review.

## Next steps
Image/screenshot input (Claude vision), Hindi/Telugu UI strings, pgvector semantic search over `fact_checks`,
WhatsApp/Telegram bot, Redis cache + shared rate limiting, Alembic migrations, evaluation set (LIAR / Indian fact-check archives).
