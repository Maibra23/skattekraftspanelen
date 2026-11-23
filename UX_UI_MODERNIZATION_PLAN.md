# UX/UI Modernization Plan: Skattekraftspanelen

**Status:** Proposal. Awaiting approval. No source file has been modified.
**Date:** 2026-11-23
**Baseline:** branch `main` at `c818fa7` (2026-09-13). Verified as the latest
version: `origin/main` is identical, and every other branch
(`remediation/model-layer`, `claude/verify-and-implement-tasks-Fi7wE`,
`origin/claude/review-swedish-vowels-xIG1P`) is 0 commits ahead of `main`.
**Test baseline:** `pytest` on the baseline: **452 passed**, 0 failed.
**Stack verified:** Streamlit (pinned `1.55.0` in `requirements.txt`, but
`1.56.0` installed in the local `.venv`; see finding P-18), Plotly 6.7,
Folium + streamlit-folium, pandas/pyarrow. No database, no authentication,
no forms, no dialogs, no external calls at runtime (the app reads committed
parquet only; the only network dependency is Esri map tiles and Google Fonts).

How this audit was done: every UI source file was read in full (`app.py`,
`pages/01_Riksoversikt.py`, `pages/02_Kommunjamforelse.py`, `src/ui/*.py`,
`.streamlit/config.toml`), together with the tests that constrain the UI
(`tests/test_pages_render.py`, `test_labels.py`, `test_choropleth.py`,
`test_copy_matches_artifacts.py`, `test_requirements.py`, `test_filters.py`),
the PRD, the README and the provenance artifact. The running app was then
inspected in a browser at 1440 px and 390 px, with computed styles and
contrast measured from the live DOM. Every finding below cites the file or
the measurement it rests on.

---

# PART A: UX/UI MODERNIZATION PROPOSAL

## A1. Executive Summary

### Current product assessment

Skattekraftspanelen is a three-page Streamlit dashboard showing where each of
Sweden's 290 kommuner stands in skattekraft (taxable income per inhabitant)
against the national average, how that position has moved over 5 and 10
years, which structural variables explain it, and a five-year drift forecast
published together with its own backtest.

The analytical substance is unusually strong and carefully guarded. A test
suite pins every number quoted in the copy to the artifacts. The number
formatting policy is singular. Colour ramps are colour-blind-safe. Every
chart has a reading guide, and glossary help travels to the section that
needs it. The redesign must not dilute any of that.

The interface layer has not kept pace. It is a navy and gold skin carried over
from a reference design ("SHAI"), with roughly 1,050 lines of CSS. Much of
that CSS fights Streamlit with `!important` and targets DOM test IDs that
changed in later Streamlit releases. The result is a product that looks
finished on a desktop screenshot and breaks in several measurable ways.

### Main UX/UI weaknesses (ranked by impact)

1. **On a phone the app cannot be navigated.** The CSS hides
   `header[data-testid="stHeader"]`, and in this Streamlit version that header
   holds the only control that opens the sidebar (`stExpandSidebarButton`,
   measured at 0×0 px at 390 px width). Page navigation and the position
   filter both live in the sidebar, so a mobile user is stuck on the first
   page they land on.
2. **Several text colours fail WCAG AA contrast.** Measured: active filter
   pills 1.8:1, gold eyebrow and year text 2.4:1, data vintage line 2.4:1,
   sidebar footer 3.1:1 at 10 px.
3. **The one shared filter is not shared and is sometimes inert.** The
   position band filter appears on the start page, where nothing reacts to
   it. It also resets on every page change, because the widget has no key
   and no persisted state.
4. **The core journey ("how is my kommun doing?") has no memory and no
   entry point.** The kommun selection is not persisted or linkable, and
   opens on Högsby every time. Nothing in the national table, map or peer
   table leads into a kommun's detail page.
5. **Affordances lie in two places.** The start page's navigation cards
   have `cursor: pointer` and a hover border but are not links (the real link
   is plain text underneath). The active sidebar item is an `<a href="#">`.
6. **The financial data presentation is inconsistent.** Plotly hover text
   uses English number formatting (`248,378`, `96.6`) beside a Swedish
   decimal-comma policy. Falls are drawn in **red** on KPI cards, while the
   maps deliberately avoid red to avoid implying "below average = bad". KPI
   values have no units ("2,1" of what?). Table columns mix left- and
   right-aligned numbers.
7. **Dense prose blocks.** Explanations run at 13 px grey across lines of
   about 200 characters, and the forecast panel stacks five paragraphs.
8. **The trust signal is wrong.** "Senast uppdaterad" is the file
   modification time. On Streamlit Cloud that is the clone time, not the
   data date. The real date is in `artifacts/data_provenance.json`
   (`generated_at`).

### Modernization objectives

* Make every page reachable and usable on every screen size.
* Bring all text to WCAG 2.1 AA contrast and give every interactive element a
  visible focus state.
* Make the main journey continuous. Any kommun seen anywhere can be opened in
  one action. The chosen kommun persists and can be shared as a URL.
* Present financial and statistical figures in one consistent, Swedish,
  unit-labelled way, with an explicit marker of what is **observed**, what
  is **modelled** and what is a **forecast**.
* Replace fragile CSS overrides with Streamlit's native theming and a small,
  tokenised component layer.
* Preserve every feature, number, explanation and test guarantee.

### Expected improvements

Mobile navigation goes from impossible to native. Contrast failures drop to
zero (enforced by a new test). The kommun journey drops from about four
actions (navigate, open selector, type, choose) to one click from the
national table, and becomes shareable by URL. CSS volume drops by an
estimated 30 to 40 % as native theming replaces overrides. A map layer toggle
no longer reruns the whole page.

---

## A2. Existing Application Assessment

### A2.1 Architecture

```
app.py                       Start page (entry point, Streamlit multipage v1: pages/ dir)
pages/01_Riksoversikt.py     National overview
pages/02_Kommunjamforelse.py Kommun detail
src/ui/css.py                COLORS, ramps, GLOBAL_CSS (~930 lines of CSS), inject_css()
src/ui/components.py         HTML-string builders: page_title, kpi_card, card_header, help_badge, footer_note
src/ui/sidebar.py            Shared sidebar: brand, nav, band filter (st.pills), legend, footer
src/ui/chart_theme.py        get_chart_layout(): Plotly layout dict
src/ui/choropleth.py         Folium map, MAP_LAYERS, colour ramp helpers, legend HTML
src/ui/filters.py            apply_kommun_filter()
src/ui/labels.py             SWEDISH_LABELS (all user text), GLOSSARY, formatters, POSITION_BANDS
src/provenance.py            analysis_year(), panel_max_year(), load_provenance()
artifacts/*.parquet          Published contract the app reads (METHODOLOGY 11.7)
data/processed/panel.parquet Panel (names, structural variables)
data/geo/kommuner.geojson    Map polygons
pipeline.py, src/fetch|clean|model   Offline pipeline. NOT touched by this plan.
```

Each page repeats the same scaffold: `set_page_config` → `inject_css()` →
`render_sidebar(key)` → `@st.cache_data` loaders → sections composed from
`st.html(...)` strings, `st.container(border=True)`, Plotly figures and
`st.dataframe`. The pattern is sound. The weaknesses are in the styling
layer and in a few interaction gaps, not in the architecture.

### A2.2 Navigation

* Auto-generated multipage navigation is hidden by
  `showSidebarNavigation = false` and by three further CSS rules.
* A hand-built sidebar renders the inactive pages as `st.page_link` and the
  active page as raw HTML `<a class="active" href="#">`. The two have
  different metrics (visible as different heights in the screenshots), and
  the active one is a link to nowhere.
* On ≤768 px the sidebar becomes an overlay, but its toggle is hidden (see
  A1). **There is no in-page navigation anywhere except the start page's
  bottom cards.**

### A2.3 Visual identity

Navy `#0B1F3F` sidebar and hero, gold `#C4A35A` accent, off-white
`#F7F8FA` ground, Source Sans 3 for text and IBM Plex Mono for figures,
4 px radii, 1 px borders. The PRD (§6) locks "navy and gold over an
off-white ground". The identity is appropriate: sober, institutional and
Swedish-public-sector in tone. This plan **refines it rather than replacing
it**.

### A2.4 Component patterns

| Pattern | Implementation | Observation |
|---|---|---|
| Page title | `components.page_title` HTML | Year badge positioned by `float:right; margin-top:-38px` hack |
| KPI card | `components.kpi_card` HTML + `render_kpi_row` columns | Value mixes number and kommun name; no unit; `danger` = red; hardcoded `#6B7280` |
| Card | Two coexisting systems: `.shai-card` HTML divs (landing) and `st.container(border=True)` (everything else) | Different backgrounds and paddings; Plotly white paper inside a transparent container gives a box-in-box look |
| Card header | `components.card_header` with optional tag and `?` glossary popover | Good. Keyboard-reachable (`tabindex=0`), CSS-only |
| Explanation text | `.shai-explanation` div, 13 px grey | No max line length |
| Summary callout | `.shai-summary` gold left border | Good pattern, used twice |
| Expander guides | `st.expander` + `st.markdown` | Consistent ("Hur läser jag ...?"). Keep |
| Tables | `st.dataframe` | CSS for `th/td` is dead code (the grid renders on canvas) |
| Charts | Plotly via `get_chart_layout` + per-page overrides | Theme partially applied; separators not localised; `config` repeated |
| Map | Folium + custom HTML legend | Strong colour logic; rebuilt on every rerun |
| Section headings outside cards | Inline-styled `<h3 style=...>` in `app.py` | Duplicated inline styles |

### A2.5 Interaction patterns

Radio (map layer), pills (band filter), multiselect (table filter; trend
comparison, max 4), selectbox (kommun), expanders, hover popovers,
download button, Plotly hover. All are native or CSS-only, which is robust
under reruns. There are no forms, no dialogs and no session state beyond the
widgets themselves.

### A2.6 Main usability problems: full evidence list

| ID | Problem | Evidence | Severity |
|---|---|---|---|
| P-1 | No way to open the sidebar on mobile, so navigation and filter are unreachable | `css.py` hides `header[data-testid="stHeader"]`; measured `stExpandSidebarButton` 0×0 px at 390 px | Critical |
| P-2 | Active filter pills ~1.8:1 contrast | Text `rgba(255,255,255,.65)` forced by the sidebar `*` rule on gold `#C4A35A` | Critical (a11y) |
| P-3 | Gold text on light ground 2.4:1 (eyebrows, year badge, step numbers); vintage line `#9CA3AF` on `#F7F8FA` 2.4:1; tertiary text used for labels, tags, footer | Computed styles | High (a11y) |
| P-4 | Band filter shown on start page where nothing uses it: an inert control | `app.py` calls `render_sidebar("landing")` and ignores `sidebar_state` | High |
| P-5 | Band filter resets on every page change | `st.pills` without `key`; widget state is per page | High |
| P-6 | Active nav item is `<a href="#">`; nav items inconsistent in size | `sidebar.py` L78–84 | Medium |
| P-7 | Kommun selection not persisted, not linkable, always opens on Högsby; no route from table, map or peers into a kommun | `02_Kommunjamforelse.py` `index=0`; no `query_params` use anywhere | High |
| P-8 | Start-page nav cards look clickable but are not | `.shai-nav-card {cursor:pointer}` + separate `st.page_link` below | Medium |
| P-9 | KPI cards: number and name share one value, so text wraps and heights differ; no units; falls shown in red, contradicting the colour policy | `01_Riksoversikt.py` L169–203; `variant="danger"` → `--color-high-risk #B94A48` | Medium |
| P-10 | Prose blocks: 13 px, unconstrained line length (~200 chars at 1440 px); forecast panel has 5 consecutive paragraphs | Screenshot; `.shai-explanation` has no `max-width` | Medium |
| P-11 | Ranking table: drift columns are left-aligned text while index columns are right-aligned numbers; only ~10 of 290 rows visible; no row count; dead table CSS | `01_Riksoversikt.py` L611–660; `css.py` L661–672 | Medium |
| P-12 | Plotly hovers use English separators; plot paper is white inside a non-white card; histogram y-title clipped ("tal kommuner"); `config` repeated 6× | `chart_theme.py`; hovertemplates `%{y:,.0f}` | Medium |
| P-13 | Model diagram iframe does not load the brand fonts (falls back to serif for "Tvärsnittsmodell"); its card is faked from two half-cards with a seam; 9 px text becomes ~4 px on mobile | `app.py` L185–303 | Medium |
| P-14 | "Senast uppdaterad" is the file mtime, so on Streamlit Cloud it shows the clone date | `app.py` L113–117 and both pages; `data_provenance.json` has `generated_at` | Medium (trust) |
| P-15 | Hardcoded hex values and inline styles in page code; unused tokens and dead classes (`low/medium/high_risk`, `.shai-pill.risk-*`, `.shai-coef-bar-*`, `.shai-risk-legend` naming) | `components.py` L88; `app.py` inline `<h3 style>`; `css.py` | Low (maintainability) |
| P-16 | Version string "v1.0" hardcoded in three places; hero uses a gradient | `app.py`, pages, `sidebar.py` | Low |
| P-17 | CSS targets test IDs that no longer exist (`stSidebarCollapse`, `collapsedControl`, `baseButton-headerNoPadding`), so these rules silently do nothing | `css.py` L159–163, L962–967 | Medium (fragility) |
| P-18 | Local `.venv` runs Streamlit 1.56.0, while the deploy pins 1.55.0, so tests do not exercise the production version | `requirements.txt` vs `import streamlit` | Medium (risk) |
| P-19 | Information architecture: the start page leads with methodology; the two task pages are reached at the very bottom (~3,500 px down) | Full-page capture | Medium |
| P-20 | Map rebuilt (290 polygons, GeoJSON mutation, Folium serialisation) on **every** rerun, including keystrokes in the table filter; the layer toggle reruns the whole page | `choropleth.render_choropleth`; no fragment | Medium (perf) |
| P-21 | On the kommun page the band filter silently narrows the selector, while peers and comparisons ignore it | `02_Kommunjamforelse.py` L125–136 | Low (clarity) |
| P-22 | Copy hardcodes year spans (`method_period` "2010 till 2026", `method_units` "17 år, 4 930 observationer") despite PRD acceptance criterion 7 | `labels.py` L85–93 | Low (flag only; content, not UX) |

