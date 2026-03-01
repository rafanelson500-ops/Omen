"""
CrewAI Demo — Cheese Trading Analysis Crew
===========================================
A multi-agent crew that analyses a cheese trade opportunity.

Agents
------
1. Market Analyst   — researches current market conditions
2. Risk Manager     — evaluates downside risks
3. Trade Strategist — synthesises both reports into a final recommendation

Setup
-----
Add your OpenAI key to backend/.env:
    OPENAI_API_KEY=sk-...

Then run:
    source venv/bin/activate
    python main.py
"""

import os
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process, LLM
from agents import agents
from tasks import tasks
# ── Load environment ──────────────────────────────────────────────────────────
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key or api_key == "your-openai-api-key-here":
    raise EnvironmentError(
        "OPENAI_API_KEY is not set.\n"
        "Add it to backend/.env:  OPENAI_API_KEY=sk-..."
    )

crew = Crew(
    agents=agents,
    tasks=tasks,
    process=Process.sequential,   # tasks run in order, each agent sees prior outputs
    verbose=True,
)

if __name__ == "__main__":
    result = crew.kickoff()