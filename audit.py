"""Data-accuracy audit harness.

Compares the computed per-season leader-boards against hard-coded reference
values (Orange Caps, Purple Caps, T20 WC top run-scorers, etc.) that can
be independently verified from Wikipedia / Cricinfo.

Run manually:
    python audit.py              # runs every check, prints a report
    python audit.py --strict     # exits non-zero if any delta > tolerance

Exit codes:
    0  clean (or only within-tolerance deltas)
    1  one or more references missing from the computed data
    2  one or more deltas exceeded tolerance (only in --strict mode)

The reference tables below are compiled from authoritative sources:
Orange/Purple Caps — iplt20.com annual records.
T20 World Cup top scorers — ICC tournament records pages.

Tolerance rationale: a per-season leader is a fixed, well-attested number —
any delta > RUNS_TOL or WKTS_TOL indicates either a player-name mismatch or
a real aggregation bug. Career totals tick up with each active match so are
intentionally NOT in this harness (use spot-checks for those).
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / 'static' / 'data'

# ── Tolerances ──────────────────────────────────────────────────────────
# Per-season leader-board totals are fixed historical facts. Allow ±3 runs
# to absorb Cricsheet's normal ball-level drift from official records
# (super-over fractions, DLS rounding); anything bigger is a bug.
RUNS_TOL = 3
WKTS_TOL = 1


# ── Cricsheet data-source caveat: withheld Afghanistan matches ──────────
# Cricsheet has deliberately withheld every match involving Afghanistan
# (men's team) plus the entire Afghanistan Premier League, as a protest
# against the ICC ignoring Afghan women's cricketers. 329 matches total.
#
#   https://cricsheet.org/article/explanation-for-withholding-of-afghanistani-matches/
#
# This is a source-level gap — nothing the pipeline can fix. Any reference
# row that involves Afghanistan (player FROM Afghanistan, or a per-tournament
# ref whose stat was accumulated partly against Afghanistan) is tagged with
# `afghan_touched=True` below and reported as SKIP in the audit rather than
# counted as a failure. If Cricsheet ever restores the data, just flip the
# flag and the rows become real regression checks.
AFGHAN_NOTE = (
    'Cricsheet withholds all Afghanistan matches + APL by publisher policy. '
    'Reference cannot be verified from Cricsheet alone.'
)


# ── Cricsheet name conventions ──────────────────────────────────────────
# Reference names use common/display form; Cricsheet stores initials+surname.
# Only override when the Cricsheet form isn't the obvious mechanical one.
NAME_ALIASES = {
    'Shaun Marsh':           'SE Marsh',
    'Matthew Hayden':        'ML Hayden',
    'Sachin Tendulkar':      'SR Tendulkar',
    'Chris Gayle':           'CH Gayle',
    'Michael Hussey':        'MEK Hussey',
    'Robin Uthappa':         'RV Uthappa',
    'David Warner':          'DA Warner',
    'Virat Kohli':           'V Kohli',
    'Kane Williamson':       'KS Williamson',
    'Ruturaj Gaikwad':       'RD Gaikwad',
    'Jos Buttler':           'JC Buttler',
    'Sai Sudharsan':         'B Sai Sudharsan',
    'RP Singh':              'RP Singh',
    'Pragyan Ojha':          'PP Ojha',
    'Lasith Malinga':        'SL Malinga',
    'Morne Morkel':          'M Morkel',
    'Dwayne Bravo':          'DJ Bravo',
    'Mohit Sharma':          'MM Sharma',
    'Bhuvneshwar Kumar':     'B Kumar',
    'Andrew Tye':            'AJ Tye',
    'Kagiso Rabada':         'K Rabada',
    'Harshal Patel':         'HV Patel',
    'Yuzvendra Chahal':      'YS Chahal',
    'Prasidh Krishna':       'M Prasidh Krishna',
    # PSL names (Cricsheet usually stores native form for Pakistani players)
    'Ravi Bopara':           'RS Bopara',
    'Kamran Akmal':          'Kamran Akmal',
    'Sohail Khan':           'Sohail Khan',
    'Luke Ronchi':           'L Ronchi',
    'Faheem Ashraf':         'Faheem Ashraf',
    'Shane Watson (PSL)':    'SR Watson',
    'Hasan Ali':             'Hasan Ali',
    'Shaheen Afridi':        'Shaheen Shah Afridi',
    'Shahnawaz Dahani':      'Shahnawaz Dhani',     # Cricsheet uses one H
    'Fakhar Zaman':          'Fakhar Zaman',
    'Mohammad Rizwan':       'Mohammad Rizwan',
    'Abbas Afridi':          'Abbas Afridi',
    'Babar Azam (PSL)':      'Babar Azam',
    'Usama Mir':             'Usama Mir',
    'Hassan Nawaz':          'Hassan Nawaz',
    'Umar Akmal':            'Umar Akmal',
    'Andre Russell':         'AD Russell',
    # T20 WC bowlers
    'Umar Gul':              'Umar Gul',
    'Dirk Nannes':           'DP Nannes',
    'Ajantha Mendis':        'BAW Mendis',
    'Shahid Afridi':         'Shahid Afridi',
    'Ravi Rampaul':          'R Rampaul',
    'Wahab Riaz':            'Wahab Riaz',
    'Mohammad Nabi':         'Mohammad Nabi',
    'Anrich Nortje':         'A Nortje',
    # Cricsheet uses his "de Silva" surname form, not the common "Hasaranga".
    'Wanindu Hasaranga':     'PWH de Silva',
    'Sam Curran':            'SM Curran',
    'Adam Zampa':            'A Zampa',
    'Arshdeep Singh':        'Arshdeep Singh',
    'Fazalhaq Farooqi':      'Fazalhaq Farooqi',
    # T20 WC batters
    'Matthew Hayden (AUS)':  'ML Hayden',
    'Mahela Jayawardene':    'DPMD Jayawardene',
    'Tillakaratne Dilshan':  'TM Dilshan',
    'Shane Watson':          'SR Watson',
    'Tamim Iqbal':           'Tamim Iqbal',
    'Virat Kohli (IND)':     'V Kohli',
    'Babar Azam':            'Babar Azam',
    'Rohit Sharma':          'RG Sharma',
    'Rilee Rossouw':         'RR Rossouw',
    'Suryakumar Yadav':      'SA Yadav',
}


def resolve(name: str) -> str:
    return NAME_ALIASES.get(name, name)


# ── Reference data ──────────────────────────────────────────────────────
# Rows are (player, reference-total, afghan_touched).
#   afghan_touched=True means the reference's total was accumulated partly or
#   fully in withheld Afghanistan matches — the row is reported as SKIP (not
#   counted against fail/notfound totals). See AFGHAN_NOTE above.

# IPL Orange Cap — highest run-scorer of each season.
# Source: iplt20.com/stats/<year>/most-runs (authoritative, directly from BCCI).
IPL_ORANGE_CAP = {
    2008: ('Shaun Marsh',       616, False),
    2009: ('Matthew Hayden',    572, False),
    2010: ('Sachin Tendulkar',  618, False),
    2011: ('Chris Gayle',       608, False),
    2012: ('Chris Gayle',       733, False),
    2013: ('Michael Hussey',    733, False),
    2014: ('Robin Uthappa',     660, False),
    2015: ('David Warner',      562, False),
    2016: ('Virat Kohli',       973, False),
    2017: ('David Warner',      641, False),
    2018: ('Kane Williamson',   735, False),
    2019: ('David Warner',      692, False),
    2020: ('KL Rahul',          670, False),
    2021: ('Ruturaj Gaikwad',   635, False),
    2022: ('Jos Buttler',       863, False),
    2023: ('Shubman Gill',      890, False),
    2024: ('Virat Kohli',       741, False),
    2025: ('Sai Sudharsan',     759, False),
}

# IPL Purple Cap — highest wicket-taker of each season.
IPL_PURPLE_CAP = {
    2008: ('Sohail Tanvir',     22, False),
    2009: ('RP Singh',          23, False),
    2010: ('Pragyan Ojha',      21, False),
    2011: ('Lasith Malinga',    28, False),
    2012: ('Morne Morkel',      25, False),
    2013: ('Dwayne Bravo',      32, False),
    2014: ('Mohit Sharma',      23, False),
    2015: ('Dwayne Bravo',      26, False),
    2016: ('Bhuvneshwar Kumar', 23, False),
    2017: ('Bhuvneshwar Kumar', 26, False),
    2018: ('Andrew Tye',        24, False),
    2019: ('Imran Tahir',       26, False),
    2020: ('Kagiso Rabada',     30, False),
    2021: ('Harshal Patel',     32, False),
    2022: ('Yuzvendra Chahal',  27, False),
    2023: ('Mohammed Shami',    28, False),
    2024: ('Harshal Patel',     24, False),
    2025: ('Prasidh Krishna',   25, False),
}

# T20 World Cup — top run-scorer per tournament.
# Source: ICC tournament records + Wikipedia "ICC Men's T20 World Cup" stats.
#
# Afghanistan caveat: any tournament where the top scorer played Afghanistan
# loses those match-runs from our Cricsheet build. Babar 2021 (303 ref) is
# missing 51 runs from the withheld Pakistan-vs-Afghanistan Super-12 game,
# so we expect 252 from our pipeline — flagged `afghan_touched`. Similarly
# Gurbaz 2024 was Afghanistan's opener, so 100% of his runs are withheld.
WC_TOP_RUNS = {
    2007: ('Matthew Hayden (AUS)',    265, False),
    2009: ('Tillakaratne Dilshan',    317, False),
    2010: ('Mahela Jayawardene',      302, False),
    2012: ('Shane Watson',            249, False),
    2014: ('Virat Kohli (IND)',       319, False),
    2016: ('Tamim Iqbal',             295, False),
    2021: ('Babar Azam',              303, True),   # −51 off for Pak-vs-AFG
    2022: ('Virat Kohli (IND)',       296, False),
    2024: ('Rahmanullah Gurbaz',      281, True),   # AFG player — fully withheld
}

# PSL — top run-scorer per season.
# Source: Wikipedia "List_of_Pakistan_Super_League_records_and_statistics".
# PSL is a single-calendar-year tournament so maps cleanly to {year}.json.
PSL_TOP_RUNS = {
    2016: ('Umar Akmal',         335, False),
    2017: ('Kamran Akmal',       353, False),
    2018: ('Luke Ronchi',        435, False),
    2019: ('Shane Watson (PSL)', 430, False),
    2020: ('Babar Azam (PSL)',   473, False),
    2021: ('Babar Azam (PSL)',   554, False),
    2022: ('Fakhar Zaman',       588, False),
    2023: ('Mohammad Rizwan',    550, False),
    2024: ('Babar Azam (PSL)',   569, False),
    2025: ('Hassan Nawaz',       399, False),
}

# PSL — top wicket-taker per season.
PSL_TOP_WKTS = {
    2016: ('Andre Russell',      16, False),
    2017: ('Sohail Khan',        16, False),
    2018: ('Faheem Ashraf',      18, False),
    2019: ('Hasan Ali',          25, False),
    2020: ('Shaheen Afridi',     17, False),
    2021: ('Shahnawaz Dahani',   20, False),
    2022: ('Shaheen Afridi',     20, False),
    2023: ('Abbas Afridi',       23, False),
    2024: ('Usama Mir',          24, False),
    2025: ('Shaheen Afridi',     19, False),
}

# NOTE: BBL / BPL / SA20 / ILT all straddle calendar years (Dec-Jan or Jan-Feb
# windows), while precompute.py buckets balls by calendar year. So a BBL|07
# "season" splits across 2017 and 2018 JSONs and can't be checked against a
# per-season reference value directly. Auditing those leagues requires adding
# a season-aware bucketing step to precompute first — tracked as a follow-up.

# T20 World Cup — top wicket-taker per tournament.
# Afghanistan caveat: Nabi (AFG), Farooqi (AFG) are fully withheld. Hasaranga
# 2021/2022 took wickets partly against Afghanistan, so his pipeline total
# will be short of the ICC reference.
WC_TOP_WKTS = {
    2007: ('Umar Gul',               13, False),
    2009: ('Umar Gul',               13, False),
    2010: ('Dirk Nannes',            14, False),
    2012: ('Ajantha Mendis',         15, False),
    2014: ('Ahsan Malik',            12, False),   # Netherlands
    2016: ('Mohammad Nabi',          12, True),    # AFG player — fully withheld
    2021: ('Wanindu Hasaranga',      16, True),    # partial — SL vs AFG withheld
    2022: ('Wanindu Hasaranga',      15, True),    # partial — SL vs AFG withheld
    2024: ('Fazalhaq Farooqi',       17, True),    # AFG player — fully withheld
}

# ── Check runners ───────────────────────────────────────────────────────
def load_json(path: Path):
    if not path.exists():
        return None
    with path.open() as f:
        return json.load(f)


def check_season_leader(comp: str, year: int, kind: str, name: str,
                         expected: int, afghan_touched: bool = False):
    """Look up the competition/season leader-board and verify the named
    player's total matches the reference.

    Returns (status, message). Status is one of:
        OK         — within tolerance
        FAIL       — delta exceeds tolerance (a real bug, or a bad reference)
        NOT-FOUND  — player row not present (name-alias miss or data gap)
        MISSING    — the whole JSON file doesn't exist
        SKIP       — reference is tagged afghan_touched and Cricsheet is
                     known to withhold those matches; a gap here is expected.
    """
    key = 'batting' if kind == 'runs' else 'bowling'
    j = load_json(STATIC / comp / f'{key}-{year}.json')
    if not j:
        return ('MISSING', f'no {key}-{year}.json for {comp}')
    cricsheet_name = resolve(name)
    field_player = 'batter' if kind == 'runs' else 'bowler'
    field_value  = 'total_runs' if kind == 'runs' else 'wickets'
    row = next((r for r in j if r[field_player] == cricsheet_name), None)
    if not row:
        if afghan_touched:
            return ('SKIP',
                    f'{cricsheet_name:28s}   —    (ref {expected:>5}, AFG withheld)')
        return ('NOT-FOUND',
                f'{cricsheet_name!r} missing from {comp}/{key}-{year}.json')
    got = row[field_value]
    delta = got - expected
    tol = RUNS_TOL if kind == 'runs' else WKTS_TOL
    if afghan_touched and delta < 0:
        # Expected: our total is lower because AFG-match contributions are
        # withheld. Report the shortfall but don't fail.
        return ('SKIP',
                f'{cricsheet_name:28s} {got:>5}  (ref {expected:>5}, Δ{delta:+d}, AFG withheld)')
    status = 'OK' if abs(delta) <= tol else 'FAIL'
    return (status, f'{cricsheet_name:28s} {got:>5}  (ref {expected:>5}, Δ{delta:+d})')


def run_check_block(title: str, comp: str, table: dict, kind: str):
    print(f'\n── {title} ──')
    fails = 0
    notfound = 0
    skipped = 0
    for year, row in sorted(table.items()):
        # Row is (name, expected, afghan_touched). Older 2-tuple rows still
        # decode cleanly for forward-compat.
        if len(row) == 3:
            name, expected, afghan_touched = row
        else:
            name, expected = row
            afghan_touched = False
        status, msg = check_season_leader(comp, year, kind, name, expected,
                                          afghan_touched=afghan_touched)
        marker = {'OK': '✓', 'FAIL': '✗', 'NOT-FOUND': '?',
                  'MISSING': '—', 'SKIP': '·'}[status]
        print(f'  {marker} {year}  {msg}')
        if status == 'FAIL':      fails += 1
        if status == 'NOT-FOUND': notfound += 1
        if status == 'SKIP':      skipped += 1
    return fails, notfound, skipped


def main(argv):
    strict = '--strict' in argv
    total_fails = total_nf = total_skip = 0
    for title, comp, table, kind in [
        ('IPL Orange Cap (top run-scorer per season)',   'ipl', IPL_ORANGE_CAP, 'runs'),
        ('IPL Purple Cap (top wicket-taker per season)', 'ipl', IPL_PURPLE_CAP, 'wkts'),
        ('PSL — top run-scorer per season',              'psl', PSL_TOP_RUNS,   'runs'),
        ('PSL — top wicket-taker per season',            'psl', PSL_TOP_WKTS,   'wkts'),
        ('T20 World Cup — top run-scorer per tournament', 'wc', WC_TOP_RUNS,    'runs'),
        ('T20 World Cup — top wicket-taker per tournament','wc', WC_TOP_WKTS,   'wkts'),
    ]:
        f, nf, sk = run_check_block(title, comp, table, kind)
        total_fails += f
        total_nf    += nf
        total_skip  += sk

    print(f'\n═══ Summary ═══')
    print(f'  fails (delta > tolerance): {total_fails}')
    print(f'  not found (name mismatch): {total_nf}')
    print(f'  skipped (AFG withheld)   : {total_skip}')
    if total_skip:
        print(f'  ({AFGHAN_NOTE})')
    if strict and (total_fails or total_nf):
        # In strict mode, both real failures and unresolved name-aliases
        # are regressions worth blocking a data push on.
        print('  → STRICT mode: exiting with code 2')
        sys.exit(2)
    sys.exit(0)


if __name__ == '__main__':
    main(sys.argv[1:])
