import pandas as pd
df = pd.read_csv('data/psl.csv')

legal = df[df["extras_type"] != 'wides']

innings = legal.groupby(['batter', 'match_id'])['batsman_runs'].sum().reset_index()
innings.columns = ['batter', 'match_id', 'innings_runs']

highest = innings.groupby("batter")['innings_runs'].max().reset_index()
highest.columns = ['batter', 'highest_score']
print(highest.sort_values('highest_score', ascending=False).head(10))


