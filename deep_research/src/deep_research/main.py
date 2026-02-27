#!/usr/bin/env python3
"""
Deep Research Multi-Agent System
================================
A CrewAI-powered competitive intelligence tool for the German DSO market.

Usage:
    # Full competitive deep dive (all 5 agents)
    python -m deep_research.main company "Envelio"

    # Topic research (market + technical + validation + synthesis)
    python -m deep_research.main topic "§14a EnWG steuerbare Verbrauchseinrichtungen"

    # Quick scan (company researcher only)
    python -m deep_research.main quick "ThinkLabs AI"

    # Or via installed entry point:
    deep_research company "Envelio"

Environment variables required (.env file):
    ANTHROPIC_API_KEY=sk-ant-...
    SERPER_API_KEY=...
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def validate_env():
    """Check required environment variables."""
    missing = []
    if not os.getenv("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY")
    if not os.getenv("SERPER_API_KEY"):
        missing.append("SERPER_API_KEY")

    if missing:
        print(f"\n❌ Missing environment variables: {', '.join(missing)}")
        print(f"\nSet them in your .env file at the project root:")
        print(f"  ANTHROPIC_API_KEY=sk-ant-...")
        print(f"  SERPER_API_KEY=...")
        print(f"\nGet a free Serper API key at: https://serper.dev")
        sys.exit(1)


def run_full(target: str):
    """Full competitive deep dive — all 5 agents."""
    from .crew import DeepResearchCrew

    print(f"\n{'='*60}")
    print(f"🔍 COMPETITIVE DEEP DIVE: {target}")
    print(f"{'='*60}\n")

    start = time.time()
    result = DeepResearchCrew().crew().kickoff(inputs={"target": target})
    elapsed = time.time() - start

    _save_result(result, target, "report", elapsed)


def run_topic(topic: str):
    """
    Topic research — skips company_researcher, uses market + technical
    + validation + synthesis only.
    """
    from crewai import Crew, Process

    from .crew import DeepResearchCrew

    print(f"\n{'='*60}")
    print(f"🔍 TOPIC RESEARCH: {topic}")
    print(f"{'='*60}\n")

    dc = DeepResearchCrew()

    # Build a slimmed-down crew without the company researcher
    topic_crew = Crew(
        agents=[
            dc.market_researcher(),
            dc.technical_researcher(),
            dc.validator(),
            dc.synthesizer(),
        ],
        tasks=[
            dc.market_research(),
            dc.technical_research(),
            dc.validation(),
            dc.synthesis(),
        ],
        process=Process.sequential,
        verbose=True,
        memory=True,
        respect_context_window=True,
        max_rpm=20,
    )

    start = time.time()
    result = topic_crew.kickoff(inputs={"target": topic})
    elapsed = time.time() - start

    _save_result(result, topic, "briefing", elapsed)


def run_quick(target: str):
    """Quick scan — company researcher only."""
    from crewai import Crew, Process

    from .crew import DeepResearchCrew

    print(f"\n{'='*60}")
    print(f"⚡ QUICK SCAN: {target}")
    print(f"{'='*60}\n")

    dc = DeepResearchCrew()

    quick_crew = Crew(
        agents=[dc.company_researcher()],
        tasks=[dc.company_research()],
        process=Process.sequential,
        verbose=True,
        max_rpm=20,
    )

    start = time.time()
    result = quick_crew.kickoff(inputs={"target": target})
    elapsed = time.time() - start

    _save_result(result, target, "quickscan", elapsed)


def _save_result(result, target: str, suffix: str, elapsed: float):
    """Save research output to the output/ directory as Markdown AND PDF."""
    output_dir = Path(__file__).resolve().parents[2] / "output"
    output_dir.mkdir(exist_ok=True)

    slug = target.replace(" ", "_").replace("/", "_")[:50]
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"{slug}_{suffix}_{ts}.md"
    filepath = output_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(str(result))

    # Generate PDF for ALL modes
    pdf_path = None
    try:
        from .tools.pdf_report import markdown_to_pdf

        pdf_path = markdown_to_pdf(str(filepath), target)
        print(f"📄 PDF generated: {pdf_path}")
    except Exception as e:
        print(f"⚠️  PDF generation failed: {e}", file=sys.stderr)

    print(f"\n{'='*60}")
    print(f"✅ RESEARCH COMPLETE")
    print(f"{'='*60}")
    print(f"⏱️  Time: {elapsed/60:.1f} minutes")
    print(f"📄 Report: {filepath}")
    if pdf_path:
        print(f"📄 PDF:    {pdf_path}")
    print(f"{'='*60}\n")


def run():
    """Entry point for the CLI (pyproject.toml scripts)."""
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    validate_env()

    mode = sys.argv[1].lower()
    target = " ".join(sys.argv[2:])

    if mode == "company":
        run_full(target)
    elif mode == "topic":
        run_topic(target)
    elif mode == "quick":
        run_quick(target)
    else:
        print(f"❌ Unknown mode: {mode}")
        print(f"   Available modes: company, topic, quick")
        sys.exit(1)


if __name__ == "__main__":
    run()