### A2.7 Existing strengths to keep

Single Swedish label source with mechanical enforcement; the "two-layer
language rule"; one number policy; colour-blind-safe, midpoint-anchored
ramps shared by map, histogram and legend; per-section glossary popovers;
"Hur läser jag ...?" guides with worked examples; the forecast published
with its benchmarks and its predecessor's failure; graceful absence of the
forecast artifact; caching of all loaders.

---

## A3. Feature and Functionality Inventory

Classification: **C** core, **S** supporting, **A** advanced, **Ad**
administrative, **X** experimental/optional. "Modify?" states whether this
plan touches the feature's presentation (never its logic unless stated).

### Shell (all pages)

| ID | Feature | Class | Location | Interaction | Dependencies | Current issues | Modify? |
|---|---|---|---|---|---|---|---|
| F01 | Brand block | S | `sidebar.py` | none | labels | footer text contrast | Style |
| F02 | Page navigation (3 pages, active state) | C | `sidebar.py` `_NAV_ITEMS` | click | `st.page_link` | P-1, P-6 | Yes |
| F03 | Position band filter (multi, empty = all) | C | `sidebar.py` `st.pills` | toggle | `POSITION_BANDS` | P-2, P-4, P-5 | Yes |
| F04 | Band legend + note | S | `sidebar.py` | none | `POSITION_SCALE` (test-pinned) | none | Style only |
| F05 | Sidebar source/version footer | S | `sidebar.py` | none | labels | contrast, hardcoded version | Yes |
| F06 | Glossary help badges `?` | S | `components.help_badge` | hover/focus | `GLOSSARY` | none (keep) | No |
| F07 | Data vintage note | S | both pages `.shai-vintage` | none | provenance | contrast | Style |
| F08 | Page footer (source, updated, version) | S | `components.footer_note` | none | file mtime | P-14 | Yes |
| F09 | Hidden Streamlit chrome, removed menu items | Ad | `css.py`, `set_page_config` | none | none | P-1, P-17 | Yes |
| F10 | Global CSS / fonts | Ad | `css.py` | none | Google Fonts | fragile selectors | Yes |

### Startsida (`app.py`)

| ID | Feature | Class | Interaction | Dependencies | Current issues | Modify? |
|---|---|---|---|---|---|---|
| F11 | Hero (eyebrow, title, lead) | S | none | labels | gradient, contrast | Style |
| F12 | Concept + "how to use" expander | S | expand | labels | none | Position only |
| F13 | Stat strip (kommuner, years, vars, identified) with explanation | S | none | provenance, `coefficients_cross` | none | Style |
| F14 | Model overview SVG diagram + explanation | S | none | `components.html` | P-13 | Yes |
| F15 | Coefficient dot-and-whisker chart (hover, value column, zero line, grey for unidentified) | C | hover | `coefficients_cross` | hover separators | Theme only |
| F16 | Coefficient table (effect, CI, identified) | C | sort | same | none | Style |
| F17 | Coefficient reading guide expander | S | expand | labels (copy-tested) | none | No |
| F18 | Within-kommun FE panel: lead, spec, table with stars, caveat, guide | A | expand | `coefficients.parquet` role=primary | none | Style |
| F19 | Pipeline steps + explanation | S | none | labels | contrast of step numbers | Style |
| F20 | Navigation cards to the two pages | S | click | `st.page_link` | P-8, P-19 | Yes |
| F21 | Sources & method block (SCB table pills) | S | none | labels | none | Style |

### Riksöversikt (`pages/01_Riksoversikt.py`)

| ID | Feature | Class | Interaction | Dependencies | Current issues | Modify? |
|---|---|---|---|---|---|---|
| F22 | Title, subtitle, year | S | none | provenance | P-21 hack | Style |
| F23 | KPI row: spread, largest 10-yr fall, rise, cross R² (tooltips) | C | hover | `position`, `coefficients_cross` | P-9 | Yes |
| F24 | National summary sentence | S | none | labels | long line | Style |
| F25 | Choropleth, layer radio (position / drift 5y), tooltips, legend, keyless tiles | C | radio, hover, zoom/pan | `choropleth.py`, GeoJSON | P-20 | Perf + layout |
| F26 | Layer caption + map guide expander | S | expand | labels | none | No |
| F27 | Histogram synced to layer: coloured bins, band cuts, reference, median, pooled end bins; follows band filter | C | hover | `build_colormap`/`color_for` | clipped y-title, hover format | Theme |
| F28 | Index comparison scatter (ours vs SCB) + note + expander | A | hover | `position` | hover format | Theme |
| F29 | Forecast panel (conditional on artifact): lead, backtest lead, 4 score cards, verdict, coverage, historical caveat, guide | A | expand | `forecast.parquet` | P-9, P-10 | Yes |
| F30 | Ranking table (290 rows, both indexes, difference, drifts, forecast + interval when present) | C | sort, scroll | position, forecast | P-11 | Yes |
| F31 | Kommun name filter (multiselect) + active-count note | C | select | `filters.apply_kommun_filter` | none | Keep |
| F32 | CSV download of the displayed table | C | click | `display_df` | none | Keep |
| F33 | Ranking guide expander | S | expand | labels | none | No |

### Kommunjämförelse (`pages/02_Kommunjamforelse.py`)

| ID | Feature | Class | Interaction | Dependencies | Current issues | Modify? |
|---|---|---|---|---|---|---|
| F34 | Kommun selector ordered by position, label "Namn (Län) index N", narrowed by band filter with fall-back to all | C | select | position, panel | P-7, P-21 | Yes |
| F35 | Lead sentence (with or without drift) | C | none | labels | none | Style |
| F36 | KPI row: our index, SCB index, drift 5y, drift 10y + explanation | C | none | position | P-9 | Yes |
| F37 | Position-over-time line with riket = 100 + note + guide | C | hover | position | hover format | Theme |
| F38 | Historical skattekraft (kr) with national average and up to 4 comparison kommuner + guide | C | multiselect | panel | hover thousands separator | Theme |
| F39 | Decomposition bars (identified + residual), residual note | C | hover | `decomposition_cross` | none | Theme |
| F40 | Controls table with CIs (never bars) | C | none | coefficients | none | No |
| F41 | Decomposition guide | S | expand | labels | none | No |
| F42 | Peer table (5 nearest by position) + guide | S | sort | panel | no route to a peer | Yes (link) |

### Infrastructure (invisible but must survive)

| ID | Feature | Class | Location |
|---|---|---|---|
| F43 | `@st.cache_data` loaders on every page | Ad | pages |
| F44 | Forecast artifact absent leads to correct rendering without it | Ad | Riksöversikt |
| F45 | Missing GeoJSON leads to a Swedish warning instead of a crash | Ad | `choropleth.py` |
| F46 | Swedish number policy (`format_*`, `DISPLAY_DECIMALS`, no "-0,0") | C | `labels.py` |
| F47 | Provenance-driven years (no hardcoded years in code) | Ad | `provenance.py` |
| F48 | Offline pipeline (`pipeline.py`, `src/fetch|clean|model`) | Ad | out of UI scope, **not touched** |

**Not present (and not introduced):** authentication, database, user input
forms, persistence beyond the session, file upload, admin pages.

---

## A4. Proposed Design Direction

### Design principles

1. **Statistics office, not startup.** The reference class is a modern
   national statistics publication (SCB, Riksbanken, ONS) executed with
   the restraint of Stripe's and Linear's product UI. That means flat
   surfaces, hairline borders, one accent, and figures that dominate their
   labels.
2. **Every number says what it is.** Unit, year, sign and kind (observed,
   modelled, forecast) are visible without hovering.
3. **Direction is not judgement.** Below riket is a position, not a failure.
   No red/green good/bad encoding anywhere. Sign is shown by symbol and text
   first, and colour (blue up, orange down, from the existing Okabe-Ito
   ramp) second.
4. **Native first.** Use Streamlit theming and widgets wherever they can do
   the job, and custom HTML/CSS only for typography, cards and the glossary
   popover.
5. **Progressive disclosure keeps all content.** Nothing is deleted. Long
   explanation moves behind a clearly labelled guide only where it is
   currently a wall of text, and never where a test or the PRD requires it
   to be visible (the backtest panel and its history).

### Visual identity (refined, not replaced)

* **Keep** navy `#0B1F3F` (sidebar, hero, primary marks) and gold
  `#C4A35A`, but restrict gold to the brand bar, active navigation, active
  pills and focus rings. **Add** a text-safe gold `#8A6D2B` (4.9:1 on
  white) for eyebrows and year labels.
* Solid navy hero (drop the gradient). Same 4 px gold left rule.
* White cards on `#F7F8FA`, 1 px `#E5E7EB` border, **6 px** radius, no
  shadow. Shadows are reserved for popovers.
* Source Sans 3 for all text and for large figures (with
  `font-variant-numeric: tabular-nums`). IBM Plex Mono only for codes,
  tags and axis ticks. The vintage line moves to sans (the mono read as
  terminal output).

### Industry suitability

The audience is municipal finance staff (ekonomichef, controller),
politicians on nämnder, regional analysts (SKR, länsstyrelser), journalists
and students. They need credibility, comparability and citeability more than
delight. They cite numbers into reports, so the design must:

* survive screenshots and print (white cards, no dark backgrounds behind
  data),
* make every figure self-describing (unit, year, kind),
* allow sharing a precise view (kommun URL),
* export what is on screen (CSV exists and stays).

### Reference products and what is taken from each

| Reference | What is borrowed |
|---|---|
| Stripe Dashboard | Figure-first KPI cards: big tabular number, small label, one context line |
| Linear | Quiet chrome, one accent colour, crisp focus rings |
| Mercury / Ramp | Tables as primary surfaces: right-aligned numerics, pinned identifier column, row count |
| Wise | Plain-language explanation directly beside numbers |
| SCB Statistikdatabasen / Kolada | Domain conventions: decimal comma, "riket = 100", explicit reference year per figure |

Nothing is copied. These are quality bars.

---

## A5. Proposed Information Architecture

### Navigation

* Keep three pages, their file names and their URLs (`/`, `/Riksoversikt`,
  `/Kommunjamforelse`). Changing them would break shared links and the
  test harness.
* Sidebar navigation becomes three `st.page_link` items, including the
  current page (Streamlit marks the current page natively), each with a
  Material icon: `:material/home:`, `:material/map:`,
  `:material/location_city:`. This removes the fake `href="#"`.
* The sidebar toggle is restored on mobile, so navigation is reachable
  everywhere.
* Migration to `st.navigation`/`st.Page` was evaluated and **deferred**
  (D-1). It is the modern API, but it would change the entry point and the
  test harness (`AppTest.switch_page`) for no user-visible gain beyond what
  `st.page_link` already gives.

### Cross-page journeys (new links, no new pages)

```
Startsida ──[Hitta din kommun]──────────────► Kommunjämförelse
    └─────[Se hela riket]───► Riksöversikt
                                 │ select a row in Rangordning
                                 └──[Öppna X i Kommunjämförelse]──► Kommunjämförelse?kommun=<kod>
Kommunjämförelse: peer table row ──[Öppna Y]──► Kommunjämförelse?kommun=<kod of Y>
```

The kommun choice is held in `st.query_params["kommun"]` (4-digit
kommun_kod), which makes it linkable, and mirrored in `st.session_state`, so
it survives navigating away and back.

### Filter scope

The position band filter is shown only on the two pages that apply it, and
its selection persists across them. On the kommun page, a one-line notice
appears when the persisted kommun falls outside the selected bands (today it
silently disappears from the selector).

### Start page content order (all content kept)

| # | Today | Proposed |
|---|---|---|
| 1 | Hero | Hero + **two primary actions** (Hitta din kommun / Se hela riket) |
| 2 | Concept expander | Stat strip + its explanation |
| 3 | Stat strip + explanation | Concept expander |
| 4 | Model overview diagram | Model overview diagram (single card) |
| 5 | Variables & coefficients | Variables & coefficients |
| 6 | Within-kommun panel | Within-kommun panel |
| 7 | Pipeline steps | Pipeline steps |
| 8 | Nav cards ("Utforska dashboarden") | Nav cards, now whole-card links (kept as the end-of-page route) |
| 9 | Sources & method | Sources & method |
| 10 | Footer | Footer (date from provenance) |

Riksöversikt and Kommunjämförelse keep their section order. Their changes
are inside sections (A6).

---

## A6. Page-by-Page Redesign Specification

### A6.0 Shell (sidebar, header, footer)

