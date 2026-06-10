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

import uuid
from typing import Any, Dict, Optional

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


def _process_single_output(
    output, current_session_state: Dict[str, Any]
) -> Dict[str, Any]:
    """Processes a single output, updating the running state and extracting tool calls."""
    pb_output = getattr(output, "_pb", output)
    text = getattr(pb_output, "text", "")

    tool_calls_map = {}

    # Check for diagnostic info which contains the variables and tool calls
    if hasattr(pb_output, "diagnostic_info") and pb_output.diagnostic_info:
        diag = pb_output.diagnostic_info
        if hasattr(diag, "messages") and diag.messages:
            for message in diag.messages:
                for chunk in message.chunks:
                    pb_chunk = getattr(chunk, "_pb", chunk)

                    # 1. Extract and update session variables
                    if (
                        hasattr(pb_chunk, "default_variables")
                        and pb_chunk.default_variables
                    ):
                        items = getattr(
                            pb_chunk.default_variables,
                            "fields",
                            pb_chunk.default_variables,
                        ).items()
                        for key, val_obj in items:
                            current_session_state[key] = _unwrap(val_obj)

                    if (
                        hasattr(pb_chunk, "updated_variables")
                        and pb_chunk.updated_variables
                    ):
                        items = getattr(
                            pb_chunk.updated_variables,
                            "fields",
                            pb_chunk.updated_variables,
                        ).items()
                        for key, val_obj in items:
                            current_session_state[key] = _unwrap(val_obj)

                    # 2. Extract tool calls (inputs)
                    if (
                        hasattr(pb_chunk, "tool_call")
                        and pb_chunk.tool_call
                        and pb_chunk.tool_call.id
                    ):
                        tc = pb_chunk.tool_call
                        tool_calls_map[tc.id] = {
                            "id": tc.id,
                            "name": getattr(tc, "display_name", ""),
                            "parameters": _unwrap(tc.args)
                            if getattr(tc, "args", None)
                            else {},
                            "output": None,
                        }

                    # 3. Extract tool responses (outputs)
                    if (
                        hasattr(pb_chunk, "tool_response")
                        and pb_chunk.tool_response
                        and pb_chunk.tool_response.id
                    ):
                        tr = pb_chunk.tool_response
                        out_val = (
                            _unwrap(tr.response)
                            if getattr(tr, "response", None)
                            else {}
                        )
                        if tr.id in tool_calls_map:
                            tool_calls_map[tr.id]["output"] = out_val
                        else:
                            tool_calls_map[tr.id] = {
                                "id": tr.id,
                                "name": getattr(tr, "display_name", ""),
                                "parameters": None,
                                "output": out_val,
                            }

    return {
        "text": text,
        "session_variables": dict(
            current_session_state
        ),  # Take a snapshot of variables for this output
        "tool_calls": list(tool_calls_map.values()),
        "end_session": getattr(pb_output, "end_session", False),
    }


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
            session_id (str): The session id
            agent_messages (list[dict]): A list of messages (text, variables, tool_calls) output by the agent
            raw_response (str): The raw string response
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

        agent_messages = []
        current_session_state = {}  # Tracks cumulative variables across multiple outputs
        session_ended = False

        # 7. Extract data for each individual output block
        if response.outputs:
            for output in response.outputs:
                msg_data = _process_single_output(output, current_session_state)

                agent_messages.append(
                    {
                        "text": msg_data["text"],
                        "session_variables": msg_data["session_variables"],
                        "tool_calls": msg_data["tool_calls"],
                    }
                )

                if msg_data["end_session"]:
                    session_ended = True

        # 8. Build the requested tool output format
        tool_response: Dict[str, Any] = {
            "session_id": session_id,
            "agent_messages": agent_messages,
            # "raw_response": str(response),
        }

        if session_ended:
            tool_response["end_session"] = (
                "The session has ended. Do not send another message for this session."
            )

    except Exception as e:
        return {"status": "error", "error": str(e)}

    return tool_response
