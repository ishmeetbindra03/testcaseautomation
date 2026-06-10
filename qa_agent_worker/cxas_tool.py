import uuid
from typing import Any, Dict, List, Optional

from google.cloud import ces_v1


def _unwrap(val) -> Any:
    """Safely extracts native Python types from Google's proto-plus and Protobuf objects."""
    pb_val = getattr(val, "_pb", val)

    # 1. If it's a Struct (e.g., tool args or response values), recurse over fields
    if hasattr(pb_val, "fields"):
        return {k: _unwrap(v) for k, v in pb_val.fields.items()}

    # 2. If it's a ListValue, recurse over list values
    if hasattr(pb_val, "values"):
        return [_unwrap(v) for v in pb_val.values]

    # 3. Use Protobuf's WhichOneof to grab the populated field in a Value wrapper
    if hasattr(pb_val, "WhichOneof"):
        kind = pb_val.WhichOneof("kind")
        if kind == "string_value":
            return pb_val.string_value  # type: ignore
        elif kind == "number_value":
            return pb_val.number_value  # type: ignore
        elif kind == "bool_value":
            return pb_val.bool_value  # type: ignore
        elif kind == "struct_value":
            return _unwrap(pb_val.struct_value)  # type: ignore
        elif kind == "list_value":
            return _unwrap(pb_val.list_value)  # type: ignore
        elif kind == "null_value":
            return None  # type: ignore

    # 4. Fallback if it is already a native Python type
    if isinstance(pb_val, (str, int, float, bool, list, dict)) or pb_val is None:
        return pb_val

    # 5. Ultimate fallback as string
    return str(pb_val)


def _extract_tool_calls_and_variables(
    response,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Extracts correlated tool calls/responses and all session variables from the run response."""
    session_state = {}
    tool_calls_map = {}

    if not response.outputs:
        return [], session_state

    # Traverse through all conversational diagnostic messages
    for message in response.outputs[0].diagnostic_info.messages:
        for chunk in message.chunks:
            pb_chunk = getattr(chunk, "_pb", chunk)

            # 1. Extract and update session variables
            if hasattr(pb_chunk, "default_variables") and pb_chunk.default_variables:
                for key, val_obj in pb_chunk.default_variables.items():
                    session_state[key] = _unwrap(val_obj)

            if hasattr(pb_chunk, "updated_variables") and pb_chunk.updated_variables:
                for key, val_obj in pb_chunk.updated_variables.items():
                    session_state[key] = _unwrap(val_obj)

            # 2. Extract tool calls (inputs)
            if (
                hasattr(pb_chunk, "tool_call")
                and pb_chunk.tool_call
                and pb_chunk.tool_call.id
            ):
                tc = pb_chunk.tool_call
                tc_id = tc.id
                parameters = _unwrap(tc.args) if tc.args else {}

                tool_calls_map[tc_id] = {
                    "id": tc_id,
                    "name": tc.display_name,
                    "parameters": parameters,
                    "output": None,  # Will be populated when we process the matching tool_response
                }

            # 3. Extract tool responses (outputs)
            if (
                hasattr(pb_chunk, "tool_response")
                and pb_chunk.tool_response
                and pb_chunk.tool_response.id
            ):
                tr = pb_chunk.tool_response
                tr_id = tr.id
                output = _unwrap(tr.response) if tr.response else {}

                if tr_id in tool_calls_map:
                    tool_calls_map[tr_id]["output"] = output
                else:
                    tool_calls_map[tr_id] = {
                        "id": tr_id,
                        "name": tr.display_name,
                        "parameters": None,
                        "output": output,
                    }

    return list(tool_calls_map.values()), session_state


def generate_session_id() -> str:
    """Use this tool to generate a unique session_id.

    Returns
        str: the unique ssesion id to use
    """
    return str(uuid.uuid4())


def send_message_to_cx_agent(
    project_id: str,
    region_id: str,
    app_id: str,
    text: str,
    session_id: str,
    session_variables: Optional[Dict[str, str]] = {},
) -> Dict[str, Any]:
    """Sends a message to CX Agent and returns text, tool calls, and session variables.

    Args:
        project_id (str): The project id
        region_id (str): The region id (us or eu)
        app_id (str): The application id
        session_id (str): The session id to use.
        text (str): The text to send to the agent
        session_variables (Dict[str, str]): key-value pair of session variables to send

    Returns:
        dict:
            text (str): the response from the agent
            tool_calls (list[dict]): the tool calls that the agent executed for the turn
            session_variables (dict[str, Any]): the variables that the agent set for the turn
            session_id (str): The session id
    """

    # 1. Initialize the Session client
    client = ces_v1.SessionServiceClient()

    # 2. Format the fully qualified session path
    session_path = f"projects/{project_id}/locations/{region_id}/apps/{app_id}/sessions/{session_id}"

    # 3. Create the session configuration
    config = ces_v1.SessionConfig(session=session_path)

    inputs = []

    # 4. Create the user input
    user_input = ces_v1.SessionInput(text=text)
    inputs.append(user_input)

    if session_variables:
        variables_input = ces_v1.SessionInput(variables=session_variables)
        inputs.append(variables_input)

    # 5. Build the request payload
    request = ces_v1.RunSessionRequest(config=config, inputs=inputs)

    # 6. Send the request to CX Agent Studio
    try:
        response = client.run_session(request=request)

        # 7. Extract data
        tool_calls, session_vars = _extract_tool_calls_and_variables(response)
        session_ended = False

        if response.outputs and response.outputs[0].end_session:
            session_ended = True

        # 8. Build the requested tool output format
        tool_response: Dict[str, Any] = {
            "text": response.outputs[0].text if response.outputs else "",
            "tool_calls": tool_calls,
            "session_variables": session_vars,
            "session_id": session_id,
        }

        if session_ended:
            tool_response["end_session"] = (
                "The session has ended. Do not send another message for this session."
            )

    except Exception as e:
        return {"status": "error", "error": str(e)}

    return tool_response


if __name__ == "__main__":
    # Example usage
    session_id = str(uuid.uuid4())

    response = send_message_to_cx_agent(
        project_id="ces-ccai-demo",
        region_id="us",
        app_id="cb160644-1d3b-49c5-bba5-079e4fda9671",
        session_id=session_id,
        text="hello, set the variable exit_reason to resolved",
    )

    import json

    print(json.dumps(response, indent=2))