**Current.** 260 px fixed navy sidebar: brand, nav (mixed `page_link` and
fake link), band pills, legend, note, footer. Header hidden. Footer per page
with mtime date and "v1.0".

**Problems.** P-1, P-2, P-4, P-5, P-6, P-14, P-16, P-17.

**Proposed layout.**
* Header: keep `stHeader` in the DOM but transparent and height-minimal.
  Hide only `stToolbar` actions, `stDecoration` and the main menu, so the
  native sidebar expand button stays visible on mobile.
* Sidebar colours come from `[theme.sidebar]` in `config.toml`
  (`backgroundColor`, `textColor`, `secondaryBackgroundColor`,
  `borderColor`). This deletes the `section[data-testid="stSidebar"] *
  {color: ... !important}` rule that caused the pill contrast failure.
* Nav: three `st.page_link`, full width, icon + label, 40 px rows.
* Filter: rendered only when `render_sidebar(..., show_filter=True)`.
  Pills get a key, and the value persists through a session key with an
  `on_change` callback (the standard pattern for cross-page widget
  persistence).
* Active pill: navy text on gold (6.8:1). Inactive: white 85 % on navy.
* Footer: source line in white 70 % (≥4.5:1), version from a single
  `APP_VERSION` constant.
* Page footer date from `load_provenance()["generated_at"]` (date part),
  with the mtime kept only as a fallback.

**Responsive.** ≥769 px: sidebar fixed open (as today). ≤768 px: native
overlay with a visible toggle.

**Unchanged.** Brand text, nav labels, band options and defaults (all three
selected), "empty = all", legend swatches from `POSITION_SCALE` (pinned by
`test_choropleth.TestSidebarAgreesWithTheMap`).

### A6.1 Startsida

**Current layout.** Hero (gradient) → expander → 4-cell stat strip →
explanation → split HTML card + iframe SVG + split HTML card → coefficient
card (chart, note, table, guide) → within card (lead, spec, table, caveat,
guide) → inline-styled h3 + pipeline → inline h3 + two fake cards + text
links → sources card → footer.

**Existing functionality.** F11 to F21.

**Problems.** P-3 (gold eyebrow), P-8, P-13, P-15 (inline styles), P-19,
inert filter (P-4).

**Proposed layout.**
1. Hero: solid navy, eyebrow in light gold `#E2C98F` (on navy about 10:1),
   title, lead (max 68ch). Underneath, a horizontal container with **two
   `st.page_link` buttons**: "Hitta din kommun" (primary,
   `:material/location_city:`) and "Se hela riket" (`:material/map:`).
2. Stat strip (four cells, sans tabular 24 px, labels 11 px uppercase in
   `text_secondary`), explanation below at 14 px, max 80ch.
3. Concept expander, unchanged content.
4. "Modellöversikt" as **one** `st.container(border=True)` holding
   `card_header`, the SVG and the explanation. The SVG iframe gets a
   Google Fonts `<link>` and a system-sans fallback stack. At ≤640 px a
   CSS media query inside the iframe raises SVG text sizes by scaling the
   `viewBox` crop (no content change).
5. "Variabler & koefficienter": unchanged content; provenance chip
   **Modell**; chart theme v2.
6. "Samband inom kommuner över tid": unchanged content; chip **Modell**.
7. Pipeline: section heading via a `section_heading()` component (no inline
   styles); step numbers in text-safe gold.
8. "Utforska dashboarden": each card is a `st.container(border=True)`
   containing a heading, description and a full-width `st.page_link`. The
   card's only affordance is the real link. The `cursor:pointer` fake is
   removed.
9. Sources & method: unchanged content; `.shai-card` HTML replaced by a
   bordered container for surface consistency.
10. Footer.

**Interaction improvements.** The primary journeys are reachable without
scrolling. Fake affordances are removed.

**Responsive.** CTA buttons stack at ≤480 px. Stat strip 2×2 at ≤768 px
(exists). Nav cards stack (exists).

**Must remain unchanged.** All copy; the coefficient chart's encoding
(dot-and-whisker, grey for unidentified, zero line, value column); table
columns; the "rangordna" caveat and the within-section title (test-pinned);
no "tillväxtprognos" text (test-pinned).

### A6.2 Riksöversikt

**Current layout.** Title + floating year → 4 KPI cards → vintage →
summary → [map card 3/5 | histogram card 2/5] → index scatter card →
forecast card (lead, backtest lead, 4 cards, 3 paragraphs, guide) → ranking
card (guide, multiselect, table, CSV) → footer.

**Problems.** P-9, P-10, P-11, P-12, P-20, P-21, no route into a kommun.

**Proposed layout and components.**
1. **Title block.** Eyebrow (text-safe gold) and title; the year becomes a
   `.shai-tag`-style chip inline after the subtitle ("Data till 2026").
   The negative-margin float is removed.
2. **KPI row v2** (`kpi_card(label, value, unit=, context=, tone=)`):
   * "Högsta / lägsta index": value `208 / 80`, context "Danderyd / Högsby".
   * "Största fall, 10 år": value `-8,1`, unit "indexenheter", context
     "Oskarshamn", tone `negative` (orange glyph ▼, **no red border**).
   * "Största ökning, 10 år": value `+17,3`, unit "indexenheter", context
     "Danderyd", tone `positive` (blue ▲).
   * "Modellens förklaringsgrad": `69 %`, context "Tvärsnitt 2024".
   All four cards get equal height (CSS `height:100%` inside columns).
   Tooltips are kept as `title` and **also** exposed via the card's `?`
   help pattern so they are reachable by keyboard.
3. **Vintage note** in sans 12 px `text_secondary` (4.6:1).
4. **Summary callout**, max 80ch.
5. **Map | histogram row** wrapped in `@st.fragment`, so the layer radio
   reruns only this row. Both cards stretch to equal height. The histogram
   gets left margin and `title_standoff` so its y-title is not clipped. Map
   layers are cached per layer key (styled GeoJSON built once per layer
   per session). The map gets a `st.spinner` on first build. Chip:
   **Observerat**.
6. **Index scatter**: theme v2 (localised hovers). Chip **Observerat**.
7. **Forecast panel** (only when the artifact exists, as today). Chip
   **Prognos**:
   * the lead paragraph (kept);
   * score cards with units: "Rangkorrelation 0,33 (0 till 1)",
     "Medelfel 2,1 indexenheter", and the two benchmarks
     (2,3 / 3,0 indexenheter);
   * **new compact horizontal bar chart** "Medelfel, lägre är bättre",
     with three bars (model, gissa genomsnittet, anta att trenden
     fortsätter) on one axis. This makes "beats both, by a small margin"
     visible at a glance. Data is already in the artifact; no logic
     change;
   * verdict and coverage sentences kept, visible;
   * historical caveat kept **visible** (test-pinned: "0,02" and
     "1,51 procentenheter" must render without interaction), styled as a
     neutral `callout(variant="note")` so it reads as a record rather than
     as part of the current result;
   * the backtest lead line moves directly under the chart it describes;
   * guide expander kept.
8. **Ranking table**:
   * Columns, order and CSV content unchanged.
   * All numeric-looking columns right-aligned. Index columns stay
     `NumberColumn`. Pre-formatted text columns (drift, forecast,
     interval) get `alignment="right"` where the 1.55 API supports it on
     `TextColumn` (verified in T02; if not supported, CSS is not attempted
     because the grid is canvas, and this sub-item is dropped).
   * `Kommun` column pinned. `height` set to show ~15 rows. A caption
     "Visar 290 av 290 kommuner" is always shown (today it shows only
     while filtering).
   * Column `help` texts reuse glossary text (both index measures,
     difference, drift, forecast, interval).
   * **Row selection** (`on_select="rerun"`, `selection_mode="single-row"`).
     When a row is selected, a `st.page_link` "Öppna {kommun} i
     Kommunjämförelse" appears above the table, with
     `query_params={"kommun": kod}`.
   * The CSV download button moves to the card header row (right
     aligned) using a horizontal container.
   * Chip: **Observerat** (forecast columns are already named "Prognos").

**Responsive.** KPI row 2×2 at ≤1024 px and 1×4 at ≤768 px (today it
jumps from 4 to 1). Map height 360 px at ≤768 px. The table scrolls
horizontally inside its card (native).

**Must remain unchanged.** `riks.radio[0]` is the layer radio with exactly
the `MAP_LAYERS` labels, position default; `riks.dataframe[0]` is the
ranking table with 290 rows by default; `riks.multiselect[0]` is the
kommun filter with 290 options; column names (test-pinned); band filter
effects on histogram and table; histogram binning and pooled end bins;
colour ramps; CSV.

### A6.3 Kommunjämförelse

**Current layout.** Title → selector → lead callout → vintage → 4 KPI
cards → explanation → position-over-time card → kronor trend card
(compare multiselect) → decomposition card (bars, note, controls header,
controls table, guide) → peers card → footer.

**Problems.** P-7, P-9, P-21, P-12, no link from peers.

**Proposed layout.**
1. Title + **selector in a header row**: eyebrow and title left, selector
   right (≥1024 px). Stacked on smaller screens.
   * Value is the kommun_kod. The label keeps "Namn (Län) index N"
     (test-pinned: contains "index", not "rang"; 290 options by default).
   * Initial value: `st.query_params["kommun"]` → else
     `st.session_state["kss_kommun"]` → else first option (today's
     default, Högsby). Every change writes both.
   * If the requested kommun is outside the active band filter: fall back
     to the first option and show a one-line `st.caption` naming both
     (preserves today's narrowing behaviour; see A10 R-1 for the
     alternative).
2. Lead sentence promoted to the page's headline callout (bigger, 16 px),
   followed by the vintage note.
3. **KPI row v2**: "Vårt index (oviktat)" `80` context "riket = 100";
   "SCB:s index (viktat)" `73` context "riksmedelvärdet = 100";
   "Förflyttning 5 år" `-1,9` unit "indexenheter", tone by sign;
   "Förflyttning 10 år" likewise. The red `danger` border is gone. The
   explanation stays below.
4. Position over time: theme v2, chip **Observerat**.
5. Historical kronor: theme v2 (Swedish thousands separator in hover and
   axis via layout `separators=", "`). Comparison multiselect unchanged
   (max 4). Chip **Observerat**.
6. Decomposition: unchanged encoding. Chip **Modell**. The controls
   sub-header becomes a `section_heading(level=4)` inside the card.
7. Peers: table unchanged in columns. Adds single-row selection that offers
   "Öppna {kommun}" as a `st.page_link` to the same page with
   `query_params`. Chip **Observerat**.

**Responsive.** Header row stacks. KPI 2×2 / 1×4 as on Riksöversikt.

**Must remain unchanged.** `kommun.selectbox[0]` has 290 options ordered
lowest position first, labels contain "index"; the controls table has the
`vars_table_ci` column with 2 rows; the decomposition draws only
`contrib_*` + residual; all copy.

---

## A7. Component and Design System Changes

### A7.1 Colour system (tokens in `src/ui/css.py`; existing keys kept for compatibility)

| Token | Value | Use | Contrast |
|---|---|---|---|
| `primary` | `#0B1F3F` | Sidebar, hero, primary marks, highlight stroke | 16.8:1 on white |
| `accent` | `#C4A35A` | Brand bar, active nav/pill **backgrounds**, focus ring, median line | non-text only |
| `accent_text` **new** | `#8A6D2B` | Eyebrows, year chips, step numbers on light ground | 4.9:1 on white |
| `accent_on_dark` **new** | `#E2C98F` | Eyebrow on navy hero | about 10:1 on navy |
| `secondary` | `#4A6FA5` | Chart series 1 | non-text |
| `text_primary` | `#1A1A2E` | Body, figures | 16.6:1 |
| `text_secondary` | `#6B7280` | Secondary text, labels, captions (min 12 px) | 4.8:1 white / 4.6:1 bg |
| `text_tertiary` | `#9CA3AF` | **Non-text only** from now on: grid, dashed reference lines, disabled | (2.4:1, not for text) |
| `border` | `#E5E7EB` (was `#EEF0F3`, 1.1:1, nearly invisible) | Card and table borders | 1.25:1 (hairline) |
| `grid` | `#E5E7EB` | Chart grids | |
| `bg` / `card_bg` | `#F7F8FA` / `#FFFFFF` | Ground / surfaces | |
| `positive` | `#2E75A8` | Positive sign marks (bars, glyphs) | 5.0:1 |
| `negative` | `#C2670A` | Negative sign marks | 4.0:1 (marks, large text) |
| `negative_text` **new** | `#9A4F06` | Negative values as small text | 6.0:1 |
| `focus` **new** | `#C4A35A` 2 px ring + 2 px offset | All focusable custom elements | |
| `low_risk`, `medium_risk`, `high_risk` | **deprecated**: retained only if a test or file still imports them (checked in T05), otherwise removed | | |

The map ramps `POSITION_SCALE` and `DIVERGING_SCALE` and `CHART_PALETTE`
are **unchanged** (test-pinned and correct).

All text/background pairs above are added to a contrast test (T17) that
computes WCAG ratios from the tokens and fails below 4.5:1 for text tokens.

### A7.2 Typography

