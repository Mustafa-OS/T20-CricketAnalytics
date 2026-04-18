# Context XI — T20 Cricket Analytics

Ball-by-ball analytics across every major T20 competition — leagues, men's
T20 internationals, and T20 World Cups — fronted by **CAIS**, a
context-adjusted impact score that re-prices every delivery by phase,
bowler type, batter quality, form, and match pressure.

> Conventional averages and strike rates flatten context. 35 off 25 in the
> 18th over defending 160 does not equal 35 off 25 in a dead middle over
> against the 5th bowler. CAIS separates them.

![Stack](https://img.shields.io/badge/python-3.11+-3776ab) ![Flask](https://img.shields.io/badge/flask-backend-000) ![Plotly](https://img.shields.io/badge/plotly.js-charts-3f4f75) ![Cricsheet](https://img.shields.io/badge/data-cricsheet-ef4444)

## What's in it

- **13 competitions**, ~2.1 million ball-by-ball rows
  - PSL · IPL · BBL · CPL · Vitality Blast · The Hundred · SA20 · ILT20 · MLC · LPL · BPL
  - Men's T20 Internationals *(restricted to ICC Full-Member nations — no associate noise)*
  - T20 World Cups
- **Pick-a-league first**: a blocking picker on first visit, then one-click
  swap from the top-bar badge.
- **Five views per competition**:
  - **CAIS** leaderboards (batting + bowling), bar + scatter, season + team filters
  - **Batting** — runs, strike rate, average-vs-SR bubble
  - **Bowling** — wickets, economy, wickets-vs-economy scatter
  - **Records** — highest scores, century makers, team win-rates, dismissal breakdown
  - **Player profile modal** — career stats, season trends, innings history,
    CAIS rank within the selected competition
- **Dual delivery**: runs as a Flask dev server *or* as a fully-static
  GitHub Pages site backed by precomputed per-competition JSON.

## CAIS in one paragraph

Every legal delivery is re-priced before it lands on the scorecard.

- **Batting** — `runs × phase_weight × pressure`, normalised per 100 balls,
  scaled by rolling form. PP is the *easiest* phase (0.95), death is the
  hardest (1.35). Pressure combines wicket-loss + 2nd-innings required-rate.
- **Bowling** — wickets score `30 × phase×role × batter_tier × form × pressure
  × partnership_mult × early_wicket_mult` against a phase-weighted run cost.
  A pace powerplay wicket (2.0×) that breaks a 60-run stand against an elite
  batter in a high-RRR chase can score 5–6× a tailender in a dead over.

The methodology page inside the app lists every weight and formula.

## Quick start

```bash
pip install flask pandas numpy pyarrow
python app.py            # http://localhost:5000
```

First request loads `data/all.parquet` (~2.8s, ~10s on first-ever run while
the parquet cache is built from CSV). Switching leagues after that is
sub-second thanks to per-competition memoisation of the enriched frame.

### Static / GitHub Pages mode

`index.html` is drag-and-drop openable. It reads from
`static/data/<comp>/*.json` directly when it's not being served by Flask.
Regenerate those files with:

```bash
python precompute.py              # every competition (~10 min)
python precompute.py ipl psl      # just named ones
```

## Getting fresh data

```bash
pip install pandas
python ingest.py                  # downloads every supported league's Cricsheet zip
python ingest.py ipl bbl          # just these
```

`ingest.py` writes `data/<code>.csv`, a combined `data/all.csv`, and derives
`wc.csv` from T20Is events containing "World Cup". The T20I and WC views
are filtered to ICC Full Members only
(`{Afghanistan, Australia, Bangladesh, England, India, Ireland, New Zealand,
Pakistan, South Africa, Sri Lanka, West Indies, Zimbabwe}`) so that
leaderboards reflect games against first-tier opposition.

## Project layout

```
.
├── index.html               # Single-page UI (Plotly + vanilla JS)
├── app.py                   # Flask — /api routes for dynamic mode
├── CricketAnalyser.py       # Analytics engine + CAIS v2
├── ingest.py                # Cricsheet → project schema
├── precompute.py            # Pre-bakes static/data/<comp>/*.json
├── data/                    # (gitignored) CSVs + parquet cache
│   ├── raw/                 #   cached Cricsheet zips
│   ├── all.csv              #   combined ball-by-ball
│   └── all.parquet          #   5× faster sidecar, auto-built
└── static/
    └── data/
        ├── competitions.json          # manifest
        └── <comp>/
            ├── cais-batting.json      # career
            ├── cais-batting-2024.json # per-season
            ├── batting.json
            ├── bowling.json
            ├── players.json
            └── …
```

## Performance notes

The first build of this app across 2M rows was visibly sluggish. The current
hot-path:

1. **Parquet sidecar cache** — `pandas.read_parquet` is ~5× faster than
   `read_csv` on this dataset. Built on first load, reused after.
2. **Per-competition memoisation** — `_build_enriched`, `_batter_tiers`,
   `_batter_form_scores`, `_infer_bowler_roles` each cache per-comp output.
   Switching leagues doesn't retouch the 2M-row frame; it slices ~70k–300k
   rows and reuses everything else.
3. **Static mode** — every view reads a ~10–200 KB JSON file; no server, no
   pandas, no runtime cost.

Measured on an M2 laptop after the parquet cache is warm:

| operation | time |
|---|---|
| app boot (parquet) | ~2.8s |
| first CAIS for PSL | ~0.35s |
| repeat CAIS for PSL | ~0.13s |
| first CAIS for IPL (new comp) | ~1.6s |

## Data source & credits

All ball-by-ball data is from [Cricsheet](https://cricsheet.org/) — the
definitive open archive for cricket scorecards. CAIS, the UI, and all
analysis code are original to this project.

## Licence

MIT — see `LICENSE` if present; otherwise treat as MIT with attribution.
Data belongs to Cricsheet under their [ODbL-style terms](https://cricsheet.org/register/).
