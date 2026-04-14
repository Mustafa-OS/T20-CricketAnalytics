"""
Run this once before pushing to GitHub to export all static JSON files.
    python precompute.py
Outputs go to static/data/ — commit that folder alongside index.html.
"""
import json
import os
import numpy as np
from CricketAnalyser import PSLAnalyzer

OUT = os.path.join('static', 'data')
os.makedirs(OUT, exist_ok=True)

analyzer = PSLAnalyzer('data/psl.csv')


def _clean(obj):
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


def serialize(df):
    records = df.replace([np.inf, -np.inf], np.nan).to_dict(orient='records')
    return [_clean(r) for r in records]


def save(name, data):
    path = os.path.join(OUT, f'{name}.json')
    with open(path, 'w') as f:
        json.dump(data, f, separators=(',', ':'))
    print(f'  wrote {path}')


print('Generating static JSON files...')

save('batting',       serialize(analyzer.batting_averages(min_innings=10).head(20)))
save('strike-rates',  serialize(analyzer.strike_rate_analysis(min_balls=150).head(20)))
save('bowling',       serialize(analyzer.bowling_stats(min_balls=30).head(25)))
save('teams',         serialize(analyzer.team_performance()))
save('highest-scores',serialize(analyzer.highest_scores(top_n=15)))
save('dismissals',    serialize(analyzer.dismissal_analysis()))
save('players',       sorted(
    set(analyzer.df['batter'].dropna().unique()) |
    set(analyzer.df['bowler'].dropna().unique())
))
save('over-heatmap',  _clean(analyzer.over_heatmap()))
save('phase-stats',   _clean(analyzer.phase_stats()))
save('matchup',       _clean(analyzer.matchup_heatmap()))

centuries_df = analyzer.century_makers()
counts = (centuries_df.groupby('batter').size()
            .reset_index(name='centuries')
            .sort_values('centuries', ascending=False)
            .head(15))
save('centuries', serialize(counts))

print(f'\nDone — {len(os.listdir(OUT))} files in {OUT}/')
print('Commit the static/ folder and push to GitHub.')
