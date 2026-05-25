# DepthChartAgent

AI-powered MLB depth chart generator. Uses OpenAI (`gpt-5-mini` by default) to
produce a ranked, explainable depth chart for any MLB team.

The agent follows a three-phase SOP — **Research → Write → Validation** — to
ensure every generated chart is grounded in live roster and lineup data from
the MLB Stats API.

## Project structure

```
DepthChartAgent/
├── src/
│   └── depth_chart_agent/
│       ├── mlb_client.py        # MLB Stats API client (unauthenticated)
│       ├── storage.py           # Shared chart file I/O (read/write, atomic)
│       ├── logging_config.py    # Shared logging setup (file + console)
│       ├── agent/
│       │   ├── orchestrator.py  # Agent definition (model, tools, hooks)
│       │   ├── prompt.py        # System prompt / SOP
│       │   └── hooks.py         # Per-LLM-call cost tracking, audit trail
│       ├── api/
│       │   ├── app.py           # FastAPI app and routes
│       │   ├── auth.py          # API key authentication
│       │   ├── models.py        # Pydantic response models
│       │   └── refresh.py       # Redis-backed refresh job manager
│       └── tools/
│           ├── mlb_tools.py     # Read-only MLB API tools (roster, lineups, stats)
│           └── depth_chart_tools.py  # Read/write depth chart tools
├── tests/
├── data/                        # Generated depth charts (JSON, per team)
├── logs/
│   ├── app.log                  # API and agent lifecycle events (rotating)
│   └── audit.jsonl              # Structured agent tool I/O and LLM calls
├── pyproject.toml
├── README.md
├── run_local.py                 # CLI entry point
└── run_api.py                   # API server entry point
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Create a `.env` file in the project root:

```
OPENAI_API_KEY=sk-...

# Optional overrides
OPENAI_MODEL=gpt-5-mini
DEPTH_CHART_API_KEY=<secret>    # required for force-refresh endpoint
REDIS_URL=redis://localhost:6379
CACHE_TTL_SECONDS=86400
LOG_LEVEL=INFO
```

Generate a value for `DEPTH_CHART_API_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Run

### CLI

```bash
python run_local.py
```

Prompts for a team name and runs the full Research → Write → Validation cycle,
printing per-LLM-call token usage and cost to stdout. Completed depth charts
are saved to `data/<team_id>.json`.

### API server

Requires Redis:

```bash
brew install redis && brew services start redis   # macOS
```

Then:

```bash
python run_api.py
```

The server starts on `http://localhost:8000`. Interactive API docs are available
at `http://localhost:8000/docs`.

## API

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/depth-chart/{team}` | None | Returns chart; triggers background refresh if stale |
| `GET` | `/refresh/{refresh_id}` | None | Poll refresh job status |
| `POST` | `/depth-chart/{team}/refresh` | API key | Force refresh regardless of TTL |

`{team}` accepts a full name, city, or abbreviation (e.g. `angels`, `BOS`, `red%20sox`).

**Cache behaviour** — `cache_status` in the response indicates freshness:

| Value | Meaning |
|-------|---------|
| `fresh` | Chart is within TTL; no refresh in progress |
| `stale` | Chart is expired; background refresh just triggered |
| `refreshing` | Chart is expired; refresh already in progress |
| `initializing` | No chart exists yet; refresh triggered |

When a refresh is triggered the response includes a `refresh` object with a
`refresh_id`. Poll `GET /refresh/{refresh_id}` to track progress; the response
includes the completed chart once the job finishes.

## Logging

Two log outputs are written on every run:

**`logs/app.log`** — human-readable API and agent lifecycle events, written by
Python's `logging` module. Rotates at 10 MB (5 backups). Level controlled by
`LOG_LEVEL` env var (default `INFO`). Covers:
- Server start/shutdown
- Every request: team, resolved team_id, cache_status, refresh_id
- Refresh job state transitions: `pending → running → complete / failed`
- Agent run start, completion, and errors
- Auth failures and team-not-found warnings

**`logs/audit.jsonl`** — structured JSON, one entry per line. Written by the
agent hooks. Covers every LLM call (token counts, cost), every tool input and
output, and all agent reasoning blocks. Useful for debugging agent behaviour
and replaying runs.

## How it works

1. **Research** — The agent calls the MLB Stats API to fetch the active roster,
   full 40-man roster (including IL), recent transactions, and recent game
   lineups. It derives pitcher classifications (rotation vs. bullpen role) from
   actual innings-pitched data before writing anything.

2. **Write** — The agent initializes or updates the stored depth chart using
   batch write tools. All nine field positions, the rotation (SP1–SP5), and
   every bullpen pitcher are written in as few tool calls as possible.

3. **Validation** — `validate_depth_chart` checks that every active-roster
   player appears exactly once, no inactive player is charted, every position
   has a 1st-string assignment, and pitchers are correctly classified. The
   agent loops back to research if violations are found.

## Tools

### MLB (read-only)

| Tool | Description |
|------|-------------|
| `get_team_id` | Resolves a team name / abbreviation to a numeric team ID |
| `get_active_roster` | 26-man active roster |
| `get_roster` | Full 40-man roster including IL status and notes |
| `get_transactions` | Recent IL placements, recalls, options, trades |
| `get_recent_lineups` | Batting orders and pitching usage from recent games |
| `get_player_stats` | Season or recent-form stats for a single player |

### Depth chart (read/write)

| Tool | Description |
|------|-------------|
| `read_depth_chart` | Returns the stored chart or `null` |
| `initialize_depth_chart` | Creates a blank chart; fetches active roster internally |
| `update_active_roster_ids` | Syncs active roster without wiping assignments |
| `get_depth_at_position` | Returns current entries at a single position |
| `set_position_players` | Batch-upsert one or more position-player entries |
| `remove_position_player` | Remove a player from one position |
| `set_rotation_slots` | Batch-upsert one or more rotation slots (SP1–SP5) |
| `remove_rotation_slot` | Clear a single rotation slot |
| `set_bullpen_roles` | Batch-upsert one or more bullpen entries |
| `remove_bullpen_player` | Remove a pitcher from the bullpen |
| `remove_player_everywhere` | Remove a player from all sections |
| `validate_depth_chart` | Validate and return violations |

## Tests

```bash
pytest                        # unit tests (no network)
pytest -m integration         # integration tests (hit real APIs)
```

Unit tests mock the MLB API, Redis, and redirect file I/O to a temp directory,
so they run fully offline.
