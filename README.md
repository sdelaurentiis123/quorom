# Quorum

Adversarial peer review for research papers. Drop in a paper (arXiv URL or PDF upload); an orchestrator LLM identifies the weakest surfaces of the argument; a panel of specialist reviewer agents works in parallel against those surfaces, each writing and executing Python in an isolated sandbox to verify or falsify numerical claims; three senior reviewers reconcile the findings; a final composer produces a multi-page referee report that renders as a PDF with an accompanying "revisions prompt" ready to paste into Claude Code.

Localhost-only. Single-user. Built in front of an interview panel, so the architecture favors clarity over production polish.

---

## Why

Peer review today is slow, inconsistent, and gated by the availability of specific experts. The ambition behind Quorum is not to replace that process — it's to show what an adversarial, tool-using panel of LLM reviewers can actually do when you take their critique seriously: run code, cross-reference prior art, point at the exact section and figure, commit a structured finding, and defend it in follow-up chat. The result isn't a grade. It's a rigorous document an author could use to improve the paper before submission, written in the voice of a real referee panel.

Frontier labs already use versions of this shape internally as a first-pass filter on internal drafts. Quorum is a public, readable reference implementation of that shape — honest about what works, what's hard, and what's still out of scope.

---

## What happens when you convene a session

```
                         QUORUM SESSION FLOW
                         ═══════════════════

 [0] IDLE                                           (UI: PhaseIdle)
 ─────
   user drops a PDF, pastes an arxiv URL, or clicks "try the demo paper"
                           │
                           ▼
         POST /api/sessions { source: {kind, id|upload_id} }
                           │
                           ▼
   SessionStore.create(sid)    spawn asyncio.create_task(run_session)
         │                              │
         ▼                              ▼
   Session dataclass           session_runner.run_session
   with SessionBus             ── drives the phase machine ──

 ┌───────────────────────── SSE bus ────────────────────────┐
 │  phase.change, paper.extracted, chair.trace,             │
 │  vector.identified, agent.start, agent.trace,            │
 │  agent.finding, senior.start / progress / trace /        │
 │  signed / inconclusive, verdict.trace, verdict.ready     │
 └──────────────────────────────────────────────────────────┘


 [1] INTAKE  (phase.change → "intake")
 ──────────
   ingest the paper
     arxiv → `arxiv` package → fetch + Content-Type check → pypdf
     pdf   → bytes from /api/uploads (pypdf + pymupdf4llm markdown)
     demo  → hardcoded arxiv id for a reliable no-input demo
                           ▼
   sectionize()  regex-first; Haiku fallback if regex fails (<3 sections)
                           ▼
   sess.paper_pdf_bytes  = raw PDF  (served at /api/sessions/:id/paper.pdf)
   sess.paper            = { id, title, authors, venue, abstract,
                             sections, body, has_pdf }
   bus.publish(paper.extracted)


 [2] READING  (phase.change → "reading")
 ────────────
   Orchestrator  Claude Opus 4.7
     system: "pick 3 of {METH, STAT, THRY, EMPR} whose angles best match
              this paper's weakest surfaces. STLM is appended automatically."
     user:   paper body + pre-segmented sections
     tools:  emit_vector(agent_id, angle, relevant_sections)

     text_delta      → chair.trace { kind: "think", … }
     emit_vector     → vector.identified  (hard-capped at 3 non-STLM)
                       + chair.trace { kind: "flag", text: "convene X: …" }
                           ▼
   STLM force-appended. Final panel: 4 reviewers (3 chosen + STLM).


 [3] DELIBERATION  (phase.change → "deliberation")
 ────────────────
   warmup_reviewer_cache()
     One throwaway messages.create with
       system: [PREAMBLE, PAPER(cache_control=ephemeral)]
     to write the paper into Anthropic's prompt cache BEFORE fan-out.
     Saves ~90% of subsequent reviewer ITPM.
                           │
                           ▼
   asyncio.gather( 4 reviewers, semaphore=REVIEWER_PARALLEL=5 ):
     each reviewer  Claude Opus 4.7
       system = [PREAMBLE,              ← stable across all reviewers
                 PAPER(cache_control),  ← stable; shared cache
                 PERSONA]               ← varies per reviewer
       tools  = arxiv_search, arxiv_read, s2_neighbors,
                bootstrap, power_calc, sympy_simplify,
                sandbox_run, flag, commit_finding

     stream_loop.run_agent_loop:
       content_block_start  (tool_use)       → buffer input_json
       content_block_delta  (text_delta)     → agent.trace { think } per newline
       content_block_delta  (input_json_delta) → accumulate args
       content_block_stop                    → emit agent.trace { tool, … }
       stop_reason == "tool_use"             → execute tool, append tool_result
       commit_finding                        → agent.finding (structured)
       tenacity retry on 429/529 with retry-after header

     each reviewer MUST call sandbox_run at least once
     (enforced by prompt, not code). The sandbox is Docker one-shot,
     no-network, with numpy/scipy/pandas/sympy/statsmodels/matplotlib/
     scikit-learn/seaborn/networkx/pingouin/arviz/scikit-image prebaked.


 [4] CONVERGING  (phase.change → "converging")
 ─────────────
   3 seniors run sequentially:
     CHAIR      — synthesizer
     SKEPTIC    — cross-examines upheld findings
     METHOD     — independent methodology pass

   Each streams text_delta as senior.trace and emits progress ticks.
   senior.signed       publishes only when commit_senior_review fires.
   senior.inconclusive on failure (no more lying about completion state).


 [5] VERDICT  (phase.change → "verdict")  — frontend auto-flips to verdict tab
 ──────────
   report composer  Claude Opus 4.7
     system: "Your ENTIRE response is a single emit_report tool call. No
              free-form text. Write the complete Markdown report inside
              the markdown field. Target ~2 pages of journal-referee prose."
     tools:  emit_report(markdown, ranked_ids, recommended_experiment)

     text_delta   → verdict.trace  (streams into the composing panel)
     emit_report  → ranked findings + prose markdown + recommended_experiment
                           ▼
     generate_verdict_pdf()  reportlab renders Markdown → PDF
       - DejaVu Sans Unicode font family (Greek, math symbols, accents)
       - serif body, italic headings, accent-highlighted §/fig/eq refs
       - cover + panel signatures + running header + page numbers
                           ▼
     bus.publish(verdict.ready, { ranked, recommended_experiment,
                                  report_markdown })


 [6] CHAT  (post-verdict, verdict right-rail card)
 ────────
   user selects "swarm" or a specific committed agent
   POST /api/sessions/:id/chat { target, message }
                           ▼
   "all"    → fan out: CHAIR + each committed reviewer streaming in parallel,
              events interleave via asyncio.Queue
   agent_id → single agent with its persona, paper excerpt, committed finding,
              and prior chat history

   Events: chat.start / chat.token / chat.done / chat.error / chat.finished
```

