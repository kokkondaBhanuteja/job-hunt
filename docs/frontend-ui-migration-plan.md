# R-CRAFT Spec — Frontend UI Migration to Tailwind + shadcn/ui (app-wide)

> This document is an **execution contract for AI agents** (Claude Code, Cursor,
> Codex, Copilot). It is written so an agent builds a **responsive, modern UI**
> exactly as specified and **cannot invent scope, features, screens, components,
> or dependencies** that are not listed here. If something you want to do is not
> explicitly permitted below, it is **out of scope** — STOP and ask the owner.
>
> Reviewed at commit `24c01c5`. Read `frontend/CLAUDE.md` before any edit.

---

## R — Role

You are a **Senior Frontend Engineer** migrating the `frontend/` SPA to
**Tailwind CSS + shadcn/ui** and delivering a **responsive, modern, accessible**
UI with **light + dark** themes. You implement the spec below literally. You do
**not** act as a product designer inventing new features. You do **not** redesign
flows that are not named here.

---

## C — Context

- Stack: React 19 + Vite + TypeScript (strict) + TanStack Query + hash router.
- Today: one global `src/styles.css` (192 lines) with `:root` CSS variables. Dark
  theme only. Plain CSS, native elements.
- The app has exactly these pages/areas — **this is the complete list; do not add
  pages**:

  | Area | Files |
  |---|---|
  | App shell | `App.tsx`, `main.tsx`, `ErrorBoundary.tsx`, `styles.css` |
  | Board | `pages/Board/*` |
  | Inbox | `pages/Inbox/*` |
  | Runs | `pages/Runs.tsx` |
  | Analytics | `pages/Analytics.tsx` |
  | Settings | `pages/Settings.tsx` + `ContextPanel.tsx` + `ApplicantPanel.tsx` + `SearchPrefsPanel.tsx` |
  | Shared views | `components/LoadingView.tsx`, `ErrorView.tsx`, `EmptyView.tsx` |

- Decided direction (owner): **Tailwind + shadcn is the app-wide UI standard.**
  Responsiveness and light/dark come from Tailwind breakpoints + shadcn tokens —
  not hand-written media queries.
- `frontend/CLAUDE.md` currently forbids Tailwind/shadcn/new-deps. This spec
  supersedes it; **Phase M task 1 amends that file**. Until amended, do not start
  component work.

---

## R — Requirements

### Allowed technology (exhaustive — do not add anything else)

- `tailwindcss` + Vite plugin. Default to **Tailwind v4** unless owner says v3.
- shadcn/ui components, **only** from this allow-list:
  `Button, Input, Textarea, Select, Switch, Checkbox, Label, Card, Tabs, Table,
  Form, Skeleton, Sonner (toast), Dialog, Sheet, DropdownMenu, Tooltip, Badge,
  Separator, ScrollArea, Alert`.
- shadcn support deps: `class-variance-authority`, `clsx`, `tailwind-merge`,
  `lucide-react`, `tailwindcss-animate` / `tw-animate-css`.
- Forms: `react-hook-form` + `zod` + `@hookform/resolvers` (form state only).
- **Any dependency not in this list → STOP and ask.** Do not `npm install`
  anything else. Do not pull an icon set other than `lucide-react`.

### Styling rules (app-wide)

1. **Default to Tailwind utilities + shadcn components.** Every page and shared
   component migrates to this.
2. **Write plain CSS/SCSS only when Tailwind + shadcn genuinely cannot express it**
   (bespoke keyframe, non-tokenizable gradient, a layout materially clearer as
   CSS). When you do, scope it and add a `/* why utilities weren't enough: … */`
   comment. **No new CSS-in-JS, no CSS Modules.**
