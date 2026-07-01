# Frontend Engineering Standards — `frontend/`

> The single source of truth for how we build and change the Tapza Clinic React SPA
> (`frontend/`). Every feature, page, component, hook, service, and refactor follows
> these rules. They exist so the codebase stays **consistent, scalable, and equally
> readable to humans and AI tools** (Claude, Cursor).

**Applies to:** `frontend/` (Vite + React 19 + React Router 7 + TanStack Query +
react-bootstrap + Sass). It does **not** cover the backend (`backend/`) or the Next.js
app (`web/clinic-ui`), which have their own conventions.

---

## How to read this document

Rules are grouped from broad principles down to day-to-day practice. Two things matter
most and are called out first because they are what the team most often asks about:

1. **A `CLAUDE.md` in every folder** (Part 2).
2. **Folder-scoped files** — each folder owns its own `.tsx`, `.constants.ts`,
   `.api.ts`, `.types.ts`; anything shared by two or more children moves up to the
   parent (Part 3).

## How these standards are enforced

Each rule is either **Automated** (ESLint / TypeScript / Prettier / CI block the merge —
reviewers never check these by hand) or **Review judgment** (a human checks it because it
needs context). When a rule _can_ be automated, adding that lint/CI check is part of
adopting the rule. The aim: code review spends its time on judgment, not on catching what
a tool should catch.

---

## Part 0 — Golden Principles

1. **Reuse before you create.** Search first; duplicate never.
2. **Keep files small and single-purpose.**
3. **Separate business logic from UI** (logic → hooks/services, UI → components).
4. **Make UI configurable through props.**
5. **Localize all user-facing text.**
6. **Keep types strict** — no `any`, no `unknown` leaking out of a boundary.
7. **Never hardcode a value** — colors, sizes, fonts, URLs, routes, strings, numbers all
   come from tokens/constants.
8. **Document as you go** — the folder's `CLAUDE.md` is updated in the same PR as the code.
9. **Design for reuse and the next reader.** Names explain the _what_; comments explain
   the _why_.
10. Keep code accessible, performant, testable, and maintainable.

---

## Part 1 — Project Structure

The SPA lives under `frontend/src`. This is the canonical layout — **create only the
folders a feature actually needs; never create empty folders.**

```text
frontend/
├── src/
│   ├── main.tsx                # Entry point: renders <App />
│   ├── App.tsx                 # Root: wires providers + router
│   │
│   ├── core/                   # Design tokens ONLY (SCSS): colors, typography,
│   │   │                       #   spacing, radii, breakpoints, z-index, sizes
│   │   ├── colors.scss
│   │   ├── typography.scss
│   │   ├── variables.scss      # entry that forwards all token partials
│   │   └── …
│   │
│   ├── providers/              # Global React providers (QueryClient, auth, theme)
│   ├── routes/                 # The ONLY place that maps URL ↔ page/layout + guards
│   ├── layouts/                # Page shells (TopBar, sidebar) composing <Outlet />
│   ├── pages/                  # Route entry screens — thin: read params, compose features
│   │
│   ├── features/               # Product verticals (the real logic + UI). See Part 1.2
│   │   ├── ai-scribe/
│   │   ├── appointments/
│   │   ├── consultation/
│   │   └── …
│   │
│   ├── components/             # Shared UI kit used by 2+ features (Button, Table, Modal…)
│   ├── hooks/                  # App-wide hooks only (no feature-specific hooks here)
│   ├── services/               # HTTP client, auth headers, interceptors — NO React here
│   ├── queries/                # Shared TanStack Query read hooks (cross-feature)
│   ├── mutations/              # Shared TanStack Query write hooks (cross-feature)
│   │
│   └── rsrc/                   # Localization resources (planned — see Part 8)
│       ├── en/
│       ├── hi/
│       └── te/
```

### 1.1 Pages vs Features vs Routes

These sound similar but do different jobs:

- **`routes/`** — the only place that knows about URLs. Maps a path (incl. params like
  `/patients/:id`) to a page and a layout, and applies route guards.
- **`pages/`** — the routing target. A page reads route params and **composes** features.
  Keep pages thin; they wire, they do not implement.
