# 🏏 The T20 Analyst

**Cricket analytics for every major T20 league, built around a new metric that rates every ball by how much it actually mattered.**

**[▶ Open the live site](https://mustafa-os.github.io/T20-CricketAnalytics/)** · Python · pandas · Flask · Plotly · GitHub Actions

![The T20 Analyst home page: competition picker covering 13 T20 leagues and international events](docs/img/home.png)

## At a glance

- 📊 **13 competitions, 6,300+ matches, ~1.8 million balls**: IPL, PSL, Big Bash, The Hundred, T20 World Cups and more.
- 🧮 **CAIS, my own metric.** It scores every ball by match situation (phase, pressure, opponent, knockout stage), so a last-over six against a top bowler isn't worth the same as a single in a dead game.
- 🔁 **Updates itself every night.** A GitHub Actions pipeline downloads new matches, rebuilds the site, and **refuses to publish if the numbers drift** from official records (IPL Orange/Purple Caps, PSL leaders, World Cup top scorers).
- ⚡ **Fast and free to host.** The public site is static JSON on GitHub Pages: no server, under 50 ms per view.

## The idea

Normal batting and bowling tables ignore **context**, which is what matters most in T20:

- A strike rate of 140 is average in the first six overs and elite at the death.
- 30 runs off a bowler is cheap in the 18th over and expensive in the middle overs.
- Four wickets against India at a World Cup is not the same as four against Namibia.

The T20 Analyst attaches context to every ball before adding anything up, so leaderboards show **quality, not just volume**. The scoring sliders are live, so you can switch any factor off or double it and watch the rankings change.

![CAIS view for the T20 World Cups: leaderboard, season and team filters, and the scoring-control sliders](docs/img/cais-leaderboard.png)

## What you can do on the site

Pick a competition, then:

1. **CAIS:** batting and bowling leaderboards using the context-adjusted score, with live sliders to tune the weights. This is the flagship view.
2. **Batting:** runs, average, strike rate, with an average-vs-strike-rate bubble chart.
3. **Bowling:** wickets and economy, with a wickets-vs-economy scatter.
4. **Records:** highest scores, centuries, team win rates, how batters get out.
5. **Player profiles:** career stats, season-by-season trends and CAIS rank. Click any name in any table.

<details>
<summary><b>All 13 competitions</b></summary>

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

The T20I view is filtered to the 12 ICC Full Members so leaderboards reflect
first-tier opposition, not tier-6 warm-up fixtures.

</details>

## How CAIS works

**Batting:** every run is multiplied by how hard it was to score, then turned into a rate:

    CAIS = Σ (runs × phase × pressure × stage × opponent) / balls × 100 × form

**Bowling:** every wicket is worth more when it matters more (an elite batter, a big partnership, a tense chase, an early breakthrough), and every run conceded costs more at the death:

    CAIS = Σ (wicket value − run cost) / overs

A powerplay wicket that breaks a 60-run stand against an elite batter in a tense chase can score **5–6× more** than dismissing a tailender in a dead middle over. That's the whole point.

<details>
<summary><b>Full weights and design choices</b></summary>

![CAIS view for the T20 World Cups — leaderboard, season and team filters, and the scoring-control sliders](docs/img/cais-leaderboard.png)

Every legal delivery is re-priced before it lands on the scorecard. The weights
live in `CricketAnalyser.py` (see `_build_enriched`); the gist:

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
| early_wicket      | 1.35 in first over, 1.15 in overs 2–3, 1.0 otherwise      |
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
Bilateral T20Is are excluded from the stage ladder — the last match of a
calendar year is not a "final" in any meaningful sense.

### Opponent-quality multiplier

Only applies inside the T20 World Cup, where the main draw mixes Full Members
and qualified associates: a Test-nation player gets less credit (0.85) for
runs or wickets against associate opposition, and an associate player gets
more (1.20) against Test-nation opposition. Everywhere else it stays at 1.00.
A **Pool** chip in the WC view further restricts the leaderboard to the 12
Test nations for apples-to-apples comparisons.

### Scoring controls

The CAIS page exposes the phase weights and context bonuses as live sliders —
set a bonus to 0% to switch that factor off, 200% to double it, and the
leaderboard re-ranks client-side without recomputing anything server-side.

</details>

## How it's built

```
Cricsheet data ──ingest.py──▶ CSVs ──CricketAnalyser.py──▶ every ball enriched with context
                                                    │
                                     precompute.py  ▼
                                     static JSON per competition ──▶ GitHub Pages
                                     (audit.py blocks publishing if numbers drift)
```

- **`CricketAnalyser.py`**: the analytics engine, ~1,100 lines of vectorised pandas/NumPy.
- **`audit.py`**: checks computed leaderboards against official records before anything goes live.
- **`index.html`**: one page that works both as a static site and against the local Flask API.

<details>
<summary><b>Technical details: delivery modes, pipeline, automation, performance</b></summary>

### Two delivery modes, one page

- **Static GitHub Pages** (the public deployment) — precomputed
  per-competition JSON under `static/data/`, served as plain files. No
  backend, no pandas, sub-100 ms competition switching.
- **Flask dev server** (local) — dynamic, reads the full ball-by-ball frame,
  recomputes on demand.

The same `index.html` handles both: it hits `/api/...` first when running
under Flask and falls back to `static/data/<comp>/<file>.json` otherwise.

### Pipeline

    Cricsheet zips ──ingest.py──▶ data/*.csv ──CricketAnalyser──▶ enriched frame
                                                     │
                                       precompute.py ▼
                                       static/data/<comp>/*.json ──▶ GitHub Pages

- `ingest.py` downloads Cricsheet's per-competition ball-by-ball zips,
  normalises them into one CSV schema, derives the World Cup slice from T20I
  events, and filters T20Is to Full Members.
- `CricketAnalyser.py` (~1,100 lines of pandas/NumPy) enriches every delivery
  with phase, pressure, partnership state, stage and opponent multipliers,
  batter tiers, bowler roles and rolling form, then aggregates CAIS and every
  other view. Vectorised throughout.
- `precompute.py` bakes the whole thing into a per-competition folder of
  career and per-season JSON (one file per view per season) plus a
  `competitions.json` manifest carrying the freshness timestamp shown in the
  site header.
- `audit.py` cross-checks the computed leaderboards against hard-coded
  reference values (IPL Orange/Purple Caps, PSL season leaders, T20 WC top
  scorers) and, in `--strict` mode, fails the pipeline before anything is
  published if a number drifts out of tolerance.

### Automation

Two GitHub Actions workflows keep the public site current without manual
intervention:

- **Nightly refresh** (`refresh.yml`) — re-ingests every Cricsheet zip,
  rebuilds the static JSON bundle, runs the audit gate, and commits the
  result (`chore(data): nightly refresh`).
- **Pages deploy** (`pages.yml`) — republishes the static site whenever
  `index.html` or `static/**` changes on `main`.

### Performance

The first version was visibly sluggish across ~2 M rows — full CSV parse on
every request, full `groupby` scan on every league switch. The current hot
path:

1. **Parquet sidecar cache** — `read_parquet` is ~5× faster than `read_csv`
   on this dataset. Built on first boot, reused every run after.
2. **Per-competition memoisation** — enrichment, batter tiers, form scores
   and bowler roles are each cached per competition, so switching leagues
   slices ~70k–300k rows once and reuses everything after.
3. **Static mode** — every public view reads a 10–200 KB JSON. No server, no
   pandas, no runtime cost.

Measured on an M2 laptop with a warm parquet cache: app boot ~2.8 s, first
CAIS build for a competition ~0.35–1.6 s, repeat views ~0.14 s, any static
JSON fetch <50 ms.

### Notable design choices

- **`match_id` collision guard.** WC matches also appear inside the raw T20I
  frame under the same `match_id`, so the stage-multiplier map is keyed on
  `(competition, match_id)` — knockout bumps from the World Cup can't leak
  into a bilateral view.
- **Every aggregated row carries a balls-weighted `team` field**, which powers
  the client-side team chip and the WC Pool filter without an extra
  round-trip.
- **Multi-season merge.** Selecting several seasons fetches each season's JSON
  and combines them per player with an endpoint-specific merger
  (balls-weighted CAIS, additive runs/wickets, weighted SR/economy) — a
  player who appears in three seasons shows once, aggregated.
- **Accuracy audited, not assumed.** The nightly pipeline refuses to publish
  if computed leaderboards drift from published reference values.

### Project layout

    .
    ├── index.html               # Single-page UI (Plotly + vanilla JS). Dual-mode.
    ├── app.py                   # Flask backend — /api routes for dynamic mode.
    ├── CricketAnalyser.py       # Analytics engine. Enrichment + CAIS v3.
    ├── ingest.py                # Cricsheet zips → project CSV schema.
    ├── precompute.py            # Bakes every static/data/<comp>/*.json file.
    ├── audit.py                 # Leaderboard accuracy gate vs reference values.
    ├── CAIS_Methodology.docx    # Longer methodology write-up.
    ├── .github/workflows/       # Nightly data refresh + Pages deploy.
    ├── data/                    # (gitignored) raw zips, CSVs, parquet cache.
    └── static/data/             # Precomputed JSON — manifest + ~15 files per comp.

</details>

## Run it locally

The zero-setup option is the [live site](https://mustafa-os.github.io/T20-CricketAnalytics/).
To run locally:

```bash
pip install -r requirements.txt   # pandas, numpy, flask
pip install pyarrow               # optional — enables the faster parquet cache

# 1. Pull ball-by-ball data from Cricsheet (data/ is not committed)
python ingest.py                  # every league
python ingest.py ipl psl          # or just the ones you want

# 2. Run the Flask app
python app.py                     # http://localhost:5000
```

To regenerate the static bundle that GitHub Pages serves:

```bash
python precompute.py              # every competition (~10 min)
python precompute.py ipl psl wc   # just the named ones
```

> **Gotcha:** running `precompute.py` with specific codes overwrites
> `static/data/competitions.json` with a manifest covering only those codes.
> Restore it with `git checkout HEAD -- static/data/competitions.json`.

## About

Personal project, built from April 2026 and still running nightly. It started as a PSL-only dashboard and grew into a multi-competition platform with its own metric, static-site compiler and automated data pipeline. All ball-by-ball data is from [Cricsheet](https://cricsheet.org/). CAIS, the pipeline, the UI and all analysis code are my own.

Code is MIT-licensed (see [LICENSE](LICENSE)); the data stays subject to [Cricsheet's terms](https://cricsheet.org/register/).

---

<sub>Built by <b>Mustafa Suleman</b>, MEng Design Engineering, Imperial College London · <a href="https://github.com/Mustafa-OS">More projects</a> · <a href="https://www.linkedin.com/in/mustafaosuleman/">LinkedIn</a></sub>