3. **Theming:** shadcn CSS-variable tokens with the `.dark` class strategy on
   `<html>`. Map the existing palette onto tokens — **use exactly these mappings,
   do not invent new color values**:

   | Existing var | shadcn token (dark = current look) |
   |---|---|
   | `--bg #0f1216` | `--background` |
   | `--panel #171b21` | `--card`, `--popover` |
   | `--panel-2 #1e242c` | `--secondary`, `--muted` |
   | `--line #2a323c` | `--border`, `--input` |
   | `--text #e6eaef` | `--foreground` |
   | `--muted #8b97a6` | `--muted-foreground` |
   | `--accent #4f9dff` | `--primary` |
   | `--bad #f87171` | `--destructive` |
   | `--ok #34d399` / `--warn #fbbf24` | keep as semantic status tokens |

   Design a **light** counterpart for each. Do not introduce brand colors beyond
   these.
4. **Responsive is mandatory** on every migrated view: no horizontal page scroll
   at 375 / 768 / 1024 / 1440px; tables get `overflow-x-auto` or become stacked
   cards; touch targets ≥ 40px on coarse pointers. Use Tailwind breakpoints
   (`sm md lg`), not custom media queries.

### Rules kept from `CLAUDE.md` (do not break)

- Strict TS, no `any`; response types mirror `backend/job_hunt/api/dto.py`.
- No hardcoded routes/endpoints/query keys/thresholds → `src/lib/constants.ts`.
- Server state → TanStack Query; URL → hash router; local UI → `useState`;
  form state → react-hook-form. **No Redux/Zustand.**
- Four data-loading states everywhere (loading → `Skeleton`).
- 401 handled once in `req()`; precise query invalidation.
- Board `COLUMNS` stays in sync with `backend/job_hunt/enums.py::JobState`.
- Co-locate files; keep components focused.

### Scope boundaries — DO NOT (anti-hallucination)

- ❌ Do **not** add pages, tabs, routes, or nav items beyond those in Context.
- ❌ Do **not** implement any item from "Deferred backlog" unless the owner
  assigns it. Listing ≠ permission.
- ❌ Do **not** add new settings fields, endpoints, or DTOs. UI-only migration.
  A backend/DTO change requires owner approval and a paired `api.ts` edit.
- ❌ Do **not** redesign copy, iconography, or flows not named in a task.
- ❌ Do **not** invent empty states, illustrations, onboarding, or animations not
  requested.
- ❌ Do **not** change behavior while restyling — a migrated component must be
  behavior-identical unless a defect (D1–D10) says otherwise.
- ❌ Do **not** install unlisted deps or add unlisted shadcn components.
- ⚠️ When a task is ambiguous or tempts you outside these lines → **STOP and ask**,
  do not guess.

---

## A — Actions (phased, ordered — do them in this sequence)

Each phase ends with `npm run build` + `npx vitest run` green, and a co-located
Vitest test for any non-trivial new logic. Do not start a phase before the prior
one is green.

### Phase M — Foundation (blocks all component work)
1. Amend `frontend/CLAUDE.md` to the Tailwind + shadcn standard (styling rule,
   theming, allowed deps, relaxed file-size note).
2. Install/configure Tailwind (Vite plugin); add `@/` alias in `tsconfig.json` +
   `vite.config.ts`; run `shadcn init` → `components.json`, `src/lib/utils.ts`.
3. Add the token mappings above for `:root` (light) and `.dark`.
4. Add theme provider + topbar toggle (class strategy, `localStorage`; small local
   provider — **do not** add `next-themes`).
5. Generate only the allow-listed shadcn components.
**Done when:** build green; theme toggle flips light/dark app-wide; old pages
still render (Tailwind is additive).

### Phase 0 — Settings quick fixes
Fix D1, D4, D5, D6, D9 (D2 comes free from shadcn focus rings).

### Phase 1 — Settings IA (shadcn `Tabs`)
Rebuild `Settings.tsx` as a shell: vertical tab rail `md:`+, scrollable tabs on
mobile. Extract `ConnectionPanel.tsx` + `ProfilesPanel.tsx` (co-located). Merge
Search preferences + Search profiles into one "Search" tab (D7).

### Phase 2 — Settings shared abstraction
Add `useSettingsForm<T>()` (value-diff dirty, owns Sonner confirm → D1 once) and
`<SettingsSection>` (shadcn `Card` wrapper: header + four states + Save +
last-updated → D3 once). Refactor all four panels onto them.

