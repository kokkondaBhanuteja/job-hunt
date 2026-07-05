# frontend/ — engineering standards (MANDATORY)

> **AI agents — Claude Code, Cursor, Codex, Copilot, and any other tool:**
> This file is your contract for every change under `frontend/`. Read it *before*
> proposing edits. Following it is not optional. If a rule blocks the change you
> were asked to make, stop and ask the user — do not silently break the rule.

Scope: everything under `frontend/src`. React 19 + Vite + TypeScript (strict) +
TanStack Query. **Tailwind CSS + shadcn/ui** for styling and components. Client
router (clean URLs, History API — see `src/lib/router.tsx`). Single-user local
tool served over `127.0.0.1`.

This doc is our tailored subset of the Tapza clinic frontend standards
(`~/Downloads/engineering-standards.md`). We take the rules that scale down to a
~1000-line SPA and defer the ones that only pay off at team/multi-feature scale.

---

## Agent quick-check (run through this on every change)

Before you finalize any edit under `frontend/`:

- [ ] No `any`. No `unknown` leaked out of a boundary.
- [ ] No hardcoded route, endpoint, query key, magic number, or user-visible
      string literal — pull from `src/lib/constants.ts` (add there if missing).
- [ ] Every new/changed **app** `.tsx` file is ≤ 150 lines. Split by extracting
      child components in the same file first, sibling files only when reused.
      **Generated shadcn/ui primitives under `src/components/ui/` are exempt**
      from this cap — they are vendored library code, not app code.
- [ ] Related files (component, its test, its page-scoped sub-components, its
      SCSS if applicable) live in the **same folder**. A component's test is
      `Foo.tsx` + `Foo.test.ts`, not a top-level `__tests__/` folder.
- [ ] Server state uses TanStack Query. URL state uses the client router
      (`src/lib/router.tsx`, History API — clean URLs, no `#`). Local UI state
      uses `useState`. **No** Redux/Zustand/etc.
- [ ] Data-loading views use `<LoadingView />`, `<ErrorView />`, `<EmptyView />`
      from `src/components/`. No ad-hoc `{isError && ...}` chains.
- [ ] Query invalidations are precise — the smallest key set that could be
      affected by the mutation. Never invalidate the whole cache except when
      the token changes.
- [ ] Auth failures are NOT handled per-caller; the `req()` wrapper in
      `src/lib/api.ts` owns 401 handling.
- [ ] Styling uses **Tailwind utilities + shadcn/ui components** with the token
      variables in `src/styles.css` (shadcn CSS-variable tokens, `.dark` class
      strategy). Plain CSS is only allowed when Tailwind + shadcn genuinely
      cannot express it — scoped, with a `/* why utilities weren't enough: … */`
      comment. No CSS-in-JS, no CSS Modules, no SCSS, no inline hex or raw
      pixel values in components.
- [ ] Responsive is mandatory: no horizontal page scroll at 375 / 768 / 1024 /
      1440px; use Tailwind breakpoints (`sm md lg`), not custom media queries;
      touch targets ≥ 40px on coarse pointers.
- [ ] Interactive elements are native or shadcn (`<Button>`, `<Input>`, native
      `<a>`) with labels tied to inputs (`htmlFor` / shadcn `<Label>`) and
      visible focus. WCAG 2.1 AA is the floor.
- [ ] Any backend DTO field change is mirrored in `src/lib/api.ts` in the same PR,
      and vice versa.
- [ ] Board `COLUMNS` in `src/pages/Board.tsx` is in sync with the `JOB_STATE`
      constants (which mirror `backend/job_hunt/enums.py::JobState`).
- [ ] Comments explain **why**, never **what**. Rename or refactor first.
- [ ] Non-trivial logic has a Vitest test in the same PR.
- [ ] `npm run build` passes locally. `npx vitest run` passes locally.

If you cannot check every applicable box, do not claim the change is complete.

---

## Rules we follow (the source of truth)

### Correctness

1. **Strict types.** No `any`. No `unknown` leaked out of a boundary. `strict: true`
   in `tsconfig.json` is not negotiable.
2. **Types mirror `backend/job_hunt/api/dto.py`.** Every response interface in `src/lib/api.ts`
   corresponds to a Pydantic DTO on the backend. Changes come in pairs.
