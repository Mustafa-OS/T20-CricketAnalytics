import pandas as pd
import numpy as np
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

class PSLAnalyzer:
    """Pakistan Super League Cricket Statistics Analyzer"""
    
    def __init__(self, csv_path):
        """Initialize analyzer with CSV file"""
        self.df = pd.read_csv(csv_path)
        self.legal = self.df[self.df["extras_type"] != 'wides'].copy()
        
    def batting_averages(self, min_innings=5):
        """Calculate batting averages and aggregate stats"""
        innings = self.legal.groupby(['batter', 'match_id', 'batting_team'])['batsman_runs'].sum().reset_index()
        innings.columns = ['batter', 'match_id', 'batting_team', 'runs']
        
        stats = self.legal.groupby('batter').agg({
            'batsman_runs': 'sum',
            'match_id': 'nunique',
            'is_wicket': 'sum'
        }).reset_index()
        stats.columns = ['batter', 'total_runs', 'matches', 'dismissals']
        
        stats['average'] = stats.apply(
            lambda r: round(r['total_runs'] / r['dismissals'], 2) if r['dismissals'] > 0 else np.inf,
            axis=1
        )
        balls_faced = self.legal.groupby('batter').size().rename('balls_faced')
        stats = stats.merge(balls_faced, on='batter', how='left')
        stats['SR'] = (stats['total_runs'] / stats['balls_faced'] * 100).round(2)
        
        return stats[stats['matches'] >= min_innings].sort_values('total_runs', ascending=False)
    
    def highest_scores(self, top_n=20):
        """Get highest individual scores"""
        innings = self.legal.groupby(['batter', 'match_id', 'batting_team', 'date'])['batsman_runs'].sum().reset_index()
        innings.columns = ['batter', 'match_id', 'batting_team', 'date', 'runs']
        
        highest = innings.nlargest(top_n, 'runs')[['batter', 'batting_team', 'date', 'runs']]
        return highest.reset_index(drop=True)
    
    def bowling_stats(self, min_balls=30):
        """Calculate bowling statistics"""
        legal_balls = self.legal[self.legal['bowler'].notna()]
        
        stats = legal_balls.groupby('bowler').agg({
            'total_runs': 'sum',
            'is_wicket': 'sum',
            'match_id': 'nunique',
            'id': 'count'  # total balls
        }).reset_index()
        stats.columns = ['bowler', 'runs_conceded', 'wickets', 'matches', 'balls']
        
        stats['economy'] = (stats['runs_conceded'] / (stats['balls'] / 6)).round(2)
        stats['avg'] = (stats['runs_conceded'] / (stats['wickets'] + 0.001)).round(2)
        
        return stats[stats['balls'] >= min_balls].sort_values('wickets', ascending=False)
    
    def strike_rate_analysis(self, min_balls=100):
        """Analyze strike rates for batters"""
        batter_data = self.legal.groupby('batter').agg({
            'batsman_runs': 'sum',
            'id': 'count',
            'match_id': 'nunique'
        }).reset_index()
        batter_data.columns = ['batter', 'runs', 'balls', 'matches']
        
        batter_data['SR'] = (batter_data['runs'] / batter_data['balls'] * 100).round(2)
        batter_data = batter_data[batter_data['balls'] >= min_balls]
        
        return batter_data.sort_values('SR', ascending=False)
    
    def team_performance(self):
        """Analyze team-level stats"""
        team_stats = self.df.groupby('batting_team').agg({
            'match_id': 'nunique',
            'bowling_team': 'count'
        }).reset_index()
        team_stats.columns = ['team', 'matches_played', 'balls_faced']
        
        # Calculate wins — deduplicate to one row per match before counting
        match_results = self.df[['match_id', 'batting_team', 'winner']].drop_duplicates()
        wins = match_results[match_results['batting_team'] == match_results['winner']].groupby('batting_team').size().reset_index(name='wins')
        team_stats = team_stats.merge(wins, left_on='team', right_on='batting_team', how='left')
        team_stats['wins'] = team_stats['wins'].fillna(0).astype(int)
        team_stats['win_rate'] = (team_stats['wins'] / team_stats['matches_played'] * 100).round(2)
        
        return team_stats[['team', 'matches_played', 'wins', 'win_rate']].sort_values('wins', ascending=False)
    
    def season_breakdown(self, player=None, bowler=None):
        """Analyze performance by season"""
        if player:
            data = self.legal[self.legal['batter'] == player].groupby('season').agg({
                'batsman_runs': 'sum',
                'match_id': 'nunique',
                'is_wicket': 'sum'
            }).reset_index()
            data.columns = ['season', 'runs', 'matches', 'dismissals']
            data['avg'] = (data['runs'] / (data['dismissals'] + 0.001)).round(2)
            return data.sort_values('season')
        
        if bowler:
            legal_balls = self.legal[self.legal['bowler'].notna()]
            data = legal_balls[legal_balls['bowler'] == bowler].groupby('season').agg({
                'total_runs': 'sum',
                'is_wicket': 'sum',
                'id': 'count'
            }).reset_index()
            data.columns = ['season', 'runs', 'wickets', 'balls']
            data['economy'] = (data['runs'] / (data['balls'] / 6)).round(2)
            return data.sort_values('season')
    
    def head_to_head(self, batter, bowler):
        """Get head-to-head stats between batter and bowler"""
        h2h = self.legal[(self.legal['batter'] == batter) & (self.legal['bowler'] == bowler)]
        
        if len(h2h) == 0:
            return None
        
        stats = {
            'balls_faced': len(h2h),
            'runs_scored': h2h['batsman_runs'].sum(),
            'dismissals': h2h['is_wicket'].sum(),
            'sr': (h2h['batsman_runs'].sum() / len(h2h) * 100),
            'avg': (h2h['batsman_runs'].sum() / (h2h['is_wicket'].sum() + 0.001))
        }
        return {k: round(v, 2) for k, v in stats.items()}
    
    def venue_analysis(self, venue=None, top_venues=10):
        """Analyze performance by venue"""
        if venue:
            venue_data = self.legal[self.legal['venue'] == venue].groupby('batter').agg({
                'batsman_runs': 'sum',
                'match_id': 'nunique'
            }).reset_index()
            venue_data.columns = ['batter', 'runs', 'matches']
            return venue_data.sort_values('runs', ascending=False).head(20)
        
        else:
            venues = self.df.groupby('venue').agg({
                'match_id': 'nunique'
            }).reset_index()
            venues.columns = ['venue', 'matches']
            return venues.sort_values('matches', ascending=False).head(top_venues)
    
    def partnership_analysis(self, min_runs=50):
        """Analyze partnership runs"""
        # Group by match and inning to get partnerships
        partnerships = self.legal.groupby(['match_id', 'inning', 'batter', 'non_striker']).agg({
            'batsman_runs': 'sum'
        }).reset_index()
        partnerships.columns = ['match_id', 'inning', 'batter', 'non_striker', 'partnership_runs']
        
        partnerships = partnerships[partnerships['partnership_runs'] >= min_runs]
        partnerships = partnerships.sort_values('partnership_runs', ascending=False)
        
        return partnerships.head(20)
    
    def player_comparison(self, players):
        """Compare multiple players"""
        batting_stats = self.batting_averages(min_innings=0)
        return batting_stats[batting_stats['batter'].isin(players)][
            ['batter', 'total_runs', 'matches', 'dismissals', 'average', 'SR']
        ].sort_values('total_runs', ascending=False)
    
    def dismissal_analysis(self):
        """Analyze dismissal patterns"""
        dismissals = self.legal[self.legal['is_wicket'] == 1].copy()
        
        stats = dismissals.groupby('dismissal_kind').size().reset_index(name='count')
        stats['percentage'] = (stats['count'] / dismissals.shape[0] * 100).round(2)
        
        return stats.sort_values('count', ascending=False)
    
    def century_makers(self):
        """Find all centuries (100+ runs) in an inning"""
        innings = self.legal.groupby(['batter', 'match_id', 'batting_team', 'date']).agg({
            'batsman_runs': 'sum'
        }).reset_index()
        innings.columns = ['batter', 'match_id', 'batting_team', 'date', 'runs']
        
        centuries = innings[innings['runs'] >= 100].sort_values('runs', ascending=False)
        centuries['milestone'] = centuries['runs'].apply(lambda x: 'Century' if x < 150 else 'Ton+' if x < 200 else '200+')
        
        return centuries[['batter', 'batting_team', 'date', 'runs', 'milestone']]
    
    def player_profile(self, name):
        """Complete player profile: batting stats, innings list, bowling stats, seasonal trends."""
        result = {'name': name}

        # ── Batting ──────────────────────────────────────────────────────
        bat = self.legal[self.legal['batter'] == name]
        if len(bat) >= 5:
            inn = (bat.groupby(['match_id', 'date'])
                      .agg(runs=('batsman_runs', 'sum'), dismissed=('is_wicket', 'max'))
                      .reset_index()
                      .sort_values('date')
                      .reset_index(drop=True))
            inn['inning_num'] = range(1, len(inn) + 1)

            total_runs = int(bat['batsman_runs'].sum())
            total_balls = len(bat)
            dismissals  = int(inn['dismissed'].sum())

            result['batting'] = {
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

            seasons = (bat.groupby('season')
                          .agg(runs=('batsman_runs', 'sum'),
                               matches=('match_id', 'nunique'),
                               dismissals=('is_wicket', 'sum'))
                          .reset_index())
            seasons['avg'] = seasons.apply(
                lambda r: round(r['runs'] / r['dismissals'], 2) if r['dismissals'] > 0 else None,
                axis=1)
            result['batting_seasons'] = seasons.to_dict(orient='records')
            result['innings_list']    = inn.to_dict(orient='records')

        # ── Bowling ──────────────────────────────────────────────────────
        bowl = self.legal[self.legal['bowler'] == name]
        if len(bowl) >= 30:
            runs_c  = int(bowl['total_runs'].sum())
            wickets = int(bowl['is_wicket'].sum())
            balls   = len(bowl)

            result['bowling'] = {
                'wickets':       wickets,
                'matches':       int(bowl['match_id'].nunique()),
                'balls':         balls,
                'runs_conceded': runs_c,
                'economy':       round(runs_c / (balls / 6), 2) if balls else None,
                'average':       round(runs_c / wickets, 2) if wickets else None,
            }

            bseas = (bowl.groupby('season')
                         .agg(runs=('total_runs', 'sum'),
                              wickets=('is_wicket', 'sum'),
                              balls=('id', 'count'),
                              matches=('match_id', 'nunique'))
                         .reset_index())
            bseas['economy'] = (bseas['runs'] / (bseas['balls'] / 6)).round(2)
            result['bowling_seasons'] = bseas.to_dict(orient='records')

        return result

    def over_heatmap(self):
        """Average run rate and wickets-per-match for every over, split by season."""
        data = self.legal.copy()
        if data['over'].min() == 0:          # normalise to 1-indexed
            data['over'] = data['over'] + 1

        agg = (data.groupby(['season', 'over'])
                   .agg(runs=('batsman_runs', 'sum'),
                        wickets=('is_wicket', 'sum'),
                        balls=('id', 'count'),
                        matches=('match_id', 'nunique'))
                   .reset_index())
        agg['run_rate']      = (agg['runs'] / (agg['balls'] / 6)).round(2)
        agg['wkt_per_match'] = (agg['wickets'] / agg['matches']).round(3)
        return agg.to_dict(orient='records')

    def phase_stats(self):
        """Batting SR and bowling economy split by Powerplay / Middle / Death."""
        data = self.legal.copy()
        if data['over'].min() == 0:
            data['over'] = data['over'] + 1

        data['phase'] = np.select(
            [data['over'] <= 6, data['over'] >= 16],
            ['Powerplay (1-6)', 'Death (16-20)'],
            default='Middle (7-15)'
        )

        batting = (data.groupby(['batting_team', 'phase'])
                       .agg(runs=('batsman_runs', 'sum'),
                            balls=('id', 'count'),
                            wickets=('is_wicket', 'sum'))
                       .reset_index())
        batting['sr'] = (batting['runs'] / batting['balls'] * 100).round(2)

        bowling = (data.groupby(['bowling_team', 'phase'])
                       .agg(runs=('total_runs', 'sum'),
                            balls=('id', 'count'))
                       .reset_index())
        bowling['economy'] = (bowling['runs'] / (bowling['balls'] / 6)).round(2)

        return {
            'batting': batting.to_dict(orient='records'),
            'bowling': bowling.to_dict(orient='records'),
        }

    def matchup_heatmap(self, top_n=12, min_balls=6):
        """Strike-rate matrix: top-N batters vs top-N bowlers."""
        top_bat  = (self.legal.groupby('batter')['batsman_runs']
                              .sum().nlargest(top_n).index.tolist())
        top_bowl = self.bowling_stats(min_balls=30).head(top_n)['bowler'].tolist()

        h2h = (self.legal[
            self.legal['batter'].isin(top_bat) & self.legal['bowler'].isin(top_bowl)
        ].groupby(['batter', 'bowler'])
         .agg(runs=('batsman_runs', 'sum'),
              balls=('id', 'count'),
              dismissals=('is_wicket', 'sum'))
         .reset_index())

        h2h = h2h[h2h['balls'] >= min_balls].copy()
        h2h['sr']  = (h2h['runs'] / h2h['balls'] * 100).round(1)
        h2h['avg'] = h2h.apply(
            lambda r: round(r['runs'] / r['dismissals'], 1) if r['dismissals'] > 0 else None,
            axis=1)
        return {
            'batters':  top_bat,
            'bowlers':  top_bowl,
            'matchups': h2h.to_dict(orient='records'),
        }

    def export_to_csv(self, data, filename):
        """Export dataframe to CSV"""
        data.to_csv(filename, index=False)
        print(f"Exported to {filename}")


if __name__ == "__main__":
    # Initialize analyzer
    analyzer = PSLAnalyzer('data/psl.csv')
    
    print("="*60)
    print("PSL CRICKET STATS ANALYZER")
    print("="*60)
    
    # 1. Batting averages
    print("\n1. TOP BATTERS BY TOTAL RUNS")
    print("-" * 60)
    batting = analyzer.batting_averages(min_innings=10)
    print(batting[['batter', 'total_runs', 'matches', 'average', 'SR']].head(15))
    
    # 2. Highest scores
    print("\n2. HIGHEST INDIVIDUAL SCORES")
    print("-" * 60)
    highest = analyzer.highest_scores(top_n=10)
    print(highest)
    
    # 3. Bowling stats
    print("\n3. TOP BOWLERS BY WICKETS")
    print("-" * 60)
    bowling = analyzer.bowling_stats(min_balls=30)
    print(bowling[['bowler', 'wickets', 'matches', 'economy', 'avg']].head(15))
    
    # 4. Strike rates
    print("\n4. STRIKE RATE LEADERS (min 100 balls)")
    print("-" * 60)
    sr = analyzer.strike_rate_analysis(min_balls=100)
    print(sr[['batter', 'SR', 'runs', 'balls', 'matches']].head(15))
    
    # 5. Team performance
    print("\n5. TEAM PERFORMANCE")
    print("-" * 60)
    teams = analyzer.team_performance()
    print(teams)
    
    # 6. Century makers
    print("\n6. ALL CENTURIES")
    print("-" * 60)
    centuries = analyzer.century_makers()
    print(centuries.head(15))
    
    # 7. Dismissal analysis
    print("\n7. DISMISSAL METHODS")
    print("-" * 60)
    dismissals = analyzer.dismissal_analysis()
    print(dismissals)
    
    # 8. Player-specific analysis
    print("\n8. BABAR AZAM - SEASON BREAKDOWN")
    print("-" * 60)
    babar_seasons = analyzer.season_breakdown(player="Babar Azam")
    print(babar_seasons)
    
    # 9. Head-to-head
    print("\n9. HEAD-TO-HEAD: BABAR AZAM vs SHAHEEN AFRIDI")
    print("-" * 60)
    h2h = analyzer.head_to_head("Babar Azam", "Shaheen Shah Afridi")
    if h2h:
        for k, v in h2h.items():
            print(f"  {k}: {v}")
    
    # 10. Top venues
    print("\n10. TOP VENUES BY MATCHES")
    print("-" * 60)
    venues = analyzer.venue_analysis(top_venues=10)
    print(venues)
    
    # 11. Compare players
    print("\n11. COMPARE TOP 5 BATTERS")
    print("-" * 60)
    comparison = analyzer.player_comparison(['Babar Azam', 'Mohammad Rizwan', 'Fakhar Zaman', 'Shoaib Malik', 'RR Rossouw'])
    print(comparison)
    
    # 12. Partnerships
    print("\n12. BEST PARTNERSHIPS (50+ runs)")
    print("-" * 60)
    partnerships = analyzer.partnership_analysis(min_runs=50)
    print(partnerships.head(15))