---

## The panel

Five seats; four reviewers always convened.

| ID   | Name              | Angle                                      |
|------|-------------------|--------------------------------------------|
| METH | The Methodologist | Experimental design, ablations, controls.   |
| STAT | The Statistician  | Power, significance, confidence intervals.  |
| THRY | The Theorist      | Mechanism, priors, first-principles.        |
| EMPR | The Empiricist    | Replication, prior art, adjacent baselines. |
| STLM | The Steelman      | Strongest version of the paper's argument.  |

The orchestrator picks exactly 3 of {METH, STAT, THRY, EMPR} whose angles match the paper's weakest surfaces. STLM is always appended so the panel never reads as purely destructive. HIST (Historian) was removed as redundant with EMPR in practice.

Seniors: **CHAIR**, **SKEPTIC**, **METHOD** — run sequentially over the findings pool.

---

## Rate-limit and cost math

Real multi-agent Opus sessions hit Tier 1 Anthropic limits hard. The fix is three-fold:

1. **Prompt caching on the paper block.** `cache_control: {type: "ephemeral"}` on the `<paper>…</paper>` system text. All 4 reviewers share the same cache key because the prefix before that marker (just the preamble) is identical across personas. On Opus 4.x, `cache_read_input_tokens` do not count toward ITPM — so the only ITPM charge after warmup is the persona shell + user message (~500 tokens per reviewer, not 20k+).

