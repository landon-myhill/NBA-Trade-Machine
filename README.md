# NBA Trade Machine

A mock-trade builder with a **rubric-driven fairness calculator**. The differentiator vs. ESPN/Fanspo/RealGM: a transparent, configurable scoring model that explains *why* a trade is or isn't fair.

## Status

v1 covers stats-based fairness with rubric-driven tiers, draft pick valuation, and team-fit adjustments, plus a **CBA legality checker** (`backend/app/cba/`): 2023-CBA salary-matching brackets, tax-apron team status, and mid-level exception absorption, surfaced as a separate signal alongside fairness rather than folded into the score.

## Architecture

```
backend/   Flask + Pydantic. Serves the API at /api/* AND the built React app
           at / (from frontend/dist). One server, one terminal.
frontend/  React + Vite + TypeScript. `npm run build` outputs to dist/, which
           Flask serves as static assets.
```

### Fairness formula

For each player asset:
```
total = stats_value(player) × tier_multiplier(player) + fit_bonus(player, receiving_team)
```

- **stats_value** — composite of EPM/BPM/VORP, age curve, durability (games played %)
- **tier** — assigned by walking [`rubric.json`](backend/app/data/seed/rubric.json) rules in order; first match wins
- **fit_bonus** — small +/- for positional need and team timeline (contender vs. rebuild)

For draft picks, a Pelton-style curve maps expected pick → value, discounted 3% per future year and trimmed for protections.

Fairness score is `100 × (1 − |gap| / max_side_total)`. Verdict thresholds: 90+ fair, 75+ slightly uneven, 50+ lopsided, <50 very lopsided.

### Customizing the rubric

[`backend/app/data/seed/rubric.json`](backend/app/data/seed/rubric.json) is data, not code. Edit the rules and multipliers, restart the backend, done. Each rule is a set of conditions (min EPM/BPM/VORP/age, requires_all_nba, etc.) — first matching rule (by tier number ascending) wins.

## Setup

Requires Python 3.11+ (tested on 3.13) and Node 18+.

### One-time install

```bash
# backend
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# frontend
cd ../frontend
npm install
```

### Build the frontend, then run Flask

```bash
cd frontend && npm run build       # produces frontend/dist/
cd ../backend && source .venv/bin/activate
flask --app app.main run --port 8000 --debug
```

Open **http://localhost:8000** — Flask serves both the React UI and the `/api/*` endpoints.

> **Heads up:** changes to frontend code require re-running `npm run build`. Flask's `--debug` only hot-reloads Python.

### Optional: dev mode with hot-reload

If you're iterating on the frontend and want hot-reload, run two servers:

```bash
# terminal 1
cd backend && source .venv/bin/activate
flask --app app.main run --port 8000 --debug

# terminal 2
cd frontend && npm run dev         # http://localhost:5173
```

In dev mode, Vite proxies `/api/*` to `http://127.0.0.1:8000`. Open http://localhost:5173.

## Data

`backend/app/data/seed/` ships with a small snapshot (6 teams, ~20 players, ~10 picks) labeled `2025-26`. Numbers are illustrative — replace with your own scraped/curated data. The repository pattern in [`repository.py`](backend/app/data/repository.py) is the swap-in point for a live API later.

## Roadmap

- [x] CBA legality module (salary-matching, tax aprons, MLE absorption) — separate signal from fairness
- [ ] 3+ team trades (need explicit per-asset destinations)
- [ ] Persisted scenarios / shareable trade URLs
- [ ] Real data ingestion (Basketball-Reference scrape or paid API)
- [ ] Rubric editor in the UI

## Testing

```bash
cd backend && pytest -q
```
# NBA-Trade-Machine