- **`features/`** — the business logic and UI for one area. Features know nothing about
  URLs and are the reusable blocks pages assemble.

This is why `patients` can appear in both `pages/` and `features/`: `pages/patients`
reads the `id` and renders the patient detail component from `features/patients`.

### 1.2 Feature structure

A feature uses the same dotted-file convention as the rest of the SPA. **Group into a
subfolder only once you have several files to group**; until then files sit at the feature
root. This is the real shape of an existing feature:

```text
features/ai-scribe/
├── AiScribeScreen.tsx          # component(s) — PascalCase
├── useAiScribeSession.ts       # feature hook   — camelCase, use* prefix
├── ai-scribe.api.ts            # feature API calls
├── ai-scribe.types.ts          # feature types
├── ai-scribe.constants.ts      # feature constants/enums
├── ai-scribe.scss              # feature styles
└── CLAUDE.md                   # describes the whole feature (mandatory)
```

Grow into subfolders (`components/`, `hooks/`, `queries/`, `mutations/`, `utils/`) only
when the count justifies it — and each subfolder then gets **its own `CLAUDE.md`**.

### 1.3 Import boundaries (enforced by review; lint where possible)

1. **Pages** import layouts, features, hooks — **not** `services` directly (go through a
   feature module or a query/mutation hook).
2. **Features must not import sibling features.** Cross-feature logic is promoted to a
   shared layer (`services`, `hooks`, `queries`, `components`) after a deliberate review.
3. **Components** never import a TS design layer — they consume design tokens via CSS
   variables from `core` (see Part 6).
4. **Routes** import pages and layouts only (plus react-router APIs).

### 1.4 Where does this go? (quick reference)

| Adding…                                       | Put it in…                                    |
| --------------------------------------------- | --------------------------------------------- |
| A screen tied to a URL                        | `pages/`                                      |
| Logic or UI for one business area             | that feature under `features/`                |
| A UI component used by 2+ features            | `components/`                                 |
| A UI component used by one feature            | that feature's folder                         |
| A global provider (query client, auth, theme) | `providers/`                                  |
| Route definitions / guards                    | `routes/`                                     |
| A page shell (TopBar, sidebar)                | `layouts/`                                    |
| An HTTP/API call                              | `services/` (shared) or `<feature>.api.ts`    |
| A TanStack Query read hook                    | `queries/` (shared) or feature `queries/`     |
| A TanStack Query write hook                   | `mutations/` (shared) or feature `mutations/` |
| A reusable hook                               | `hooks/` (shared) or feature `hooks/`         |
| A constant / enum / type                      | the matching `.constants.ts` / `.types.ts`    |
| A design token (color, font size, spacing)    | `core/*.scss`                                 |
| Any user-facing text                          | the matching file in `rsrc/<lang>/`           |

---

## Part 2 — `CLAUDE.md` in Every Folder (mandatory)

**Every folder under `src/` contains a `CLAUDE.md`.** It is the contract for humans and
AI tools, and it is named `CLAUDE.md` specifically so Claude Code auto-loads it as nested
context when working inside that folder.

> We document at the **folder level only** — there is no per-component doc file. Because
> `.tsx` files are capped small (Part 4), a folder's `CLAUDE.md` is enough to explain
> everything in it.

A folder's `CLAUDE.md` must answer, briefly and normatively:

```md
# <Folder name>

Scope: One sentence — what belongs in this folder (and what does not).
Purpose: Why this folder/feature exists.
Contents: The key files and what each is responsible for.
Business logic: The behaviours implemented here (search, pagination, queue sync…).
Dependencies: What it imports (services, queries, shared components).
Boundaries: "Do not" rules — e.g. "no sibling-feature imports", "no API logic in hooks".
Impacted modules: What breaks downstream if this changes.
```

Rules:

- A folder is **not complete** until its `CLAUDE.md` exists.
- **Keep it in sync.** Update the `CLAUDE.md` in the _same PR_ as the code whenever the
  scope, logic, dependencies, boundaries, or impacted modules change. An outdated
  `CLAUDE.md` is worse than none — it misleads everyone who reads it.
