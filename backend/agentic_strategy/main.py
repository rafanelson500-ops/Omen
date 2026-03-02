from typing import Callable, Optional
from crewai import Crew, Process
from agentic_strategy.agents import agents
from agentic_strategy.tasks import tasks

def get_result(on_task_complete: Optional[Callable] = None):
    crew = Crew(
        agents=agents,
        tasks=tasks,
        process=Process.sequential,   # tasks run in order, each agent sees prior outputs
        verbose=True,
        task_callback=on_task_complete,
    )
    return crew.kickoff()