| Role | Font | Size / weight | Notes |
|---|---|---|---|
| Hero title | Source Sans 3 | clamp(26px, 3vw, 36px) / 700 | |
| Page title (h1) | Source Sans 3 | 28 / 700 | |
| Section heading (h3 outside cards) | Source Sans 3 | 18 / 700 | `section_heading()` |
| Card title | Source Sans 3 | 15 / 700 | existing |
| Body / explanation | Source Sans 3 | **14** / 400, line-height 1.55, **max-width 80ch** | was 13 px, unbounded |
| Label / eyebrow | Source Sans 3 | 11 / 600, uppercase, +0.08em | |
| KPI figure | Source Sans 3 | 30 / 700, `tabular-nums` | 26 at ≤1024, 22 at ≤768 |
| KPI unit / context | Source Sans 3 | 13 / 400 `text_secondary` | new |
| Chart ticks | IBM Plex Mono | 11 | existing |
| Codes, tags | IBM Plex Mono | 10.5 / 500 | existing |
| Table | native grid font via `[theme] codeFont`/`font` | | dead CSS removed |

### A7.3 Spacing, radius, elevation

Scale `4 · 8 · 12 · 16 · 24 · 32 · 48` px, exposed as CSS variables
`--space-1..7`. Card padding 20/24 px (unchanged visually); section gap
24 px; page padding 32/40 px desktop, 24 px tablet, 16 px mobile (today
14). Radius: cards 6 px, controls 6 px (via `[theme] baseRadius`), pills
999 px. Elevation: none on cards; popover `0 6px 20px rgba(26,26,46,.14)`
(existing).

### A7.4 Components (rules of use)

| Component | API (Python, returns HTML unless noted) | Use when | Do not use when |
|---|---|---|---|
| `page_title(eyebrow, title, subtitle, year)` | existing, year rendered as inline chip | Top of each page | |
| `section_heading(title, level=3, help_terms=())` **new** | Headings outside cards (start page) | Inside cards (use `card_header`) |
| `card_header(title, subtitle, tag, help_terms, kind=None)` | add `kind in {"observed","model","forecast"}` → provenance chip | Every data card | |
| `provenance_chip(kind)` **new** | small chip "Observerat" / "Modell" / "Prognos" with `title` tooltip | Through `card_header(kind=...)` | Free-floating |
| `kpi_card(label, value, unit="", context="", tone="neutral", tooltip=None, delta=..., variant=...)` | `tone in {"neutral","positive","negative"}`; legacy `variant`/`delta` kept and mapped | Headline figures, at most 4 per row | Lists of numbers (use a table) |
| `render_kpi_row(cards)` | equal-height columns; `st.columns(..., gap="small")` | | |
| `callout(html, variant="summary"|"note")` **new** | summary = gold rule (existing `.shai-summary`), note = neutral grey rule | Lead sentences, historical records | Body text |
| `data_note(text)` **new** | replaces `.shai-vintage` markup | Data vintage line | |
| `explanation(text)` **new** | wraps `.shai-explanation` | All explanatory paragraphs | |
| `footer_note(source, version, updated)` | updated from provenance | Page end | |
| `help_badge(*terms)` | unchanged | | |
| Buttons | native `st.page_link`, `st.download_button`; theme radius | | Custom HTML buttons |
| Tables | native `st.dataframe` + `column_config`; numeric right-aligned; identifier pinned; `help` on columns | All tabular data | |
| Charts | `get_chart_layout()` v2 + `CHART_CONFIG` | All Plotly figures | |
| Notifications | native `st.caption` for inline notices; `st.warning` only for missing assets (existing) | | Toasts (not needed) |
| Loading | `st.spinner` around the first map build | Map only (other work is cached and fast) | |
| Empty states | `st.caption` sentence from labels, never an empty chart | Filters that match nothing | |

### A7.5 Charts (`chart_theme.py` v2)

* `paper_bgcolor` and `plot_bgcolor` `rgba(0,0,0,0)`, so charts sit on the
  card surface (fixes the box-in-box effect).
* `separators=", "`, so Plotly renders decimal comma and space thousands
  everywhere (hover and ticks). Hovertemplates keep their `:,.0f` / `.1f`
  specifiers; Plotly maps them through `separators`.
* `CHART_CONFIG = {"displayModeBar": False, "locale": "sv"}`: one constant
  replacing six literals. The `locale` key is verified in T08; if the Plotly
  Swedish locale bundle is not loaded by Streamlit, only `separators` is
  relied on.
* Axis `title.standoff = 8`, `automargin=True` on both axes (fixes the
  clipped histogram title).
* Hover label: navy background, white text (kept).

### A7.6 Navigation, notifications and reusable pieces

Covered in A5/A6.0. No toasts, dialogs or popovers are introduced; the
product has no transactional actions that need them.

---

## A8. Industry-Specific Improvements

| Need | Improvement | Where |
|---|---|---|
| Observed vs modelled vs forecast | Provenance chip on every data card, with tooltip text from labels | All pages |
| Units always visible | KPI `unit`/`context` lines ("indexenheter", "riket = 100", "kr") | KPI rows |
| One numeric locale | Plotly `separators=", "` brings hovers and ticks into line with `format_*` | All charts |
| Sign without judgement | ▲/▼ glyph + explicit sign + blue/orange; red removed from KPIs | KPI rows |
| Numeric alignment | Right-aligned figures; pinned identifier column | Tables |
| Reference period per figure | Vintage note kept; year chip in titles; column headers with years (kept) | All |
| Data currency you can trust | Footer date from `generated_at` | Footer |
| Citeable, shareable view | `?kommun=<kod>` URLs; CSV unchanged | Kommun page, table |
| Forecast honesty | Benchmark bar chart makes "beats both by a small margin" visual; history kept visible | Forecast panel |
| Analytical depth preserved | No column, chart, interval or guide removed | Everywhere |

---

## A9. Performance and Technical Improvements

1. **Fragment for map + histogram.** The layer radio reruns only that row
   instead of the page (both charts and the ranking table today).
2. **Cache the styled GeoJSON per layer** (`@st.cache_data` keyed on layer
   key and a hash of the input frame). The Folium object itself cannot be
   cached safely, but GeoJSON property injection and formatting (290 ×
   7 fields) can. `_load_geojson` is already cached, and the cached return
   value is a copy, so mutation is safe today and stays safe.
3. **Native theming replaces CSS overrides** (`[theme]`, `[theme.sidebar]`,
   `baseRadius`, `borderColor`, `codeFont`), which removes most
   `!important` rules and all stale test-ID selectors.
4. **One `CHART_CONFIG`, one `APP_VERSION`, one `UPDATED` source.**
5. **Dead CSS removed**: risk pills, coefficient bars, `stDataFrame th/td`,
   duplicate sidebar-collapse selectors (verified unused by grep in T05).
6. **Version parity:** the local venv is installed from `requirements.txt`
   (Streamlit 1.55.0), so tests run against what production runs.
7. No new runtime dependencies. Evaluated and rejected:
   * **streamlit-aggrid**: `st.dataframe` already sorts, pins, selects and
     exports; AgGrid adds ~5 MB, licence nuance for enterprise features,
     and a second table look.
   * **streamlit-option-menu / streamlit-extras**: native `st.page_link`
     with Material icons covers it.
   * **Lucide**: Streamlit ships Material Symbols natively; one icon family
     avoids mixing styles.
   * **Altair**: Plotly is established and themed; a second chart library
     would split the theme.

---

## A10. Feature Preservation Matrix

| Feature | Current implementation | Proposed change | Preserved? | Risk |
|---|---|---|---|---|
| F01 Brand | HTML in sidebar | colours via theme | Yes | Low |
| F02 Navigation | page_link + fake active link | 3 × page_link with icons; mobile toggle restored | Yes, improved | Med (CSS of header) |
| F03 Band filter | pills, no key, on all pages | keyed, persisted, hidden on start page | Yes | Med (state) |
| F04 Band legend | HTML swatches from `POSITION_SCALE` | style only | Yes | Low |
| F05 Sidebar footer | HTML | contrast, `APP_VERSION` | Yes | Low |
| F06 Glossary badges | CSS popover | unchanged | Yes | None |
| F07 Vintage note | mono div | `data_note()` sans | Yes | Low |
| F08 Footer | mtime date | provenance date, mtime fallback | Yes | Low |
| F09 Chrome hiding | hides header | hides toolbar/menu/decoration only | Yes | Med |
| F10 CSS | 930 lines | tokenised, pruned | Yes | Med |
| F11 Hero | gradient HTML | solid + 2 CTAs | Yes, extended | Low |
| F12 Concept expander | expander | moved below stat strip | Yes | Low |
| F13 Stat strip | HTML | style | Yes | Low |
| F14 Model diagram | iframe + split cards | single card, fonts | Yes | Low |
| F15 Coefficient chart | Plotly | theme v2, chip | Yes | Low |
| F16 Coefficient table | dataframe | style | Yes | Low |
| F17 Coef guide | expander | none | Yes | None |
| F18 Within panel | card | chip | Yes | Low |
| F19 Pipeline | HTML | `section_heading` | Yes | Low |
| F20 Nav cards | fake card + text link | real link cards | Yes | Low |
| F21 Sources | HTML card | bordered container | Yes | Low |
| F22 Riks title | float hack | inline chip | Yes | Low |
| F23 Riks KPIs | value+name | value/unit/context/tone | Yes | Low |
| F24 Summary | callout | width | Yes | None |
| F25 Map | Folium, full rerun | fragment + cached GeoJSON + spinner | Yes | **Med** (fragment + st_folium) |
| F26 Map caption/guide | text/expander | none | Yes | None |
| F27 Histogram | Plotly | theme v2, margins, in fragment | Yes | Med |
| F28 Index scatter | Plotly | theme v2 | Yes | Low |
| F29 Forecast panel | 4 cards + 5 paragraphs | cards with units + RMSE bar chart; text kept | Yes, extended | Low |
| F30 Ranking table | dataframe | alignment, pinned, height, help, count, row → link | Yes, extended | **Med** (selection API) |
| F31 Kommun filter | multiselect | none | Yes | None |
| F32 CSV | download_button | moved into header row; content identical | Yes | Low |
| F33 Ranking guide | expander | none | Yes | None |
| F34 Kommun selector | selectbox index=0 | value=kod; query param/session persistence; notice when filtered out | Yes, extended | **Med** |
| F35 Lead | callout | headline style | Yes | Low |
| F36 Kommun KPIs | red danger | tone by sign, units | Yes | Low |
| F37 Position chart | Plotly | theme v2 | Yes | Low |
| F38 Kronor trend + compare | Plotly + multiselect | theme v2 | Yes | Low |
| F39 Decomposition | Plotly | theme v2, chip | Yes | Low |
| F40 Controls table | dataframe | none | Yes | None |
| F41 Decomp guide | expander | none | Yes | None |
| F42 Peers | dataframe | + row → open kommun | Yes, extended | Med |
| F43 Caching | cache_data | + GeoJSON per layer | Yes | Low |
| F44 Forecast absent | conditional | conditional kept (chart inside the same `if`) | Yes | Low |
| F45 GeoJSON missing | warning | unchanged | Yes | None |
| F46 Number policy | labels.py | + Plotly separators | Yes, extended | Low |
| F47 Provenance years | provenance.py | + `generated_at` reader | Yes | Low |
| F48 Pipeline | offline | **not touched** | Yes | None |

### Proposed functional changes requiring explicit review

| ID | Change | Why | Behaviour affected | Safer alternative |
|---|---|---|---|---|
| R-1 | Kommun outside band filter: fall back + notice | Today the persisted/linked kommun would silently vanish | None today (no persistence exists); new notice text | *Alternative:* always include the requested kommun in the selector regardless of bands. Better UX, but changes the filter's semantics. **Recommended: fall back + notice (default)**. |
| R-2 | Band filter hidden on the start page | It filters nothing there (inert control) | The pills are no longer visible on the start page | Keep visible but disabled with a caption. More clutter, no function. |
| R-3 | Band filter persists across pages | Users expect a sidebar filter to be global | Filter no longer resets when switching page | None needed; the reset is a defect |
| R-4 | Concept expander moved below the stat strip | Lets the CTAs and key figures lead | Order only | Keep order (lower impact) |
| R-5 | Red removed from KPI "danger" | Contradicts the product's own colour policy (PRD, `css.py` comments) | Colour only; sign and value unchanged | Keep red (inconsistent) |
| R-6 | Footer date semantics: "data generated" instead of "file modified" | Correctness | Date shown changes (2026-09-07 instead of the deploy date) | Show both |

---

## A11. Expected Outcomes

| Improvement | Usability | Consistency | Accessibility | Productivity | Maintainability |
|---|---|---|---|---|---|
| Mobile nav restored | Pages reachable on phones | | Operable on touch | | Native control, no hacks |
| Contrast tokens + test | Legible labels | One palette | AA for all text, enforced | | Regressions caught by CI |
| Persisted filter | Filter means what it says | Same state everywhere | | Fewer repeated clicks | |
| Kommun URL + row links | One click to a kommun; shareable | | | ~4 actions → 1 | |
| KPI v2 | Self-describing figures | One card grammar | Not colour-only | Faster reading | Fewer variants |
| Provenance chips | Trust and clarity | Same marker on all cards | Text, not colour | | |
| Chart theme v2 | Swedish numbers in hovers | Charts sit on cards | | | One config |
| Table v2 | Scannable numbers | Right alignment rule | | Row → detail | |
| Fragment + cache | Faster layer toggle | | | Less waiting | |
| Native theming, dead CSS removed | | | | | ~30–40 % less CSS, no stale selectors |

