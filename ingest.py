"""
Cricsheet ingestion — downloads and normalises ball-by-ball CSVs for every
supported T20 competition into the schema used by CricketAnalyser.

Usage:
    python ingest.py            # refresh all competitions
    python ingest.py ipl bbl    # refresh specific ones
    python ingest.py --all-t20is  # include full T20I archive (~1M rows)

Output files (gitignored by default):
    data/{code}.csv           one file per competition
    data/all.csv              combined, with 'competition' column

Raw zips live in data/raw/ and are cached across runs.
"""
from __future__ import annotations
import io
import os
import sys
import zipfile
import urllib.request
from pathlib import Path
from typing import Iterable
import pandas as pd

# ── Competition catalogue ────────────────────────────────────────────────
# code: (display name, cricsheet zip filename, include_by_default)
COMPS = {
    'psl':   ('Pakistan Super League',     'psl_male_csv2.zip',  True),
    'ipl':   ('Indian Premier League',     'ipl_male_csv2.zip',  True),
    'bbl':   ('Big Bash League',           'bbl_male_csv2.zip',  True),
    'cpl':   ('Caribbean Premier League',  'cpl_male_csv2.zip',  True),
    'ntb':   ('Vitality Blast (T20 Blast)','ntb_male_csv2.zip',  True),
    'hnd':   ('The Hundred',               'hnd_male_csv2.zip',  True),
    'sa20':  ('SA20',                      'sat_male_csv2.zip',  True),
    'ilt':   ('International League T20',  'ilt_male_csv2.zip',  True),
    'mlc':   ('Major League Cricket',      'mlc_male_csv2.zip',  True),
    'lpl':   ('Lanka Premier League',      'lpl_male_csv2.zip',  True),
    'bpl':   ('Bangladesh Premier League', 'bpl_male_csv2.zip',  True),
    't20is': ('T20 Internationals',        't20s_male_csv2.zip', True),
    # 'wc' is derived from t20is by filtering event name — see build_wc()
}

DATA_DIR = Path('data')
RAW_DIR  = DATA_DIR / 'raw'
RAW_DIR.mkdir(parents=True, exist_ok=True)

# T20I / World Cup data is dominated by associate-nation fixtures that pollute
# the leaderboards (e.g. Pakistan batter averaging 90 against Germany). Restrict
# T20Is and the World Cup view to games between ICC Full-Member nations.
TEST_NATIONS = {
    'Afghanistan', 'Australia', 'Bangladesh', 'England', 'India', 'Ireland',
    'New Zealand', 'Pakistan', 'South Africa', 'Sri Lanka', 'West Indies',
    'Zimbabwe',
}


def filter_test_nations(df: pd.DataFrame) -> pd.DataFrame:
    """Drop balls where either side isn't a Test-playing nation."""
    if df is None or df.empty:
        return df
    mask = df['batting_team'].isin(TEST_NATIONS) & df['bowling_team'].isin(TEST_NATIONS)
    return df[mask].copy()


# ── Download helpers ────────────────────────────────────────────────────
def download(code: str, zip_name: str) -> Path | None:
    """Download a Cricsheet zip (or use cached copy). Returns path or None."""
    out = RAW_DIR / zip_name
    if out.exists() and out.stat().st_size > 1024:
        return out
    url = f'https://cricsheet.org/downloads/{zip_name}'
    print(f'  ↓ {url}')
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'CricketInsights/1.0'})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        out.write_bytes(data)
        return out
    except Exception as e:
        print(f'  ✗ {code}: {e}')
        return None


# ── Cricsheet → project schema ──────────────────────────────────────────
def _parse_info(text: str) -> dict:
    """Parse a match _info.csv blob into a dict of useful metadata."""
    winner = None
    pom    = None
    umpires: list[str] = []
    event  = None
    match_type = 'regular'
    win_runs = win_wkts = None
    for line in text.splitlines():
        parts = line.split(',', 3)
        if len(parts) < 3 or parts[0] != 'info':
            continue
        k = parts[1]
        v = parts[2]
        if k == 'winner':         winner = v
        elif k == 'player_of_match': pom = v
        elif k == 'umpire':       umpires.append(v)
        elif k == 'event':        event = v
        elif k == 'winner_runs':  win_runs = v
        elif k == 'winner_wickets': win_wkts = v
        elif k == 'match_number' and v and not v.isdigit():
            match_type = v  # "Final", "Qualifier 1" etc.
    win_by = (f'runs {win_runs}' if win_runs else
              f'wickets {win_wkts}' if win_wkts else None)
    return {
        'winner': winner,
        'player_of_match': pom,
        'umpire_1': umpires[0] if umpires else None,
        'umpire_2': umpires[1] if len(umpires) > 1 else None,
        'event':   event,
        'win_by':  win_by,
        'match_type': match_type,
    }


def _pick_extra(row) -> str | None:
    for k in ('wides', 'noballs', 'byes', 'legbyes', 'penalty'):
        v = row.get(k)
        if pd.notna(v) and v not in ('', 0, '0'):
            return k
    return None


def _season_to_int(s):
    """'2018', '2018/19', 2018 → 2018."""
    if pd.isna(s): return None
    try:    return int(str(s)[:4])
    except: return None


def _split_ball(b):
    """Cricsheet ball '0.1' → over=1, ball=1 (we store 1-indexed overs)."""
    try:
        s = str(b)
        over_s, ball_s = s.split('.', 1)
        return int(over_s) + 1, int(ball_s)
    except Exception:
        return None, None


