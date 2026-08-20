---
name: web_app_development
description: Triggers when the user is working on the Flask application, UI, frontend, CSS, or HTML files.
---

# Web App & Frontend Conventions

Adapted from `T20_Win_Probability_Model`'s frontend conventions for this project's Flask API (`app.py`, Phase 10) and vanilla-JS SPA (`static/`, Phase 11).

## Flask App Conventions

- Solved grids, count indices, and the fitted edge model are dict-based registries keyed on the shipped `RuleSet` keys (`GRIDS`, `INDICES`, `EDGE_MODELS`), each loaded once at startup from `data/strategy/`, `data/indices/`, `data/baselines/edge_model_baseline.json` — adding a new shipped ruleset is a one-line addition to `SHIPPED_RULESETS`, not a copy-pasted code block. Mirrors T20's `MODELS`/`FIRST_INNINGS_MODELS` registry pattern keyed on `ACTIVE_FORMATS`.
- **Game state lives server-side, keyed by session id — never round-tripped through the browser.** The shoe composition must stay on the server; the client holds a session id and a redacted view. A shoe that round-trips through the client can desynchronise the count from the actual deal, silently corrupting every downstream number (advice, count, stake).
- API routes return JSON.
- `/api/simulate` must be bounded (cap hands per request, or stream/paginate) — an unbounded simulate endpoint on the 7.7GB dev machine is a self-inflicted denial of service.

## Frontend Conventions

- Single-page app with tab navigation: Play / Strategy Grid / Counting / Bankroll / Simulator (see the build plan's Phase 11 for full tab specs).
- Vanilla JS — no framework.
- Glassmorphism dark-mode design, matching T20's aesthetic.
- API calls via `fetch()` to the Flask backend on `localhost:5000`.
- Every EV/edge figure shown in the UI carries its margin or standard error where one exists — no bare "the answer is X" without the "how close was the alternative" or "how confident are we" context. This mirrors the counting/simulation no-bare-point-estimates rule but applies specifically to what's rendered.
- The Bankroll and Play tabs must state plainly, near the recommendation, that this is a simulation with real variance and that casinos may refuse service to counters — this belongs in the UI itself, not only the README.
