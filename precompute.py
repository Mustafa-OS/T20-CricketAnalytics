"""
Precompute static JSON for every supported competition.

Output layout:
    static/data/competitions.json                    manifest
    static/data/{comp}/<endpoint>.json               career view
    static/data/{comp}/<endpoint>-{season}.json      per season
    static/data/{comp}/players.json                  search list (names)
    static/data/{comp}/player-index.json             name → slug map
    static/data/{comp}/player/<slug>.json            per-player profile

Run this once before pushing to GitHub. The Flask app can serve everything
dynamically; this file powers the static GitHub Pages build.

    python precompute.py             # everything
    python precompute.py ipl psl     # only named competitions
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
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


def _slugify(name, taken):
    """Turn 'MDKJ Perera' → 'mdkj_perera'. Appends _N on collision."""
    s = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_') or 'x'
    if s in taken:
        i = 2
        while f'{s}_{i}' in taken:
            i += 1
        s = f'{s}_{i}'
    taken.add(s)
    return s


def build_player_profiles(a: CricketAnalyser, code: str):
    """
    Bake a per-player profile JSON for the static/Pages build.

    Each file mirrors what CricketAnalyser.player_profile() returns on the
    Flask path (batting + bowling splits, per-season bars, innings list,
    CAIS rank). Shared per-competition work — CAIS tables, groupbys — is
    done ONCE and reused across players, so the whole pass is cheap.
    """
    dir_ = code
    scope = a.legal[a.legal['competition'] == code]
    if not len(scope):
        return

    # ── 1. Career CAIS tables, computed once ─────────────────────────
    try:
        cb = a.cais_batting(min_balls=50, min_runs=200, competition=code)
        cb_total = len(cb)
        cb_rank = {
            r.batter: {'score': float(r.cais),
                       'rank':  int(getattr(r, 'rank')),
                       'total': cb_total}
            for r in cb.itertuples()
        }
    except Exception as e:
        print(f'  (cais_batting skipped: {e})')
        cb_rank = {}

    try:
        cbw = a.cais_bowling(min_balls=30, min_wickets=10, competition=code)
        cbw_total = len(cbw)
        cbw_rank = {
            r.bowler: {'score': float(r.cais),
                       'rank':  int(getattr(r, 'rank')),
                       'total': cbw_total}
            for r in cbw.itertuples()
        }
    except Exception as e:
        print(f'  (cais_bowling skipped: {e})')
        cbw_rank = {}

    # ── 2. Group by batter / bowler once — O(N) instead of O(players × N)
    bat_groups  = {name: g for name, g in scope.groupby('batter')}
    bowl_groups = {name: g for name, g in scope.groupby('bowler')}

    names = sorted(set(bat_groups) | set(bowl_groups))
    taken, index = set(), {}
    built = 0

    for name in names:
        if not isinstance(name, str) or not name:
            continue
        profile = {'name': name, 'competition': code}

        # ── Batting block ─────────────────────────────────────────────
        bat = bat_groups.get(name)
        if bat is not None and len(bat) >= 5:
            inn = (bat.groupby(['match_id', 'date'])
                      .agg(runs=('batsman_runs', 'sum'),
                           dismissed=('is_wicket', 'max'))
                      .reset_index()
                      .sort_values('date')
                      .reset_index(drop=True))
            inn['inning_num'] = range(1, len(inn) + 1)

            total_runs  = int(bat['batsman_runs'].sum())
            total_balls = len(bat)
            dismissals  = int(inn['dismissed'].sum())

            profile['batting'] = {
                'total_runs': total_runs,
                'matches':    int(bat['match_id'].nunique()),
                'innings':    len(inn),
                'dismissals': dismissals,
                'average':    round(total_runs / dismissals, 2) if dismissals else None,
                'sr':         round(total_runs / total_balls * 100, 2) if total_balls else None,
                'highest':    int(inn['runs'].max()),
                'fifties':    int(((inn['runs'] >= 50) & (inn['runs'] < 100)).sum()),
                'hundreds':   int((inn['runs'] >= 100).sum()),
            }
            # Slim the innings list to the fields the chart actually reads —
            # drops match_id / date bloat (saves ~40% of per-player payload).
            profile['innings_list'] = [
                {'inning_num': int(r['inning_num']),
                 'runs':       int(r['runs']),
                 'dismissed':  bool(r['dismissed'])}
                for r in inn.to_dict(orient='records')
            ]

            seasons = (bat.groupby('season')
                          .agg(runs=('batsman_runs', 'sum'),
                               matches=('match_id', 'nunique'),
                               dismissals=('is_wicket', 'sum'))
                          .reset_index())
            seasons['avg'] = seasons.apply(
                lambda r: round(r['runs'] / r['dismissals'], 2)
                          if r['dismissals'] > 0 else None,
                axis=1)
            profile['batting_seasons'] = seasons.to_dict(orient='records')

        # ── Bowling block ─────────────────────────────────────────────
        bowl = bowl_groups.get(name)
        if bowl is not None and len(bowl) >= 30:
            # Cricinfo-correct attribution: bowler_runs excludes byes/legbyes/
            # penalty; is_bowler_wicket excludes run-outs and retired-outs;
            # legal_delivery excludes wides and no-balls from the over count.
            runs_c       = int(bowl['bowler_runs'].sum())
            wickets      = int(bowl['is_bowler_wicket'].sum())
            legal_balls  = int(bowl['legal_delivery'].sum())

            profile['bowling'] = {
                'wickets':       wickets,
                'matches':       int(bowl['match_id'].nunique()),
                'balls':         legal_balls,
                'runs_conceded': runs_c,
                'economy':       round(runs_c / (legal_balls / 6), 2) if legal_balls else None,
                'average':       round(runs_c / wickets, 2) if wickets else None,
            }

            bseas = (bowl.groupby('season')
                         .agg(runs=   ('bowler_runs',      'sum'),
                              wickets=('is_bowler_wicket', 'sum'),
                              balls=  ('legal_delivery',   'sum'),
                              matches=('match_id',         'nunique'))
                         .reset_index())
            bseas['economy'] = (bseas['runs'] / (bseas['balls'] / 6)).round(2)
            profile['bowling_seasons'] = bseas.to_dict(orient='records')

        # Skip players who don't meet either threshold — nothing to show.
        if 'batting' not in profile and 'bowling' not in profile:
            continue

        # Attach CAIS rank where the player is on the leaderboard.
        if name in cb_rank:
            profile['cais_batting'] = cb_rank[name]
        if name in cbw_rank:
            profile['cais_bowling'] = cbw_rank[name]

        slug = _slugify(name, taken)
        index[name] = slug
        # Write without the chatty per-file log line — otherwise the console
        # gets flooded (~500 lines per competition). Count is summarised below.
        full = os.path.join(ROOT, f'{dir_}/player/{slug}.json')
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w') as f:
            json.dump(_clean(profile), f, separators=(',', ':'))
        built += 1

    save(f'{dir_}/player-index.json', index)
    print(f'  wrote {built} player profiles → {dir_}/player/')


def build_comp(a: CricketAnalyser, code: str):
    dir_ = code
    print(f'\n── {code} ──')
    # Career views — moderate thresholds keep leaderboards meaningful without
    # wiping short-window tournaments like SA20 / ILT20 / MLC / WC.
    save(f'{dir_}/batting.json',
         serialize(a.batting_averages(min_innings=8, min_runs=250, competition=code)))
    save(f'{dir_}/strike-rates.json',
         serialize(a.strike_rate_analysis(min_balls=150, min_runs=150, competition=code)))
    save(f'{dir_}/bowling.json',
         serialize(a.bowling_stats(min_balls=72, min_wickets=8, competition=code)))
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
         serialize(a.cais_batting(min_balls=100, min_runs=250, competition=code)))
    save(f'{dir_}/cais-bowling.json',
         serialize(a.cais_bowling(min_balls=72, min_wickets=8, competition=code)))

    # Centuries count per batter — preserve team for client-side filtering.
    cent = a.century_makers(competition=code)
    counts = (cent.groupby('batter')
                   .agg(centuries=('runs', 'size'),
                        team=('batting_team',
                              lambda s: s.mode().iat[0] if len(s.mode()) else None))
                   .reset_index()
                   .sort_values('centuries', ascending=False).head(15))
    save(f'{dir_}/centuries.json', serialize(counts))

    # Players list for search
    df = a.df[a.df['competition'] == code]
    batters = set(df['batter'].dropna().unique())
    bowlers = set(df['bowler'].dropna().unique())
    save(f'{dir_}/players.json', sorted(batters | bowlers))

    # Per-player profile JSONs — feeds the search-result modal on the static
    # build. Shares CAIS tables + groupbys so the whole pass stays cheap.
    build_player_profiles(a, code)

    # Per-season variants
    seasons = sorted(df['season'].dropna().unique().tolist())
    save(f'{dir_}/seasons.json', [int(s) for s in seasons])
    for s in seasons:
        si = int(s)
        try:
            # Per-season thresholds are loose enough to catch short WC / SA20
            # group-stage exits (3 innings) without drowning the board in noise.
            save(f'{dir_}/cais-batting-{si}.json',
                 serialize(a.cais_batting(min_balls=40, min_runs=60, season=si, competition=code)))
            save(f'{dir_}/cais-bowling-{si}.json',
                 serialize(a.cais_bowling(min_balls=24, min_wickets=3, season=si, competition=code)))
            save(f'{dir_}/batting-{si}.json',
                 serialize(a.batting_averages(min_innings=3, min_runs=60, season=si, competition=code)))
            save(f'{dir_}/strike-rates-{si}.json',
                 serialize(a.strike_rate_analysis(min_balls=45, min_runs=60, season=si, competition=code)))
            save(f'{dir_}/bowling-{si}.json',
                 serialize(a.bowling_stats(min_balls=24, min_wickets=3, season=si, competition=code)))
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
        # Freshness by competition — latest ball-by-ball date we have.
        # Nightly refresh bumps this whenever cricsheet adds completed matches.
        latest_match = None
        if 'date' in sub.columns:
            try:
                latest_match = sub['date'].dropna().max()
                latest_match = (latest_match.isoformat()
                                if hasattr(latest_match, 'isoformat')
                                else str(latest_match))
            except Exception:
                latest_match = None
        manifest.append({
            'code': code,
            'name': COMP_NAMES.get(code, code.upper()),
            'matches': int(sub['match_id'].nunique()),
            'rows': int(len(sub)),
            'first_season': int(seasons[0]) if seasons else None,
            'last_season':  int(seasons[-1]) if seasons else None,
            'latest_match': latest_match,
        })
        build_comp(analyzer, code)

    # Wrap the manifest with top-level freshness metadata. The UI shows
    # last_updated under the logo, and the nightly GH Actions workflow
    # bumps it every run. latest_match is the newest actual match date
    # in the raw data (some days cricsheet has nothing to publish).
    latest_match_overall = None
    try:
        if 'date' in analyzer.df.columns:
            m = analyzer.df['date'].dropna().max()
            latest_match_overall = (m.isoformat()
                                    if hasattr(m, 'isoformat') else str(m))
    except Exception:
        pass

    payload = {
        'last_updated': datetime.now(timezone.utc)
                                .replace(microsecond=0)
                                .isoformat(),
        'latest_match': latest_match_overall,
        'competitions': manifest,
    }
    save('competitions.json', payload)
    print(f'\n✅ Done — manifest covers {len(manifest)} competitions')
    print(f'   last_updated = {payload["last_updated"]}')
    print(f'   latest_match = {latest_match_overall}')


if __name__ == '__main__':
    main(sys.argv[1:])
