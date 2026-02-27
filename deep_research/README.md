# 🔍 Deep Research — Multi-Agent Competitive Intelligence

CrewAI-powered multi-agent system for the German DSO market with PDF report generation.

## Setup

```bash
# Edit .env with your API keys
# Then:
crewai install
```

## Usage

### Via CrewAI (default target)
```bash
crewai run                          # researches RESEARCH_TARGET from .env (default: Envelio)
```

### Via direct invocation (custom target)
```bash
uv run deep_research "Envelio"
uv run deep_research "ThinkLabs AI"
uv run deep_research "§14a EnWG steuerbare Verbrauchseinrichtungen"
```

### Via orchestrator script (with email delivery)
```bash
python orchestrate.py "Envelio"
python orchestrate.py "Envelio" --email max@example.com
python orchestrate.py "Envelio" --output /tmp/reports/
```

## Output

Reports are saved to `output/`:
- `output/report.md` — Raw markdown report
- `output/{target}_report_{timestamp}.pdf` — Professional PDF with confidence ratings

## Architecture

```
Layer 1 — RESEARCH
  ├── Company Researcher  → profile, team, funding, customers
  ├── Market Researcher   → landscape, competitors, trends, gaps
  └── Technical Researcher → tech stack, APIs, standards

Layer 2 — VALIDATION
  └── Validator → cross-reference, confidence scoring, gaps

Layer 3 — SYNTHESIS → PDF
  └── Synthesizer → CI report with SWOT → PDF generation
```
