#!/usr/bin/env python3
"""
QA Automation Test Runner
-------------------------
This script automates QA testing using the `qa_agent_worker` (Agent Development Kit).
It reads test cases from an input CSV, invokes the QA Agent for each test case,
and incrementally saves the JSON results into a .jsonl file.

Prerequisites:
  1. Active virtual environment with dependencies installed.
  2. Authenticated GCP credentials:
     gcloud auth application-default login
  3. Correct GCP project and application configuration (set below or via environment variables).

Usage:
  python run_qa_tests.py
"""

import os
import sys
import json
from datetime import datetime
import csv
import argparse

# Import ADK Runner
try:
    from google.adk.runners import InMemoryRunner
except ImportError:
    print("Error: Could not import google.adk. Make sure your virtual environment is active.")
    print("Try running: source .venv/bin/activate")
    sys.exit(1)

# Import the QA Worker Agent
try:
    from qa_agent_worker.agent import root_agent
except ImportError:
    print("Error: Could not import qa_agent_worker. Make sure you are running this script from the project root.")
    sys.exit(1)

# =====================================================================
# CONFIGURATION
# =====================================================================
# GCP / Dialogflow CX Agent configuration for the agent under test.
# You can set these environment variables or replace the default values here.
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "demoish-471214")
REGION_ID = os.getenv("GCP_REGION_ID", "US")
APP_ID = os.getenv("GCP_APP_ID", "6d05a6fe-69c8-4c70-8b1d-094d71721606")

# Gemini API Key for the ADK LLM agent (gemini-3.5-flash).
# If not set in your terminal environment, paste your API key here:
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", " ")
if GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
    os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY

# =====================================================================

def clean_val(val) -> str:
    """Helper to convert None or empty string to empty string."""
    if val is None:
        return ""
    return str(val).strip()

def format_test_case_prompt(row, project_id: str, region_id: str, app_id: str) -> str:
    """Formats a row from the CSV into the XML-like structure expected by the QA Agent worker."""
    tcid = clean_val(row.get("TC ID"))
    required_vars = clean_val(row.get("Required Variables [UnorderedList]"))
    test_procedure = clean_val(row.get("Agent Test Procedure [OrderedList]"))
    expectation_goal = clean_val(row.get("Expectation_Goal [UnorderedList]"))
    expectation_transcript = clean_val(row.get("Expectation_Transcript [UnorderedList]"))
    expectation_variables = clean_val(row.get("Expectations_Variables [UndoredList[key=value]]"))

    prompt = f"""Please execute the following test case:

<test_case>
    <metadata>
        <tcid>{tcid}</tcid>
    </metadata>

    <agent_configuration>
        <project_id>{project_id}</project_id>
        <region_id>{region_id}</region_id>
        <app_id>{app_id}</app_id>
    </agent_configuration>

    <required_variables>
        {required_vars}
    </required_variables>

    <agent_test_procedure>
        {test_procedure}
    </agent_test_procedure>

    <evaluation>
        <expectation_goal>
            {expectation_goal}
        </expectation_goal>
        <expectations_transcript>
            {expectation_transcript}
        </expectations_transcript>
        <expectations_variables>
            {expectation_variables}
        </expectations_variables>
    </evaluation>
</test_case>
"""
    return prompt

def extract_agent_output(events) -> str:
    """Extracts the final text output from the list of events returned by run_debug."""
    # 1. Try to find the output from the last event's output field
    for event in reversed(events):
        if hasattr(event, "output") and event.output is not None:
            if isinstance(event.output, str):
                return event.output
            elif isinstance(event.output, dict):
                return json.dumps(event.output)
            else:
                return str(event.output)

    # 2. Try to find the text parts in the final content of the conversation
    for event in reversed(events):
        if (
            hasattr(event, "content")
            and event.content
            and hasattr(event.content, "parts")
            and event.content.parts
        ):
            parts_text = []
            for part in event.content.parts:
                if hasattr(part, "text") and part.text and not getattr(part, "thought", False):
                    parts_text.append(part.text)
            if parts_text:
                return "".join(parts_text)
                
    return ""

def parse_json_from_text(text: str) -> dict:
    """Parses a JSON object from text, handling markdown code blocks if present."""
    text = text.strip()
    # Remove markdown code block formatting if present
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    return json.loads(text)

