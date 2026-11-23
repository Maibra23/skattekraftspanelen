# Skattekraftspanelen — One-Day Modernization Runbook

This supersedes **Part B** (§B2 task table, §B3 five-day schedule) of
`UX_UI_MODERNIZATION_PLAN.md`. **Part A is unchanged and remains the
specification** — every "what and why" question is answered there, and this
document does not repeat it. §B4 prompts, §B5 regression checklist and §B6
rollback remain in force; this runbook only changes *sequencing, gating and
commit granularity*.

Mode: **single continuous session, no stop for approval mid-run.**

---

## 0. Feasibility basis

Measured on `ux/modernization` at `ce40d14`:

| Fact | Value | Consequence |
|---|---|---|
| `pytest -q` | 452 passed, 16.7 s | Full regression after every task is affordable. |
| `tests/test_pages_render.py` | 28 passed, 4.7 s | Render breakage is caught in seconds. |
| Code surface | ~5,300 lines / 9 files | Localised edits; no module is rewritten. |
| New dependencies | none | `test_requirements.py` stays green by construction. |
| Build / deploy / data steps | none | No waiting on anything external. |

The five-day estimate was human-paced authoring plus manual inspection at
four widths on three pages. The compression comes from (a) a 20-second
automated gate replacing manual passes, and (b) batching browser
verification instead of doing it 19 times.

---

## 1. Preconditions — decided, not asked

These were §A10 open items R-1…R-6. All are hereby **locked to the
recommended default** so the run never blocks:

| ID | Locked decision |
|---|---|
| R-1 | Kommun outside the band filter: **fall back to nearest valid + show notice.** |
| R-2 | Band filter **hidden on the start page** (it filters nothing there). |
| R-3 | Band filter **persists across pages** via session state. |
| R-4 | Concept expander **moves below** the stat strip. |
| R-5 | **Red removed** from KPI "danger"; tone carried by ▲/▼ + `negative_text` #9A4F06. |
| R-6 | Footer shows **data-generated date** (2026-09-07), not file mtime. |

If any of these is wrong, say so **before** the run starts — reversing R-3 or
R-6 mid-run invalidates Phase 2 and Phase 5 work.

Standing constraints **SC-1…SC-8** (§B4.0) apply unchanged, with one
amendment: **SC-1 is relaxed** from one commit per task to one commit per
phase (§4).

---

## 2. Phase plan

Six phases, strict order. Dependencies are preserved exactly as in the §B2
table — no task runs before its predecessor.

### Phase 0 — Baseline (was T01, T02)
* Annotated tag `pre-ux-modernization` on `main` @ `c818fa7`.
* Pin `.venv` to `streamlit==1.55.0` (matches `requirements.txt`; venv
  currently holds 1.56.0 — finding P-18).
* Confirm every API the plan uses exists in 1.55.0: `st.fragment`,
  `st.query_params`, `[theme.sidebar]` config, `st.page_link`.
* Record the 452-test baseline and "before" screenshots **outside the repo**
  (scratchpad), at 390 and 1440 for all three pages.

**Gate G0:** 452 passed on 1.55.0. If the version swap breaks tests, that is
a real finding — fix or report before any UI work.

### Phase 1 — Foundation (was T03, T04, T05)
* Design tokens v2 in `css.py` + native `[theme]` / `[theme.sidebar]` in
  `.streamlit/config.toml`. New contrast-safe tokens: `accent_text` #8A6D2B,
  `accent_on_dark` #E2C98F, `negative_text` #9A4F06. Map ramps
  (`POSITION_SCALE`, `DIVERGING_SCALE`, `CHART_PALETTE`) **untouched** —
  they are test-pinned.
* App shell: restore the mobile sidebar toggle (the 0×0 button at 390 px
  caused by hiding `stHeader`), visible focus rings, chrome cleanup.
* Cleanup: dead CSS and tokens, single-source `APP_VERSION`, provenance date.

**Gate G1:** suite green; Playwright at 390 and 1440 on all three pages —
sidebar toggle has non-zero box and opens; no console error; focus ring
visible on tab.

### Phase 2 — Shell and design system (was T06, T07, T08)
* Sidebar v2: navigation, filter scope (hidden on start page), persistence.
* Component library v2: KPI v2 (unit, context, tone via ▲/▼, no red),
  provenance chips (Observerat / Modell / Prognos), callout, headings, notes.
* Chart theme v2: `separators=", "`, transparent backgrounds, one shared
  `CHART_CONFIG`.

**Gate G2:** suite green; filter survives a page switch and is absent on the
start page; a chart hover shows `248 378` (space group, comma decimal).

