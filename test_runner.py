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

# Set environment variable to force GenAI to use Vertex AI
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"

import sys
import contextvars
from io import StringIO
import argparse
import csv
import json
import asyncio
from datetime import datetime
import warnings
from uuid import uuid4
# Import your agent from your agent.py file

from google.adk.runners import InMemoryRunner
from google.genai.types import Part, UserContent

from qa_agent_worker.agent import root_agent
from report import generate_index_html, generate_individual_html

import logging

logging.basicConfig(level=logging.INFO)


warnings.filterwarnings("ignore")

row_log_buffer = contextvars.ContextVar("row_log_buffer", default=None)

class ContextAwareStdout:
    def __init__(self, original_stdout):
        self.original_stdout = original_stdout

    def write(self, string):
        self.original_stdout.write(string)
        buf = row_log_buffer.get()
        if buf is not None:
            buf.write(string)

    def flush(self):
        self.original_stdout.flush()

    def __getattr__(self, name):
        return getattr(self.original_stdout, name)

class ContextAwareStderr:
    def __init__(self, original_stderr):
        self.original_stderr = original_stderr

    def write(self, string):
        self.original_stderr.write(string)
        buf = row_log_buffer.get()
        if buf is not None:
            buf.write(string)

    def flush(self):
        self.original_stderr.flush()

    def __getattr__(self, name):
        return getattr(self.original_stderr, name)

if not isinstance(sys.stdout, ContextAwareStdout):
    sys.stdout = ContextAwareStdout(sys.stdout)
if not isinstance(sys.stderr, ContextAwareStderr):
    sys.stderr = ContextAwareStderr(sys.stderr)

def clean_json_response(text: str) -> str:
    """Helper to remove markdown formatting if the agent returns ```json ... ```"""
    text = text.strip()
    if text.startswith('```json'):
        text = text[7:]
    elif text.startswith('```'):
        text = text[3:]
    if text.endswith('```'):
        text = text[:-3]
    return text.strip()