---

# PART B: STEP-BY-STEP IMPLEMENTATION ROADMAP

## B1. Implementation Principles

* Preserve all existing functionality (A3 inventory is the checklist).
* One task = one focused commit on `ux/modernization`, message prefixed with
  the task ID (`T07: ...`). Each commit leaves `pytest` green.
* Do not touch `pipeline.py`, `src/fetch`, `src/clean`, `src/model`,
  `artifacts/`, `data/`.
* Do not edit any number in `SWEDISH_LABELS` copy
  (`tests/test_copy_matches_artifacts.py` pins them). New strings are
  **added** as new keys.
* Every new user-facing string is Swedish, lives in `SWEDISH_LABELS`, and
  contains no typographic dash (– — −).
* No new runtime dependency. Any Streamlit API used must exist in 1.55.0.
* Keep `shai-`/`kss-` class prefixes (PRD §6: renaming is wasted scope).
* Test after every task: `pytest -q` and a manual check of the affected
  page at 1440 px and 390 px.

## B2. Prioritized Task Breakdown

| ID | Pri | Task | Objective | Files | Depends | Est. | Risk |
|---|---|---|---|---|---|---|---|
| T01 | P0 | Branch, tag, baseline | Safe workspace and reference screenshots | none (git) | none | 0.5 h | Low |
| T02 | P0 | Version parity and API check | Tests run on production Streamlit; confirm APIs | `.venv` only; notes in plan | T01 | 0.5 h | Low |
| T03 | P0 | Design tokens v2 + native theme | Contrast-safe palette; theme in config | `css.py`, `.streamlit/config.toml` | T02 | 3 h | Med |
| T04 | P0 | App shell: mobile toggle, chrome, focus | Navigation reachable on mobile; visible focus | `css.py` | T03 | 1.5 h | Med |
| T05 | P1 | Cleanup: dead CSS/tokens, `APP_VERSION`, provenance date | Single sources, correct date | `css.py`, `components.py`, `provenance.py`, pages, `sidebar.py` | T03 | 1 h | Low |
| T06 | P0 | Sidebar v2: nav, filter scope and persistence | Fix P-2, P-4, P-5, P-6 | `sidebar.py`, `app.py`, `labels.py`, tests | T04 | 3 h | Med |
| T07 | P1 | Component library v2 | KPI v2, chips, callout, headings, notes | `components.py`, `css.py`, `labels.py`, tests | T03 | 3 h | Low |
| T08 | P1 | Chart theme v2 | Swedish separators, transparent bg, one config | `chart_theme.py`, all pages | T03 | 2 h | Low |
| T09 | P1 | Riksöversikt header + KPI row | Apply KPI v2, chips, year chip | `01_Riksoversikt.py`, `labels.py` | T07 | 1.5 h | Low |
| T10 | P1 | Ranking table v2 + row → kommun link | Alignment, count, pinned, help, deep link | `01_Riksoversikt.py`, `labels.py`, tests | T09, T11 | 3 h | Med |
| T11 | P0 | Kommun persistence + header + KPI | `?kommun=` and session; KPI v2; peer links | `02_Kommunjamforelse.py`, `labels.py`, tests | T07 | 3 h | Med |
| T12 | P2 | Forecast panel restructure | Units, benchmark chart, grouped text | `01_Riksoversikt.py`, `labels.py` | T08, T09 | 2 h | Low |
| T13 | P1 | Start page IA + diagram card + link cards | CTAs, single card, real links | `app.py`, `components.py`, `labels.py` | T06, T07 | 3 h | Low |
| T14 | P2 | Map/histogram fragment + GeoJSON cache + layout | Perf and equal heights | `01_Riksoversikt.py`, `choropleth.py` | T08 | 2.5 h | Med |
| T15 | P1 | Responsive pass | 390/768/1024/1440 verified | `css.py` | T09–T13 | 2 h | Low |
| T16 | P2 | Loading/empty/notice states | No blank or silent states | pages, `labels.py` | T10, T11, T14 | 1 h | Low |
| T17 | P1 | Accessibility audit + contrast test | AA enforced in CI | `tests/test_design_tokens.py` (new), `css.py` | T15 | 2 h | Low |
| T18 | P0 | Full regression | Prove nothing lost | none (tests, manual) | all | 2.5 h | Low |
| T19 | P1 | Docs + final report | PRD §6/§7, README, report | `docs/PRD.md`, `README.md`, `UX_UI_IMPLEMENTATION_REPORT.md` | T18 | 1.5 h | Low |
| | | **Total** | | | | **38.5 h** | |

**Deferred (P3, outside the 5 days):** D-1 `st.navigation` migration; D-2
dark mode (needs map/legend/ramp review); D-3 a dedicated mobile version of
the model diagram; D-4 printable kommun profile (PDF); D-5 Excel export;
D-6 a Streamlit Cloud preview app for the branch (useful but needs account
access). Copy finding P-22 (hardcoded year spans) is logged for a content
pass, not this UX plan.

**Cut order if behind schedule:** T12 → T16 → T14 → (T10 row-link part).
P0 tasks are never cut.

## B3. Five-Day Implementation Schedule

At ~7.5 focused hours a day; 38.5 h total.

| Day | Tasks | Hours | Exit check |
|---|---|---|---|
| **1: Foundation** | T01, T02, T03, T04, T05 | 6.5 | `pytest` green on 1.55.0; mobile toggle visible at 390 px; footer shows 2026-09-07 |
| **2: Navigation & components** | T06, T07, T08 | 8 | Filter persists across pages and is absent on the start page; new components unit-tested; hovers show "248 378" |
| **3: Main pages** | T11, T09, T10 | 7.5 | `?kommun=0180` opens Stockholm; row in Rangordning opens kommun; KPI rows v2 |
| **4: Remaining pages & responsive** | T13, T12, T14, T15 | 9.5 → cut T14 to day 5 if needed | Start page CTAs; forecast chart; layout verified at 4 widths |
| **5: QA & refinement** | (T14 if moved), T16, T17, T18, T19 | 7 | Contrast test green; full checklist B5 ticked; report written |

Day 4 carries 9.5 h. T14 (P2) is the planned overflow into day 5, which
has ~1 h of slack after T16–T19 (7 h).

## B4. Implementation Prompts

### B4.0 Standing constraints (every prompt below says "apply SC")

* **SC-1** Work on branch `ux/modernization`. One commit per task, message
  starts with the task ID. End commits with the session's attribution lines.
* **SC-2** Never modify `pipeline.py`, `src/fetch/`, `src/clean/`,
  `src/model/`, `artifacts/`, `data/`.
* **SC-3** All user-visible text is Swedish and lives in `SWEDISH_LABELS`
  (`src/ui/labels.py`). Add new keys; never edit existing numbers in copy.
  No `–`, `—` or `−` in any string. ASCII hyphen only where Swedish
  spelling requires it.
* **SC-4** No new runtime dependency (`tests/test_requirements.py`). Any
  Streamlit API must exist in 1.55.0 (check with the venv from T02).
* **SC-5** Preserve these test anchors: `riks.radio[0]` = layer radio;
  `riks.dataframe[0]` = ranking table (290 rows by default);
  `riks.multiselect[0]` = kommun filter (290 options); `kommun.selectbox[0]`
  = kommun selector (290 options, labels contain "index", not "rang"); the
  controls table keeps the `vars_table_ci` column; backtest texts render
  without interaction; "0,02" and "1,51 procentenheter" render on
  Riksöversikt.
* **SC-6** After the change run `.venv/Scripts/python -m pytest -q` (must
  be fully green) and run the app (`streamlit run app.py`), checking the
  affected page at 1440×900 and 390×844 with no exception or error
  element.
* **SC-7** Keep `shai-`/`kss-` class prefixes. Prefer native Streamlit
  over CSS; never target a `data-testid` without first confirming it
  exists in the 1.55 DOM.
* **SC-8** Report what changed, the files touched, test output, and
  anything not done.

---

### T01: Branch, tag, baseline (P0, 0.5 h)

> **Task T01. Objective:** create a safe, reversible workspace and a
> visual baseline for the UX modernization of Skattekraftspanelen.
>
> **Context:** a Streamlit app (`app.py`, `pages/01_Riksoversikt.py`,
> `pages/02_Kommunjamforelse.py`, `src/ui/`). `main` at `c818fa7` is the
> latest version and deploys to Streamlit Cloud directly, so nothing may be
> committed to `main` during this work.
>
> **Requirements:**
> 1. `git status` must be clean. Create the annotated tag
>    `pre-ux-modernization` on `main` HEAD and the branch
>    `ux/modernization` from it.
> 2. Run `.venv/Scripts/python -m pytest -q` and record the pass count
>    (expected 452).
> 3. Start the app on a free port and capture viewport screenshots of all
>    three pages at 1440×900 (scrolled through) and 390×844 (top of
>    page). Save them **outside the repo** (or into a git-ignored folder)
>    as the visual baseline. Note the measured facts: sidebar expand
>    button size at 390 px; active pill text/background colours.
> 4. Do not change any source file.
>
> **Must remain intact:** everything; this task is read-only apart from git
> refs. **Acceptance:** tag and branch exist; baseline test count recorded;
> screenshots exist; `git status` clean. **Done when:** you report the tag
> SHA, branch name, test count and screenshot location. Apply SC.

### T02: Version parity and API check (P0, 0.5 h)

> **Task T02. Objective:** make local tests run on the Streamlit version
> production uses, and confirm every API this plan relies on exists in it.
>
> **Context:** `requirements.txt` pins `streamlit==1.55.0` (what
> Streamlit Cloud installs). The local `.venv` has 1.56.0, so the 452 tests
> currently exercise a different version than production.
>
> **Requirements:**
> 1. `.venv/Scripts/python -m pip install "streamlit==1.55.0"`.
> 2. Run the full test suite; it must stay green. If it is not, stop and
>    report.
> 3. In that venv, verify by `inspect.signature`/`hasattr` and record
>    yes/no for each: `st.page_link(query_params=, icon=)`,
>    `st.switch_page(query_params=)`, `st.query_params`, `st.fragment`,
>    `st.container(horizontal=, gap=)`, `st.dataframe(on_select=,
>    selection_mode=, row_height=)`, `st.column_config.NumberColumn(
>    alignment=, pinned=)`, `st.column_config.TextColumn(alignment=,
>    pinned=)`, `st.pills(key=, on_change=)`, and the config options
>    `theme.sidebar.*`, `theme.baseRadius`, `theme.borderColor`,
>    `theme.codeFont`, `theme.headingFont` (`streamlit config show`).
>    Also check whether `AppTest` exposes `query_params` and a pills or
>    button-group accessor.
> 4. Write the results as a short table into a new section
>    "B7. Verified API matrix (T02)" at the end of
>    `UX_UI_MODERNIZATION_PLAN.md`. Every later task that relies on a
>    missing API must use its documented fallback.
>
> **Constraints:** do not change `requirements.txt` or `pyproject.toml`.
> **Acceptance:** `pip show streamlit` reports 1.55.0; tests green; matrix
> written. **Done when:** committed as `T02: ...`. Apply SC.

### T03: Design tokens v2 and native theme (P0, 3 h)

> **Task T03. Objective:** introduce the contrast-safe token set of plan
> §A7.1 to §A7.3 and move base theming into Streamlit's native config.
>
> **Context:** `src/ui/css.py` holds `COLORS` (Python dict, interpolated into
> `GLOBAL_CSS` with `%` formatting, so literal `%` must be written `%%`) and
> about 930 lines of CSS. `.streamlit/config.toml` sets only five theme
> keys. Measured failures: gold text on light 2.4:1, `#9CA3AF` text 2.4:1,
> border `#EEF0F3` nearly invisible.
>
> **Requirements:**
> 1. In `COLORS` add `accent_text #8A6D2B`, `accent_on_dark #E2C98F`,
>    `negative_text #9A4F06`, `focus #C4A35A`; change `border` to
>    `#E5E7EB`. Do **not** remove or rename existing keys in this task.
>    Do **not** touch `POSITION_SCALE`, `DIVERGING_SCALE`, `CHART_PALETTE`.
> 2. Expose new CSS variables: every colour token, spacing
>    `--space-1..7` (4, 8, 12, 16, 24, 32, 48 px), `--radius-card: 6px`,
>    and type sizes from §A7.2.
> 3. Replace every use of `--color-accent` **as text colour on a light
>    ground** (`.shai-page-title .shai-eyebrow`, `.shai-year`,
>    `.shai-step-num`) with `--color-accent-text`. On the navy hero use
>    `--color-accent-on-dark`. Replace every **text** use of
>    `--color-text-tertiary` with `--color-text-secondary`
>    (`.shai-vintage`, `.shai-stat-label`, `.shai-card-header .shai-tag`,
>    `.shai-footer-*`, `.shai-help-mark`), keeping tertiary for borders,
>    lines and non-text marks.
> 4. `.shai-explanation`: 14 px, line-height 1.55, `max-width: 80ch`.
>    `.shai-summary`: `max-width: 88ch`. `.shai-vintage`: sans, 12 px.
> 5. Card radius 6 px (`.shai-card`, `.shai-kpi`, `.shai-nav-card`).
>    Remove the hero gradient (solid `--color-primary`).
> 6. `.streamlit/config.toml`: keep existing keys; add, **only where T02
>    confirmed support**, `baseRadius = "6px"`, `borderColor = "#E5E7EB"`,
>    `codeFont = "IBM Plex Mono, monospace"`, and a `[theme.sidebar]`
>    block with `backgroundColor = "#0B1F3F"`, `secondaryBackgroundColor =
>    "#13294D"`, `textColor = "#FFFFFF"`, `primaryColor = "#C4A35A"`,
>    `borderColor = "#22375C"`.
> 7. Do not yet delete the sidebar `*` colour override (that is T06), but
>    verify nothing renders worse with the native sidebar theme in place.
>
> **Must remain intact:** all class names, all page output, all tests (the
> choropleth tests import `POSITION_SCALE` and `COLORS`).
> **Visual expectation:** same identity, calmer: visible card borders,
> readable eyebrows and vintage line, no gradient.
> **Testing:** pytest; screenshots of all pages at 1440 px compared with the
> baseline; measure eyebrow and vintage contrast in DevTools (≥4.5:1).
> **Acceptance:** no text token below 4.5:1 on its background (except
> large ≥24 px text at ≥3:1); tests green. **Done:** committed `T03: ...`.
> Apply SC.