2. **Explicit warmup.** Before `asyncio.gather` fans out reviewers, a single `messages.create(max_tokens=1)` writes the paper into cache. Without this, the parallel reviewers race each other to write the cache and several miss.

3. **Tier 2.** A one-time $40 deposit in the Anthropic console jumps Opus to 1000 RPM / 450k ITPM / 90k OTPM. Tier 1 (50 / 30k / 8k) is too tight for 4 parallel Opus reviewers + 1 orchestrator + 3 seniors + 1 verdict composer, even with perfect caching. Tier 2 eliminates rate-limit stalls.

A full session end-to-end consumes roughly 100k–300k input tokens and 15k–40k output tokens, ~$0.50–$1.50 per paper at current Opus pricing. The paper block cache cuts the input cost by ~85% on the parallel reviewer leg.

---

## Directory layout

```
quorum/
├── backend/
│   ├── app/
│   │   ├── main.py                 FastAPI entry, lifespan (Docker probe), routers
│   │   ├── config.py               env, model IDs, caps
│   │   ├── types.py                TypedDicts mirroring frontend types.ts
│   │   ├── bus.py                  per-session SSE event bus (backlog + overflow)
│   │   ├── sessions.py             in-memory store + 30s cancel grace watcher
│   │   ├── session_runner.py       top-level run_session coroutine
│   │   ├── chat.py                 post-verdict chat: single + swarm fanout
│   │   ├── verdict_pdf.py          reportlab Markdown → PDF renderer
│   │   ├── fonts/                  vendored DejaVu Sans (Unicode support)
│   │   ├── ingest/
│   │   │   ├── arxiv_ingest.py     arxiv package + PDF fetch + MIME check
│   │   │   ├── pdf_ingest.py       pymupdf4llm → markdown, pypdf fallback
│   │   │   └── sectionize.py       regex first, Haiku fallback
│   │   ├── llm/
│   │   │   ├── client.py           shared AsyncAnthropic instance
│   │   │   ├── stream_loop.py      tool-use loop with tenacity retry
│   │   │   ├── cache_warmup.py     primes the paper prompt cache
│   │   │   ├── tools_schema.py     tool JSON schemas (Anthropic tool-use)
│   │   │   └── prompts/
│   │   │       ├── orchestrator.py vector identification prompt
│   │   │       ├── reviewer.py     per-persona reviewer system
│   │   │       ├── senior.py       3 senior role prompts
│   │   │       ├── verdict.py      (deprecated) old verdict prompt
│   │   │       └── report.py       prose-report composer
│   │   ├── routes/
│   │   │   ├── sessions.py         POST / GET session metadata
│   │   │   ├── stream.py           GET /stream — SSE
│   │   │   ├── paper.py            GET /paper.pdf, /verdict.pdf
│   │   │   └── chat.py             POST /chat (streams SSE back)
│   │   ├── tools/
│   │   │   ├── arxiv_tool.py       arxiv_search, arxiv_read
│   │   │   ├── s2_tool.py          semanticscholar neighbors
│   │   │   ├── stats_tool.py       bootstrap, power_calc, sympy_simplify
│   │   │   ├── sandbox_tool.py     docker run --rm -i … python - (stdin piped)
│   │   │   └── dispatch.py         tool name → impl routing
│   │   └── mock_runner.py          fake-timer session for fast UI dev
│   ├── sandbox/
│   │   └── Dockerfile              python:3.11-slim + scientific stack
│   └── tests/                      pytest (30 tests)
│
├── frontend/
│   ├── index.html
│   ├── vite.config.ts              dev proxy /api → :8000
│   └── src/
│       ├── main.tsx, App.tsx, App.css
│       ├── types.ts                mirrors backend TypedDicts
│       ├── styles/
│       │   ├── tokens.css          --paper, --ink, --accent, --page-pad, …
│       │   └── global.css          .j-mono, .j-serif, .j-caret, .shim, keyframes
│       ├── session/
│       │   ├── reducer.ts          SSE event → SessionState, seq-gated idempotent
│       │   ├── sseClient.ts        EventSource + bounded reconnect
│       │   └── useSession.ts       React hook wrapping the above
│       ├── components/
│       │   ├── Masthead.tsx        top bar
│       │   ├── TopNav.tsx          trace / verdict tabs + phase ribbon
│       │   ├── TopProgress.tsx     thin accent pulse + composing line
│       │   ├── PhaseIdle.tsx       drop-zone, arxiv URL field, Choose PDF
│       │   ├── PaperPDF.tsx        iframe render of /paper.pdf + text fallback
│       │   ├── MarginRail.tsx      right-rail, phase-specific
│       │   ├── ChairCard.tsx       reading-phase chair trace card
│       │   ├── AgentCard.tsx       reviewer card with TraceLine sub-component
│       │   ├── SeniorLive.tsx      converging-phase senior card
│       │   ├── VerdictPage.tsx     full-page verdict view
│       │   ├── ClaudeCodePackage.tsx  copy-for-claude-code markdown block
│       │   ├── ChatCard.tsx        post-verdict swarm/agent chat
│       │   ├── SevBadge.tsx        HIGH/MED/LOW/NOTE chip
│       │   └── Toasts.tsx
│       └── test-setup.ts           vitest + happy-dom
│
├── Makefile                        make dev / make install / make sandbox-image / make test
├── .env                            ANTHROPIC_API_KEY (gitignored)
├── .env.example
└── .gitignore
```