3. **No hardcoded routes, endpoints, query keys, or thresholds.**
   - Routes live in `src/lib/constants.ts` as `ROUTES`.
   - API paths live in `src/lib/constants.ts` as `API_ENDPOINTS`.
   - Query keys live in `src/lib/constants.ts` as `QUERY_KEYS`.
   - Score thresholds live as named constants (`SCORE_THRESHOLDS`), not inline
     numbers.
4. **Enums, not string literals.** Job state values (`"discovered"`, `"scored"`,
   …) live in `src/lib/constants.ts` as `JOB_STATE` and mirror
   `backend/job_hunt/enums.py::JobState`. Referenced everywhere, declared once.

### Structure & size

5. **Every app `.tsx` ≤ 150 lines.** ~120 lines is the "look closer" signal.
   Split by extracting child components into the *same file* first, sibling
   files only when they're reused. **Generated shadcn/ui primitives under
   `src/components/ui/` are exempt** — treat them as vendored library code
   (edit sparingly, never restyle from scratch).
6. **One responsibility per component.** If a component fetches, transforms,
   *and* renders three sub-views, it's really three components — split.
7. **Small helpers stay local.** A helper used in one file lives in that file.
   Promote to a shared module only when a second consumer appears.
8. **Co-locate related files (tests, page-scoped components, styles).**
   Everything that belongs to the same feature lives in the same folder.
   - A component's test lives next to the component
     (`Board.tsx` → `Board.test.ts`, not in a top-level `__tests__/` folder).
   - Components that exist only to compose one page live in the **same folder**
     as that page. `pages/JobPanel.tsx` and `pages/JobActions.tsx` are only used
     by `pages/Board.tsx`, so they stay in `pages/`. Do not create a shared
     `components/` entry for a single-use component.
   - Reusable UI (`components/`) is only for things used by **2+ pages**.
   - When/if we adopt SCSS: a page's SCSS lives in that page's folder
     (`pages/Board.scss`), not in the global stylesheet.
9. **Folder layout stays flat until it hurts.**
   - `src/*.ts(x)` for **app shell only** — `App.tsx`, `main.tsx`,
     `ErrorBoundary.tsx`, `styles.css`. Keep this list short so the top level
     stays scannable.
   - `src/lib/*.ts` for framework-agnostic utility modules (`api.ts`,
     `constants.ts`, `format.ts`, `router.ts`) and their co-located tests.
     Add a new lib module only when it's a pure utility usable from anywhere.
   - `src/pages/*.tsx` for route-target components and their page-scoped
     supporting components + tests (rule 8).
   - `src/components/*.tsx` for UI used by 2+ pages (`LoadingView`, `ErrorView`,
     `EmptyView`).
   - **Promote a page to its own subfolder** (`pages/<page>/` with an
     `index.tsx` re-export) only when its supporting files reach **~4+**
     (component + 2 sub-components + test + style). Do not pre-create the
     subfolder for 1–2 files.

### Data & state

10. **Server state → TanStack Query. URL state → client router (clean URLs).
    Local UI → `useState`.** That is the whole state-management story. No
    Redux, no Zustand, no Jotai. Internal navigation uses the `<Link>` component
    from `src/lib/router.tsx`; programmatic navigation uses `navigate()` from
    the same module. Never write `<a href="/board">` directly for internal
    links — that would trigger a full page reload.
11. **Every data-loading view handles four states:** loading, error, empty, data.
    Use the shared `<LoadingView />`, `<ErrorView />`, `<EmptyView />` primitives
    from `src/components/`. Ad-hoc `{isError && ...}` chains are not allowed in
    new code.
12. **401s handled once.** The `req()` wrapper in `src/lib/api.ts` clears the token
    and pushes `#/settings` on 401. Individual callers never handle auth
    failure.
13. **Invalidate precisely.** After a mutation, invalidate the smallest set of
    query keys that could be affected. Over-invalidation is wasted work. The
    only place a bare `qc.invalidateQueries()` (no filter) is allowed is when
    the connection config changes.

### Style

14. **Tailwind CSS + shadcn/ui is the app-wide standard.** Default to Tailwind
    utility classes and shadcn components. Plain CSS is only allowed when
    Tailwind + shadcn genuinely cannot express it (bespoke keyframe,
    non-tokenizable gradient, a layout materially clearer as CSS) — scope it
    and add a `/* why utilities weren't enough: … */` comment. **No CSS-in-JS,
    no CSS Modules, no SCSS.** Never inline a hex or a raw px in a component.
    `src/styles.css` holds only the Tailwind directives, the shadcn token
    variables for `:root` (light) and `.dark`, and justified exceptions.