### T04: App shell, mobile toggle, chrome, focus (P0, 1.5 h)

> **Task T04. Objective:** make the sidebar reachable on mobile and give
> every custom interactive element a visible focus state.
>
> **Context:** `GLOBAL_CSS` sets `header[data-testid="stHeader"]
> {display:none}`. In Streamlit 1.55 the sidebar expand button
> (`stExpandSidebarButton`) lives inside that header, so at ≤768 px it
> measures 0×0 and users cannot open navigation. Several selectors target
> test IDs that no longer exist (`stSidebarCollapse`, `collapsedControl`,
> `baseButton-headerNoPadding`, `button[kind="headerNoPadding"]`).
>
> **Requirements:**
> 1. In the 1.55 DOM, identify the actual test IDs for the header, toolbar,
>    main menu, decoration, sidebar expand and collapse buttons (DevTools
>    or Playwright `document.querySelectorAll('[data-testid]')`).
> 2. Replace the header rule: keep `stHeader` displayed, background
>    transparent, no height beyond what the expand control needs. Hide
>    only the toolbar actions, main menu and decoration.
> 3. Desktop (≥769 px): keep the sidebar locked open at 260 px; hide the
>    collapse/expand controls **by their current test IDs**.
>    Mobile (≤768 px): native overlay behaviour; the expand control must be
>    visible (≥40×40 px hit area), top-left, with navy icon on the page
>    background.
> 4. Delete every selector that targets a test ID not present in 1.55.
> 5. Add a global `:focus-visible` style for `.shai-help`, links in the
>    sidebar and `a[data-testid="stPageLink-NavLink"]`: 2 px
>    `--color-focus` outline, 2 px offset.
> 6. Remove the custom `::after` dim overlay if the native overlay already
>    provides one; keep it only if it does not.
>
> **Must remain intact:** desktop sidebar fixed at 260 px; Streamlit menu
> and toolbar not visible to users; `menu_items` config.
> **Testing:** at 390×844, the expand control is visible; tapping it opens
> the sidebar; tapping a page link navigates; the sidebar closes. At
> 1440×900 there is no visible header strip. Keyboard: Tab reaches every
> nav link and `?` badge with a visible ring. pytest green.
> **Acceptance:** all three pages navigable on mobile using only taps.
> **Done:** committed `T04: ...`. Apply SC.

### T05: Cleanup, single sources, provenance date (P1, 1 h)

> **Task T05. Objective:** remove dead styling, centralise the version
> string, and show the data date instead of the file date.
>
> **Context:** "v1.0" is hardcoded in `app.py`, both pages and
> `sidebar.py`. The footer date is `position.parquet` mtime, which on
> Streamlit Cloud is the clone time. `artifacts/data_provenance.json` has
> `generated_at` (ISO-8601). CSS contains unused rules.
>
> **Requirements:**
> 1. Add `APP_VERSION = "v1.0"` to `src/ui/components.py` (or a small
>    `src/ui/meta.py`) and use it in all four places.
> 2. Add `data_generated_date() -> str` to `src/provenance.py`: return
>    the `YYYY-MM-DD` part of `generated_at`; fall back to the
>    `position.parquet` mtime and then to `""`. Add a unit test in
>    `tests/test_provenance.py` for both paths.
> 3. Replace the three `_UPDATED_DATE` blocks with that function.
> 4. Grep the repo (including tests) for each of `.shai-pill`, `risk-lag`,
>    `risk-medel`, `risk-hog`, `shai-coef-bar`, `stDataFrame`, `low_risk`,
>    `medium_risk`, `high_risk`. Delete CSS rules with no user; delete
>    colour keys only if nothing imports them (keep `--color-*-risk` CSS
>    variables if `.shai-kpi.variant-*` still uses them until T07).
> 5. Remove the dead `div[data-testid="stDataFrame"] th/td` rules (the grid
>    is canvas-rendered and ignores them).
> 6. Remove the inline hex `#6B7280` in `kpi_card` (use a CSS class).
>
> **Must remain intact:** visual output except the footer date. **Testing:**
> pytest; footer shows `2026-09-07`. **Acceptance:** no remaining "v1.0"
> literal outside the constant; grep shows no dead selectors listed above.
> **Done:** committed `T05: ...`. Apply SC.

### T06: Sidebar v2, navigation, filter scope and persistence (P0, 3 h)

> **Task T06. Objective:** fix the sidebar's four defects: fake active link,
> unreadable active pills, filter shown where it does nothing, and filter
> reset on every page change.
>
> **Context:** `src/ui/sidebar.py::render_sidebar(page_key)` renders inactive
> pages with `st.page_link` and the active page as raw `<a href="#">`;
> `st.pills` has no key; `app.py` renders the filter although it never reads
> `sidebar_state`. Pages read `sidebar_state["selected_bands"]` (a list of
> band labels; empty is coerced to all). The test
> `tests/test_choropleth.py::TestSidebarAgreesWithTheMap` pins
> `_BAND_LEGEND` and `_BAND_OPTIONS` order.
>
> **Requirements:**
> 1. Signature becomes `render_sidebar(page_key: str, show_filter: bool =
>    True) -> dict`. `app.py` passes `show_filter=False`; the return value
>    then still contains `selected_bands` (the persisted value, or all).
> 2. Navigation: render all three items with `st.page_link(page, label,
>    icon=...)`, including the current page. Icons `:material/home:`,
>    `:material/map:`, `:material/location_city:`. Delete the raw-HTML
>    active link and its CSS. Style active/inactive via the native theme
>    plus minimal CSS: 40 px rows, active row gold background with navy
>    text (≥6.8:1), inactive white 85 %.
> 3. Persistence: store the canonical selection in
>    `st.session_state["kss_bands"]` (initialised to all options). Render
>    `st.pills(..., key="kss_bands_widget", default=st.session_state[
>    "kss_bands"], on_change=_sync)` where `_sync` copies the widget value
>    (coercing empty to all) into `kss_bands`. This is the standard pattern
>    for state surviving page switches.
> 4. Delete the `section[data-testid="stSidebar"] * {color ... !important}`
>    rule and the related overrides now covered by `[theme.sidebar]`
>    (T03). Re-check that brand title, nav, section label, legend and
>    footer meet contrast (footer text ≥4.5:1; use white at ≥70 %).
> 5. Do not change band labels, options, legend swatches or their order.
>
> **Must remain intact:** empty selection = all (pages never get an empty
> list); histogram and ranking table on Riksöversikt follow the bands; the
> kommun selector narrows by bands with fall-back to all.
> **Testing:** add tests in `tests/test_pages_render.py` (or a new
> `tests/test_sidebar.py`): (a) the start page renders no pills widget;
> (b) on Riksöversikt, setting the bands to "Under 90" then switching to
> Kommunjämförelse leaves the selector narrowed to kommuner under 90
> (use `AppTest` session state if no pills accessor exists, per T02);
> (c) all existing tests green. Manual: select "Över 110" on Riksöversikt,
> open Kommunjämförelse, return: the selection is still "Över 110".
> **Acceptance:** P-2, P-4, P-5, P-6 resolved; tests added and green.
> **Done:** committed `T06: ...`. Apply SC.

### T07: Component library v2 (P1, 3 h)

> **Task T07. Objective:** extend `src/ui/components.py` with the components
> in plan §A7.4, without breaking existing call sites.
>
> **Context:** components return HTML strings rendered through `st.html`;
> CSS in `src/ui/css.py`. `kpi_card` today takes `label, value, unit,
> delta, delta_direction, variant('default'|'danger'|'success'), tooltip`.
>
> **Requirements:**
> 1. `kpi_card(..., context: str = "", tone: str = "neutral")` with
>    `tone in {"neutral","positive","negative"}`. Layout: label (11 px
>    uppercase), value (30 px tabular), then an optional line combining a
>    sign glyph (▲ positive, ▼ negative, none for neutral) with unit and
>    context (13 px `text_secondary`). Positive glyph `--color-positive`,
>    negative glyph `--color-negative-text`. The left border is always
>    `--color-primary`. Legacy `variant="danger"` maps to
>    `tone="negative"`, `variant="success"` to `tone="positive"`. Cards in
>    a row get equal height. The tooltip stays in `title`, and when present
>    a `help_badge`-like `?` is shown beside the label (keyboard
>    reachable).
> 2. `provenance_chip(kind)` for kind in `observed|model|forecast`, text
>    from new labels `tag_observed` = "Observerat", `tag_model` = "Modell",
>    `tag_forecast` = "Prognos"; tooltips `tag_observed_help`,
>    `tag_model_help`, `tag_forecast_help` (write plain Swedish: observed =
>    SCB statistics recomputed to index, no model; model = estimated
>    statistical relationship, not cause; forecast = forward estimate with
>    an interval, always shown with its track record). Distinct but quiet
>    styles: outline chip, text in `text_secondary`; the forecast chip
>    uses `accent_text`.
> 3. `card_header(..., kind: str | None = None)` renders the chip on the
>    right; if `tag` is also given, both render.
> 4. `section_heading(title, level=3, help_terms=())`, `callout(html,
>    variant="summary"|"note")`, `data_note(text)` and `explanation(html)`.
>    Move the styling from inline styles to CSS classes.
> 5. `page_title(...)`: render `year` as an inline chip after the
>    subtitle; remove `.shai-year` float and negative margin.
> 6. Unit tests in a new `tests/test_components.py`: tone/variant mapping;
>    glyph present only for signed tones; chip text comes from labels; no
>    Swedish literal in `components.py` (reuse the label-reference scanner
>    pattern from `tests/test_labels.py`); HTML escapes nothing
>    unexpectedly.
>
> **Must remain intact:** every existing call site renders identically
> until pages adopt the new arguments (T09, T11, T13).
> **Acceptance:** tests green; components documented by docstrings.
> **Done:** committed `T07: ...`. Apply SC.

### T08: Chart theme v2 (P1, 2 h)

> **Task T08. Objective:** one chart theme that is Swedish in its numbers
> and sits flush on cards.
>
> **Context:** `src/ui/chart_theme.py::get_chart_layout` returns a dict;
> pages tweak it afterwards (margins, ranges, fonts). Hovertemplates use
> `%{y:,.0f}` and `%{y:.1f}`, which Plotly renders as `248,378` and `96.6`.
> `config={"displayModeBar": False}` is repeated six times.
>
> **Requirements:**
> 1. In the layout dict: `separators=", "`, `paper_bgcolor` and
>    `plot_bgcolor` `"rgba(0,0,0,0)"`, both axes `automargin=True` and
>    `title.standoff=8`.
> 2. Export `CHART_CONFIG = {"displayModeBar": False}` and use it in every
>    `st.plotly_chart` call (`app.py` ×1, Riksöversikt ×2 (+1 in T12),
>    Kommunjämförelse ×3).
> 3. Do not change any hovertemplate text, trace, colour or range.
> 4. Verify in the browser: the kronor trend hover shows `248 378 kr`;
>    the position hover shows `96,6`; the histogram y-title is no longer
>    clipped; charts have no white box inside the cards.
> 5. Add a test asserting `get_chart_layout()["separators"] == ", "` and a
>    scan test that no page passes a literal `displayModeBar` dict.
>
> **Must remain intact:** every chart's encoding (dot-and-whisker,
> coloured histogram bins, band cut lines, median annotation, 100 line,
> decomposition colours). **Acceptance:** hovers Swedish; tests green.
> **Done:** committed `T08: ...`. Apply SC.

### T09: Riksöversikt header and KPI row (P1, 1.5 h)

> **Task T09. Objective:** apply KPI v2 and provenance chips to
> Riksöversikt.
>
> **Context:** `pages/01_Riksoversikt.py` L162–204 builds four KPI cards
> whose values concatenate number and kommun name (`"-8,1, Oskarshamn"`),
> which wraps and makes heights unequal; the fall uses `variant="danger"`
> (red).
>
> **Requirements:**
> 1. Cards:
>    * spread: value `"208 / 80"`, context `"{high_name} / {low_name}"`;
>    * fall: value `format_index_points(drift)`, unit
>      `SWEDISH_LABELS["unit_index_points"]`, context kommun name,
>      `tone="negative"`;
>    * rise: likewise with `tone="positive"`;
>    * R²: value as today, context new label `kpi_cross_r2_context` =
>      "Tvärsnitt {year}" formatted with the analysis year.
>    Tooltips unchanged.
> 2. `card_header(kind=...)`: map, histogram, index scatter, ranking →
>    `"observed"`; forecast → `"forecast"`.
> 3. Use `data_note()` for the vintage line and `callout()` for the summary.
> 4. Keep all numbers computed exactly as today.
>
> **Must remain intact:** all of SC-5; KPI tooltips; numbers.
> **Testing:** pytest; visual check at 1440 (equal card heights), 1024 and
> 390. **Acceptance:** no red on the page; units visible.
> **Done:** committed `T09: ...`. Apply SC.

