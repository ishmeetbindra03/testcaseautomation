from google.adk.agents.llm_agent import Agent
import os
from .prompts import QA_AGENT_ANALYST_INSTRUCTIONS
from .tools.test_case import create_test_case, get_test_cases_csv


os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"

root_agent = Agent(
    model='gemini-3.5-flash',
    name='root_agent',
    description='The QA Agent Analyst specializes in test case creation',
    instruction=QA_AGENT_ANALYST_INSTRUCTIONS,
    tools=[create_test_case, get_test_cases_csv],
)