- Keep it **short, current, normative.** If code and `CLAUDE.md` disagree, fix one of
  them in that PR.

> **Migration note:** the repo previously used a file literally named `.md` per folder.
> We are standardizing on `CLAUDE.md`. When you touch a folder that still has a `.md`,
> rename it to `CLAUDE.md` and bring it up to the template above.

---

## Part 3 — Folder-Scoped Files & the "Promote Upward" Rule

This is the structural backbone of the codebase.

### 3.1 Each folder owns its own supporting files

A folder that holds code keeps its **own scoped** companion files, used **only within
that folder**:

| File                  | Holds                                       |
| --------------------- | ------------------------------------------- |
| `*.tsx`               | Components belonging to this folder         |
| `<name>.constants.ts` | Constants & enums used only in this folder  |
| `<name>.types.ts`     | Types & interfaces used only in this folder |
| `<name>.api.ts`       | API/service calls used only in this folder  |

Do not reach into another folder's `*.constants.ts` / `*.types.ts` / `*.api.ts`. If you
need it elsewhere, that is a signal to promote it (3.2).

### 3.2 Shared-across-children → move to the parent

> If a constant, type, hook, or function is used by **two or more children** of a folder,
> it does **not** live in any one child — it moves **up to the nearest common parent**.

- Used in one feature only → stays in that feature.
- Used by two features → promote to the **global** layer (`components`, `hooks`,
  `services`, `queries`, `mutations`, or a top-level `*.constants.ts` / `*.types.ts`).
- Used by two subfolders of one feature → promote to that **feature's** root file.

This keeps each folder self-contained and stops the global layer from becoming a dumping
ground. **Default to keeping code local; promote only when a real second consumer
appears** — not preemptively.

---

## Part 4 — Type Safety (strict)

- **No `any`. No `unknown` leaking out of a boundary.** `unknown` is allowed only at a
  trust boundary (e.g. parsing a raw response) and must be narrowed immediately with a
  type guard or schema before use. It must never appear in a function signature, prop, or
  exported type.
- No implicit `any` — `tsconfig` runs in `strict` mode; keep it on.
- Use real `interface`/`type` for every shape, and a named set for every fixed group of
  values. Never compare against raw string literals.

```ts
// House style: string enums
export enum QueueStatus {
  WAITING = "WAITING",
  IN_CONSULT = "IN_CONSULT",
  DONE = "DONE",
}
```

- **Never hardcode** URLs, API endpoints, routes, image paths, icon names, magic numbers,
  or status values — put them in the folder's `*.constants.ts`.

```ts
export const API_ENDPOINTS = { queue: "/queue" } as const;
export const ROUTES = {
  patientDetail: (id: string) => `/patients/${id}`,
} as const;
export const APP_ICONS = { patient: "person" } as const; // referenced, never inlined
```

---

## Part 5 — Naming & Readability

| Item             | Convention                 | Example                          |
| ---------------- | -------------------------- | -------------------------------- |
| Component files  | PascalCase `.tsx`          | `AiScribeScreen.tsx`             |
| Hook files       | camelCase, `use` prefix    | `useAiScribeSession.ts`          |
| Supporting files | kebab-case + dotted suffix | `ai-scribe.api.ts`, `*.types.ts` |
| Style files      | kebab-case `.scss`         | `ai-scribe.scss`                 |
| Components       | PascalCase                 | `AiScribeScreen`                 |
| Hooks            | camelCase `use*`           | `useAiScribeSession`             |
| Constants        | UPPER_SNAKE_CASE           | `QUEUE_STATUS`                   |
| Enums / types    | PascalCase                 | `QueueStatus`                    |

- Give every variable, function, and prop a name that explains itself. No `a`, `tmp`,
  `data2` (loop indexes `i`/`j` are the only exception).
- Booleans read as questions (`isLoading`, `hasError`, `canEdit`); functions read as
  actions (`fetchQueue`, `formatCurrency`, `validateAbha`).
- **Comments explain the _why_, never the _what_.** If code needs a comment to be
  understood, first try renaming or extracting a function. Reserve comments for business
  reasons, workarounds, non-obvious decisions, or a spec/ticket link.

---