### T10: Ranking table v2 and row → kommun link (P1, 3 h)

> **Task T10. Objective:** make the 290-row table scannable and make every
> row a way into the kommun detail page.
>
> **Context:** `pages/01_Riksoversikt.py` L566–668. Index columns are
> `NumberColumn` (right-aligned); drift, forecast and interval are
> pre-formatted Swedish text (left-aligned) on purpose (comment at L620–626:
> Streamlit number formats cannot produce a fixed-decimal Swedish comma).
> Requires T11 (the kommun page accepts `?kommun=<kod>`).
>
> **Requirements:**
> 1. Keep `display_df` columns, order, values and the CSV **exactly**
>    (the CSV is built from `display_df`; do not add a hidden kod column
>    to it. Keep kods in a parallel list).
> 2. `column_config`: `Kommun` pinned; text columns for drift, forecast and
>    interval `TextColumn(alignment="right")` if T02 confirmed support
>    (otherwise skip this sub-item and note it); every column gets `help`
>    from existing glossary/label text (no new copy needed except where
>    absent).
> 3. `height`: show about 15 rows (`row_height` default × 15 + header).
> 4. Always show a count caption via new label `table_row_count`
>    = "Visar {shown} av {total} kommuner". Keep the existing
>    `kommun_filter_active` sentence when names are chosen.
> 5. Selection: `st.dataframe(..., key="kss_ranking",
>    on_select="rerun", selection_mode="single-row")`. When a row is
>    selected, render above the table `st.page_link(
>    "pages/02_Kommunjamforelse.py", label=SWEDISH_LABELS[
>    "table_open_kommun"].format(kommun=name), icon=":material/arrow_forward:",
>    query_params={"kommun": kod})`. When none is selected, show the hint
>    label `table_select_hint` = "Markera en rad för att öppna kommunen i
>    Kommunjämförelse." as a caption. Selected row indices refer to
>    `display_df` order (sorted by position); map them through the
>    parallel kod list.
> 6. Put the download button in a horizontal container with the count
>    caption (right-aligned button).
>
> **Must remain intact:** `riks.dataframe[0]` is still this table with 290
> rows; the name filter tests still pass; band filtering; CSV bytes
> identical to before for the same selection (add a test comparing column
> names and row count).
> **Testing:** pytest; manual: sort by "Förflyttning 10 år", select a row,
> click the link, and the kommun page opens on that kommun.
> **Acceptance:** one click from table to kommun. **Done:** committed
> `T10: ...`. Apply SC.

### T11: Kommun persistence, header, KPI v2, peer links (P0, 3 h)

