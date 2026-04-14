# PSL Cricket Analytics Dashboard

An interactive analytics dashboard for Pakistan Super League (PSL) cricket data, built with Python, Flask, and Plotly.js.

![PSL Logo](static/psl_logo.png)

## Features

- **Batting** — Top run scorers, strike rate leaders, average vs strike rate bubble chart
- **Bowling** — Top wicket takers, best economy rates, wickets vs economy scatter
- **Teams** — Franchise wins and win rate comparison
- **Records** — Highest individual scores, century makers
- **Dismissals** — Dismissal method breakdown (pie + bar)
- **Player Search** — Search any player and view their full profile: career stats, season-by-season breakdown, and innings history chart

## Tech Stack

- **Backend**: Python, Pandas, Flask
- **Frontend**: HTML, JavaScript, Plotly.js
- **Data**: Ball-by-ball PSL CSV (~66,000 deliveries)

## Getting Started

### Prerequisites

```bash
pip install flask pandas numpy
```

### Run Locally

```bash
python app.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser.

### Static Mode (no server needed)

You can also open `index.html` directly in a browser. Most tabs work using precomputed JSON files in `static/data/`. Player Search requires the Flask server.

## Project Structure

```
.
├── index.html           # Dashboard UI
├── app.py               # Flask server + API routes
├── CricketAnalyser.py   # Core analytics engine (PSLAnalyzer class)
├── precompute.py        # Generates static JSON for serverless hosting
├── data/
│   └── psl.csv          # Ball-by-ball PSL dataset
└── static/
    ├── psl_logo.png     # PSL logo
    └── data/            # Precomputed JSON files
```

## Updating Data

1. Replace `data/psl.csv` with the updated file (same column format)
2. Regenerate static JSON:
   ```bash
   python precompute.py
   ```
3. Restart Flask if running locally, or commit and push for GitHub Pages

## Deployment on GitHub Pages

1. Push the repo to GitHub
2. Go to Settings > Pages > set source to `main` branch, root `/`
3. The dashboard will be live at `https://<username>.github.io/PSL-CricketAnalytics/`
