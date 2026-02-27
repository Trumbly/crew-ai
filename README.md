# CrewAI Agents

A collection of autonomous multi-agent systems, each exposing an API to handle specific tasks.

Built with [CrewAI](https://github.com/crewAIInc/crewAI) and served via FastAPI.

## Agents

| Agent | Description | Port | Status |
|-------|-------------|------|--------|
| [deep_research](deep_research/) | Competitive intelligence reports for the German DSO market | `8042` | Active |

## Quick Start

Each agent lives in its own directory with a Dockerfile and docker-compose setup.

```bash
cd <agent_directory>
cp .env_template .env   # fill in your API keys
docker compose up --build -d
```

## Adding a New Agent

1. Create a new directory at the repo root
2. Set up the CrewAI crew (`crew.py`, `agents.yaml`, `tasks.yaml`)
3. Wrap it in a FastAPI server
4. Add a `Dockerfile` and `docker-compose.yml`
5. Update the table above
