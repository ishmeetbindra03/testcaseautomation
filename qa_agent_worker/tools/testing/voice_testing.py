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
from qa_agent_worker.models import (
    TestCaseResult,
    TestCase,
    ActualMessage,
    ActualTurn,
    ActualTestProcedure,
)
from datetime import datetime, timezone
import logging

from qa_agent_worker.tools.cxas import send_message_to_cx_agent
from qa_agent_worker.tools.testing.evaluate import _evaluate_test_case_expectations, _get_final_output

def _execute_test_case_voice(
    test_case: TestCase,
    tool_context: ToolContext
) -> str:
    """Executes a test case through voice (audio) channel using bidirectional streaming."""
    tcid = test_case.tcid
    logging.info(f"Executing voice test case: {tcid}")
    logging.info(f"Session ID: {test_case.session_id}")

    actual_turns = []
    current_vars = dict(test_case.initial_input_variables or {})

    # Execute the test case sequential conversation
    for idx, turn in enumerate(test_case.expected_test_procedure.turn_expectations):
        turn_id = turn.turn_id if turn.turn_id is not None else (idx + 1)
        print(f"\n--- [EXECUTE VOICE] Executing Turn {turn_id} ---")

        user_text = ""
        if turn.user_message and turn.user_message.text:
            user_text = turn.user_message.text.text

        send_vars = {}
        if idx == 0 and test_case.initial_input_variables:
            send_vars.update(test_case.initial_input_variables)

        actual_user = ActualMessage(text=user_text, vars=dict(send_vars))
        if user_text:
            print(f"  User (Text input for TTS): {user_text}")

        # Send utterance to CX Agent using audio (voice) modality
        print("  [EXECUTE VOICE] Sending request to CX Agent (as voice/audio)...")
        response = send_message_to_cx_agent(
            project_id=test_case.project_id,
            region_id=test_case.region_id,
            app_id=test_case.app_id,
            text=user_text,
            session_id=test_case.session_id,
            context=tool_context,
            session_variables=send_vars if send_vars else None,
            modality="audio"
        )

        if "status" in response and response["status"] == "error":
            test_case.overall_result = TestCaseResult.ERROR
            tool_context.state["test_cases"][tcid] = test_case.model_dump(mode='json')
            print(f"  [ERROR] CX interaction failed at turn {turn_id}: {response.get('error')}")
            return f"Error executing test case turn {turn_id}: {response.get('error')}"

        agent_messages = response.get("agent_messages", [])
        agent_text = " ".join([m.get("text", "") for m in agent_messages if m.get("text")]).strip()

        last_vars = {}
        if agent_messages:
            for agent_message in agent_messages:
                last_vars.update(agent_message.get("session_variables", {}))

        # Compute strictly updated or newly added variables on this turn
        updated_vars_this_turn = {}
        for k, v in last_vars.items():
            if k not in current_vars or current_vars[k] != v:
                updated_vars_this_turn[k] = v

        current_vars.update(last_vars)

        actual_agent = ActualMessage(text=agent_text, vars=dict(updated_vars_this_turn))
        if agent_text:
            print(f"  Agent: {agent_text}")

        print(f"  [EXECUTE VOICE] Updated variables after Turn {turn_id}: {updated_vars_this_turn}")

        turn_timestamp = datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M:%S %Z")
        actual_turn = ActualTurn(
            turn_id=turn_id,
            timestamp=turn_timestamp,
            user_message=actual_user,
            agent_message=actual_agent
        )
        actual_turns.append(actual_turn)

    # Save gathered actual results
    test_case.actual_test_procedure = ActualTestProcedure(
        actual_turns=actual_turns,
        actual_variables=current_vars
    )

    print(f"\n[EXECUTE VOICE] Conversation finished. Saved {len(actual_turns)} turns.")

    # Programmatically evaluate actuals against expectations
    try:
        print("\n========================================================")
        print("Starting Test Case Expectations Evaluations (Voice)")
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
    return f"Test Case {tcid} Voice Execution Report:\nResult: {status_emoji}\nTurns Evaluated: {len(actual_turns)}"
