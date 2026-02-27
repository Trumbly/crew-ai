import os
from typing import List

from dotenv import load_dotenv

load_dotenv()

from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task
from crewai_tools import SerperDevTool

from crewai import LLM, Agent, Crew, Process, Task
from deep_research.tools.custom_tool import claim_validator


def get_llm() -> LLM:
    return LLM(
        model="anthropic/claude-sonnet-4-5-20250929",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        max_tokens=4096,
        temperature=0.1,
        num_retries=5,  # litellm retry config
        request_timeout=120,
    )


# Common agent kwargs for Anthropic compatibility
AGENT_DEFAULTS = dict(
    llm=None,  # set per-agent via get_llm()
    use_system_prompt=False,  # Required: Anthropic + CrewAI system prompt bug
    max_retry_limit=5,  # Retry on intermittent None responses
    respect_context_window=True,
    verbose=True,
)


@CrewBase
class DeepResearchCrew:
    """Multi-agent competitive intelligence crew for the German DSO market."""

    agents: List[BaseAgent]
    tasks: List[Task]

    @agent
    def company_researcher(self) -> Agent:
        return Agent(
            config=self.agents_config["company_researcher"],
            tools=[SerperDevTool()],
            llm=get_llm(),
            use_system_prompt=False,
            max_retry_limit=5,
            max_iter=6,
            verbose=True,
        )

    @agent
    def market_researcher(self) -> Agent:
        return Agent(
            config=self.agents_config["market_researcher"],
            tools=[SerperDevTool()],
            llm=get_llm(),
            use_system_prompt=False,
            max_retry_limit=5,
            max_iter=6,
            verbose=True,
        )

    @agent
    def technical_researcher(self) -> Agent:
        return Agent(
            config=self.agents_config["technical_researcher"],
            tools=[SerperDevTool()],
            llm=get_llm(),
            use_system_prompt=False,
            max_retry_limit=5,
            max_iter=6,
            verbose=True,
        )

    @agent
    def validator(self) -> Agent:
        return Agent(
            config=self.agents_config["validator"],
            tools=[SerperDevTool(), claim_validator],
            llm=get_llm(),
            use_system_prompt=False,
            max_retry_limit=5,
            max_iter=4,
            verbose=True,
        )

    @agent
    def synthesizer(self) -> Agent:
        return Agent(
            config=self.agents_config["synthesizer"],
            tools=[],
            llm=get_llm(),
            use_system_prompt=False,
            max_retry_limit=5,
            max_iter=3,
            verbose=True,
        )

    @task
    def company_research(self) -> Task:
        return Task(config=self.tasks_config["company_research"])

    @task
    def market_research(self) -> Task:
        return Task(config=self.tasks_config["market_research"])

    @task
    def technical_research(self) -> Task:
        return Task(config=self.tasks_config["technical_research"])

    @task
    def validation(self) -> Task:
        return Task(config=self.tasks_config["validation"])

    @task
    def synthesis(self) -> Task:
        return Task(
            config=self.tasks_config["synthesis"],
            output_file="output/report.md",
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
            memory=False,
            respect_context_window=True,
            max_rpm=1,
        )
