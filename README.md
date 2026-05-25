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
│       ├── agent/
│       │   ├── orchestrator.py  # Agent definition (model, tools, hooks)
│       │   ├── prompt.py        # System prompt / SOP
│       │   └── hooks.py         # Logging, cost tracking, audit trail
│       └── tools/
│           ├── mlb_tools.py     # Read-only MLB API tools (roster, lineups, stats)
│           └── depth_chart_tools.py  # Read/write depth chart tools
├── tests/
├── data/                        # Generated depth charts (JSON, per team)
├── logs/                        # Audit log (JSONL, one entry per event)
├── pyproject.toml
├── README.md
└── run_local.py                 # CLI entry point
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Set your OpenAI API key:

```bash
export OPENAI_API_KEY=sk-...
```

Optionally override the model (defaults to `gpt-5-mini`):

```bash
export OPENAI_MODEL=gpt-5-mini
```

## Run

```bash
python run_local.py
```

The script prompts for a team name and runs the full Research → Write →
Validation cycle, printing per-LLM-call token usage and cost to stdout.
Completed depth charts are saved to `data/<team_id>.json`. All tool inputs
and outputs are appended to `logs/audit.jsonl`.

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

Unit tests mock the MLB API and redirect file I/O to a temp directory, so
they run fully offline.
