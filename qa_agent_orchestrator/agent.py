# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
