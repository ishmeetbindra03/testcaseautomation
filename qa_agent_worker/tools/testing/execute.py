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
from typing import Any, Dict, List, Literal
from qa_agent_worker.models import (
    TestCase,
    TestCaseResult,
    Turn,
    ExpectedTestProcedure,
    ConversationExpectations,
    ActualMessage,
    ActualTurn,
    ActualTestProcedure,
    
)

from datetime import datetime, timezone
from uuid import uuid4

import logging

from qa_agent_worker.tools.cxas import send_message_to_cx_agent
from qa_agent_worker.tools.testing.evaluate import _evaluate_test_case_expectations, _get_final_output

DEFAULT_AUDIO_INPUT_CONFIG = {
    "model": "en-US-Standard-A",
    "language_code": "en-US",
    "sample_rate_hertz": 8000
}

def _execute_test_case(
    test_case: TestCase,
    tool_context: ToolContext
) -> str:
    """Executes a test case through text channel."""
    tcid = test_case.tcid
    logging.info(f"Executing text test case: {tcid}")
    logging.info(f"Session ID: {test_case.session_id}")

    actual_turns = []
    current_vars = dict(test_case.initial_input_variables or {})

    # Execute the test case sequential conversation
    for idx, turn in enumerate(test_case.expected_test_procedure.turn_expectations):
        turn_id = turn.turn_id if turn.turn_id is not None else (idx + 1)
        print(f"\n--- [EXECUTE {test_case.modality.upper()}] Executing Turn {turn_id} ---")


        user_message = {
            "project_id": test_case.project_id,
            "region_id": test_case.region_id,
            "app_id": test_case.app_id,
            "session_id": test_case.session_id,
            "modality": test_case.modality,
            "context": tool_context
        }

        user_text = None
        event = None
        dtmf = None
        send_vars = {}
        if turn.user_message and turn.user_message.text:
            user_text = turn.user_message.text.text
            user_message.update({"text": user_text})
            print(f"  User:  {user_text}")

        if turn.user_message and turn.user_message.event:
            event = turn.user_message.event.event
            user_message.update({"event": event})
            print(f"  User:  {event}")

        if turn.user_message and turn.user_message.dtmf:
            dtmf = turn.user_message.dtmf.dtmf
            user_message.update({"dtmf": dtmf})
            print(f"  User:  {dtmf}")
            
        if idx == 0 and test_case.initial_input_variables:
            send_vars.update(test_case.initial_input_variables)
        
        if turn.user_message and turn.user_message.vars:
            send_vars.update(turn.user_message.vars.vars)
        
        user_message.update({"session_variables": send_vars})

        actual_user = ActualMessage(text=user_text, event=event, dtmf=dtmf, vars=dict(send_vars))

        # Send utterance to CX Agent using text modality
        logging.info(f"  [EXECUTE {test_case.modality.upper()}] Sending request to CX Agent...")

        response = send_message_to_cx_agent(**user_message)

        if "status" in response and response["status"] == "error":
            test_case.overall_result = TestCaseResult.ERROR
            tool_context.state["test_cases"][tcid] = test_case.model_dump(mode='json')
            logging.error(f"  [ERROR] CX interaction failed at turn {turn_id}: {response.get('error')}")
            return f"Error executing test case turn {turn_id}: {response.get('error')}"

        agent_messages = response.get("agent_messages", [])
        agent_text = " ".join([m.get("text", "") for m in agent_messages if m.get("text")]).strip()

        turn_vars = {}
        if agent_messages:
            for agent_message in agent_messages:
                turn_vars.update(agent_message.get("session_variables", {}))

        actual_agent = ActualMessage(text=agent_text, vars=dict(turn_vars))
        if agent_text:
            print(f"  Agent: {agent_text}")
        if turn_vars:
            print(f". Agent: {turn_vars}")

        turn_timestamp = datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M:%S %Z")
        actual_turn = ActualTurn(
            turn_id=turn_id,
            timestamp=turn_timestamp,
            user_message=actual_user,
            agent_message=actual_agent
        )
        actual_turns.append(actual_turn)
        current_vars.update(turn_vars)

        if "end_session" in response:
            print("  [EXECUTE] CX Agent indicated end of session. Stopping test execution early.")
            break

    # Save gathered actual results
    test_case.actual_test_procedure = ActualTestProcedure(
        actual_turns=actual_turns,
        actual_variables=current_vars
    )

    print(f"\n[EXECUTE] Conversation finished. Saved {len(actual_turns)} turns.")

    # Programmatically evaluate actuals against expectations
    try:
        print("\n========================================================")
        print("Starting Test Case Expectations Evaluations")
        test_case = _evaluate_test_case_expectations(test_case)
    except Exception as e:
        print(f"[ERROR] Evaluation failed: {str(e)}")
        test_case.overall_result = TestCaseResult.ERROR
        tool_context.state["test_cases"][tcid] = test_case.model_dump(mode='json')
        return f"Execution succeeded, but programmatic evaluation failed: {str(e)}"

    # Save back to context state
    print("Saving to context state")
    tool_context.state["test_cases"][tcid] = test_case.model_dump(mode='json')
    tool_context.state["final_output"] = _get_final_output(tcid, tool_context)

    # Return structured test execution summary report
    status_emoji = "✅ PASSED" if test_case.overall_result == TestCaseResult.PASSED else "❌ FAILED"
    return f"Test Case {tcid} Execution Report:\nResult: {status_emoji}\nTurns Evaluated: {len(actual_turns)}"