> **Task T11. Objective:** the chosen kommun persists across navigation, can
> be shared as a URL, and can be reached from peers.
>
> **Context:** `pages/02_Kommunjamforelse.py` L156–171 builds string
> options `"Namn (Län) index N"` sorted by position (lowest first) from the
> band-filtered frame, `index=0`, and maps the label back to a kod. Tests
> assert 290 options, the first containing "index" and not "rang".
>
> **Requirements:**
> 1. Options become the kod list; `format_func` produces the existing label
>    string (unchanged text). Confirm in T02 that `AppTest`'s
>    `selectbox.options` returns formatted labels, so tests keep passing.
>    If not, keep string options and map kods separately.
> 2. Resolve the initial kod: `st.query_params.get("kommun")` → else
>    `st.session_state.get("kss_kommun")` → else first option. Validate it
>    against `position_latest` (unknown kod → ignore). If valid but
>    outside the band-filtered options, use the first option and show
>    `st.caption` with new label `kommun_outside_filter` = "{kommun} ligger
>    utanför det valda positionsfiltret. Visar {fallback} i stället."
> 3. On change (`key="kss_kommun_select"`, `on_change`): write
>    `st.session_state["kss_kommun"]` and `st.query_params["kommun"]`.
>    Also set the query param on first render so the URL always reflects
>    the shown kommun.
> 4. Header row: `page_title` left, selector right in `st.columns([3,2])`
>    (stacks on mobile by existing CSS).
> 5. KPI v2: our index (context new label `kpi_context_ours` = "riket =
>    100"), SCB index (context `kpi_context_scb` = "riksmedelvärdet =
>    100"), drift 5y/10y with unit `unit_index_points` and `tone` by sign
>    (`neutral` when the value rounds to 0 or is missing). Remove the red
>    `danger` usage.
> 6. Chips: position chart, kronor trend, peers → observed; decomposition
>    and controls → model.
> 7. Peers: `st.dataframe(..., on_select="rerun",
>    selection_mode="single-row", key="kss_peers")`; on selection show
>    `st.page_link` to this page with `query_params={"kommun": kod}` and
>    label `table_open_kommun`.
>
> **Must remain intact:** SC-5 kommun anchors; order lowest first; default
> with no params and no state = Högsby (current behaviour); all charts and
> tables; comparison multiselect (max 4).
> **Testing:** new tests with `AppTest`: (a) query param `kommun=0180`
> selects Stockholm (if `AppTest` supports query params per T02;
> otherwise test the resolver function, extracted as a pure function in
> `src/ui/filters.py` with unit tests); (b) invalid kod falls back to
> default; (c) the filtered-out case returns the fallback and the notice
> flag. Manual: open `/Kommunjamforelse?kommun=0180`, switch to
> Riksöversikt and back: still Stockholm; copy the URL into a new tab:
> Stockholm.
> **Acceptance:** P-7 resolved. **Done:** committed `T11: ...`. Apply SC.

### T12: Forecast panel restructure (P2, 2 h)

> **Task T12. Objective:** make the forecast's track record readable at a
> glance without removing any text.
>
> **Context:** `pages/01_Riksoversikt.py` L464–560: lead, backtest lead,
> four score cards (no units), verdict, coverage sentence, historical
> caveat, guide. All inside `if not forecast_df.empty`. Tests require the
> backtest title, the three benchmark labels, horizon and origins, "0,02"
> and "1,51 procentenheter" to render without interaction.
>
> **Requirements:**
> 1. Score cards via KPI v2 with units: Spearman (context "0 till 1, 1 =
>    exakt rätt ordning", new label `kpi_context_spearman`), RMSE and the
>    two benchmarks with unit `unit_index_points`.
> 2. New horizontal bar chart beneath the cards: three bars (model,
>    naive, persistence RMSE) from the artifact, sorted ascending, model bar
>    `COLORS["primary"]`, benchmarks `COLORS["text_tertiary"]`, values
>    printed with `format_index_points`-style one decimal (unsigned, use a
>    small local formatter via labels), x-axis title new label
>    `chart_rmse_axis` = "Medelfel i indexenheter, lägre är bättre",
>    height 160, theme v2, `CHART_CONFIG`. Bar labels reuse
>    `backtest_rmse`, `backtest_naive`, `backtest_persistence`.
> 3. Order: lead → cards → chart → backtest lead (as the chart's note) →
>    verdict → coverage → historical caveat in `callout(variant="note")`
>    → guide expander.
> 4. Everything stays inside the existing `if not forecast_df.empty`.
>
> **Must remain intact:** every sentence; all `TestBacktestPanelIsPublished`
> and `TestRetiredLayerIsGone` tests. **Testing:** pytest; also temporarily
> rename `artifacts/forecast.parquet` locally to confirm the page renders
> without the panel (restore it afterwards; never commit that).
> **Done:** committed `T12: ...`. Apply SC.

### T13: Start page IA, diagram card, real link cards (P1, 3 h)

> **Task T13. Objective:** let the two main journeys lead the start page,
> and remove its fake affordances and inline styles.
>
> **Context:** `app.py`: hero (L123–129), concept expander, stat strip, a
> model card faked from two HTML half-cards around a `components.html`
> SVG iframe (fonts not loaded inside the iframe), inline-styled `<h3>`
> headings for pipeline and navigation, `.shai-nav-card` divs with
> `cursor:pointer` that are not links, followed by plain `st.page_link`
> text links.
>
> **Requirements:**
> 1. Under the hero, a horizontal container with two `st.page_link`
>    buttons: new labels `cta_find_kommun` = "Hitta din kommun"
>    (`:material/location_city:`, to Kommunjämförelse) and `cta_national` =
>    "Se hela riket" (`:material/map:`, to Riksöversikt). Style the first as
>    primary (gold background, navy text) and the second as secondary
>    (outline) through scoped CSS on a wrapper key/class.
> 2. Order per plan §A5: hero + CTAs → stat strip + explanation → concept
>    expander → rest unchanged.
> 3. Model overview: one `st.container(border=True)` containing
>    `card_header(...)`, the `components.html` SVG and the explanation
>    (`explanation()`). Inside the iframe add `<link
>    href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Source+Sans+3:wght@400;600;700&display=swap"
>    rel="stylesheet">` and font stacks with `system-ui, sans-serif`
>    fallbacks. Keep every SVG element and colour as today.
> 4. Pipeline and navigation headings via `section_heading()`; no inline
>    `style=` left in `app.py` except inside the SVG.
> 5. Nav cards: two `st.container(border=True)`, each with heading,
>    description and a full-width `st.page_link` (icon + label). Delete
>    `.shai-nav-card` hover/cursor rules.
> 6. Sources block: `st.container(border=True)` with the same content.
> 7. Chips: coefficients card and within card → `kind="model"`.
>
> **Must remain intact:** all copy; `TestLandingLeadsWithTheIdentifiedModel`
> tests; stat counts read from artifacts; coefficient chart and tables.
> **Testing:** pytest; manual: both CTAs navigate; Tab order reaches them
> right after the hero; screenshots at 1440 and 390.
> **Done:** committed `T13: ...`. Apply SC.

### T14: Map/histogram fragment, GeoJSON cache, layout (P2, 2.5 h)

> **Task T14. Objective:** a layer toggle reruns only the map row, and the
> styled GeoJSON is built once per layer.
>
> **Context:** `pages/01_Riksoversikt.py` L249–405 builds the map and
> histogram inside `st.columns([3, 2])`; `src/ui/choropleth.py::
> render_choropleth` formats tooltip columns and injects properties into
> all 290 features on every rerun, then calls `st_folium(...,
> key="kss_choropleth", returned_objects=[])`.
>
> **Requirements:**
> 1. Extract the row into `def _map_row(map_df, filtered_df)` decorated
>    with `@st.fragment`; call it with the frames. The radio stays inside
>    (so `riks.radio[0]` remains the layer radio; confirm with tests).
> 2. In `choropleth.py` extract `_styled_geojson(layer_key, data_hash)`
>    (or pass a hashable frame) under `@st.cache_data` that returns the
>    GeoJSON with properties injected. Keep `render_choropleth`'s
>    signature and behaviour. Keep `color_for`/`build_colormap` public and
>    unchanged.
> 3. Wrap the first map build in `st.spinner(SWEDISH_LABELS[
>    "spinner_map"])`, new label "Ritar kartan".
> 4. Equal card heights for the two columns (`vertical_alignment` or CSS
>    on the column block); map height 480 desktop, 360 at ≤768 px (CSS on
>    the folium iframe).
>
> **Must remain intact:** layer default, colours, legend, tooltips, the
> histogram's dependence on the band filter, all choropleth tests.
> **Testing:** pytest; manual: toggle the layer and confirm that the
> ranking table does not flash (whole-page rerun gone) and that the
> histogram follows; measure toggle latency before and after (DevTools
> Performance) and report both.
> **Fallback:** if `st_folium` misbehaves inside a fragment (blank map
> after toggle), drop the fragment and keep only the cache.
> **Done:** committed `T14: ...`. Apply SC.

### T15: Responsive pass (P1, 2 h)

> **Task T15. Objective:** verified layouts at 390, 768, 1024 and 1440 px.
>
> **Context:** `css.py` has breakpoints at 1024 and 768. At ≤768 every
> column stacks; KPI rows jump from four across to one.
>
> **Requirements:**
> 1. KPI rows: 2×2 between 769 and 1100 px; 1 column at ≤768 px only if 2
>    columns cannot hold the value (test with "+17,3 indexenheter").
>    Implement with CSS on the KPI row container (`flex-wrap`, `min-width`).
> 2. Page padding: 16 px on mobile.
> 3. The header row on Kommunjämförelse stacks; the selector becomes full
>    width.
> 4. Tables scroll horizontally inside their card; the card never
>    overflows the viewport (`overflow-x: auto` on the card only if needed).
> 5. Hero CTAs stack at ≤480 px.
> 6. SVG diagram: at ≤640 px the iframe height adapts (set `height` from
>    an estimated aspect ratio, or accept horizontal scroll inside the
>    card; report which).
> 7. No horizontal page scroll at any width.
>
> **Testing:** screenshots of all three pages at four widths; check
> `document.documentElement.scrollWidth <= innerWidth`. pytest.
> **Done:** committed `T15: ...`. Apply SC.

### T16: Loading, empty and notice states (P2, 1 h)

> **Task T16. Objective:** no silent or blank state anywhere.
>
> **Requirements:**
> 1. Riksöversikt: if band filter + name filter yield 0 rows, show
>    `st.caption(SWEDISH_LABELS["empty_filter_result"])` = "Inga kommuner
>    matchar filtren. Ändra positionsfiltret i sidopanelen eller rensa
>    kommunvalet." instead of an empty grid (keep the dataframe element
>    rendered with 0 rows so test indexing stays stable).
> 2. Histogram with no values (all bands off is impossible, but guard
>    anyway): caption instead of an empty chart.
> 3. Kommun page: the `kommun_outside_filter` notice from T11 is visible;
>    verify the "no drift" lead variant still renders for a kommun with
>    missing drift (find one in the artifact or simulate it in a unit
>    test of the lead builder).
> 4. Forecast absent: confirm the page reads naturally without the panel
>    (no orphan heading).
>
> **Testing:** unit tests for each branch where practical; pytest.
> **Done:** committed `T16: ...`. Apply SC.

### T17: Accessibility audit and contrast test (P1, 2 h)

> **Task T17. Objective:** WCAG 2.1 AA for everything this project
> controls, enforced by a test.
>
> **Requirements:**
> 1. New `tests/test_design_tokens.py`: a WCAG relative-luminance function;
>    assert ratio ≥4.5 for each text pair: `text_primary`,
>    `text_secondary`, `accent_text`, `negative_text`, `positive` on both
>    `card_bg` and `bg`; `accent_on_dark` and white 70 % (composited) on
>    `primary`; navy on `accent`. Assert `text_tertiary` is not used as a
>    `color:` value for any text class in `GLOBAL_CSS` (regex scan).
> 2. Keyboard pass: Tab through every page; every interactive element is
>    reachable in a logical order with a visible focus ring; the `?`
>    popovers open on focus; no keyboard trap in the map iframe (Tab must
>    leave it).
> 3. Semantics: one `h1` per page; card titles `h3`; section headings
>    `h3`/`h4` in order; the SVG iframe has a `title` attribute and the
>    diagram's meaning is in the adjacent explanation (it already is).
> 4. Colour-not-alone: KPI tones carry glyph and sign; chips carry text;
>    map layers have text legends (already true; verify).
> 5. `prefers-reduced-motion` rule kept.
>
> **Testing:** pytest; axe DevTools (or Playwright + axe-core injected) run
> on all three pages, with zero serious or critical issues attributable to
> project code (document any that come from Streamlit internals).
> **Done:** committed `T17: ...`. Apply SC.

### T18: Full regression (P0, 2.5 h)

> **Task T18. Objective:** prove every feature from the inventory (plan §A3,
> F01 to F48) still works.
>
> **Requirements:** run `pytest -q` (all green; report the count, which must
> be ≥452 plus new tests). Run the app and execute checklist B5 item by
> item at 1440 px and the mobile items at 390 px. Compare against the T01
> baseline screenshots. Fix regressions in a separate `T18-fix: ...`
> commit per issue. Record the results in the checklist (ticked or failed
> with a note).
>
> **Done:** checklist complete with no failed item, or failures listed with
> cause and decision. Apply SC.

### T19: Documentation and final report (P1, 1.5 h)

> **Task T19. Objective:** docs describe the product as built.
>
> **Requirements:**
> 1. `docs/PRD.md` §6 Design System: tokens, contrast rule, components and
>    when to use them, provenance chips, chart theme, "no red/green".
>    §7 Page Structure: the new start page order, CTAs, deep links,
>    persisted filter and kommun. §8 Acceptance Criteria: add "text
>    contrast ≥4.5:1 enforced by `tests/test_design_tokens.py`".
> 2. `README.md` "Vill du ... ändra utseendet": mention
>    `.streamlit/config.toml` theme + `src/ui/css.py` tokens +
>    `src/ui/components.py`; add a line on `?kommun=<kod>` links.
> 3. Write `UX_UI_IMPLEMENTATION_REPORT.md`: completed changes per task,
>    files modified (`git diff --stat pre-ux-modernization..HEAD`),
>    preserved functionality (A3 checklist result), tests performed with
>    counts, remaining issues, deferred items (D-1 to D-6, P-22), and known
>    limitations.
>
> **Done:** committed `T19: ...`; the branch is ready for review and merge
> (merging is the owner's decision). Apply SC.

## B5. Testing and Regression Checklist

Run at 1440×900 unless marked 📱 (390×844). Tick each in T18.

### Startup & shell
- [ ] `streamlit run app.py` starts with no traceback; no `st.exception`/`st.error` on any page
- [ ] `pytest -q` all green (≥452 + new)
- [ ] F02 Sidebar shows 3 nav links with icons; the current page is highlighted; each link navigates
- [ ] F02 📱 Expand control visible; opens sidebar; links navigate; sidebar closes
- [ ] F03 Band filter absent on Startsida; present on both other pages
- [ ] F03 Set "Under 90" on Riksöversikt → Kommunjämförelse keeps it → back keeps it
- [ ] F03 Deselecting all pills shows all kommuner (empty = all)
- [ ] F04 Legend swatches match map colours (Över 110 green, 90 till 110 neutral, Under 90 purple)
- [ ] F05/F08 Footer shows "Senast uppdaterad: 2026-09-07" and v1.0
- [ ] F06 Every `?` opens on hover **and** keyboard focus, with correct terms
- [ ] F09 No Streamlit toolbar/menu visible to users on desktop

### Startsida
- [ ] F11 Hero renders; both CTAs navigate to the right pages
- [ ] F12 Concept expander opens and shows full text
- [ ] F13 Stat strip shows 290 / 17 / 4 / 2 (from artifacts) + explanation
- [ ] F14 Diagram renders with brand fonts, single card, no seam; 📱 legible or scrollable
- [ ] F15 Coefficient chart: 4 rows, education and unemployment coloured, controls grey, zero line, value column, hover shows Swedish decimals
- [ ] F16 Coefficient table 4 rows with CI and "Går att särskilja"
- [ ] F17 Guide expander opens
- [ ] F18 Within panel title "Samband inom kommuner över tid", table with stars, caveat, guide
- [ ] F19 Pipeline 4 steps + explanation
- [ ] F20 Both nav cards navigate via their link
- [ ] F21 Sources block with 4 SCB codes and text

### Riksöversikt
- [ ] F22 Title, subtitle, year chip "2026"
- [ ] F23 KPIs: 208 / 80 (Danderyd / Högsby); -8,1 indexenheter Oskarshamn ▼; +17,3 indexenheter Danderyd ▲; 69 % Tvärsnitt 2024; tooltips work; no red
- [ ] F24 Summary sentence complete
- [ ] F25 Map renders; default layer "Nuvarande position"; toggle to "Förflyttning 5 år" recolours; tooltips list name, indexes, drifts, skattekraft, unemployment, population; legend 80/90/100/110/130 and -4/0/+4
- [ ] F25 Layer toggle does not rerun the ranking table (T14)
- [ ] F26 Caption follows layer; guide opens
- [ ] F27 Histogram follows layer and band filter; band cut lines; dashed reference; median annotation; end-bin hover says "och lägre/högre"; y-title not clipped
- [ ] F28 Scatter: all points above the dashed line; hover Swedish
- [ ] F29 Forecast panel: lead, 4 cards with units, RMSE chart (model shortest), backtest lead, verdict, coverage sentence, historical caveat with "0,02" and "1,51 procentenheter", guide
- [ ] F44 With `forecast.parquet` temporarily absent: page renders, no panel, no forecast columns
- [ ] F30 Table: 290 rows; columns unchanged; right-aligned figures; Kommun pinned; ~15 rows visible; count caption; column help tooltips
- [ ] F30 Sorting by any column works
- [ ] F30 Select row → "Öppna X i Kommunjämförelse" → opens X
- [ ] F31 Name filter: choose Filipstad + Danderyd → 2 rows + note; clear → 290
- [ ] F32 CSV downloads; same columns/rows as the table; opens in Excel with å/ä/ö intact
- [ ] F33 Guide opens

### Kommunjämförelse
- [ ] F34 Selector: 290 options, lowest first, labels "Namn (Län) index N"
- [ ] F34 No params, fresh session → Högsby
- [ ] F34 `?kommun=0180` → Stockholm; URL updates when changing kommun; survives navigation away/back; invalid `?kommun=9999` → default without error
- [ ] F34 Band filter "Över 110" with a persisted low kommun → fallback + notice
- [ ] F35 Lead sentence with drift; a kommun without drift uses the short variant
- [ ] F36 KPIs: two indexes with "riket = 100" contexts; drifts with unit and ▲/▼; explanation below
- [ ] F37 Position line with 100 line + annotation; note; guide
- [ ] F38 Kronor trend with national average; add 4 comparison kommuner (5th blocked); hover "kr" with space thousands
- [ ] F39 Decomposition: education + unemployment + residual bars only; residual grey; sum equals gap (spot-check Filipstad: -16,7)
- [ ] F40 Controls table: 2 rows with intervals
- [ ] F41 Guide opens
- [ ] F42 Peers: 5 rows; selecting a row offers a link that opens that kommun

### Cross-cutting
- [ ] F46 No "." decimal anywhere in rendered numbers (tables, hovers, KPIs); no "-0,0"
- [ ] F47 No year hardcoded in changed code (`grep -n "20[12][0-9]" app.py pages src/ui` reviewed)
- [ ] 📱 No horizontal page scroll on any page; KPIs readable; tables scroll inside cards
- [ ] Tablet 768 and 1024: layouts as specified
- [ ] Keyboard-only walk-through of all pages; visible focus throughout
- [ ] Contrast test green; axe scan has no serious/critical issues from project code
- [ ] Browsers: Chrome and Firefox desktop, Safari iOS (or WebKit via Playwright) 📱
- [ ] Two-layer language rule: `tests/test_labels.py` green (no Swedish outside labels.py, no dashes)
- [ ] Copy-matches-artifacts tests green (no number in copy changed)

Not applicable (and confirmed absent): authentication, database operations,
form submissions, data persistence beyond the session, external API calls at
runtime.

## B6. Rollback Strategy

* **Original preserved:** tag `pre-ux-modernization` on `main` at
  `c818fa7`. `main` (which Streamlit Cloud serves) is not touched until the
  owner merges.
* **Isolation:** all work on `ux/modernization`. Optionally deploy that
  branch as a separate Streamlit Cloud app for review (D-6).
* **Traceability:** one commit per task with the task ID as prefix.
  `git log --oneline pre-ux-modernization..ux/modernization` lists every
  change; `git show <sha> --stat` shows its files.
* **Revert one task:** `git revert <sha>` (tasks were ordered so later
  tasks depend on earlier ones; revert in reverse dependency order: e.g.
  reverting T07 requires reverting T09, T11, T12 and T13 first, or
  re-pointing them to legacy arguments, which T07 keeps working).
* **Failed task mid-way:** `git restore .`/`git stash` to return to the
  previous task's commit; the test suite at each commit is the gate.
* **After merge:** `git revert -m 1 <merge-sha>` on `main` restores the
  previous UI in one commit; Streamlit Cloud redeploys automatically.
  Artifacts and pipeline are untouched by design, so data cannot be
  affected by a UI rollback.
* **Dependency rollback:** none needed. No dependency is added or changed
  (T02 only aligns the local venv to the existing pin).

---

## Stage 4: Internal Review of This Proposal

| Check | Result |
|---|---|
| Missing pages | All three pages and the shared shell are specified (A6.0 to A6.3). |
| Overlooked features | Inventory F01 to F48 cross-checked against every `st.*` call in the three page files and `sidebar.py`; each appears in A10 and B5. |
| Unnecessary changes | Rejected: `st.navigation` migration, class renames, new libraries, dark mode, copy rewrites. Each would cost time without fixing a measured problem. |
| Unrealistic estimates | 38.5 h over 5 days is tight; a cut order is defined (T12 → T16 → T14 → T10 link part), with P0 work (11 h) front-loaded on days 1 to 3. |
| Conflicting decisions | Gold for text vs accent resolved by two tokens. "No red" applied to KPIs while ramps stay test-pinned. Persistence (T06, T11) is consistent with "empty = all". |
| Technical incompatibilities | Every API is gated by T02 on 1.55.0 with a stated fallback (TextColumn alignment, AppTest query params, fragment + st_folium). Canvas grid limits are respected (no CSS on cells). |
| Risks to functionality | Test anchors listed (SC-5); CSV bytes protected (T10); forecast-absent path re-verified (T12, B5); copy numbers frozen (SC-3). |
| Industry fit | Provenance chips, units, Swedish locale in charts, shareable kommun URLs and the "direction is not judgement" rule are specific to public-finance statistics, not generic SaaS styling. |

**Verdict:** achievable in 5 working days with the P2 items as the
buffer. If time runs short, the essential improvements are T01 to T11 plus
T17 and T18 (mobile nav, contrast, persistence, deep links, KPI clarity,
Swedish charts, regression proof). That set fits in about 4 days.

---

## Stage 5: STOP FOR APPROVAL

No source file has been modified. Implementation (Stage 6) starts with T01
only after explicit approval. Decisions requested at approval:

1. Approve the plan as a whole, or name tasks to drop or defer.
2. Review items R-1 to R-6 (A10). Defaults: R-1 fall back + notice, R-2
   hide, R-3 persist, R-4 reorder, R-5 remove red, R-6 provenance date.