async def process_csv(input_csv: str, results_dir: str, project_id: str, region: str, app_id: str, modality: str = "text", max_parallel_workers: int = 1):
    # 1. Create a timestamped folder within results_dir
    timestamp = datetime.now().strftime("%Y%m%d_%H_%M_%S")
    output_folder = os.path.join(results_dir, timestamp)
    os.makedirs(output_folder, exist_ok=True)
    print(f"Created output directory: {output_folder}")
    
    # Extract the base name of the input_csv without its extension (e.g., "data" from "data.csv")
    csv_basename = os.path.splitext(os.path.basename(input_csv))[0]

    # Initialize the runner once outside the loop
    runner = InMemoryRunner(agent=root_agent, app_name="qa_agent_worker")

    print(f"Reading data from: {input_csv}")

    semaphore = asyncio.Semaphore(max_parallel_workers)

    async def process_row(row_num, row):
        async with semaphore:
            buf = StringIO()
            token = row_log_buffer.set(buf)
            try:
                print(f"Processing row {row_num}...")

                # 2. Create a brand new session for this specific row
                session = await runner.session_service.create_session(
                    app_name=runner.app_name, 
                    user_id="qa_user"
                )

                add_vars = {}
                add_vars.update({"conversationId": str(uuid4())})

                # 3. Input the row CSV data into text
                # Converting the row dictionary to a JSON string makes it easy for the agent to read
                row_text = json.dumps(row)

                prompt = f"""
                Project ID: {project_id}
                Region: {region}
                App ID: {app_id}

                Execute the test in this modality:
                Modality: {modality}
                
                <additional_variables>
                Add these into the initial variables to the agent
                {add_vars}
                </additional_variables>

                Please process the following data and return JSON:\n
                <test_case>
                {row_text}
                </test_case>
                """

                message = UserContent(
                    parts=[Part(text=prompt)]
                )

                agent_output_text = ""

                # 4. Run the agent for this session
                async for event in runner.run_async(
                    new_message=message,
                    session_id=session.id,
                    user_id=session.user_id,
                ):
                    # We only want to capture the text generated by the agent (assistant)
                    if event.author == "qa_agent_worker" and event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.text:
                                agent_output_text += part.text

                # 5. Parse the output as a JSON string
                cleaned_text = clean_json_response(agent_output_text)
                try:
                    parsed_json = json.loads(cleaned_text)
                except json.JSONDecodeError as e:
                    print(f"  -> Warning: Failed to parse JSON on row {row_num}. Error: {e}")
                    print(f"  -> Raw output was: {agent_output_text}")
                    # Fallback so we don't lose the data if parsing fails
                    parsed_json = {"raw_text": agent_output_text, "error": "JSONDecodeError"}

                # Structure the row result
                row_result = {
                    "row_index": row_num,
                    "input_data": row,
                    "agent_output": parsed_json
                }

                print(f"Raw row_result: {row_result}")

                # 6. Dump the result into its individual .json file within the timestamped folder
                out_filename = f"{csv_basename}_{row_num}.json"
                out_filepath = os.path.join(output_folder, out_filename)
                
                print(f"  -> Saving parsed output to: {out_filepath}")
                with open(out_filepath, 'w', encoding='utf-8') as jsonfile:
                    json.dump(row_result, jsonfile, indent=4)

                # 7. Save the corresponding HTML visual report next to the JSON
                html_filename = f"{csv_basename}_{row_num}.html"
                html_filepath = os.path.join(output_folder, html_filename)
                print(f"  -> Saving visual HTML report to: {html_filepath}")
                individual_html = generate_individual_html(row_result)
                with open(html_filepath, 'w', encoding='utf-8') as htmlfile:
                    htmlfile.write(individual_html)

                return row_result
            finally:
                # 7.5. Save the captured stdout/stderr log
                log_filename = f"{csv_basename}_{row_num}.log"
                log_filepath = os.path.join(output_folder, log_filename)
                print(f"  -> Saving row log to: {log_filepath}")
                with open(log_filepath, 'w', encoding='utf-8') as logfile:
                    logfile.write(buf.getvalue())
                row_log_buffer.reset(token)

    tasks = []

    # Open and read the CSV
    with open(input_csv, 'r', encoding='utf-8') as csvfile:
        # DictReader converts each row into a dictionary automatically mapping headers to values
        reader = csv.DictReader(csvfile) 

        for index, row in enumerate(reader):
            row_num = index + 1
            tasks.append(process_row(row_num, row))

    all_results = await asyncio.gather(*tasks)

    # 8. Generate index/dashboard HTML after all cases have finished
    index_filepath = os.path.join(output_folder, "index.html")
    print(f"Generating run summary dashboard to: {index_filepath}")
    index_html = generate_index_html(all_results, timestamp, csv_basename)
    with open(index_filepath, 'w', encoding='utf-8') as indexfile:
        indexfile.write(index_html)

    print("Done!")


def main():
    # Set up parameterization
    parser = argparse.ArgumentParser(description="Run Google ADK Agent over a CSV file with Vertex AI backend")
    parser.add_argument("--input_csv", required=True, help="Filepath to the input CSV")
    
    # Replaced output_json with results_dir
    parser.add_argument("--results_dir", default="results", help="Directory where timestamped output folders will be created")

    parser.add_argument("--project_id", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--app_id", required=True)

    parser.add_argument(
        "--modality", 
        required=True, 
        choices=["text", "audio"],
        help="The modality to use (must be 'text' or 'audio')"
    )

    parser.add_argument(
        "--MAX_PARALLEL_WORKERS",
        type=int,
        default=1,
        help="Maximum number of parallel workers to run test cases at any time"
    )
    
    args = parser.parse_args()

    # Run the async loop
    asyncio.run(process_csv(
        args.input_csv, 
        args.results_dir, 
        args.project_id, 
        args.region, 
        args.app_id, 
        args.modality,
        args.MAX_PARALLEL_WORKERS
    ))

# -----------------------------------------------------------------------------
# Premium HTML Templates
# -----------------------------------------------------------------------------


if __name__ == "__main__":
    main()
