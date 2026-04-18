"""
Precompute static JSON for every supported competition.

Output layout:
    static/data/competitions.json              manifest
    static/data/{comp}/<endpoint>.json          career view
    static/data/{comp}/<endpoint>-{season}.json per season
    static/data/{comp}/players.json             search list

Run this once before pushing to GitHub. The Flask app can serve everything
dynamically; this file powers the static GitHub Pages build.

    python precompute.py             # everything
    python precompute.py ipl psl     # only named competitions
"""
import json
import os
import sys
import numpy as np
from CricketAnalyser import CricketAnalyser

ROOT = os.path.join('static', 'data')
os.makedirs(ROOT, exist_ok=True)

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


def save(path, data):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as f:
        json.dump(data, f, separators=(',', ':'))
    print(f'  wrote {full}')


def build_comp(a: CricketAnalyser, code: str):
    dir_ = code
    print(f'\n── {code} ──')
    # Career views
    save(f'{dir_}/batting.json',
         serialize(a.batting_averages(min_innings=10, min_runs=200, competition=code)))
    save(f'{dir_}/strike-rates.json',
         serialize(a.strike_rate_analysis(min_balls=150, min_runs=200, competition=code)))
    save(f'{dir_}/bowling.json',
         serialize(a.bowling_stats(min_balls=30, min_wickets=10, competition=code)))
    save(f'{dir_}/teams.json',
         serialize(a.team_performance(competition=code)))
    save(f'{dir_}/highest-scores.json',
         serialize(a.highest_scores(top_n=15, competition=code)))
    save(f'{dir_}/dismissals.json',
         serialize(a.dismissal_analysis(competition=code)))
    save(f'{dir_}/over-heatmap.json',
         _clean(a.over_heatmap(competition=code)))
    save(f'{dir_}/phase-stats.json',
         _clean(a.phase_stats(competition=code)))
    try:
        save(f'{dir_}/matchup.json',
             _clean(a.matchup_heatmap(competition=code)))
    except Exception as e:
        print(f'  (matchup skipped: {e})')

    save(f'{dir_}/cais-batting.json',
         serialize(a.cais_batting(min_balls=50, min_runs=200, competition=code)))
    save(f'{dir_}/cais-bowling.json',
         serialize(a.cais_bowling(min_balls=30, min_wickets=10, competition=code)))

    # Centuries count per batter
    cent = a.century_makers(competition=code)
    counts = (cent.groupby('batter').size()
                   .reset_index(name='centuries')
                   .sort_values('centuries', ascending=False).head(15))
    save(f'{dir_}/centuries.json', serialize(counts))

    # Players list for search
    df = a.df[a.df['competition'] == code]
    batters = set(df['batter'].dropna().unique())
    bowlers = set(df['bowler'].dropna().unique())
    save(f'{dir_}/players.json', sorted(batters | bowlers))

    # Per-season variants
    seasons = sorted(df['season'].dropna().unique().tolist())
    save(f'{dir_}/seasons.json', [int(s) for s in seasons])
    for s in seasons:
        si = int(s)
        try:
            save(f'{dir_}/cais-batting-{si}.json',
                 serialize(a.cais_batting(min_balls=20, min_runs=200, season=si, competition=code)))
            save(f'{dir_}/cais-bowling-{si}.json',
                 serialize(a.cais_bowling(min_balls=12, min_wickets=10, season=si, competition=code)))
            save(f'{dir_}/batting-{si}.json',
                 serialize(a.batting_averages(min_innings=3, min_runs=200, season=si, competition=code)))
            save(f'{dir_}/strike-rates-{si}.json',
                 serialize(a.strike_rate_analysis(min_balls=50, min_runs=200, season=si, competition=code)))
            save(f'{dir_}/bowling-{si}.json',
                 serialize(a.bowling_stats(min_balls=12, min_wickets=10, season=si, competition=code)))
        except Exception as e:
            print(f'  season {si} skipped: {e}')


def main(codes):
    analyzer = CricketAnalyser('data/all.csv')
    available = sorted(analyzer.df['competition'].unique().tolist())
    if not codes:
        codes = [c for c in COMP_NAMES if c in available]

    manifest = []
    for code in codes:
        if code not in available:
            print(f'skip {code}: no data')
            continue
        sub = analyzer.df[analyzer.df['competition'] == code]
        seasons = sorted(sub['season'].dropna().unique().tolist())
        manifest.append({
            'code': code,
            'name': COMP_NAMES.get(code, code.upper()),
            'matches': int(sub['match_id'].nunique()),
            'rows': int(len(sub)),
            'first_season': int(seasons[0]) if seasons else None,
            'last_season':  int(seasons[-1]) if seasons else None,
        })
        build_comp(analyzer, code)

    save('competitions.json', manifest)
    print(f'\n✅ Done — manifest covers {len(manifest)} competitions')


if __name__ == '__main__':
    main(sys.argv[1:])
