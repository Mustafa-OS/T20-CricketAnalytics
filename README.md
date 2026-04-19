# The T20 Analyst

**Ball-by-ball analytics across every major T20 competition, fronted by CAIS —
a context-adjusted impact score that re-prices every delivery.**

13 competitions. ~2.1 million legal deliveries. One lens that refuses to let a
death-over six against an elite attack count the same as a middle-over single
off the fifth bowler in a dead game.

![Python](https://img.shields.io/badge/python-3.11+-3776ab)
![Flask](https://img.shields.io/badge/flask-backend-000)
![Plotly](https://img.shields.io/badge/plotly.js-charts-3f4f75)
![Cricsheet](https://img.shields.io/badge/data-cricsheet-ef4444)
![Licence](https://img.shields.io/badge/licence-MIT-6aa84f)

---

## Why this exists

Conventional batting and bowling tables flatten the thing that actually matters
in T20: **context**. A strike rate of 140 is average in the powerplay and elite
at the death. A 30-run spell is cheap in the 18th over and expensive in the
middle. A four-for against Sri Lanka and Namibia at a World Cup is not a
four-for against Sri Lanka and India.

Most public databases paper over this with career averages and raw economy
rates. The T20 Analyst doesn't. Every legal delivery in the dataset is scored
*with context attached* — phase of the innings, batter quality, bowler type,
match pressure, tournament stage, opponent quality — and rolled up from there.

The result is a leaderboard where the order actually reflects the quality of
what happened, not just the volume.

---

## What's in it

### Competitions (13)

| Code     | Competition                      |
| -------- | -------------------------------- |
| `psl`    | Pakistan Super League            |
| `ipl`    | Indian Premier League            |
| `bbl`    | Big Bash League                  |
| `cpl`    | Caribbean Premier League         |
| `ntb`    | Vitality Blast                   |
| `hnd`    | The Hundred                      |
| `sa20`   | SA20                             |
| `ilt`    | International League T20         |
| `mlc`    | Major League Cricket             |
| `lpl`    | Lanka Premier League             |
| `bpl`    | Bangladesh Premier League        |
| `t20is`  | Men's T20 Internationals *(Full Members only)* |
| `wc`     | T20 World Cups                   |

The T20I view is filtered to the 12 ICC Full Members —
Afghanistan, Australia, Bangladesh, England, India, Ireland, New Zealand,
Pakistan, South Africa, Sri Lanka, West Indies, Zimbabwe — so leaderboards
reflect first-tier opposition, not tier-6 warm-up fixtures.

### Five views per competition

1. **CAIS** — batting and bowling leaderboards with the context-adjusted score,
   a bar chart of the top 20, a CAIS-vs-raw-SR scatter, season filters, and a
   team filter. The flagship view; everything else is supporting cast.
2. **Batting** — runs, average, strike rate, and an average-vs-SR bubble plot.
3. **Bowling** — wickets, economy, and a wickets-vs-economy scatter.
4. **Records** — highest scores, century makers, team win-rates, dismissal
   breakdowns.
5. **Player profile modal** — career stats, per-season trends, innings history,
   and the player's CAIS rank within the current competition. Opens from any
   name in any leaderboard.

### Two delivery modes

- **Flask dev server** — dynamic, reads the parquet cache, recomputes on
  demand. Used locally.
- **Static GitHub Pages** — precomputed per-competition JSON under
  `static/data/`, served as plain files. No backend, no pandas, sub-100ms
  switching. Used for the public deployment.

The same `index.html` handles both: it hits `/api/...` first when running under
Flask, falls back to `static/data/<comp>/<file>.json` otherwise.

---

## CAIS in one page

Every legal delivery is re-priced before it lands on the scorecard. The weights
are stored in `CricketAnalyser.py` — search for `_build_enriched` — but the
gist is:

### Batting

    CAIS = Σ (runs × phase × pressure × stage × opponent) / balls × 100 × form

| factor        | value                                     |
| ------------- | ----------------------------------------- |
| phase         | 0.95 powerplay · 1.15 middle · 1.35 death |
| pressure      | 1.0 → 1.5, combining wickets-lost and 2nd-innings required rate |
| stage         | 1.00 group · 1.10 QF · 1.20 SF · 1.30 final (tournaments only) |
| opponent      | WC only: 1.20 associate-vs-Test, 0.85 Test-vs-associate |
| form          | rolling-5 innings ratio vs the field mean, clipped 1.0–1.45 |

The phase weight is **flipped** on purpose — strike rate in the powerplay is
inflated by fielding restrictions, death bowlers aim at your toes. A 20-ball
30 at the death is genuinely harder than a 20-ball 30 in the first six.

### Bowling

    wicket_value = 30 × (phase × role) × batter_tier × form × pressure
                      × partnership × early_wicket × stage × opponent
    run_cost     = runs_conceded × phase_bowl_weight × 0.5 × stage × opponent
    CAIS         = Σ (is_wicket × wicket_value − run_cost) / overs

| factor            | value                                                     |
| ----------------- | --------------------------------------------------------- |
| phase × role      | pace: 2.0 / 1.2 / 1.8 · spin: 1.5 / 1.5 / 1.2 (PP/mid/death) |
| batter_tier       | derived per competition from runs + SR percentile         |
| form              | per-batter rolling form at the time of the wicket         |
| pressure          | same wicket + chase pressure as batting                   |
| partnership       | 1.0 at 20-run stand, ramps to 1.6 at 70+                  |
| early_wicket      | 1.35 in first over, 1.15 in overs 2-3, 1.0 otherwise      |
| stage             | same group/QF/SF/final ladder as batting                  |
| opponent          | WC only: 1.20 associate-vs-Test, 0.85 Test-vs-associate   |
| phase_bowl_weight | 1.2 powerplay · 1.0 middle · 1.3 death (run cost only)    |

A pace powerplay wicket that breaks a 60-run stand against an elite batter in
a high-RRR chase can score **5–6× more** than a tailender in a dead middle
over. That's the whole point.

### Stage multiplier

Cricsheet's CSV schema stores `match_number` as plain integers even for finals,
so the stage is inferred from match dates: within each (competition, season)
the latest match is the Final (1.30), the 1–3 matches within 7 days of it are
the Semis / Qualifiers (1.20), and the 4–5 matches within 10 days are
Quarters / Eliminators (1.10). Everything else is group stage (1.00).

Bilateral T20Is are **excluded** from the stage ladder — the last match of a
calendar year is not a "final" in any meaningful sense.

### Opponent-quality multiplier

Only applies inside the T20 World Cup, where the main draw mixes Full Members
and qualified associates:

- Test batter vs associate bowling → **0.85** (less credit)
- Associate batter vs Test bowling → **1.20** (more credit)
- Test bowler vs associate batting → **0.85** (less credit)
- Associate bowler vs Test batting → **1.20** (more credit)

Everywhere else this stays at 1.00.

> Inside the CAIS view on the World Cup competition, a **Pool** chip lets you
> further restrict the leaderboard to the 12 Test nations. Useful for
> apples-to-apples comparisons when you want the knockout-heavyweight view
> without Namibia or USA diluting the pool.

---

## Quick start

### Run the Flask app

    pip install flask pandas numpy pyarrow
    python app.py                 # http://localhost:5000

First request loads `data/all.parquet` (~2.8s, or ~10s on first-ever run while
the parquet cache is built from CSV). Switching competitions after that is
sub-second thanks to per-competition memoisation inside `CricketAnalyser`.

### Open the static site

    open index.html               # any modern browser

The page detects it's not running under Flask, reads from
`static/data/<comp>/*.json`, and works identically. This is how the GitHub
Pages deployment is served.

### Regenerate the static bundle

    python precompute.py              # every competition (~10 min)
    python precompute.py ipl psl wc   # just the named ones

`precompute.py` bakes a per-competition folder containing career and
per-season JSON for every view, plus a top-level `competitions.json`
manifest. Commit the output and it's live.

> **Gotcha:** running `precompute.py` with specific codes will overwrite
> `static/data/competitions.json` with a manifest covering only those codes.
> If you want to rebuild one competition without losing the manifest, run
> `git checkout HEAD -- static/data/competitions.json` after.

### Pull fresh data from Cricsheet

    pip install pandas
    python ingest.py                  # every supported league
    python ingest.py ipl bbl          # just these

`ingest.py` downloads and unpacks Cricsheet's per-competition ball-by-ball
zips into `data/<code>.csv`, concatenates them into `data/all.csv`, derives
`data/wc.csv` from T20I events whose name contains "World Cup", and filters
T20Is to ICC Full Members.

The t20is season is overridden to the **calendar year** of the first match in
each fixture so that Cricsheet's `2025/26`-style season labels don't
disappear behind a 2025 truncation.

---

## Project layout

    .
    ├── index.html               # Single-page UI (Plotly + vanilla JS). Dual-mode.
    ├── app.py                   # Flask backend — /api routes for dynamic mode.
    ├── CricketAnalyser.py       # Analytics engine. Enrichment + CAIS v3.
    ├── ingest.py                # Cricsheet zips → project CSV schema.
    ├── precompute.py            # Pre-bakes every static/data/<comp>/*.json file.
    ├── CAIS_Methodology.docx    # Longer methodology write-up.
    ├── data/                    # (gitignored)
    │   ├── raw/                 #   cached Cricsheet zips
    │   ├── <code>.csv           #   per-competition ball-by-ball
    │   ├── all.csv              #   concatenated ball-by-ball
    │   └── all.parquet          #   5× faster sidecar, auto-built on first load
    └── static/
        └── data/
            ├── competitions.json        # top-level manifest
            └── <comp>/
                ├── cais-batting.json    # career CAIS
                ├── cais-batting-2024.json  # per-season CAIS
                ├── cais-bowling.json
                ├── batting.json
                ├── strike-rates.json
                ├── bowling.json
                ├── teams.json
                ├── highest-scores.json
                ├── centuries.json
                ├── dismissals.json
                ├── over-heatmap.json
                ├── phase-stats.json
                ├── matchup.json
                ├── seasons.json
                └── players.json         # search list
    

---

## Performance notes

The first version of this app across 2M rows was visibly sluggish — full CSV
parse on every request, full `groupby` scan on every league switch. The
current hot path:

1. **Parquet sidecar cache** — `pandas.read_parquet` is ~5× faster than
   `read_csv` on this dataset. Built on first boot, reused every time.
2. **Per-competition memoisation** — `_build_enriched`, `_batter_tiers`,
   `_batter_form_scores`, and `_infer_bowler_roles` each cache per-comp
   output keyed off the competition code. Switching leagues doesn't retouch
   the full 2M-row frame; it slices ~70k–300k rows once and reuses everything
   after.
3. **Static mode** — every view reads a 10–200 KB JSON. No server, no
   pandas, no runtime cost. This is what GitHub Pages serves.

Measured on an M2 laptop after the parquet cache is warm:

| operation                      | time   |
| ------------------------------ | ------ |
| app boot (parquet)             | ~2.8s  |
| first CAIS for PSL             | ~0.35s |
| repeat CAIS for PSL            | ~0.13s |
| first CAIS for IPL (new comp)  | ~1.6s  |
| repeat CAIS for IPL            | ~0.14s |
| any static JSON fetch          | <50ms  |

---

## Notable design choices

- **CAIS returns a `team` field.** Every aggregated row carries the player's
  most-frequent team (balls-weighted). This powers both the client-side team
  chip and the WC Pool filter without an extra round-trip.
- **Client-side re-ranking after any filter.** When you narrow the board by
  team or pool, the visible list is re-numbered so it starts at #1. The raw
  CAIS is never recomputed, just re-sorted and re-ranked.
- **Multi-season merge.** Selecting multiple seasons in the CAIS view fetches
  each season's JSON and combines them per-player using an endpoint-specific
  merger (balls-weighted CAIS, additive runs/wickets, weighted SR/economy).
  A player who played three of the selected seasons appears once, aggregated,
  not three times.
- **`match_id` collision guard.** WC matches also appear inside the raw
  t20is frame under the same `match_id`. The stage-multiplier map is keyed
  on `(competition, match_id)` so knockout bumps from the WC can't leak into
  a bilateral view.

---

## Data source & credits

All ball-by-ball data is from [Cricsheet](https://cricsheet.org/) — the
definitive open archive for international and T20 league cricket scorecards.

CAIS, the enrichment pipeline, the UI, and every line of analysis code are
original to this project.

---

## Licence

MIT — see `LICENSE` if present; otherwise treat as MIT with attribution.
Data belongs to Cricsheet under their
[ODbL-style terms](https://cricsheet.org/register/).