## Part 6 — Styling, Design Tokens & Visual Consistency

### 6.1 Bootstrap first

Prefer react-bootstrap / Bootstrap classes. Write SCSS only when no class fits, when you
need a tokenized value, or to override a style. Avoid one-off custom CSS.

### 6.2 Tokens only — never hardcode a visual value

Colors, font sizes, line-heights, spacing, radii, breakpoints, and z-index all come
from `core/` design tokens (CSS variables). Never inline a raw value — not a hex colour,
not a `px`, not a raw `rem` literal.

```scss
/* Bad — raw px */
color: #2563eb;
font-size: 14px;
margin: 12px;

/* Bad — raw rem (still hardcoded, just a different unit) */
color: #2563eb;
font-size: 0.875rem;
margin: 0.75rem;

/* Good — tokens only */
color: var(--color-primary);
font-size: var(--font-size-xs);
margin: var(--margin-sm);
```

The token families in `core/` and what they're for:

| Concern              | Token family                                                                                          | File                     |
| -------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------ |
| Padding              | `--padding-xxs` … `--padding-vvl`                                                                     | `paddings.scss`          |
| Margin               | `--margin-xs` … `--margin-vl`                                                                         | `margins.scss`           |
| Gap (flex / grid)    | `--gap-xxs` … `--gap-xl`                                                                              | `gaps.scss`              |
| Border radius        | `--radius-xs` … `--radius-xl`, `--radius-pill`                                                        | `border-radius.scss`     |
| Font size            | `--font-size-xxs` … `--font-size-xl` (auto-swaps to a smaller scale at `$breakpoint-tablet`)          | `typography.scss`        |
| Line height          | `--line-height-xs` … `--line-height-xl`                                                               | `typography.scss`        |
| Component dimensions | Scoped per component — `--layout-*`, `--sidebar-*`, `--doctor-profile-*`, `--large-input-*`, etc.     | `sizes.scss`             |
| Color                | `--color-*`                                                                                           | `colors.scss`            |
| Z-index              | `--z-index-*`                                                                                         | `z-indexes.scss`         |
| Gradient             | `--gradient-*`                                                                                        | `gradients.scss`         |

If the design needs a value that doesn't fit any existing token, **add a new token in
`core/`** (with a one-line comment about where it came from — the existing
`--doctor-profile-*` and `--layout-sidebar-*` blocks in `sizes.scss` are the template).
Do not inline.

### 6.3 Typography & component consistency (important)

The whole app uses **one** font family and **one** set of weights/sizes — defined once in
`core/typography.scss` and consumed via variables. Never set a raw `font-family`,
`font-weight`, or `font-size`.

```scss
font-family: var(--font-body); /* Inter + fallback stack */
font-weight: var(--font-weight-semibold); /* 400 / 500 / 600 / 700 only */
font-size: var(--font-size-m);
line-height: var(--line-height-m);
```

**Components of the same type must look identical everywhere.** A "primary button" has the
same height, padding, radius, font size, and weight on every screen. Achieve this by
building one configurable shared component per type (Part 7) — not by re-styling buttons
per feature. If a new variant is genuinely needed, add it as a prop/variant on the shared
component, not as a bespoke style.

### 6.4 Use `rem` by default; `px` only when `rem` won't work

All CSS lengths in `frontend/src/**` should be expressed in `rem`. **Default to `rem`
everywhere** — type, spacing, borders, radii, `box-shadow` blur/offset, gradient stops,
icon sizes, component dimensions.

**Why.** With `rem`, a user can zoom the UI by pressing the browser's zoom controls
(Ctrl+, Ctrl-) or by changing the root font-size, and the entire layout scales
proportionally — typography, spacing, borders, icons, everything. With `px`, layouts
crack the moment a user with low vision enlarges the page. We want the UI to "just work"
at any zoom level, without anyone having to fight the browser.

**`px` is allowed only when `rem` genuinely doesn't fit.** Two clear cases:

1. **Media-query breakpoints** (see below) — they describe physical device widths, not
   user-scalable UI.
2. **Third-party APIs that require `px`** — a library prop, a JS API that takes a number
   of pixels, or vendor CSS we can't touch.

