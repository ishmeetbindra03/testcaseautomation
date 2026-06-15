import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List
from google.adk.tools import ToolContext
from .models import TestCase, Turn, ActualTurn, ActualMessage, TestCaseResult
from .cxas_tool import send_message_to_cx_agent

def execute_test_case(
    tcid: str,
    context: ToolContext,
) -> str:
    """Reads a TestCase from state, executes it programmatically against Dialogflow CX, and saves the actual execution results.

    This tool sends the user messages specified in each turn of the test_procedure to the
    Dialogflow CX agent under test, captures the agent's actual responses and cumulative 
    session variables, and writes the entire recorded execution back to the TestCase state.

    Args:
        tcid: The unique test case identifier (e.g., "tc_001") whose TestCase is stored in context.state.
        context: The ADK ToolContext (automatically injected).

    Returns:
        A message describing the execution result or indicating any errors encountered.
    """
    if tcid not in context.state:
        return f"Test case id {tcid} not found in state."

    try:
        # 1. Parse the TestCase from the context state (stored as a dictionary)
        test_case = TestCase.model_validate(context.state[tcid])
    except Exception as e:
        return f"Failed to validate test case {tcid}: {str(e)}"

    # 2. Generate a unique session ID for this specific execution run
    session_id = str(uuid.uuid4())

    actual_turns: List[ActualTurn] = []
    actual_transcript: List[str] = []
    current_vars: Dict[str, Any] = dict(test_case.initial_input_variables or {})

    # 3. Iterate through each expected Turn in the procedure
    for idx, turn in enumerate(test_case.test_procedure):
        turn_id = turn.turn_id if turn.turn_id is not None else (idx + 1)

        # Extract text to send
        user_text = ""
        if turn.user_message and turn.user_message.text:
            user_text = turn.user_message.text.text

        # Determine input session variables to pass
        send_vars = {}
        if idx == 0 and test_case.initial_input_variables:
            send_vars.update(test_case.initial_input_variables)

        # Record what was sent from the user side
        actual_user = ActualMessage(text=user_text, vars=dict(send_vars or current_vars))
        if user_text:
            actual_transcript.append(f"User: {user_text}")

        # Send the turn's user utterance
        response = send_message_to_cx_agent(
            project_id=test_case.project_id,
            region_id=test_case.region_id,
            app_id=test_case.app_id,
            text=user_text,
            session_id=session_id,
            context=context,
            session_variables=send_vars if send_vars else None
        )

        if "status" in response and response["status"] == "error":
            test_case.overall_result = TestCaseResult.ERROR
            context.state[tcid] = test_case.model_dump(mode='json')
            return f"Error executing test case turn {turn_id}: {response.get('error')}"

        # Parse agent responses
        agent_messages = response.get("agent_messages", [])
        agent_text = " ".join([m.get("text", "") for m in agent_messages if m.get("text")]).strip()

        # Update cumulative session variables
        if agent_messages:
            last_vars = agent_messages[-1].get("session_variables", {})
            current_vars.update(last_vars)

        actual_agent = ActualMessage(text=agent_text, vars=dict(current_vars))
        if agent_text:
            actual_transcript.append(f"Agent: {agent_text}")

        # Save actual turn execution metrics
        actual_turn = ActualTurn(
            turn_id=turn_id,
            user_message=actual_user,
            agent_message=actual_agent
        )
        actual_turns.append(actual_turn)

    # 4. Save results and update state
    test_case.actual_test_procedure = actual_turns
    test_case.actual_transcript = actual_transcript
    test_case.actual_variables = current_vars
    test_case.overall_result = TestCaseResult.PENDING  # Ready for expectation checking

    # Save back to context state
    context.state[tcid] = test_case.model_dump(mode='json')

    return f"Successfully executed test case {tcid}. Recorded {len(actual_turns)} turns."