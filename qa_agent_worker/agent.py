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

import os

from google.adk.agents.llm_agent import Agent
from google.adk.tools import ToolContext
from .cxas_tool import generate_session_id, send_message_to_cx_agent
from .prompts import QA_AGENT_INSTRUCTIONS_2
from pydantic import BaseModel
from .test_case_tools import execute_test_case, get_test_case, export_test_case

from datetime import datetime, timezone
from typing import Optional, Any, Dict
from google.genai import types

from enum import Enum
import warnings 

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse, LlmRequest


import json

# set region
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"

warnings.filterwarnings("ignore")


from .models import TestCase, Turn, TestCaseResult, ConversationExpectations, ExpectedTestProcedure

def get_var(key, context: ToolContext) -> str:
    return context.state[key] if key in context.state else f"{key} does not exist."

def set_var(key, value, context: ToolContext) -> str:
    context.state[key] = value
    return {
        "name": key,
        "value": value,
        "status": "success"
    }


def initialize_test_case(
        project_id: str, 
        region_id: str, 
        app_id: str,
        tcid: str,
        initial_input_variables: dict[str, Any],
        test_procedure: list[dict[str, Any]], 
        transcript_expectations: list[str],
        variable_expectations: dict[str, str],
        context: ToolContext,
        overall_result: Optional[TestCaseResult] = TestCaseResult.PENDING
        ) -> str:
    """Initializes a TestCase, serializes it, and saves it to the agent's context state.

    This tool is called by the agent at the start of a test run to establish the test
    configuration, expectations, and sequence of turns to verify.

    Args:
        project_id: The Google Cloud Project ID containing the agent under test.
        region_id: The Dialogflow CX region/location ID (e.g., "us-central1", "global").
        app_id: The ID of the Dialogflow CX agent (the application under test).
        tcid: A unique identifier for this specific test case (e.g., "tc_001").
        initial_input_variables: Key-value pairs representing variables to initialize the session with.
        test_procedure: A list of turns representing the expected conversational flow.
            Each turn must be a dictionary representing a Turn model containing:
                - "user_message" (dict, optional): Expectations for the user/caller turn.
                    - "text" (dict, optional): Expected text check, formatted as:
                        {"expectation_type": "any" | "exact" | "semantic" | "optional", "text": "value"}
                    - "vars" (dict, optional): Expected variables, formatted as:
                        {"expectation_type": "any" | "exact" | "semantic" | "optional", "vars": [...]}
                - "agent_message" (dict, optional): Expectations for the agent response turn.
                    - "text" (dict, optional): Expected text check, formatted as:
                        {"expectation_type": "any" | "exact" | "semantic" | "optional", "text": "value"}
                    - "vars" (dict, optional): Expected variables, formatted as:
                        {"expectation_type": "any" | "exact" | "semantic" | "optional", "vars": [...]}
        transcript_expectations: A list of expectations regarding the final conversation transcript.
        variable_expectations: A dictionary mapping variable names to their expected final string values.
        context: The ADK ToolContext injected by the agent runtime. Do not pass this manually.
        overall_result: The initial result status of the test case. Defaults to TestCaseResult.PENDING.

    Returns:
        A success message indicating the test case has been successfully initialized.
    """

    try:
        turn_objs = []
        for idx, t in enumerate(test_procedure):
            if isinstance(t, dict):
                t_copy = dict(t)
                if t_copy.get("turn_id") is None:
                    t_copy["turn_id"] = idx + 1
                turn_objs.append(Turn.model_validate(t_copy))
            else:
                turn_obj = t.model_copy() if hasattr(t, "model_copy") else t
                if hasattr(turn_obj, "turn_id") and turn_obj.turn_id is None:
                    turn_obj.turn_id = idx + 1
                turn_objs.append(turn_obj)

        expected_procedure = ExpectedTestProcedure(
            turn_expectations=turn_objs,
            conversation_expectations=ConversationExpectations(
                goal_expectations=[],
                transcript_expectations=transcript_expectations,
                variable_expectations=variable_expectations
            )
        )
        
        context.state[tcid] = TestCase(
            project_id=project_id,
            region_id=region_id,
            app_id=app_id,
            start_time=datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M:%S %Z"),
            tcid=tcid,
            initial_input_variables=initial_input_variables,
            expected_test_procedure=expected_procedure,
            overall_result=overall_result
        ).model_dump(mode='json')
    except Exception as e:
        return f"Failed to initialize test case: {str(e)}"
    
    return f"Successfully initialized test case: {tcid}"


def before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest) -> Optional[LlmRequest]:

    if "final_output" in callback_context.state:
        final_output_json = json.dumps(callback_context.state["final_output"])

        # return types.Content(
        #     parts=[types.Part.from_text(text=final_output_json)]
        # )

        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(text=final_output_json)
                ]
            )
        )
    else:
        return None

root_agent = Agent(
    model="gemini-3.5-flash",
    name="qa_agent_worker",
    description="An QA agent that executes test cases",
    instruction=QA_AGENT_INSTRUCTIONS_2,
    tools=[initialize_test_case, execute_test_case],
    before_model_callback=before_model_callback
)
