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

from google.adk.tools import ToolContext
from typing import Any, Optional, Dict, List, Literal
from qa_agent_worker.models import (
    TestCaseResult,
    Turn,
    ExpectedTestProcedure,
    ConversationExpectations,
    TestCase,
)
from datetime import datetime, timezone
from uuid import uuid4

import logging

from .text_testing import _execute_test_case_text
from .voice_testing import _execute_test_case_voice

DEFAULT_AUDIO_INPUT_CONFIG = {
    "model": "en-US-Standard-A",
    "language_code": "en-US",
    "sample_rate_hertz": 8000
}


def initialize_test_case(
    project_id: str,
    region_id: str,
    app_id: str,
    tcid: str,
    initial_input_variables: Dict[str, Any],
    test_procedure: List[Dict[str, Any]],
    transcript_expectations: List[str],
    variable_expectations: Dict[str, str],
    tool_context: ToolContext,
    channel: Literal["text", "voice"] = "text",
    input_audio_config: Optional[Dict[str, Any]] = DEFAULT_AUDIO_INPUT_CONFIG,
) -> str:
    """Executes a test case.

    This tool is called by the agent at the start of a test run to establish the test
    configuration, expectations, and sequence of turns to verify.

    Args:
        project_id: The Google Cloud Project ID containing the agent under test.
        region_id: The CX region/location ID (e.g., "us-central1", "global").
        app_id: The ID of the CX agent (the application under test).
        tcid: A unique identifier for this specific test case (e.g., "tc_001").
        initial_input_variables: Key-value pairs representing variables to initialize the session with.
        test_procedure: A list of turns representing the expected conversational flow.
            Each turn must be a dictionary representing a Turn model containing:
                - "user_message" (dict, optional): Expectations for the user/caller turn.
                    - "text" (dict, optional): Expected text check, formatted as:
                        {"expectation_type": "any" | "exact" | "semantic" | "optional", "text": "value"}
                    - "event" (dict, optional): Expected event check, formatted as:
                        {"expectation_type": "any" | "exact" | "semantic" | "optional", "event": "value"}
                    - "dtmf" (dict, optional): Expected dtmf digits check, formatted as:
                        {"expectation_type": "any" | "exact" | "semantic" | "optional", "dtmf": "value"}
                    - "vars" (dict, optional): Expected variables, formatted as:
                        {"expectation_type": "any" | "exact" | "semantic" | "optional", "vars": [...]}
                - "agent_message" (dict, optional): Expectations for the agent response turn.
                    - "text" (dict, optional): Expected text check, formatted as:
                        {"expectation_type": "any" | "exact" | "semantic" | "optional", "text": "value"}
                    - "vars" (dict, optional): Expected variables, formatted as:
                        {"expectation_type": "any" | "exact" | "semantic" | "optional", "vars": [...]}
        transcript_expectations: A list of expectations regarding the final conversation transcript.
        variable_expectations: A dictionary mapping variable names to their expected final string values.
        channel: Whether to conduct send the messages to the CX agent in text or in voice
        input_audio_config: Optional.
        context: The ADK ToolContext injected by the agent runtime. Do not pass this manually.
    """

    logging.info(f"Initializing test case: {tcid}")
    
    turn_objs = []
    for idx, t in enumerate(test_procedure):
        if isinstance(t, dict):
            t_copy = dict(t)
            if t_copy.get("turn_id") is None:
                t_copy["turn_id"] = idx + 1

            try:
                turn_objs.append(Turn.model_validate(t_copy))
            except Exception as e:
                msg = f"Failed to validate turn: {str(e)}"
                logging.error(msg)
                return msg
        else:
            turn_obj = t.model_copy() if hasattr(t, "model_copy") else t
            if hasattr(turn_obj, "turn_id") and turn_obj.turn_id is None:
                turn_obj.turn_id = idx + 1
            turn_objs.append(turn_obj)

    try:
        expected_procedure = ExpectedTestProcedure(
            turn_expectations=turn_objs,
            conversation_expectations=ConversationExpectations(
                goal_expectations=[],
                transcript_expectations=transcript_expectations,
                variable_expectations=variable_expectations,
            ),
        )
    except Exception as e:
        msg = f"Failed to validate expected procedure: {str(e)}"
        logging.error(msg)
        return msg

    try:
        test_case = TestCase(
            project_id=project_id,
            region_id=region_id,
            app_id=app_id,
            start_time=datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M:%S %Z"),
            tcid=tcid,
            modality=channel,
            initial_input_variables=initial_input_variables,
            expected_test_procedure=expected_procedure,
            overall_result=TestCaseResult.PENDING,
            session_id=str(uuid4())
        )
    except Exception as e:
        msg = f"Failed to validate test case: {str(e)}"
        logging.error(msg)
        return msg


    if "test_cases" not in tool_context.state:
        tool_context.state["test_cases"] = {}

    tool_context.state["test_cases"][tcid] = test_case.model_dump_json()

    logging.info(f"Successfully initialized test case {tcid}. Routing execution...")

    return {
        "status": f"Initialized test case {tcid}. Review the initialized test case for accuracy against provided test case.",
        "test_case": tool_context.state["test_cases"][tcid]
    }