async def main():
    # Set up argument parsing
    parser = argparse.ArgumentParser(description="QA Automation Test Runner")
    parser.add_argument(
        "--input_file",
        type=str,
        required=True,
        help="Path to the input CSV file containing test cases"
    )
    parser.add_argument(
        "--output_result",
        type=str,
        required=True,
        help="Path to the output JSONL results file"
    )
    args = parser.parse_args()

    input_file_path = os.path.abspath(args.input_file)
    output_file_path = os.path.abspath(args.output_result)

    print("=" * 60)
    print("QA Automation Test Runner Starting")
    print("=" * 60)
    print(f"Target Project ID: {PROJECT_ID}")
    print(f"Target Region ID:  {REGION_ID}")
    print(f"Target App ID:     {APP_ID}")
    print(f"Input CSV Path:    {input_file_path}")
    print(f"Output JSONL Path: {output_file_path}")
    print("-" * 60)

    # Validate input CSV exists
    if not os.path.exists(input_file_path):
        print(f"Error: Input CSV file not found at '{input_file_path}'.")
        sys.exit(1)

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file_path), exist_ok=True)

    # Initialize the ADK InMemoryRunner
    print("Initializing ADK InMemoryRunner...")
    try:
        runner = InMemoryRunner(
            agent=root_agent,
            app_name="qa_agent_worker"
        )
        runner.auto_create_session = True
    except Exception as e:
        print(f"Error initializing ADK Runner: {e}")
        sys.exit(1)
    print("Runner initialized successfully.\n")

    # Load CSV using built-in csv.DictReader
    try:
        with open(input_file_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            test_cases = list(reader)
        print(f"Successfully loaded {len(test_cases)} test cases from CSV.\n")
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        sys.exit(1)

    # Track execution stats
    total_cases = len(test_cases)
    success_count = 0
    failure_count = 0

    # Use the runner's async context manager to ensure proper setup and teardown
    async with runner:
        # Row-by-Row Loop
        for idx, row in enumerate(test_cases, start=1):
            tcid = clean_val(row.get("TC ID"))
            summary = clean_val(row.get("Summary"))
            
            print(f"[{idx}/{total_cases}] Processing TC ID: {tcid} - {summary[:50]}...")
            
            # Format the XML prompt payload
            prompt = format_test_case_prompt(row, PROJECT_ID, REGION_ID, APP_ID)
            
            try:
                # Run the agent using run_debug (await the coroutine)
                events = await runner.run_debug(user_messages=prompt, quiet=True)
                
                # Extract the raw output text
                output_text = extract_agent_output(events)
                if not output_text:
                    raise ValueError("Agent returned an empty response or no final response event.")
                
                # Parse the JSON from the output text
                result_json = parse_json_from_text(output_text)
                
                # Append execution metadata if not already present
                if "tcid" not in result_json or not result_json["tcid"]:
                    result_json["tcid"] = tcid
                if "timestamp" not in result_json:
                    result_json["timestamp"] = datetime.now().strftime("%Y/%m/%d %H:%M:%S+00:00")
                if "project_id" not in result_json:
                    result_json["project_id"] = PROJECT_ID
                if "region" not in result_json:
                    result_json["region"] = REGION_ID
                if "app_id" not in result_json:
                    result_json["app_id"] = APP_ID
                
                # Incremental save: Append to JSONL file
                with open(output_file_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(result_json, ensure_ascii=False) + "\n")
                
                status = result_json.get("result", "unknown")
                print(f"  --> SUCCESS: Test Case {tcid} finished. Result: {status.upper()}")
                success_count += 1

            except Exception as e:
                print(f"  --> ERROR: Failed to execute TC ID: {tcid}. Error: {e}")
                failure_count += 1
                
                # Write a failure record that perfectly conforms to the <results_template> structure
                error_record = {
                    "project_id": PROJECT_ID,
                    "region": REGION_ID,
                    "app_id": APP_ID,
                    "session_id": "",
                    "timestamp": datetime.now().strftime("%Y/%m/%d %H:%M:%S+00:00"),
                    "tcid": tcid,
                    "transcript": [
                        {
                            "speaker": "System",
                            "utterance": f"Execution failed with error: {str(e)}",
                            "variables": {}
                        }
                    ],
                    "expectations": [],
                    "reasoning": f"System execution failure: {str(e)}",
                    "result": "failed"
                }
                try:
                    with open(output_file_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(error_record, ensure_ascii=False) + "\n")
                except Exception as write_err:
                    print(f"  --> CRITICAL: Could not write error record to file: {write_err}")

            print("-" * 60)

    # Print final summary
    print("\n" + "=" * 60)
    print("QA Automation Test Execution Complete")
    print("=" * 60)
    print(f"Total Test Cases:  {total_cases}")
    print(f"Succeeded/Saved:   {success_count}")
    print(f"Failed/Error:      {failure_count}")
    print(f"Results saved to:  {output_file_path}")
    print("=" * 60)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
