from flask import Flask, jsonify, render_template, request
from urllib.parse import unquote
import numpy as np
import pandas as pd
from CricketAnalyser import PSLAnalyzer

app = Flask(__name__, template_folder='.', static_folder='static')
analyzer = PSLAnalyzer('data/psl.csv')

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


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/batting')
def batting():
    season = request.args.get('season', type=int)
    mi = 10 if season is None else 3
    mr = 200
    return jsonify(serialize(analyzer.batting_averages(min_innings=mi, season=season, min_runs=mr)))


@app.route('/api/strike-rates')
def strike_rates():
    season = request.args.get('season', type=int)
    mb = 150 if season is None else 50
    mr = 200
    return jsonify(serialize(analyzer.strike_rate_analysis(min_balls=mb, season=season, min_runs=mr)))


@app.route('/api/bowling')
def bowling():
    season = request.args.get('season', type=int)
    mb = 30 if season is None else 12
    mw = 10
    return jsonify(serialize(analyzer.bowling_stats(min_balls=mb, season=season, min_wickets=mw)))


@app.route('/api/teams')
def teams():
    return jsonify(serialize(analyzer.team_performance()))


@app.route('/api/highest-scores')
def highest_scores():
    return jsonify(serialize(analyzer.highest_scores(top_n=15)))


@app.route('/api/dismissals')
def dismissals():
    return jsonify(serialize(analyzer.dismissal_analysis()))


@app.route('/api/centuries')
def centuries():
    df = analyzer.century_makers()
    counts = (df.groupby('batter').size()
                .reset_index(name='centuries')
                .sort_values('centuries', ascending=False)
                .head(15))
    return jsonify(serialize(counts))


@app.route('/api/players')
def players():
    batters = set(analyzer.df['batter'].dropna().unique())
    bowlers = set(analyzer.df['bowler'].dropna().unique())
    return jsonify(sorted(batters | bowlers))


@app.route('/api/player/<path:name>')
def player_profile(name):
    name = unquote(name)
    return jsonify(_clean(analyzer.player_profile(name)))


@app.route('/api/over-heatmap')
def over_heatmap():
    return jsonify(_clean(analyzer.over_heatmap()))


@app.route('/api/phase-stats')
def phase_stats():
    return jsonify(_clean(analyzer.phase_stats()))


@app.route('/api/matchup')
def matchup():
    return jsonify(_clean(analyzer.matchup_heatmap()))


@app.route('/api/cais/batting')
def cais_batting():
    season = request.args.get('season', type=int)
    min_balls = request.args.get('min_balls', default=50, type=int)
    mr = 200
    return jsonify(serialize(analyzer.cais_batting(min_balls=min_balls, season=season, min_runs=mr)))


@app.route('/api/cais/bowling')
def cais_bowling():
    season = request.args.get('season', type=int)
    min_balls = request.args.get('min_balls', default=30, type=int)
    mw = 10
    return jsonify(serialize(analyzer.cais_bowling(min_balls=min_balls, season=season, min_wickets=mw)))


if __name__ == '__main__':
    app.run(debug=True, port=5000)