def convert_zip(zip_path: Path, comp_code: str) -> pd.DataFrame:
    """Extract ball-by-ball + info from one Cricsheet zip → project schema DF."""
    print(f'  ⚙  parsing {zip_path.name}…')
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        info_names = [n for n in names if n.endswith('_info.csv')]
        ball_names = [n for n in names
                      if n.endswith('.csv') and not n.endswith('_info.csv')
                      and n != 'README.txt']

        # ── match metadata ──
        meta_rows = []
        for n in info_names:
            mid = n.split('_info.csv')[0]
            try:    mid_int = int(mid)
            except: continue
            with zf.open(n) as f:
                info = _parse_info(f.read().decode('utf-8', errors='ignore'))
            info['match_id'] = mid_int
            meta_rows.append(info)
        meta = pd.DataFrame(meta_rows)

        # ── ball-by-ball (read per-match files, faster than all_matches.csv
        #    when present, and works regardless) ──
        frames = []
        for n in ball_names:
            try:
                with zf.open(n) as f:
                    df = pd.read_csv(f, dtype={'ball': str})
                frames.append(df)
            except Exception:
                continue
        if not frames:
            return pd.DataFrame()
        balls = pd.concat(frames, ignore_index=True)

    # ── transform ──
    over_ball = balls['ball'].apply(_split_ball)
    balls['over'] = over_ball.apply(lambda t: t[0])
    balls['ball_n'] = over_ball.apply(lambda t: t[1])

    out = pd.DataFrame({
        'id':              range(1, len(balls) + 1),
        'match_id':        balls['match_id'],
        'date':            balls['start_date'],
        'season':          balls['season'].apply(_season_to_int),
        'venue':           balls['venue'],
        'inning':          balls['innings'],
        'batting_team':    balls['batting_team'],
        'bowling_team':    balls['bowling_team'],
        'over':            balls['over'],
        'ball':            balls['ball_n'],
        'batter':          balls['striker'],
        'bowler':          balls['bowler'],
        'non_striker':     balls['non_striker'],
        'batsman_runs':    pd.to_numeric(balls['runs_off_bat'], errors='coerce').fillna(0).astype(int),
        'extra_runs':      pd.to_numeric(balls['extras'],       errors='coerce').fillna(0).astype(int),
        'total_runs':      (pd.to_numeric(balls['runs_off_bat'], errors='coerce').fillna(0)
                          + pd.to_numeric(balls['extras'],       errors='coerce').fillna(0)).astype(int),
        'extras_type':     balls.apply(_pick_extra, axis=1),
        'is_wicket':       balls['wicket_type'].notna() & (balls['wicket_type'] != ''),
        'player_dismissed':balls.get('player_dismissed'),
        'dismissal_kind':  balls.get('wicket_type'),
        'fielder':         None,
    })

    # merge match metadata
    if not meta.empty:
        out = out.merge(
            meta[['match_id','winner','win_by','match_type',
                  'player_of_match','umpire_1','umpire_2','event']],
            on='match_id', how='left')
    else:
        for c in ('winner','win_by','match_type','player_of_match',
                  'umpire_1','umpire_2','event'):
            out[c] = None

    out['competition'] = comp_code
    return out


# ── Orchestration ──────────────────────────────────────────────────────
def build_one(code: str, zip_name: str) -> pd.DataFrame | None:
    zp = download(code, zip_name)
    if zp is None:
        return None
    df = convert_zip(zp, code)
    if df.empty:
        return None
    # Restrict T20Is to Test-playing nations (see TEST_NATIONS).
    if code == 't20is':
        before = len(df)
        df = filter_test_nations(df)
        print(f'  ⛉  T20Is Test-nations filter: {before:,} → {len(df):,} rows')
    # Cache per-comp CSV
    out = DATA_DIR / f'{code}.csv'
    df.to_csv(out, index=False)
    print(f'  ✓ {code}: {len(df):,} rows  →  {out}')
    return df


def build_wc(t20is: pd.DataFrame) -> pd.DataFrame:
    """T20 World Cups = T20Is where event contains 'World Cup'.

    T20Is are already Test-nations-filtered by `build_one`, so the WC slice
    inherits that. (In practice WC fixtures already are Test-nation-only,
    but the filter is idempotent and costs nothing.)
    """
    if t20is is None or t20is.empty:
        return pd.DataFrame()
    mask = t20is['event'].fillna('').str.contains('World Cup', case=False, na=False)
    wc = t20is[mask].copy()
    wc['competition'] = 'wc'
    wc = filter_test_nations(wc)
    out = DATA_DIR / 'wc.csv'
    wc.to_csv(out, index=False)
    print(f'  ✓ wc (from T20Is): {len(wc):,} rows  →  {out}')
    return wc


def main(argv: Iterable[str]):
    wanted = [a for a in argv if a in COMPS]
    if not wanted:
        wanted = [c for c, (_, _, default) in COMPS.items() if default]
    print(f'Building: {", ".join(wanted)}')

    pieces = []
    t20is_df = None
    for code in wanted:
        name, zip_name, _ = COMPS[code]
        df = build_one(code, zip_name)
        if df is not None:
            pieces.append(df)
            if code == 't20is':
                t20is_df = df

    # Derive World Cup set from T20Is
    if t20is_df is not None:
        wc = build_wc(t20is_df)
        if not wc.empty:
            pieces.append(wc)

    if pieces:
        combined = pd.concat(pieces, ignore_index=True)
        combined['id'] = range(1, len(combined) + 1)
        out = DATA_DIR / 'all.csv'
        combined.to_csv(out, index=False)
        print(f'\n✅  combined {len(combined):,} rows  →  {out}')
        # Summary
        print('\nPer competition:')
        for c, g in combined.groupby('competition'):
            print(f'  {c:6}  {len(g):>9,} rows   '
                  f'{g["match_id"].nunique():>5,} matches   '
                  f'seasons {int(g["season"].min())}–{int(g["season"].max())}')


if __name__ == '__main__':
    main(sys.argv[1:])