### Phase 3 — Pages (was T09, T11, T10, T13)
Order is T09 → T11 → T10 → T13 (T10 depends on both T09 and T11).
* Riksöversikt header + KPI row.
* Kommun persistence: `?kommun=<kod>` + session; KPI v2; peer links.
* Ranking table v2: alignment, count, pinned column, help, row → kommun
  deep link.
* Start page IA: CTAs, single diagram card, real link cards.

**Gate G3:** suite green **and the five SC-5 anchors verified explicitly** —
`riks.radio[0]` is the layer radio; `riks.dataframe[0]` has 290 rows;
`riks.multiselect[0]` has 290 options; `kommun.selectbox[0]` has 290 options
whose labels contain "index" and not "rang"; the controls table keeps
`vars_table_ci`; `0,02` and `1,51 procentenheter` render without
interaction. Plus: `?kommun=0180` opens Stockholm; a table row opens that
kommun.

### Phase 4 — Polish (was T12, T14, T16, T15) — **the cut zone**
* T12 forecast panel restructure (units, benchmark chart, grouped text).
* T14 map/histogram `@st.fragment` + cached styled GeoJSON + equal heights.
* T16 loading / empty / notice states.
* T15 responsive pass at 390 / 768 / 1024 / 1440.

**T15 is P1 and never cut.** If the session is running long at G3, drop in
this order: **T14, then T12, then T16** — all P2 — and record each as
deferred in the report. Do not cut by abandoning a task half-finished;
either a task lands complete or it is not started.

**Gate G4:** suite green; four widths × three pages captured with no
overflow, no clipped control, no blank state.

### Phase 5 — QA and documentation (was T17, T18, T19)
* `tests/test_design_tokens.py` (new): asserts AA contrast for every text
  token pair, so the fix cannot silently regress.
* Full §B5 regression checklist, every line ticked or explained.
* `docs/PRD.md` §6/§7, `README.md`, and
  `UX_UI_IMPLEMENTATION_REPORT.md` (what changed, what was cut, before/after
  evidence, measured contrast figures).

**Gate G5:** suite green including the new contrast test; §B5 fully ticked;
report written.

---

## 3. What is explicitly *not* in scope

Unchanged from the original plan's rejected list — these are not revived to
fill a one-day window: `st.navigation` migration (deferred D-1), AgGrid,
`streamlit-option-menu`, Lucide icons, Altair, dark mode. No change to
`pipeline.py`, `src/fetch/`, `src/clean/`, `src/model/`, `artifacts/`,
`data/` (SC-2).

---

## 4. Commits

One commit per phase, six total, each message prefixed with the phase and
the tasks it carries:

```
P1(T03,T04,T05): contrast-safe tokens, native theme, mobile shell
```

Rationale for relaxing SC-1: per-task commits exist to give fine-grained
revert points. With `pre-ux-modernization` tagged and each phase gated, a
phase is the smallest *independently verified* unit — a mid-phase commit is
not a safe revert target anyway. Six reviewable commits also read better
than nineteen.

Push after each phase, so an interrupted run leaves the completed phases on
`origin/ux/modernization`.

---

## 5. Resume protocol (the real risk)

The limiting factor is not hours, it is **context**: this work will span
several compactions. Guard:

* After each phase, append to `UX_UI_PROGRESS.md` (committed with the
  phase): phase completed, tasks landed, tasks cut, test count, gate result,
  and any decision taken that is not already written in Part A.
* That file plus Part A is sufficient to resume cold. A fresh context reads
  Part A §A6/§A7 for the spec and `UX_UI_PROGRESS.md` for position, then
  starts the next phase — no re-derivation, no re-audit.
* Never leave a phase half-committed at a context boundary.

---

## 6. Rollback

§B6 applies unchanged. Summary: `main` is untouched throughout; everything
lands on `ux/modernization`. `git reset --hard pre-ux-modernization`
discards the lot; reverting a single phase commit discards exactly that
phase's work and leaves the gates below it intact.

---

## 7. Honest limits of this compression

* **Taste is not compressible.** Visual judgment at four widths is
  comparatively slow, and it is the one place where a hurried run shows. T15
  is P1 for that reason and is protected from the cut list.
* **An unknown found mid-run costs its own time.** If Phase 0 shows that
  1.55.0 lacks an API the plan assumes, or the 1.56.0 → 1.55.0 swap breaks
  tests, that is new work the budget does not contain. It gets reported, not
  absorbed by skipping gates.
* **Gates do not get skipped to make the day.** If something has to give, it
  is scope from the §4 cut list — never verification. A green suite with
  three P2 tasks deferred is a good outcome; an ungated full sweep is not.