Anything else needs a real reason — not "I want a crisp 1px border" (use a rem-valued
border-width token; if none fits, add one to `core/` per §6.2), not "rem feels weird"
(use the conversion table). When you do use `px`, **leave a one-line comment explaining
why `rem` was unsuitable**, so the next person doesn't "fix" it.

**Conversion.** `1rem = 16px` is the project's base. Common mappings:

| px   | rem        |
| ---- | ---------- |
| 1    | 0.0625rem  |
| 2    | 0.125rem   |
| 4    | 0.25rem    |
| 6    | 0.375rem   |
| 8    | 0.5rem     |
| 12   | 0.75rem    |
| 14   | 0.875rem   |
| 16   | 1rem       |
| 20   | 1.25rem    |
| 24   | 1.5rem     |
| 32   | 2rem       |
| 40   | 2.5rem     |
| 48   | 3rem       |

But in practice you should rarely write a raw `rem` either — pull the value from the
token table in §6.2.

**The most common `px` exception — media-query breakpoints.**
`frontend/src/core/breakpoints.scss` stays in `px` because breakpoints map to physical
device widths (e.g. tablet at 1024px), not user-scalable UI. The codebase uses Sass
`$breakpoint-*` variables there.

```scss
/* Good — breakpoints stay in px */
@media screen and (width <= $breakpoint-tablet) {
  ...
}
```

Everything else — every `width`, `height`, `padding`, `margin`, `gap`, `border`,
`border-radius`, `font-size`, `line-height`, `box-shadow`, `filter: blur(…)`, `outline`,
`inset`, `top`/`bottom`/`left`/`right` offset — should be `rem`, and almost always
through a token.

```scss
/* Bad */  border-radius: 8px;             /* raw px */
/* Bad */  border-radius: 0.5rem;          /* raw rem */
/* Good */ border-radius: var(--radius-md);
```

---

## Part 7 — Components & Reuse

- **One responsibility per component** (Single Responsibility). When a component starts
  doing more than one thing, split it: child components in the same folder, logic into
  hooks, constants/types/utils into their scoped files.
- **File size:** keep every `.tsx` at **≤ 150 lines**. Treat ~100–120 lines as a signal to
  look closer. Do not split _only_ to hit a number — that usually hurts readability.
- **Reuse before creating.** Before adding a component/hook/util/service, check it doesn't
  already exist. Build configurable, reusable versions of common UI: buttons, inputs,
  tables, dropdowns, search bars, modals, drawers, tooltips, pagination, loaders, and
  empty/error/loading/data views. Control behaviour through props.
- **Lists:** use semantic HTML (`<ul>/<li>`, `<table>`), and give every item a stable
  unique `key` (never the array index when items can reorder).

---

## Part 8 — Localization (`rsrc/`)

We are adopting localization now, so **build it in from the start** even though no strings
are translated yet.

- **Never hardcode user-facing text** — labels, placeholders, button text, table headers,
  modal titles, empty-state and success/error messages all live in resource files.
- `rsrc/` mirrors `src/` and holds one JSON namespace per page/feature/component, under a
  language folder:

```text
rsrc/
├── en/
│   ├── features/ai-scribe.json
│   ├── pages/patients.json
│   └── common.json        # shared text (Save, Cancel, …)
├── hi/ …
└── te/ …
```

- Put shared text in `common.json`. Switch languages only through resource files.
- Creating a page/feature/component that shows text **requires** creating its resource
  entry in the same PR.

---

## Part 9 — Data & API Layer

- **Server data lives in TanStack Query**, never in component state or a global store.
  Reads go in `queries/` (shared) or a feature's `queries/`; writes go in `mutations/`.
- Use query-key constants, typed responses, and shared config. Never hardcode values
  inside a query.

```ts
export const QUERY_KEYS = { queue: ["queue"] as const };
```

- **One service file per domain.** API/HTTP logic lives in `services/` (shared) or
  `<feature>.api.ts` — **queries and mutations call services; they never contain raw HTTP
  logic themselves.** The `services/` layer holds the configured client, auth headers, and
  interceptors and contains **no React**.
- **Every data-loading screen handles four states** with shared components:
  `LoadingView`, `ErrorView`, `EmptyView`, `DataView`.