def execute_test_case(
    tcid: str,
    tool_context: ToolContext,
    channel: Literal["text", "voice"] = "text",
):
    
    
    if tcid not in tool_context.state["test_cases"]:
        return {
            "status": f"Error. Test Case ID {tcid} not found."
        }
    else:
        test_case = TestCase.model_validate_json(tool_context.state["test_cases"][tcid])

        try:
                # Route the execution based on selected channel (modality)
            if channel == "voice":
                return _execute_test_case_voice(test_case, tool_context)
            else:
                return _execute_test_case_text(test_case, tool_context)
        except Exception as e:
            msg = f"Failed to execute test case: {str(e)}"
            logging.error(msg)
            return msg
    


# def execute_test_case(
#     project_id: str,
#     region_id: str,
#     app_id: str,
#     tcid: str,
#     initial_input_variables: Dict[str, Any],
#     test_procedure: List[Dict[str, Any]],
#     transcript_expectations: List[str],
#     variable_expectations: Dict[str, str],
#     tool_context: ToolContext,
#     channel: Literal["text", "voice"] = "text",
#     input_audio_config: Optional[Dict[str, Any]] = DEFAULT_AUDIO_INPUT_CONFIG,
# ) -> str:
#     """Executes a test case.

#     This tool is called by the agent at the start of a test run to establish the test
#     configuration, expectations, and sequence of turns to verify.

#     Args:
#         project_id: The Google Cloud Project ID containing the agent under test.
#         region_id: The CX region/location ID (e.g., "us-central1", "global").
#         app_id: The ID of the CX agent (the application under test).
#         tcid: A unique identifier for this specific test case (e.g., "tc_001").
#         initial_input_variables: Key-value pairs representing variables to initialize the session with.
#         test_procedure: A list of turns representing the expected conversational flow.
#             Each turn must be a dictionary representing a Turn model containing:
#                 - "user_message" (dict, optional): Expectations for the user/caller turn.
#                     - "text" (dict, optional): Expected text check, formatted as:
#                         {"expectation_type": "any" | "exact" | "semantic" | "optional", "text": "value"}
#                     - "event" (dict, optional): Expected event check, formatted as:
#                         {"expectation_type": "any" | "exact" | "semantic" | "optional", "event": "value"}
#                     - "vars" (dict, optional): Expected variables, formatted as:
#                         {"expectation_type": "any" | "exact" | "semantic" | "optional", "vars": [...]}
#                 - "agent_message" (dict, optional): Expectations for the agent response turn.
#                     - "text" (dict, optional): Expected text check, formatted as:
#                         {"expectation_type": "any" | "exact" | "semantic" | "optional", "text": "value"}
#                     - "vars" (dict, optional): Expected variables, formatted as:
#                         {"expectation_type": "any" | "exact" | "semantic" | "optional", "vars": [...]}
#         transcript_expectations: A list of expectations regarding the final conversation transcript.
#         variable_expectations: A dictionary mapping variable names to their expected final string values.
#         channel: Whether to conduct send the messages to the CX agent in text or in voice
#         input_audio_config: Optional. Include
#         context: The ADK ToolContext injected by the agent runtime. Do not pass this manually.
#     """

#     logging.info(f"Initializing test case: {tcid}")
#     try:
#         turn_objs = []
#         for idx, t in enumerate(test_procedure):
#             if isinstance(t, dict):
#                 t_copy = dict(t)
#                 if t_copy.get("turn_id") is None:
#                     t_copy["turn_id"] = idx + 1
#                 turn_objs.append(Turn.model_validate(t_copy))
#             else:
#                 turn_obj = t.model_copy() if hasattr(t, "model_copy") else t
#                 if hasattr(turn_obj, "turn_id") and turn_obj.turn_id is None:
#                     turn_obj.turn_id = idx + 1
#                 turn_objs.append(turn_obj)

#         expected_procedure = ExpectedTestProcedure(
#             turn_expectations=turn_objs,
#             conversation_expectations=ConversationExpectations(
#                 goal_expectations=[],
#                 transcript_expectations=transcript_expectations,
#                 variable_expectations=variable_expectations,
#             ),
#         )

#         test_case = TestCase(
#             project_id=project_id,
#             region_id=region_id,
#             app_id=app_id,
#             start_time=datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M:%S %Z"),
#             tcid=tcid,
#             modality=channel,
#             initial_input_variables=initial_input_variables,
#             expected_test_procedure=expected_procedure,
#             overall_result=TestCaseResult.PENDING,
#             session_id=str(uuid4())
#         )

#         if "test_cases" not in tool_context.state:
#             tool_context.state["test_cases"] = {}

#         tool_context.state["test_cases"][tcid] = test_case.model_dump(mode='json')
#         logging.info(f"Successfully initialized test case {tcid}. Routing execution...")

#         # Route the execution based on selected channel (modality)
#         if channel == "voice":
#             return _execute_test_case_voice(test_case, tool_context)
#         else:
#             return _execute_test_case_text(test_case, tool_context)

#     except Exception as e:
#         msg = f"Failed to execute test case: {str(e)}"
#         logging.error(msg)
#         return msg