---

## Quick start

```bash
# 1. Anthropic credential
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env

# 2. Install Python and Node deps
make install

# 3. Build the sandbox image (one-time, ~45s)
make sandbox-image

# 4. Run
make dev
```

Open http://localhost:5173. Click "try the demo paper" or paste `arxiv.org/abs/…`.

### Prerequisites

- Python 3.11 (the backend venv; pyenv works: `pyenv install 3.11`)
- Node 20+ and pnpm 9+
- Docker or Colima (for the sandbox)
- An Anthropic API key on Tier 2+ for parallel Opus (Tier 1 works but will stall on rate limits)

### Tests

```bash
make test           # runs pytest + vitest
```

30 backend + 20 frontend. One test is network-gated (`QUORUM_SKIP_NETWORK=1` to skip it in CI-like runs).

---

## Design decisions worth knowing

**Opus everywhere.** Orchestrator, reviewers, seniors, verdict composer, chat — all Claude Opus 4.7. Cheaper mixes (Sonnet/Haiku for subagents) were tried during development; the loss in reviewer analytic quality wasn't worth the rate-limit savings once Tier 2 was available. Sectionize fallback uses Haiku because it's a trivial one-shot call.

**In-process state only.** No database, no Redis, no Supabase. `SessionStore` is a Python dict in the uvicorn process; each `Session` holds the paper bytes, findings, chat threads, and SSE backlog in memory. A server restart wipes everything. This was an explicit scope decision for the interview build. The obvious productionization path is Postgres for session metadata + Supabase Storage (or S3) for paper and verdict PDFs. Mentioned because reviewers will ask.

**SSE, not WebSockets.** Uni-directional server → client is exactly the shape we need; the bus is naturally append-only with sequence numbers. Reconnect carries `?since_seq=N` and the server replays from a bounded deque, so a tab refresh doesn't lose state mid-session. `_overflow` is a control event the server emits when a subscriber queue fills; the client treats it as a resync trigger.

**Docker sandbox via stdin, not bind-mount.** `docker run --rm -i … python -` pipes the snippet via stdin. Avoids a round-trip through virtiofs mount semantics on macOS Docker Desktop and Colima (which mount `$HOME` by default, not `/var`), and means there's no temp directory to clean up. Network is off; filesystem is read-only with a small writable `/tmp`. The scientific stack is prebaked in the image so no runtime `pip install` is needed.