15. **Theming uses shadcn CSS-variable tokens with the `.dark` class strategy**
    on `<html>`. The token names (`--background`, `--foreground`, `--card`,
    `--primary`, `--muted`, `--border`, `--destructive`, …) are the palette
    contract — do not invent new color values in components. A small local
    theme provider (persists to `localStorage`) toggles `.dark`; **do not add
    `next-themes` or any other theming library.**
16. **Responsive is mandatory** on every view: no horizontal page scroll at
    375 / 768 / 1024 / 1440px; use Tailwind breakpoints (`sm md lg`), not
    custom media queries. Tables get `overflow-x-auto` or become stacked cards
    on small screens. Touch targets ≥ 40px on coarse pointers.
17. **Accessibility baseline:** semantic HTML, labels tied to inputs (`htmlFor`
    or shadcn `<Label>`), keyboard-focusable interactive elements (native
    `<button>`, `<a>`, `<input>` or their shadcn wrappers), visible focus rings
    (shadcn ships `:focus-visible` styles), sufficient contrast in both themes.
    WCAG 2.1 AA is the floor.

### Allowed dependencies (exhaustive)

Runtime and dev deps outside `package.json` at the start of this migration
require owner approval. The migration allow-list is:

- `tailwindcss` (v4) + `@tailwindcss/vite`.
- shadcn/ui components, **only** from this list:
  `Button, Input, Textarea, Select, Switch, Checkbox, Label, Card, Tabs, Table,
  Form, Skeleton, Sonner (toast), Dialog, Sheet, DropdownMenu, Tooltip, Badge,
  Separator, ScrollArea, Alert`.
- shadcn support deps: `class-variance-authority`, `clsx`, `tailwind-merge`,
  `lucide-react`, `tw-animate-css`.
- Forms: `react-hook-form` + `zod` + `@hookform/resolvers` (form state only).

Anything not on this list — including additional shadcn components or a
different icon set — needs owner sign-off before `npm install`.

### Process

18. **Tests live alongside the code they cover.** Vitest is the runner. Utility
    functions and non-trivial component logic are tested in the same PR.
    Trivial presentational components don't need tests. See rule 8 for
    co-location.
19. **Comments explain *why*, never *what*.** If the *what* is unclear, rename
    or refactor first. Reserve comments for constraints, workarounds, and links
    to external context.
20. **Every PR runs `npm run build` and `npx vitest run` locally.** `tsc -b`
    catches type drift before reviewers do; vitest catches logic regressions.

---

## Rules we explicitly do NOT follow (and why)

We considered these from the Tapza doc and declined:

| Tapza rule | Why we skip |
|---|---|
| `features/` folder with `<feature>.api.ts` / `.types.ts` / `.constants.ts` per feature | We have 6 pages, no features. Would triple the file count for no clarity gain. Revisit if we pass ~12 pages. |
| `CLAUDE.md` in every folder | Three folders total (`src/`, `src/pages/`, `src/components/`). One `CLAUDE.md` at `frontend/` covers everything. Revisit if we grow beyond 4 subfolders. |
| `rsrc/en/hi/te` localization | Single-user personal tool, English only. Localization is not planned. Add if the app ever becomes multi-user. |
| react-bootstrap / SCSS / design-token files under `core/` | The whole frontend is ~150 lines of CSS. Bootstrap + SCSS would be a rewrite, not a standard. |
| Separate `queries/` and `mutations/` folders | ~15 total React Query calls. Splitting them across folders makes navigation worse, not better. |
| `layouts/` folder + React Router 7 + guards | Our client router (`src/lib/router.tsx`, ~90 LOC, History API + Link) is enough for 6 screens with one shared layout — the topbar in `App.tsx`. Adopt React Router when we need nested routes, loaders, or per-route guards. |
| Pages must not import `services/` directly | The current `api.ts` *is* the service layer. Adding an intermediate hook layer for every endpoint is pure indirection at this scale. |

Every declined rule is a *deferral*, not a rejection. When the trigger in the
"Why we skip" column fires, revisit that row.

---

## Revisit thresholds

Adopt the corresponding Tapza rule when:

- The app crosses **~12 pages** → introduce `features/`.
- `src/lib/api.ts` crosses **~400 lines** → split into `api/client.ts` + `api/types.ts`
  + per-domain files.
- The app gains a **second user** → adopt `rsrc/` localization.
- CSS crosses **~500 lines** → move to SCSS + tokenized variables in `core/`.
- We hire a **second contributor** → adopt `CLAUDE.md`-per-folder.

---

## Where things go (current quick reference)

| Adding… | Put it in… |
|---|---|
| A screen tied to a URL | `src/pages/<Page>.tsx` |
| A component that only composes one page | that page's folder — `src/pages/` |
| A helper used by one file | inline in that file |
| A component used by ≥2 pages | `src/components/` |
| A test for anything | next to the source file (`Foo.tsx` → `Foo.test.ts`) |
| An API call | `src/lib/api.ts` |
| A response type | `src/lib/api.ts` (mirror `dto.py`) |
| A constant, route, endpoint, query key, threshold | `src/lib/constants.ts` |
| A framework-agnostic utility (dates, formatters, parsers) | `src/lib/` |
| A style rule | Tailwind utility on the element (default); `src/styles.css` only if not expressible in utilities |
| A shadcn theme token / palette entry | `src/styles.css :root` (light) and `.dark` block |
| A generated shadcn primitive | `src/components/ui/<name>.tsx` (vendored — do not restyle) |
| A React Query key | `QUERY_KEYS` in `src/lib/constants.ts` |
| A future page-scoped SCSS file | that page's folder — same as its `.tsx` |
| A page that outgrew `pages/*.tsx` (4+ files) | promote to `pages/<Page>/` |
| A new app-shell file (provider, boundary, root) | `src/` (kept short) |

---

## PR checklist

Automated (CI/build):

- [ ] `npm run build` passes (includes `tsc -b`).
- [ ] `npx vitest run` passes.
- [ ] No `any` or leaked `unknown`.

Review judgment:

- [ ] No hardcoded routes, endpoints, query keys, or magic numbers.
- [ ] New/changed `.tsx` files are ≤ 150 lines and single-purpose.
- [ ] New data-loading views use the four shared state components.
- [ ] Backend DTO changes are mirrored in `src/lib/api.ts` in the same PR.
- [ ] Board `COLUMNS` in `pages/Board.tsx` is in sync with `backend/job_hunt/enums.py::JobState`.
- [ ] Names explain the *what*; comments explain the *why*.
- [ ] Interactive elements are native (`<button>`, `<a>`, `<input>`) with labels
      and visible focus.
- [ ] Vitest tests added for any non-trivial logic.

---

## Extended rules for AI assistants

These are the same rules restated with imperative language for AI tools:

1. **Reuse before creating.** Search `src/` for an existing component/hook/util
   before adding one. If a similar thing exists, extend it via props.
2. **Follow the folder layout** in "Where things go" above. Do not invent new
   folders. If you think a new folder is genuinely needed, ask the user first.
3. **Read this file at the start of every session** where you touch `frontend/`.
   Do not rely on memory of a previous session.
4. **Update this file in the same change** whenever the scope, rule set, or a
   "revisit threshold" changes. Silent drift is worse than no rules.
5. **Types are strict.** Do not use `any` to silence a compiler error. If you
   need `unknown`, narrow it with a type guard *immediately* — never let it
   leak into a signature or exported type.
6. **Do not hardcode values.** Routes → `ROUTES`; endpoints → `API_ENDPOINTS`;
   query keys → `QUERY_KEYS`; thresholds → `SCORE_THRESHOLDS`; state strings →
   `JOB_STATE`. If a needed constant is missing, add it to `src/lib/constants.ts`
   in the same change.
7. **Data-loading uses the four shared views.** `LoadingView`, `ErrorView`,
   `EmptyView`, and the actual data render. No exceptions.
8. **Do not add dependencies without asking.** The current deps list is
   deliberate. If a task needs a new library, stop and ask the user.
9. **Do not disable strict TS, eslint rules, or tests.** If a rule is wrong,
   propose a change to this file — don't bypass.
10. **Verify before claiming done.** Run `npm run build` and `npx vitest run`.
    Report the actual output; do not assume.

---

## Governance

If a rule stops helping, propose a change in a PR against this file — same
review bar as code. Silent exceptions are not fine; documented ones are.
Revisit this doc quarterly (or when a "revisit threshold" fires).