### Phase 3 — Settings field quality
D8: Applicant on shadcn `Form` (rhf + zod) — typed fields, inline `FormMessage`,
`FormDescription` helper text, grouped Personal · Links · Compensation · Logistics,
`md:grid-cols-2`. `work_authorization`/`notice_period`/`referral_source` → `Select`.
D10: Profiles → shadcn `Table` in `overflow-x-auto`, row Edit/Delete via `Dialog`,
real `Label`s. Health readout → labeled rows + `Badge`s.

### Phase 4 — Settings polish
Contrast check both themes; touch targets; route-leave dirty guard; manual pass
375/768/1024/1440px in light + dark.

### Phase 5 — Roll out to the rest of the app (restyle only, behavior-identical)
- App shell (`App.tsx`): topbar → responsive shadcn nav; keep offline/unauthorized
  states (as `Badge`s).
- Board (`Board/*`): columns/cards/scores/pills → Tailwind + `Card`/`Badge`;
  detail panel → `Sheet` on mobile; keep `COLUMNS`↔`JobState`.
- Inbox (`Inbox/*`): responsive list/detail; `ConfirmModal` → `Dialog`.
- Runs (`Runs.tsx`): → `Table` + status `Badge`s.
- Analytics (`Analytics.tsx`): funnel/metrics → `Card` grid, responsive columns.
- Shared views: back `LoadingView`/`ErrorView`/`EmptyView` with `Skeleton`/`Alert`;
  keep the same call sites and props.

### Phase 6 — Cleanup
Shrink `styles.css` to tokens + justified exceptions only; remove dead classes;
final a11y + responsive sweep, both themes.

---

## Defect reference (Settings pilot — fix exactly these, invent no others)

| ID | File / line | Defect | Required fix |
|---|---|---|---|
| D1 | `ContextPanel.tsx:76`, `ApplicantPanel.tsx:84`, `SearchPrefsPanel.tsx:62` | Sticky permanent "Saved ✓". | Sonner toast; button "Save changes", disabled when `!dirty`. |
| D2 | `styles.css` | No `:focus-visible`. | Inherited from shadcn. |
| D3 | 4 panels | No loading state. | shadcn `Skeleton`. |
| D4 | `Settings.tsx:40` | Blank API base saves `""`. | Fall back to `DEFAULT_API_BASE`. |
| D5 | `Settings.tsx:126–130` | Toggle has no accessible name. | `Switch` + `aria-label`. |
| D6 | `Settings.tsx:109,120` | DB `id` leaked in UI. | Remove column. |
| D7 | Sections 4+5 | Prefs vs profiles overlap. | Merge into one "Search" section. |
| D8 | `ApplicantPanel.tsx:69–78` | Untyped inputs, no validation/grouping/help. | shadcn `Form` (rhf+zod). |
| D9 | `ApplicantPanel.tsx:81` | Save gated on `isPending` not dirty. | rhf `formState.isDirty`. |
| D10 | Profiles table | Mobile overflow; no edit/delete. | `Table` in scroll container + `Dialog` actions. |

---

## F — Format (how the agent reports each task)

For every task, output in this exact structure — nothing extra:

```
### <Phase>.<task> — <title>
Files touched: <paths>
Change: <1–3 sentences, what + why>
Defects addressed: <IDs or "none">
Verification: build <pass/fail>, vitest <pass/fail>, responsive <breakpoints checked>, themes <light/dark checked>
Open questions: <blockers or "none">
```

- No speculative "future improvements" sections. No new feature proposals.
- If blocked, report under "Open questions" and stop — do not improvise.

---

## T — Tone

Literal, disciplined, minimal. Implement the named change and nothing more. Prefer
asking over assuming. Behavior-preserving unless a defect ID authorizes a change.
"Clever" additions are defects here.

---

## Deferred backlog (NOT authorized — reference only, needs explicit owner sign-off)

AI model config · LLM provider API-keys UI · notifications prefs · résumé/document
management · run scheduling · data export / danger zone · auto-apply guardrails.
Do not build any of these without a direct instruction.
