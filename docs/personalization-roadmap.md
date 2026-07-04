# Career OS — Personalization & Memory Roadmap

## Vision

Evolve Career OS from a system *tuned for one person by hand* into a **personalized,
memory-backed career agent** that (a) truly *knows you*, (b) ingests any résumé format into a
clean structured profile, (c) retrieves the *right* context per job instead of stuffing raw text,
and (d) can eventually be handed to a friend who onboards with **his own** context.

**Key reframe (settled):** this is a **memory + retrieval (RAG)** problem, *not* a model-training
problem. We do NOT fine-tune Llama. We keep the model general and always put the right,
editable, inspectable context in front of it. Fine-tuning (LoRA) is parked as a far-future
experiment only if RAG proves insufficient.

## Principles (how we build)

- **Build slowly, one shippable phase at a time** — each phase is independently valuable and
  keeps the suite green (backend-first, then UI).
- **Reuse what exists** — we already have the hard parts: `pgvector` (vector memory), the résumé
  parser (`resume/parser.py` → structured JSON), the AI Gateway (`llm/` with `chat_json` +
  versioned prompt schemas), and embeddings (`embed/`).
- **Everything the AI sees is assembled, not dumped** — a context builder pulls only relevant
  slices (profile + memory + JD) into each prompt.
- **Single-user first, multi-user last** — personalization pays off immediately for you;
  multi-user is the biggest lift and comes after the value is proven.

## What already exists (Phase 0 — done)

- pgvector semantic store · résumé→JSON parser · AI Gateway + prompt schemas · embeddings ·
  the learning loop (rejection-gap signals) · Postgres/SQLite dual backend.

---

## Phase 1 — The Candidate Profile (structured ingestion)

**Goal:** one clean, typed **Candidate Profile** is the single source of truth about the user —
not raw résumé text, not a scattered variant.

- Define a **Profile schema** (identity, skills, experience, projects, education, years,
  seniority, achievements-bank, links).
- **Multi-format ingestion:** upload `.md` / `.json` / `.xml` (plus existing PDF/`.tex`); user
  **selects the format**; parse → Profile schema via **structured extraction** (reuse
  `chat_json` + a Profile JSON-schema; JSON/XML are parsed directly, prose formats via the LLM).
- Store Profile as a first-class object (new table + repo, both backends).
- **Done when:** any résumé format in → one validated Profile out; CLI + API + a Profile screen.

## Phase 2 — Personal Memory (durable, editable facts)

**Goal:** the AI "remembers you and never forgets" — via an editable memory store, not weights.

- A typed **memory store**: preferences ("remote only", "backend focus"), **hard filters**
  ("no FIFO", "≥ ₹X", "won't relocate"), soft signals, and learnings (fed by the rejection loop).
- Editable via UI/CLI; **hard filters gate** scoring, **soft signals bias** it.
- **Memory-tooling decision (evaluated):** **MemPalace** (github.com/MemPalace/mempalace) is a
  strong local-first *conversation-memory* engine (Python, pgvector-capable, KG, MCP, MIT) — but
  it's the **wrong shape for Phase 2**: (1) hard filters must be *deterministic* rules, not fuzzy
  semantic retrieval; (2) it's built to mine conversation corpora, not hold a dozen structured
  facts. **Decision:** Phase 2 uses a **plain typed `memory` table** (no new deps). MemPalace is
  parked as an **optional Phase-3 retrieval backend** to revisit once a large unstructured corpus
  (past apps, notes, JD history) justifies it — it speaks pgvector, so it slots onto our DB then.
- **Done when:** you can add/edit durable facts and see them consistently respected downstream.

## Phase 3 — RAG context assembly (stop stuffing)

**Goal:** each prompt gets a compact, *relevant* context, assembled — not the whole résumé.

- A **context builder** that, per JD, retrieves relevant Profile slices + Memory + past learnings
  (embeddings/pgvector + hard-filter rules) and composes the prompt input.
- Applies to scoring, tailoring, cover/outreach, review.
- **Done when:** prompts are built from retrieved context; token use drops; outputs sharpen.

## Phase 4 — Personalized scoring / tailoring / drafting

**Goal:** the personalization actually shows in results.

- Rewire scoring/tailoring/drafting to consume **Profile + Memory + retrieved context** instead
  of a single résumé-variant JSON.
- Hard-filter jobs pre-scoring; score/tailor explain against the Profile; drafts pull from the
  achievements-bank.
- **Done when:** the same job scores/tailors measurably differently for two different Profiles.

## Phase 5 — Multi-user (share it with a friend)

**Goal:** a friend runs the same app with **his own** everything.

- Introduce an **Owner/User** concept; scope Profile, Memory, Jobs, Scores, Applications per user.
- Real auth (beyond the single shared token), data isolation, and an **onboarding flow**
  (upload résumé → build Profile → set preferences/filters → first discovery).
- **Done when:** two users coexist with fully isolated data + context.

## Phase 6 — Agentic memory / continuous learning (future / optional)

- The learning loop **proposes** memory updates ("you keep getting rejected for lacking k8s —
  add it as a gap?") that you approve — the agent gets better over time, with you in control.
- **(Parked)** Local LoRA fine-tuning — only if RAG is proven insufficient; not core.

---

## Build order & rationale

`1 → 2 → 3 → 4` deliver escalating personal value for **you** (single-user); `5` unlocks the
friend; `6` is polish/future. Each phase is small, shippable, tested, and reuses existing infra.

## Open questions to resolve as we go

- Profile schema shape (how rich? achievements-bank granularity?).
- Memory store: external lib vs. our own table (Phase-2 decision).
- Multi-user auth model (local accounts? OAuth? still localhost?).
- Where the Profile/Memory editing UX lives (new screens in the Stitch set).