**DejaVu Sans in the verdict PDF.** reportlab's default Times and Helvetica don't carry Greek glyphs. Real papers reference α, β, γ, τ, Δ constantly; they rendered as black rectangles. DejaVu Sans is a Unicode-complete TTF family; four variants (Regular, Bold, Italic, BoldItalic) are vendored under `backend/app/fonts/` (~2.6MB) and registered on module import.

**No text truncation in the trace pipeline.** Early builds capped individual trace events at ~120 characters to keep SSE events small. That silently chopped multi-line `sandbox.run` code to the first 1–2 lines, which killed the "show more" toggle in the UI and made the agent card logs feel empty. All user-facing text now flows uncapped to the frontend; the bus backlog is bounded by event count, not by bytes.

**Sticky-bottom autoscroll in the agent cards.** The log follows the tail while new traces arrive, but if the user manually scrolls up to read earlier output, the autoscroll stops pinning. Scrolling back to the bottom resumes follow-mode. Standard chat-UI pattern; the naive version that pinned on every token made the log feel "unscrollable" mid-stream.

**Cancellation is opportunistic.** Closing the browser tab leaves the in-flight session running for a 30-second grace period. The bus notices it has no subscribers; if none reattach, the top-level `asyncio.Task` is cancelled and reviewer loops catch `CancelledError`, emit a placeholder finding, and unwind. Prevents abandoned sessions from burning Anthropic tokens indefinitely.

**Chat after verdict only.** The chat card appears on the verdict page right rail, not during the live session. Agents need their committed finding as context to answer follow-ups meaningfully; chatting with them mid-deliberation invites hallucinated pre-commitments.

---

## What is explicitly NOT in scope

- Authentication / user accounts
- Any form of persistence (DB, object storage, session replay across restarts)
- Multi-paper batch review
- Rebuttal round (the user responds and the panel re-reviews)
- Deployment pipeline / production hardening
- CI/CD
- Multi-tenant rate-limit pool across a team's Anthropic keys

These are real roadmap items, not oversights. The interview build stops at "one user, one laptop, one session at a time, and everything works end-to-end on a real paper."

---

## Known edges

- **Docker Desktop / Colima must be running.** The lifespan probe at startup checks the sandbox; if Docker is down, the sandbox tool degrades to returning `{ok: false, reason: "sandbox_offline"}` and the reviewer LLM reasons about the failure instead of crashing. Start Docker, restart uvicorn, you're good.

- **Anthropic Tier 1 will stall.** 4 parallel Opus reviewers + 1 composer × 8k OTPM budget → rate-limit retries. The code tolerates it (tenacity backoff + `retry-after` header parsing) but the session gets noticeably slower. Tier 2 is the fix.

- **Hot reload can lag on backend module edits that change closure captures.** `uvicorn --reload` picks up file changes, but an in-flight session's already-spawned task keeps the old code in its closures. Restart uvicorn between significant backend changes if you're mid-session.

- **Uploaded PDFs are not persisted.** They live in an in-memory `_uploads` dict keyed by a UUID. A restart loses them and any session that referenced them becomes irreparable. See "In-process state only" above.

---

## Verification you can run

```bash
# Backend unit tests
make test-backend

# Frontend unit tests
make test-frontend

# End-to-end: convene a real session and watch it stream
make dev
# → open http://localhost:5173, click "try the demo paper"
# → observe phase ribbon: intake → reading → deliberation → converging → verdict
# → verdict tab auto-flips; PDF iframe renders a multi-page referee report
# → right rail: copy-for-claude-code + chat with the panel
```

Backend is running on :8000, frontend on :5173; Vite proxies `/api/*` to the backend for you.

---

## License

MIT for the Quorum code. DejaVu Sans fonts bundled under `backend/app/fonts/` are under the DejaVu License (a permissive modified Bitstream Vera license).
