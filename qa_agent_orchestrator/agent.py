from google.adk.agents.llm_agent import Agent
from google.adk.tools import AgentTool

from qa_agent_worker.agent import root_agent as qa_worker_agent

from .prompts import QA_ORCHESTRATOR_INSTRUCTIONS

root_agent = Agent(
    model="gemini-3.5-flash",
    name="qa_agent_orchestrator",
    description="Orchestrates QA automation by delegating test cases to QA worker agents.",
    instruction=QA_ORCHESTRATOR_INSTRUCTIONS,
    tools=[AgentTool(qa_worker_agent)],
)