def initialize_test_case(
    project_id: str,
    region_id: str,
    app_id: str,
    tcid: str,
    initial_input_variables: Dict[str, Any],
    original_test_procedure: str,
    test_procedure: List[Dict[str, Any]],
    transcript_expectations: List[str],
    variable_expectations: Dict[str, str],
    tool_context: ToolContext,
    modality: Literal["text", "audio"] = "text",
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
        original_test_procedure: The original verbatim test procedure provided
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
        modality: text or audio. Whether to conduct send the messages to the CX agent as text or as audio. Defaults to text.
        context: The ADK ToolContext injected by the agent runtime. Do not pass this manually.
    """

    logging.info(f"Initializing test case: {tcid}")
    
    # Initialize each turn
    turn_objs = []
    for idx, t in enumerate(test_procedure):
        if isinstance(t, dict):
            t_copy = dict(t)
            if t_copy.get("turn_id") is None:
                t_copy["turn_id"] = idx + 1

            try:
                logging.info(f"Validating turn {idx + 1}")
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

    # Initialize the test procedure
    try:
        logging.info("Validating expected procedure")
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
    

    # Initialize the test case
    try:
        logging.info("Validating test case")
        test_case = TestCase(
            project_id=project_id,
            region_id=region_id,
            app_id=app_id,
            start_time=datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M:%S %Z"),
            tcid=tcid,
            modality=modality,
            initial_input_variables=initial_input_variables,
            original_test_procedure=original_test_procedure,
            expected_test_procedure=expected_procedure,
            overall_result=TestCaseResult.PENDING,
            session_id=str(uuid4())
        )
        logging.info(f"Successfully validated test case: {test_case.model_dump_json(indent=4)}")
    except Exception as e:
        msg = f"Failed to validate test case: {str(e)}"
        logging.error(msg)
        return msg

    # If test cases not yet in the state, initialize
    if "test_cases" not in tool_context.state:
        tool_context.state["test_cases"] = {}

    # Save the test case into the states
    tool_context.state["test_cases"][tcid] = test_case.model_dump_json()

    logging.info(f"Successfully initialized test case {tcid}. Routing execution...")

    return {
        "status": f"Initialized test case {tcid}. Review the initialized test case for accuracy against provided test case.",
        "test_case": tool_context.state["test_cases"][tcid]
    }

def execute_test_case(
    tcid: str,
    tool_context: ToolContext,
) -> dict:
    """Executes the test case.

    Args:
        tcid: The TCID to execute
        tool_context: The ADK ToolContext injected by the agent runtime. Do not pass this manually.

    Returns:
        dict: The result of the execution
    """
    
    logging.info(f"Tool Use: Executing test case: {tcid}")

    if tcid not in tool_context.state["test_cases"]:
        logging.error(f"TCID {tcid} not found in context state.")
        return {
            "status": f"Error. Test Case ID {tcid} not found."
        }
    else:
        # Loading the test case from context
        try:
            logging.info("Loading test case from context")
            test_case = TestCase.model_validate_json(tool_context.state["test_cases"][tcid])
        except Exception as e:
            msg = f"Failed to load test case from context: {str(e)}"
            logging.error(msg)
            return msg

        # Executing the test case
        try:
            return _execute_test_case(test_case, tool_context)
        except Exception as e:
            msg = f"Failed to execute test case: {str(e)}"
            logging.error(msg)
            return msg