import os

from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents.llm_agent import Agent

from .cxas_tool import generate_session_id, send_message_to_cx_agent
from .prompts import QA_AGENT_INSTRUCTIONS

# set region
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_CLOUD_PROJECT"] = "ces-ccai-demo"

root_agent = Agent(
    model="gemini-3.5-flash",
    name="qa_agent_worker",
    description="An QA agent that executes test cases",
    instruction=QA_AGENT_INSTRUCTIONS,
    tools=[generate_session_id, send_message_to_cx_agent],
)

a2a_app = to_a2a(root_agent, port=8000)