- **Session handling is centralized:** on `401`, clear the session and redirect to login
  in one place (an interceptor) — not per call.

---

## Part 10 — Forms, Validation & Security

- **Validate on the frontend before calling the API** (email, phone, GSTIN, PAN, ABHA,
  pincode, required fields) with clear, specific messages that match the backend.
  _Frontend validation is UX only — the backend is the source of truth and re-validates
  everything._
- Prefer one generic field handler over many single-purpose ones.
- Never expose secrets or API keys in the frontend; use environment variables (`config`).
  Keep sensitive data out of `localStorage`; prefer httpOnly cookies for the auth token
  where possible.
- Sanitize/escape any rendered untrusted content (no `dangerouslySetInnerHTML` without a
  sanitizer).

---

## Part 11 — Accessibility & Performance

- **Accessibility:** WCAG 2.1 AA baseline — semantic HTML, labels tied to inputs, ARIA
  where needed, full keyboard navigation, visible focus, sufficient contrast.
- **Performance:** optimize large lists, heavy components, and expensive calculations with
  memoization, pagination, virtualization, and lazy loading — **only where it clearly
  helps**. Lazy-load good candidates (reports, charts, large tables, admin modules).
- **Logging:** `console.log` is fine in dev but must not ship to production.

---

## Part 12 — Testing

State _what must be tested_ rather than chasing a coverage number:

- **Always unit-tested:** every utility function and all validation logic (pure, cheap).
- **Always integration-tested:** critical flows — login, queue check-in, consultation
  save, prescription create, payment.
- **Tested as needed:** components with real logic or conditional rendering. Trivial
  presentational components don't need a test.

Write the test in the **same PR** as the code.

---

## Part 13 — Pull Request Checklist

**Automated (CI must pass):**

- [ ] Build passes
- [ ] Type check passes (`strict`, no `any`/leaked `unknown`)
- [ ] ESLint + Prettier pass
- [ ] Tests pass
- [ ] No hardcoded strings, colors, sizes, fonts, or URLs (lint)

**Review (a human confirms):**

- [ ] Files live in the right folder; shared code promoted to the correct parent (Part 3)
- [ ] Each new/changed folder has an up-to-date `CLAUDE.md` (Part 2)
- [ ] Folder-scoped `.constants.ts` / `.types.ts` / `.api.ts` used correctly (Part 3.1)
- [ ] Validation added on frontend **and** confirmed on backend
- [ ] User-facing text localized in `rsrc/` (Part 8)
- [ ] Loading / error / empty / data states handled (Part 9)
- [ ] Design tokens used for all colors, spacing, and typography (Part 6)
- [ ] Names meaningful; comments explain _why_, not _what_
- [ ] No sibling-feature imports; import boundaries respected (Part 1.3)

---

## Part 14 — Rules for AI Assistants (Claude / Cursor)

Before creating anything:

1. **Reuse before creating** — search the codebase; create a reusable version only if
   none exists.
2. **Follow the folder structure** (Part 1) and the promote-upward rule (Part 3).
3. **Read and update the folder's `CLAUDE.md`** in the same change (Part 2).
4. **Keep types strict** — no `any`, no leaked `unknown` (Part 4).
5. **No hardcoded values** — tokens for visuals, constants for everything else (Parts 4, 6).
6. **Localize text** into `rsrc/` (Part 8); add validation (Part 10), accessibility
   (Part 11), and the four data states (Part 9).
7. Keep `.tsx` files ≤ 150 lines and single-responsibility (Part 7).

---

## Part 15 — Governance & Exceptions

- **Owner:** the frontend lead owns this document and reviews changes to it.
- **Proposing a change:** open a short PR against this file with the reason; the owner +
  one engineer review. Once merged it applies to new work.
- **Taking an exception:** a rule can be broken with a good reason recorded in the PR and
  one reviewer's agreement. A recorded, agreed exception is fine; a silent one is not.
- **Review cadence:** revisit quarterly — remove rules that no longer help, add ones the
  team has learned it needs.

The aim is a standard the team respects because it stays useful — not one it works around
because it has gone stale.
