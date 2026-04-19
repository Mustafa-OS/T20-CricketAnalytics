from flask import Flask, jsonify, render_template, request
from urllib.parse import unquote
import os
import numpy as np
import pandas as pd
from CricketAnalyser import CricketAnalyser

app = Flask(__name__, template_folder='.', static_folder='static')

# Load combined dataset if present, else fall back to PSL-only.
DATA_PATH = 'data/all.csv' if os.path.exists('data/all.csv') else 'data/psl.csv'
print(f'[app] loading {DATA_PATH}…')
analyzer = CricketAnalyser(DATA_PATH)
print(f'[app] loaded {len(analyzer.df):,} rows across '
      f'{analyzer.df["competition"].nunique()} competitions')

# Display names for competition codes (kept in sync with ingest.py).
COMP_NAMES = {
    'psl':   'Pakistan Super League',
    'ipl':   'Indian Premier League',
    'bbl':   'Big Bash League',
    'cpl':   'Caribbean Premier League',
    'ntb':   'Vitality Blast',
    'hnd':   'The Hundred',
    'sa20':  'SA20',
    'ilt':   'International League T20',
    'mlc':   'Major League Cricket',
    'lpl':   'Lanka Premier League',
    'bpl':   'Bangladesh Premier League',
    't20is': 'Men’s T20 Internationals',
    'wc':    'T20 World Cups',
}


# ── Serialisers ──────────────────────────────────────────────────────────────

def serialize(df):
    """DataFrame → JSON-safe list of dicts."""
    records = df.replace([np.inf, -np.inf], np.nan).to_dict(orient='records')
    return [_clean(row) for row in records]


def _clean(obj):
    """Recursively convert numpy scalars and strip inf/NaN."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if (np.isnan(obj) or np.isinf(obj)) else float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def _comp():
    """Read competition filter from request, validate, return code or None."""
    c = request.args.get('competition')
    if not c or c == 'all':
        return None
    return c if c in COMP_NAMES else None


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/competitions')
def competitions():
    """Return available competitions with row & match counts."""
    out = []
    df = analyzer.df
    for code, name in COMP_NAMES.items():
        sub = df[df['competition'] == code]
        if not len(sub):
            continue
        seasons = sorted(sub['season'].dropna().unique().tolist())
        out.append({
            'code': code,
            'name': name,
            'rows': int(len(sub)),
            'matches': int(sub['match_id'].nunique()),
            'seasons': [int(s) for s in seasons],
            'first_season': int(seasons[0]) if seasons else None,
            'last_season':  int(seasons[-1]) if seasons else None,
        })
    return jsonify(out)


@app.route('/api/seasons')
def seasons():
    """Seasons available for a given competition (or all)."""
    comp = _comp()
    df = analyzer.df if comp is None else analyzer.df[analyzer.df['competition'] == comp]
    s = sorted(df['season'].dropna().unique().tolist())
    return jsonify([int(x) for x in s])


@app.route('/api/batting')
def batting():
    season = request.args.get('season', type=int)
    # Moderate thresholds: keep legitimate contributors, cut only true noise.
    # Short-window tournaments (SA20, ILT20, MLC, WC) still surface a healthy roster.
    mi = 8  if season is None else 3
    mr = 250 if season is None else 60
    return jsonify(serialize(analyzer.batting_averages(
        min_innings=mi, season=season, min_runs=mr, competition=_comp())))


@app.route('/api/strike-rates')
def strike_rates():
    season = request.args.get('season', type=int)
    mb = 150 if season is None else 45
    mr = 150 if season is None else 60
    return jsonify(serialize(analyzer.strike_rate_analysis(
        min_balls=mb, season=season, min_runs=mr, competition=_comp())))


@app.route('/api/bowling')
def bowling():
    season = request.args.get('season', type=int)
    mb = 72 if season is None else 24
    mw = 8  if season is None else 3
    return jsonify(serialize(analyzer.bowling_stats(
        min_balls=mb, season=season, min_wickets=mw, competition=_comp())))


@app.route('/api/teams')
def teams():
    return jsonify(serialize(analyzer.team_performance(competition=_comp())))


@app.route('/api/highest-scores')
def highest_scores():
    return jsonify(serialize(analyzer.highest_scores(top_n=15, competition=_comp())))


@app.route('/api/dismissals')
def dismissals():
    return jsonify(serialize(analyzer.dismissal_analysis(competition=_comp())))


@app.route('/api/centuries')
def centuries():
    df = analyzer.century_makers(competition=_comp())
    counts = (df.groupby('batter').size()
                .reset_index(name='centuries')
                .sort_values('centuries', ascending=False)
                .head(15))
    return jsonify(serialize(counts))


@app.route('/api/players')
def players():
    comp = _comp()
    df = analyzer.df if comp is None else analyzer.df[analyzer.df['competition'] == comp]
    batters = set(df['batter'].dropna().unique())
    bowlers = set(df['bowler'].dropna().unique())
    return jsonify(sorted(batters | bowlers))


@app.route('/api/player/<path:name>')
def player_profile(name):
    name = unquote(name)
    return jsonify(_clean(analyzer.player_profile(name, competition=_comp())))


@app.route('/api/over-heatmap')
def over_heatmap():
    return jsonify(_clean(analyzer.over_heatmap(competition=_comp())))


@app.route('/api/phase-stats')
def phase_stats():
    return jsonify(_clean(analyzer.phase_stats(competition=_comp())))


@app.route('/api/matchup')
def matchup():
    return jsonify(_clean(analyzer.matchup_heatmap(competition=_comp())))


@app.route('/api/cais/batting')
def cais_batting():
    season = request.args.get('season', type=int)
    # Moderate thresholds — keep short-tournament regulars (SA20, ILT20, MLC, WC)
    # visible while still cutting one-and-done cameos.
    default_balls = 100 if season is None else 40
    default_runs  = 250 if season is None else 60
    min_balls = request.args.get('min_balls', default=default_balls, type=int)
    min_runs  = request.args.get('min_runs',  default=default_runs,  type=int)
    return jsonify(serialize(analyzer.cais_batting(
        min_balls=min_balls, season=season, min_runs=min_runs, competition=_comp())))


@app.route('/api/cais/bowling')
def cais_bowling():
    season = request.args.get('season', type=int)
    default_balls   = 72 if season is None else 24
    default_wickets = 8  if season is None else 3
    min_balls   = request.args.get('min_balls',   default=default_balls,   type=int)
    min_wickets = request.args.get('min_wickets', default=default_wickets, type=int)
    return jsonify(serialize(analyzer.cais_bowling(
        min_balls=min_balls, season=season, min_wickets=min_wickets, competition=_comp())))


if __name__ == '__main__':
    app.run(debug=True, port=5000)
