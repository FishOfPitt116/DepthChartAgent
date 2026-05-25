# DepthChartAgent

AI-powered MLB depth chart generator. Uses OpenAI (GPT-4o-mini) to produce
a ranked, explainable depth chart for any MLB team.

## Project structure

```
DepthChartAgent/
├── src/
│   └── depth_chart_agent/
│       └── agent/
│           ├── prompt.py        # System prompt
│           └── orchestrator.py  # Agent definition
├── tests/
├── pyproject.toml
├── README.md
└── run_local.py     # Local test runner CLI
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Run

```bash
python run_local.py
```

## Tests

```bash
pytest                        # unit tests (no network)
pytest -m integration         # integration tests (hit real APIs)
```
