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

import json
import os
import warnings
from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.llm_agent import Agent
from google.adk.models import LlmRequest, LlmResponse
from google.genai import types

from .prompts import QA_AGENT_INSTRUCTIONS
from .tools.testing import execute_test_case



warnings.filterwarnings("ignore")

# set region for the model to use
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"


def before_model_callback(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmRequest]:

    if "final_output" in callback_context.state:
        final_output_json = json.dumps(callback_context.state["final_output"])

        return LlmResponse(
            content=types.Content(
                role="model", parts=[types.Part(text=final_output_json)]
            )
        )
    else:
        return None

root_agent = Agent(
    model="gemini-3.5-flash",
    name="qa_agent_worker",
    description="An QA agent that executes test cases",
    instruction=QA_AGENT_INSTRUCTIONS,
    tools=[execute_test_case],
    before_model_callback=before_model_callback,
)
