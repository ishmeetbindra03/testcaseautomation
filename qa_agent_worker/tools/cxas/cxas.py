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

from datetime import datetime
import random
import time
from typing import Any, Dict, Optional

from google.adk.tools import ToolContext

def get_datetime_utc() -> str:
    # Get the current timezone-aware datetime object
    now = datetime.now().astimezone()

    # Format the datetime object into the desired string format
    # The '%z' directive gives the UTC offset in the format +HHMM or -HHMM.
    # We then manually insert the colon ':' to match the requested format.
    formatted_string = (
        now.strftime("%Y/%m/%d %H:%M:%S")
        + now.strftime("%z")[:3]
        + ":"
        + now.strftime("%z")[3:]
    )
    return formatted_string

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

def send_message_to_cx_agent(
    project_id: str,
    region_id: str,
    app_id: str,
    text: str,
    session_id: str,
    context: ToolContext,
    session_variables: Optional[Dict[str, str]] = {},
    modality: str = "text",
) -> Dict[str, Any]:
    """Sends a message to CX Agent and returns text, tool calls, and session variables.

    Args:
        project_id (str): The project id
        region_id (str): The region id (us or eu)
        app_id (str): The application id
        session_id (str): The session id to use.
        text (str): The text to send to the agent
        session_variables (Dict[str, str]): key-value pair of session variables to send
        modality (str): The interaction modality, 'text' or 'audio' (voice)

    Returns:
        dict:
            session_id (str): The session id
            agent_messages (list[dict]): A list of messages (text, variables, tool_calls) output by the agent
            raw_response (str): The raw string response
    """

    from cxas_scrapi.core.sessions import Sessions

    app_name = f"projects/{project_id}/locations/{region_id}/apps/{app_id}"
    sessions_client = Sessions(app_name=app_name)

    # Send the request using cxas-scrapi Sessions client
    try:
        max_retries = 3
        delay = 1.0  # Initial delay of 1 second
        for attempt in range(max_retries + 1):
            try:
                response = sessions_client.run(
                    session_id=session_id,
                    text=text,
                    variables=session_variables,
                    modality=modality,
                )
                break
            except Exception as e:
                if attempt == max_retries:
                    raise e
                sleep_time = delay * (2 ** attempt) + random.uniform(0.1, 0.5)
                time.sleep(sleep_time)

        agent_messages = []
        current_session_state = {}  # Tracks cumulative variables across multiple outputs
        session_ended = False

        # print(response)

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
            "timestamp": get_datetime_utc(),
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
