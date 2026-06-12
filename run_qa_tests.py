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
# You can set these environment variables or pass them as command line arguments.
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "YOUR_GCP_PROJECT_ID_HERE")
REGION_ID = os.getenv("GCP_REGION_ID", "us-central1")
APP_ID = os.getenv("GCP_APP_ID", "YOUR_DIALOGFLOW_CX_APP_ID_HERE")

# Gemini API Key for the ADK LLM agent (gemini-3.5-flash).
# If not set in your terminal environment, paste your API key here:
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")
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


# =====================================================================
# HTML REPORT GENERATOR
# =====================================================================
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QA Automation Test Execution Report</title>
    <meta name="description" content="Interactive dashboard and detailed report for QA Test Automation execution.">
    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <!-- Chart.js CDN -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    
    <style>
        :root {
            --bg-primary: #f8fafc;
            --bg-secondary: #ffffff;
            --bg-tertiary: #f1f5f9;
            --border-color: #e2e8f0;
            --text-primary: #0f172a;
            --text-secondary: #475569;
            --text-muted: #94a3b8;
            
            --primary: #c41230; /* Rogers Red */
            --primary-hover: #a00f26;
            --primary-light: #fdf2f4;
            
            --success: #10b981;
            --success-bg: #ecfdf5;
            --success-border: #a7f3d0;
            --success-text: #065f46;
            
            --danger: #ef4444;
            --danger-bg: #fef2f2;
            --danger-border: #fca5a5;
            --danger-text: #991b1b;
            
            --warning: #f59e0b;
            --warning-bg: #fffbeb;
            --warning-border: #fde68a;
            --warning-text: #92400e;
            
            --info: #3b82f6;
            --info-bg: #eff6ff;
            --info-border: #bfdbfe;
            --info-text: #1e40af;
            
            --card-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.05), 0 2px 4px -2px rgb(0 0 0 / 0.05);
            --card-shadow-hover: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
            --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            --sidebar-width: 260px;
        }

        [data-theme="dark"] {
            --bg-primary: #090d16;
            --bg-secondary: #111827;
            --bg-tertiary: #1f2937;
            --border-color: #374151;
            --text-primary: #f9fafb;
            --text-secondary: #d1d5db;
            --text-muted: #6b7280;
            
            --primary: #ef4444;
            --primary-hover: #dc2626;
            --primary-light: #2d1618;
            
            --success: #10b981;
            --success-bg: rgba(16, 185, 129, 0.15);
            --success-border: #047857;
            --success-text: #34d399;
            
            --danger: #ef4444;
            --danger-bg: rgba(239, 68, 68, 0.15);
            --danger-border: #b91c1c;
            --danger-text: #f87171;
            
            --warning: #f59e0b;
            --warning-bg: rgba(245, 158, 11, 0.15);
            --warning-border: #b45309;
            --warning-text: #fbbf24;
            
            --info: #3b82f6;
            --info-bg: rgba(59, 130, 246, 0.15);
            --info-border: #1d4ed8;
            --info-text: #60a5fa;
            
            --card-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.3), 0 2px 4px -2px rgb(0 0 0 / 0.3);
            --card-shadow-hover: 0 10px 15px -3px rgb(0 0 0 / 0.5), 0 4px 6px -4px rgb(0 0 0 / 0.5);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            display: flex;
            min-height: 100vh;
            transition: var(--transition);
        }

        /* Sidebar Navigation */
        .sidebar {
            width: var(--sidebar-width);
            background-color: var(--bg-secondary);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            position: fixed;
            height: 100vh;
            z-index: 50;
            transition: var(--transition);
        }

        .sidebar-brand {
            padding: 24px;
            display: flex;
            align-items: center;
            gap: 12px;
            border-bottom: 1px solid var(--border-color);
        }

        .brand-logo {
            width: 36px;
            height: 36px;
            background: linear-gradient(135deg, var(--primary), #ef4444);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 800;
            font-size: 1.25rem;
            font-family: 'Outfit', sans-serif;
            box-shadow: 0 4px 10px rgba(196, 18, 48, 0.3);
        }

        .brand-name {
            font-family: 'Outfit', sans-serif;
            font-weight: 700;
            font-size: 1.15rem;
            letter-spacing: -0.02em;
        }

        .sidebar-menu {
            padding: 24px 16px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            flex-grow: 1;
        }

        .menu-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 16px;
            color: var(--text-secondary);
            text-decoration: none;
            border-radius: 8px;
            font-weight: 500;
            font-size: 0.95rem;
            transition: var(--transition);
            cursor: pointer;
            border: none;
            background: none;
            width: 100%;
            text-align: left;
        }

        .menu-item:hover {
            background-color: var(--bg-tertiary);
            color: var(--text-primary);
        }

        .menu-item.active {
            background-color: var(--primary-light);
            color: var(--primary);
            font-weight: 600;
        }

        .menu-item svg {
            width: 20px;
            height: 20px;
            transition: var(--transition);
        }

        .sidebar-footer {
            padding: 20px;
            border-top: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .theme-toggle {
            background: none;
            border: 1px solid var(--border-color);
            padding: 8px;
            border-radius: 8px;
            cursor: pointer;
            color: var(--text-secondary);
            display: flex;
            align-items: center;
            justify-content: center;
            transition: var(--transition);
        }

        .theme-toggle:hover {
            background-color: var(--bg-tertiary);
            color: var(--text-primary);
        }

        .theme-toggle svg {
            width: 18px;
            height: 18px;
        }

        /* Main Content Container */
        .main-content {
            margin-left: var(--sidebar-width);
            flex-grow: 1;
            padding: 40px;
            max-width: 1600px;
            width: calc(100% - var(--sidebar-width));
            transition: var(--transition);
        }

        /* Header */
        .content-header {
            margin-bottom: 32px;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
        }

        .header-title h1 {
            font-family: 'Outfit', sans-serif;
            font-size: 2.2rem;
            font-weight: 800;
            letter-spacing: -0.03em;
            margin-bottom: 6px;
        }

        .header-title p {
            color: var(--text-secondary);
            font-size: 1rem;
        }

        .header-badge {
            background-color: var(--primary-light);
            color: var(--primary);
            padding: 8px 16px;
            border-radius: 9999px;
            font-weight: 600;
            font-size: 0.85rem;
            border: 1px solid rgba(196, 18, 48, 0.15);
        }

        /* Section Layouts */
        .section-view {
            display: none;
            animation: fadeIn 0.4s ease-out;
        }

        .section-view.active {
            display: block;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* Metric Cards Grid */
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 24px;
            margin-bottom: 32px;
        }

        .metric-card {
            background-color: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: var(--card-shadow);
            transition: var(--transition);
        }

        .metric-card:hover {
            transform: translateY(-4px);
            box-shadow: var(--card-shadow-hover);
        }

        .metric-info h3 {
            font-size: 0.875rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-secondary);
            margin-bottom: 8px;
            font-weight: 600;
        }

        .metric-value {
            font-family: 'Outfit', sans-serif;
            font-size: 2rem;
            font-weight: 800;
            line-height: 1;
            margin-bottom: 6px;
        }

        .metric-desc {
            font-size: 0.8rem;
            color: var(--text-muted);
        }

        .metric-icon {
            width: 48px;
            height: 48px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .metric-icon svg {
            width: 24px;
            height: 24px;
        }

        .metric-blue { background-color: rgba(59, 130, 246, 0.1); color: #3b82f6; }
        .metric-green { background-color: rgba(16, 185, 129, 0.1); color: #10b981; }
        .metric-red { background-color: rgba(239, 68, 68, 0.1); color: #ef4444; }
        .metric-purple { background-color: rgba(139, 92, 246, 0.1); color: #8b5cf6; }

        /* Grid Dashboard Layout */
        .dashboard-grid {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 24px;
            margin-bottom: 32px;
        }

        .dashboard-card {
            background-color: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            box-shadow: var(--card-shadow);
            overflow: hidden;
            transition: var(--transition);
        }

        .dashboard-card:hover {
            box-shadow: var(--card-shadow-hover);
        }

        .card-header {
            padding: 20px 24px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .card-header h2 {
            font-family: 'Outfit', sans-serif;
            font-size: 1.2rem;
            font-weight: 700;
        }

        .card-body {
            padding: 24px;
        }

        /* Tables */
        .table-container {
            overflow-x: auto;
            width: 100%;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.925rem;
        }

        th {
            background-color: var(--bg-tertiary);
            color: var(--text-secondary);
            font-weight: 600;
            padding: 14px 18px;
            border-bottom: 1px solid var(--border-color);
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.05em;
        }

        td {
            padding: 14px 18px;
            border-bottom: 1px solid var(--border-color);
            color: var(--text-secondary);
        }

        tr:last-child td {
            border-bottom: none;
        }

        tr {
            transition: var(--transition);
        }

        tbody tr:hover {
            background-color: rgba(196, 18, 48, 0.02);
            cursor: pointer;
        }

        /* Badges */
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.02em;
        }

        .badge-pass {
            background-color: var(--success-bg);
            color: var(--success-text);
            border: 1px solid rgba(16, 185, 129, 0.2);
        }

        .badge-fail {
            background-color: var(--danger-bg);
            color: var(--danger-text);
            border: 1px solid rgba(239, 68, 68, 0.2);
        }

        .badge-warning {
            background-color: var(--warning-bg);
            color: var(--warning-text);
            border: 1px solid rgba(245, 158, 11, 0.2);
        }

        .badge-info {
            background-color: var(--info-bg);
            color: var(--info-text);
            border: 1px solid rgba(59, 130, 246, 0.2);
        }

        /* Interactive Dropdown / Search */
        .filters-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            gap: 16px;
            flex-wrap: wrap;
        }

        .search-input-wrapper {
            position: relative;
            flex-grow: 1;
            max-width: 380px;
        }

        .search-input-wrapper svg {
            position: absolute;
            left: 14px;
            top: 50%;
            transform: translateY(-50%);
            width: 18px;
            height: 18px;
            color: var(--text-muted);
        }

        .search-input {
            width: 100%;
            padding: 10px 16px 10px 42px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
            background-color: var(--bg-secondary);
            color: var(--text-primary);
            font-family: inherit;
            font-size: 0.9rem;
            transition: var(--transition);
        }

        .search-input:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(196, 18, 48, 0.1);
        }

        .filter-buttons {
            display: flex;
            gap: 8px;
        }

        .btn {
            padding: 8px 16px;
            border-radius: 8px;
            font-weight: 500;
            font-size: 0.85rem;
            cursor: pointer;
            transition: var(--transition);
            font-family: inherit;
            border: 1px solid var(--border-color);
            background-color: var(--bg-secondary);
            color: var(--text-secondary);
        }

        .btn:hover {
            background-color: var(--bg-tertiary);
            color: var(--text-primary);
        }

        .btn-primary {
            background-color: var(--primary);
            color: white;
            border-color: var(--primary);
        }

        .btn-primary:hover {
            background-color: var(--primary-hover);
            border-color: var(--primary-hover);
            color: white;
        }

        .btn.active {
            background-color: var(--primary);
            color: white;
            border-color: var(--primary);
        }

        /* Priorities & Cost Estimations */
        .priority-list {
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .priority-item {
            display: flex;
            gap: 16px;
            align-items: flex-start;
        }

        .priority-num {
            background-color: var(--primary-light);
            color: var(--primary);
            width: 28px;
            height: 28px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 0.85rem;
            flex-shrink: 0;
            border: 1px solid rgba(196, 18, 48, 0.1);
        }

        .priority-text h4 {
            font-size: 0.95rem;
            font-weight: 600;
            margin-bottom: 4px;
        }

        .priority-text p {
            font-size: 0.85rem;
            color: var(--text-secondary);
            line-height: 1.4;
        }

        /* Detailed Report Layout */
        .report-grid-meta {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 32px;
            background-color: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 24px;
            box-shadow: var(--card-shadow);
        }

        .meta-item {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .meta-label {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            font-weight: 600;
        }

        .meta-val {
            font-size: 0.95rem;
            font-weight: 600;
            color: var(--text-primary);
        }

        /* Big Status Banner */
        .status-banner {
            border-radius: 16px;
            padding: 28px;
            margin-bottom: 32px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: var(--card-shadow);
        }

        .status-banner-passed {
            background: linear-gradient(135deg, rgba(16, 185, 129, 0.1), rgba(16, 185, 129, 0.03));
            border: 1px solid var(--success-border);
        }

        .status-banner-failed {
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.1), rgba(239, 68, 68, 0.03));
            border: 1px solid var(--danger-border);
        }

        .status-banner-title {
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .status-banner-icon {
            width: 44px;
            height: 44px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .status-banner-passed .status-banner-icon {
            background-color: var(--success);
            color: white;
            box-shadow: 0 4px 10px rgba(16, 185, 129, 0.3);
        }

        .status-banner-failed .status-banner-icon {
            background-color: var(--danger);
            color: white;
            box-shadow: 0 4px 10px rgba(239, 68, 68, 0.3);
        }

        .status-banner-text h2 {
            font-family: 'Outfit', sans-serif;
            font-size: 1.4rem;
            font-weight: 700;
            margin-bottom: 4px;
        }

        .status-banner-text p {
            font-size: 0.9rem;
            color: var(--text-secondary);
        }

        .status-banner-stamp {
            font-family: 'Outfit', sans-serif;
            font-size: 1.8rem;
            font-weight: 800;
            letter-spacing: 0.05em;
            text-transform: uppercase;
        }

        .status-banner-passed .status-banner-stamp {
            color: var(--success);
        }

        .status-banner-failed .status-banner-stamp {
            color: var(--danger);
        }

        /* Objective Box */
        .report-section-card {
            background-color: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 28px;
            margin-bottom: 32px;
            box-shadow: var(--card-shadow);
        }

        .report-section-card h3 {
            font-family: 'Outfit', sans-serif;
            font-size: 1.25rem;
            font-weight: 700;
            margin-bottom: 18px;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .report-section-card h3 svg {
            width: 22px;
            height: 22px;
            color: var(--primary);
        }

        .objective-content {
            font-size: 0.95rem;
            line-height: 1.6;
            color: var(--text-secondary);
        }

        /* Transcript & Conversations styling */
        .transcript-table th {
            padding: 16px 20px;
        }

        .transcript-table td {
            padding: 18px 20px;
            vertical-align: top;
        }

        .speaker-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-weight: 700;
            font-size: 0.85rem;
            padding: 6px 12px;
            border-radius: 8px;
        }

        .speaker-caller {
            background-color: var(--info-bg);
            color: var(--info-text);
            border: 1px solid rgba(59, 130, 246, 0.15);
        }

        .speaker-agent {
            background-color: var(--primary-light);
            color: var(--primary);
            border: 1px solid rgba(196, 18, 48, 0.15);
        }

        .speaker-system {
            background-color: var(--bg-tertiary);
            color: var(--text-secondary);
            border: 1px solid var(--border-color);
        }

        .utterance-cell {
            font-size: 0.95rem;
            line-height: 1.5;
            font-weight: 500;
            color: var(--text-primary);
        }

        /* Key Variables List */
        .variables-wrapper {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }

        .variable-pill {
            display: inline-flex;
            align-items: center;
            background-color: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 4px 8px;
            font-family: monospace;
            font-size: 0.78rem;
            color: var(--text-secondary);
        }

        .variable-name {
            font-weight: 700;
            color: var(--primary);
            margin-right: 4px;
        }

        .variable-value {
            font-weight: 500;
            color: var(--text-primary);
        }

        .variables-empty {
            font-size: 0.85rem;
            color: var(--text-muted);
            font-style: italic;
        }

        /* Conclusion styling */
        .conclusion-card {
            border-left: 4px solid var(--primary);
            background-color: var(--bg-tertiary);
            padding: 20px 24px;
            border-radius: 0 12px 12px 0;
            font-size: 0.95rem;
            line-height: 1.6;
            color: var(--text-secondary);
        }

        .conclusion-card-passed {
            border-left-color: var(--success);
            background-color: var(--success-bg);
            color: var(--success-text);
        }

        .conclusion-card-failed {
            border-left-color: var(--danger);
            background-color: var(--danger-bg);
            color: var(--danger-text);
        }

        /* Custom Selector for Detailed Reports */
        .detailed-selector-wrapper {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 28px;
            background-color: var(--bg-secondary);
            border: 1px solid var(--border-color);
            padding: 16px 24px;
            border-radius: 12px;
            box-shadow: var(--card-shadow);
        }

        .detailed-selector-info {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .detailed-selector-info h3 {
            font-family: 'Outfit', sans-serif;
            font-size: 1.1rem;
            font-weight: 700;
        }

        .detailed-selector-info p {
            font-size: 0.85rem;
            color: var(--text-secondary);
        }

        .select-input {
            padding: 10px 16px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
            background-color: var(--bg-secondary);
            color: var(--text-primary);
            font-family: inherit;
            font-weight: 600;
            font-size: 0.9rem;
            outline: none;
            cursor: pointer;
            transition: var(--transition);
        }

        .select-input:focus {
            border-color: var(--primary);
        }

        /* Responsive Design */
        @media (max-width: 1024px) {
            body {
                flex-direction: column;
            }
            .sidebar {
                width: 100%;
                height: auto;
                position: relative;
                border-right: none;
                border-bottom: 1px solid var(--border-color);
            }
            .sidebar-menu {
                flex-direction: row;
                padding: 12px;
                overflow-x: auto;
            }
            .main-content {
                margin-left: 0;
                width: 100%;
                padding: 24px;
            }
            .dashboard-grid {
                grid-template-columns: 1fr;
            }
        }

        /* Print Media Styles for PDF Export */
        @media print {
            /* Force the browser to render exact backgrounds, gradients, and colors */
            * {
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
                color-adjust: exact !important;
            }

            /* Scale down the layout to fit standard paper beautifully without being zoomed in */
            body {
                zoom: 78% !important;
                display: block !important;
                min-height: auto !important;
                background-color: var(--bg-primary) !important;
                color: var(--text-primary) !important;
            }
            
            /* Hide UI components that do not belong in a PDF */
            .sidebar, 
            .theme-toggle, 
            .sidebar-footer, 
            .sidebar-brand,
            .detailed-selector-wrapper,
            .filter-container,
            .filter-buttons,
            button,
            .btn-pdf,
            .header-badge,
            .card-header .badge,
            .brand-logo {
                display: none !important;
            }
            
            .main-content {
                margin-left: 0 !important;
                width: 100% !important;
                padding: 0 !important;
                box-shadow: none !important;
            }
            
            /* Keep theme cards with their native background and border colors */
            .dashboard-card, 
            .report-section-card,
            .conclusion-card {
                background-color: var(--bg-secondary) !important;
                border: 1px solid var(--border-color) !important;
                box-shadow: none !important;
                page-break-inside: avoid;
                margin-bottom: 16px !important;
                padding: 14px !important;
                border-radius: 8px !important;
            }
            
            /* Table Print Styling using Theme Colors */
            table {
                border-collapse: collapse !important;
                width: 100% !important;
            }
            
            th, td {
                border: 1px solid var(--border-color) !important;
                padding: 6px 10px !important;
            }
            
            th {
                background-color: var(--bg-tertiary) !important;
                color: var(--text-primary) !important;
                font-weight: 700 !important;
            }

            td {
                color: var(--text-secondary) !important;
            }
            
            /* Metadata Grid Layout for Print using Theme Colors */
            .report-grid-meta {
                display: grid !important;
                grid-template-columns: 1fr 1fr !important;
                border: 1px solid var(--border-color) !important;
                margin-bottom: 16px !important;
                background-color: var(--bg-secondary) !important;
                gap: 0 !important;
            }
            
            .meta-item {
                border-bottom: 1px solid var(--border-color) !important;
                border-right: 1px solid var(--border-color) !important;
                padding: 8px 12px !important;
            }
            
            /* Keep Status Banners styled exactly as on screen */
            .status-banner {
                box-shadow: none !important;
                margin-bottom: 16px !important;
                border: 1px solid var(--border-color) !important;
            }
            
            /* Section Titles print border */
            .report-section-card h3 {
                border-bottom: 2px solid var(--border-color) !important;
                padding-bottom: 6px !important;
                margin-bottom: 12px !important;
                display: flex !important;
                align-items: center !important;
                gap: 8px !important;
                color: var(--text-primary) !important;
            }
            
            .report-section-card h3 svg {
                display: none !important; /* Hide icons in print for a cleaner paper layout */
            }
            
            /* Only print the active section */
            .section-view {
                display: none !important;
            }
            
            .section-view.active {
                display: block !important;
            }
        }
    </style>
</head>
<body>

    <!-- Sidebar Navigation -->
    <div class="sidebar">
        <div class="sidebar-brand">
            <div class="brand-logo">R</div>
            <div class="brand-name">Rogers QA Automation</div>
        </div>
        <div class="sidebar-menu">
            <button id="nav-dashboard" class="menu-item active" onclick="switchTab('dashboard')">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2H6a2 2 0 01-2-2v-4zM14 16a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2h-2a2 2 0 01-2-2v-4z" />
                </svg>
                Overview Dashboard
            </button>
            <button id="nav-detailed" class="menu-item" onclick="switchTab('detailed')">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                Detailed Reports
            </button>
        </div>
        <div class="sidebar-footer">
            <span style="font-size: 0.8rem; color: var(--text-muted);">Version 1.0.0</span>
            <button class="theme-toggle" onclick="toggleTheme()" aria-label="Toggle Light/Dark Theme">
                <!-- Sun Icon -->
                <svg class="sun-icon" style="display:none;" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 9H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707m2.828-9.9a5 5 0 117.071 7.07m2.827 2.83l-.707.707M6.343 6.343l-.707.707" />
                </svg>
                <!-- Moon Icon -->
                <svg class="moon-icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                </svg>
            </button>
        </div>
    </div>

    <!-- Main Content Area -->
    <div class="main-content">
        
        <!-- Header -->
        <div class="content-header">
            <div class="header-title">
                <h1 id="page-title">QA Automation Dashboard</h1>
                <p id="page-subtitle">A comprehensive overview of test automation runs, metrics, and defect trends.</p>
            </div>
            <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
                <button class="btn-pdf" onclick="exportToPDF()" style="display: flex; align-items: center; gap: 8px; font-weight: 600; padding: 10px 16px; border-radius: 8px; background-color: var(--primary); color: white; border: none; cursor: pointer; transition: var(--transition); font-family: 'Inter', sans-serif; font-size: 0.9rem; box-shadow: 0 4px 10px rgba(196, 18, 48, 0.2);">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" style="width: 18px; height: 18px;">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    Export PDF
                </button>
                <div class="header-badge" id="execution-date-badge">
                    Executed: --
                </div>
            </div>
        </div>

        <!-- SECTION 1: OVERVIEW DASHBOARD -->
        <div id="section-dashboard" class="section-view active">
            
            <!-- Metric Cards -->
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-info">
                        <h3>Total Test Cases</h3>
                        <div class="metric-value" id="stat-total">0</div>
                        <div class="metric-desc">Executed from test suite</div>
                    </div>
                    <div class="metric-icon metric-blue">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
                        </svg>
                    </div>
                </div>
                <div class="metric-card">
                    <div class="metric-info">
                        <h3>Passed Cases</h3>
                        <div class="metric-value" style="color: var(--success);" id="stat-passed">0</div>
                        <div class="metric-desc" id="stat-passed-percent">0% of total</div>
                    </div>
                    <div class="metric-icon metric-green">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                    </div>
                </div>
                <div class="metric-card">
                    <div class="metric-info">
                        <h3>Failed Cases</h3>
                        <div class="metric-value" style="color: var(--danger);" id="stat-failed">0</div>
                        <div class="metric-desc" id="stat-failed-percent">0% of total</div>
                    </div>
                    <div class="metric-icon metric-red">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                    </div>
                </div>
                <div class="metric-card">
                    <div class="metric-info">
                        <h3>Success Rate</h3>
                        <div class="metric-value" style="color: var(--primary);" id="stat-rate">0%</div>
                        <div class="metric-desc">Target threshold: 90%</div>
                    </div>
                    <div class="metric-icon metric-purple">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 3.055A9.003 9.003 0 1020.945 13H11V3.055z" />
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.488 9H15V3.512A9.025 9.025 0 0120.488 9z" />
                        </svg>
                    </div>
                </div>
            </div>

            <!-- Charts & Action Items Grid -->
            <div class="dashboard-grid">
                <!-- Doughnut Chart -->
                <div class="dashboard-card">
                    <div class="card-header">
                        <h2>Automation Testing Status</h2>
                        <span class="badge badge-info">Real-time</span>
                    </div>
                    <div class="card-body" style="display: flex; align-items: center; justify-content: center; min-height: 280px; position: relative;">
                        <div style="width: 260px; height: 260px;">
                            <canvas id="statusChart"></canvas>
                        </div>
                    </div>
                </div>

                <!-- Priorities Card -->
                <div class="dashboard-card">
                    <div class="card-header">
                        <h2>Upcoming Week Priorities</h2>
                    </div>
                    <div class="card-body">
                        <div class="priority-list">
                            <div class="priority-item">
                                <div class="priority-num">1</div>
                                <div class="priority-text">
                                    <h4 id="priority-project-id">Analyze Project: --</h4>
                                    <p>Investigate early session terminations causing failures across multiple test runs.</p>
                                </div>
                            </div>
                            <div class="priority-item">
                                <div class="priority-num">2</div>
                                <div class="priority-text">
                                    <h4>Investigate TC ID 2-10</h4>
                                    <p>The agent is terminating immediately after the welcoming greeting Ban Info/Account Disambig.</p>
                                </div>
                            </div>
                            <div class="priority-item">
                                <div class="priority-num">3</div>
                                <div class="priority-text">
                                    <h4>Update Expectations</h4>
                                    <p>Verify if 'customerIdentification' variable expectations need to be updated to match the new API response.</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Defect Trend & Cost Estimation Grid -->
            <div class="dashboard-grid">
                <!-- Trend Chart -->
                <div class="dashboard-card">
                    <div class="card-header">
                        <h2>Expectation Evaluations per Test Case</h2>
                        <span class="badge badge-pass">Metrics</span>
                    </div>
                    <div class="card-body" style="min-height: 280px;">
                        <div style="width: 100%; height: 260px;">
                            <canvas id="trendChart"></canvas>
                        </div>
                    </div>
                </div>

                <!-- Cost Estimation Card -->
                <div class="dashboard-card">
                    <div class="card-header">
                        <h2>Weekly Automation Cost Estimation</h2>
                    </div>
                    <div class="card-body" style="padding: 0;">
                        <table class="cost-table">
                            <thead>
                                <tr>
                                    <th>Costs</th>
                                    <th style="text-align: right;">Automation Testing</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td>Design Test Case</td>
                                    <td style="text-align: right; font-weight: 600; color: var(--text-primary);">$7,000</td>
                                </tr>
                                <tr>
                                    <td>Tool Cost</td>
                                    <td style="text-align: right; font-weight: 600; color: var(--text-primary);">$1,500</td>
                                </tr>
                                <tr>
                                    <td>Implement Automation</td>
                                    <td style="text-align: right; font-weight: 600; color: var(--text-primary);">$4,500</td>
                                </tr>
                                <tr>
                                    <td>Full Cycle Cost Per Release</td>
                                    <td style="text-align: right; font-weight: 600; color: var(--text-primary);">$12,000</td>
                                </tr>
                                <tr>
                                    <td>Estimated Savings (vs Manual)</td>
                                    <td style="text-align: right; font-weight: 600; color: var(--success);">$8,400</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- Automation Testing Weekly Summary Table -->
            <div class="dashboard-card" style="margin-bottom: 32px;">
                <div class="card-header">
                    <h2>Automation Testing Weekly Summary</h2>
                </div>
                <div class="card-body" style="padding: 0;">
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Test Type</th>
                                    <th>Total</th>
                                    <th>Pass</th>
                                    <th>Fail</th>
                                    <th>Pending</th>
                                    <th>Ignored</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td style="font-weight: 600; color: var(--text-primary);">Automated</td>
                                    <td id="summary-auto-total" style="font-weight: 600;">0</td>
                                    <td id="summary-auto-pass" style="color: var(--success); font-weight: 600;">0 (0%)</td>
                                    <td id="summary-auto-fail" style="color: var(--danger); font-weight: 600;">0 (0%)</td>
                                    <td>0 (0%)</td>
                                    <td>0 (0%)</td>
                                </tr>
                                <tr>
                                    <td style="font-weight: 600; color: var(--text-primary);">Manual</td>
                                    <td style="font-weight: 600;">0</td>
                                    <td>0 (0%)</td>
                                    <td>0 (0%)</td>
                                    <td>0 (0%)</td>
                                    <td>0 (0%)</td>
                                </tr>
                                <tr style="background-color: var(--bg-tertiary); font-weight: bold;">
                                    <td style="color: var(--text-primary);">Total</td>
                                    <td id="summary-total-total" style="color: var(--text-primary);">0</td>
                                    <td id="summary-total-pass" style="color: var(--success);">0 (0%)</td>
                                    <td id="summary-total-fail" style="color: var(--danger);">0 (0%)</td>
                                    <td style="color: var(--text-primary);">0 (0%)</td>
                                    <td style="color: var(--text-primary);">0 (0%)</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- Automation Testing Result Report Table -->
            <div class="dashboard-card">
                <div class="card-header">
                    <h2>Automation Testing Result Report</h2>
                    <span class="badge badge-info" id="table-results-count">Total: 0</span>
                </div>
                <div class="card-body">
                    
                    <!-- Search & Filter Controls -->
                    <div class="filters-row">
                        <div class="search-input-wrapper">
                            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                            </svg>
                            <input type="text" id="tableSearch" class="search-input" placeholder="Search by Test Case ID or Description..." onkeyup="filterTable()">
                        </div>
                        <div class="filter-buttons">
                            <button id="filter-all" class="btn active" onclick="setTableFilter('all')">All</button>
                            <button id="filter-pass" class="btn" onclick="setTableFilter('passed')">Passed</button>
                            <button id="filter-fail" class="btn" onclick="setTableFilter('failed')">Failed</button>
                        </div>
                    </div>

                    <!-- Table -->
                    <div class="table-container">
                        <table id="resultsTable">
                            <thead>
                                <tr>
                                    <th style="width: 80px;">TC ID</th>
                                    <th>Summary Description</th>
                                    <th style="width: 120px;">Region</th>
                                    <th style="width: 200px;">Date & Time</th>
                                    <th style="width: 120px; text-align: center;">Status</th>
                                    <th style="width: 130px; text-align: right;">Action</th>
                                </tr>
                            </thead>
                            <tbody id="resultsTableBody">
                                <!-- Dynamic Rows -->
                            </tbody>
                        </table>
                    </div>

                </div>
            </div>

        </div>

        <!-- SECTION 2: DETAILED REPORTS -->
        <div id="section-detailed" class="section-view">
            
            <!-- Selector Row -->
            <div class="detailed-selector-wrapper">
                <div class="detailed-selector-info">
                    <h3>Inspect Test Case Execution</h3>
                    <p>Select a Test Case ID to view the full objective, transcription logs, and expectations evaluation.</p>
                </div>
                <div>
                    <select id="tcSelector" class="select-input" onchange="loadTestCaseReport(this.value)">
                        <!-- Dynamic Options -->
                    </select>
                </div>
            </div>

            <!-- Dynamic Report Content -->
            <div id="detailed-report-content">
                
                <!-- Status Banner -->
                <div id="report-banner" class="status-banner">
                    <div class="status-banner-title">
                        <div class="status-banner-icon">
                            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" style="width: 24px; height: 24px;">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                            </svg>
                        </div>
                        <div class="status-banner-text">
                            <h2 id="report-tcid-header">QA Test Execution Report: TCID --</h2>
                            <p id="report-session-id">Session ID: --</p>
                        </div>
                    </div>
                    <div class="status-banner-stamp" id="report-stamp">PASSED</div>
                </div>

                <!-- Metadata Grid -->
                <div class="report-grid-meta">
                    <div class="meta-item">
                        <span class="meta-label">Test Case ID (TCID)</span>
                        <span class="meta-val" id="meta-tcid">--</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Project Id</span>
                        <span class="meta-val" id="meta-project-id">--</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Region</span>
                        <span class="meta-val" id="meta-region">--</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Target App</span>
                        <span class="meta-val" id="meta-app-id" style="font-family: monospace; font-size: 0.8rem;">--</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Date & Time</span>
                        <span class="meta-val" id="meta-date">--</span>
                    </div>
                </div>

                <!-- Objective & Scope -->
                <div class="report-section-card">
                    <h3>
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        Objective & Scope
                    </h3>
                    <div class="objective-content" id="report-objective">
                        --
                    </div>
                </div>

                <!-- Full Transcript -->
                <div class="report-section-card">
                    <h3>
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                        </svg>
                        Full Transcript
                    </h3>
                    <div class="table-container">
                        <table class="transcript-table">
                            <thead>
                                <tr>
                                    <th style="width: 140px;">Speaker</th>
                                    <th>Utterance</th>
                                    <th style="width: 45%; max-width: 500px;">Key Tool Calls / Session Variables Set</th>
                                </tr>
                            </thead>
                            <tbody id="transcriptTableBody">
                                <!-- Dynamic Rows -->
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Evaluations of Expectations -->
                <div class="report-section-card">
                    <h3>
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-12 7h.01M11 12h.01M9 16h.01M11 16h.01" />
                        </svg>
                        Evaluations of Expectations
                    </h3>
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th style="width: 250px;">Expectation Target</th>
                                    <th>Expected Value / Behavior</th>
                                    <th>Observed Value / Behavior</th>
                                    <th style="width: 120px; text-align: center;">Status</th>
                                </tr>
                            </thead>
                            <tbody id="expectationsTableBody">
                                <!-- Dynamic Rows -->
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Conclusion -->
                <div class="report-section-card">
                    <h3>
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                        </svg>
                        Conclusion & Summary Analysis
                    </h3>
                    <div id="report-conclusion" class="conclusion-card">
                        --
                    </div>
                </div>

            </div>

        </div>

    </div>

    <!-- JavaScript Data and Operations -->
    <script>
        // Raw Data injected by Python script
        const testCasesData = ##TEST_CASES_DATA##;
        
        let activeTab = 'dashboard';
        let tableFilterStatus = 'all';
        let statusChartInstance = null;
        let trendChartInstance = null;

        // Initialize App on load
        window.onload = function() {
            // Check theme preference
            const savedTheme = localStorage.getItem('theme') || 'dark';
            document.documentElement.setAttribute('data-theme', savedTheme);
            updateThemeIcons(savedTheme);
            
            if (testCasesData.length > 0) {
                // Populate Metrics
                calculateMetrics();
                
                // Populate Table
                renderResultsTable();
                
                // Populate Charts
                renderStatusChart();
                renderTrendChart();
                
                // Populate Selector
                populateTestCaseSelector();
                
                // Load First Test Case by default in Detailed View
                loadTestCaseReport(testCasesData[0].tcid);
                
                // Set Execution Date
                const latestDate = testCasesData[0].timestamp || '--';
                document.getElementById('execution-date-badge').innerText = `Executed: ${latestDate}`;
            }
        };

        // Export current active view to PDF
        function exportToPDF() {
            window.print();
        }

        // Tab Switching
        function switchTab(tabId) {
            activeTab = tabId;
            document.querySelectorAll('.menu-item').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.section-view').forEach(el => el.classList.remove('active'));
            
            const titleEl = document.getElementById('page-title');
            const subtitleEl = document.getElementById('page-subtitle');

            if (tabId === 'dashboard') {
                document.getElementById('nav-dashboard').classList.add('active');
                document.getElementById('section-dashboard').classList.add('active');
                titleEl.innerText = "QA Automation Dashboard";
                subtitleEl.innerText = "A comprehensive overview of test automation runs, metrics, and defect trends.";
            } else {
                document.getElementById('nav-detailed').classList.add('active');
                document.getElementById('section-detailed').classList.add('active');
                titleEl.innerText = "QA Test Execution Report";
                subtitleEl.innerText = "Detailed transcription logs, expectation checks, and session variables for individual test cases.";
            }
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        // Theme Toggle
        function toggleTheme() {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcons(newTheme);
            
            // Re-render charts to update colors for light/dark themes
            renderStatusChart();
            renderTrendChart();
        }

        function updateThemeIcons(theme) {
            const sunIcon = document.querySelector('.sun-icon');
            const moonIcon = document.querySelector('.moon-icon');
            if (theme === 'dark') {
                sunIcon.style.display = 'block';
                moonIcon.style.display = 'none';
            } else {
                sunIcon.style.display = 'none';
                moonIcon.style.display = 'block';
            }
        }

        // Calculate and Display Metrics
        function calculateMetrics() {
            const total = testCasesData.length;
            const passed = testCasesData.filter(tc => tc.result === 'passed').length;
            const failed = total - passed;
            const rate = total > 0 ? Math.round((passed / total) * 100) : 0;
            
            document.getElementById('stat-total').innerText = total;
            document.getElementById('stat-passed').innerText = passed;
            document.getElementById('stat-passed-percent').innerText = `${total > 0 ? Math.round((passed / total) * 100) : 0}% of total`;
            document.getElementById('stat-failed').innerText = failed;
            document.getElementById('stat-failed-percent').innerText = `${total > 0 ? Math.round((failed / total) * 100) : 0}% of total`;
            document.getElementById('stat-rate').innerText = `${rate}%`;
            
            // Populate Priorities Project ID dynamically
            if (testCasesData[0] && testCasesData[0].project_id) {
                document.getElementById('priority-project-id').innerText = `Analyze Project: ${testCasesData[0].project_id}`;
            }

            // Populate Weekly Summary Table
            document.getElementById('summary-auto-total').innerText = total;
            document.getElementById('summary-auto-pass').innerText = `${passed} (${rate}%)`;
            document.getElementById('summary-auto-fail').innerText = `${failed} (${total > 0 ? 100 - rate : 0}%)`;
            
            document.getElementById('summary-total-total').innerText = total;
            document.getElementById('summary-total-pass').innerText = `${passed} (${rate}%)`;
            document.getElementById('summary-total-fail').innerText = `${failed} (${total > 0 ? 100 - rate : 0}%)`;
        }

        // Render Overview Results Table
        function renderResultsTable() {
            const tbody = document.getElementById('resultsTableBody');
            tbody.innerHTML = '';
            
            let filteredData = testCasesData;
            if (tableFilterStatus === 'passed') {
                filteredData = testCasesData.filter(tc => tc.result === 'passed');
            } else if (tableFilterStatus === 'failed') {
                filteredData = testCasesData.filter(tc => tc.result === 'failed');
            }
            
            document.getElementById('table-results-count').innerText = `Total: ${filteredData.length}`;

            filteredData.forEach(tc => {
                const tr = document.createElement('tr');
                tr.onclick = function() {
                    loadTestCaseReport(tc.tcid);
                    switchTab('detailed');
                };
                
                const badgeClass = tc.result === 'passed' ? 'badge-pass' : 'badge-fail';
                const summaryText = tc.reasoning ? tc.reasoning.split('.')[0] + '.' : 'No description available';
                
                tr.innerHTML = `
                    <td style="font-weight: 700; color: var(--primary);">TC-${tc.tcid}</td>
                    <td>
                        <div style="font-weight: 600; color: var(--text-primary); margin-bottom: 4px;">Test Case ${tc.tcid}</div>
                        <div style="font-size: 0.825rem; color: var(--text-muted); text-overflow: ellipsis; overflow: hidden; white-space: nowrap; max-width: 500px;">
                            ${summaryText}
                        </div>
                    </td>
                    <td><span class="badge badge-info">${(tc.region || 'US').toUpperCase()}</span></td>
                    <td style="font-size: 0.85rem;">${tc.timestamp || 'N/A'}</td>
                    <td style="text-align: center;">
                        <span class="badge ${badgeClass}">${tc.result.toUpperCase()}</span>
                    </td>
                    <td style="text-align: right;">
                        <button class="btn" style="padding: 4px 10px; font-size: 0.75rem;">View Report</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
            
            if (filteredData.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="6" style="text-align: center; padding: 40px; color: var(--text-muted);">
                            No test cases found matching the criteria.
                        </td>
                    </tr>
                `;
            }
        }

        // Table Filtering & Search
        function setTableFilter(status) {
            tableFilterStatus = status;
            document.querySelectorAll('.filter-buttons .btn').forEach(btn => btn.classList.remove('active'));
            document.getElementById(`filter-${status === 'all' ? 'all' : status === 'passed' ? 'pass' : 'fail'}`).classList.add('active');
            renderResultsTable();
        }

        function filterTable() {
            const query = document.getElementById('tableSearch').value.toLowerCase();
            const rows = document.querySelectorAll('#resultsTableBody tr');
            
            rows.forEach(row => {
                const text = row.innerText.toLowerCase();
                if (text.includes(query)) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        }

        // Populate Detailed Report Selector Dropdown
        function populateTestCaseSelector() {
            const select = document.getElementById('tcSelector');
            select.innerHTML = '';
            
            testCasesData.forEach(tc => {
                const option = document.createElement('option');
                option.value = tc.tcid;
                const statusSymbol = tc.result === 'passed' ? '✓' : '✗';
                option.innerText = `[TC-${tc.tcid}] ${statusSymbol} Test Case ${tc.tcid}`;
                select.appendChild(option);
            });
        }

        // Helper to perform variable diffs between turns
        function getVariableDiff(currentVars, previousVars) {
            if (!previousVars) return currentVars || {};
            const diff = {};
            for (const [key, val] of Object.entries(currentVars || {})) {
                if (previousVars[key] !== val) {
                    diff[key] = val;
                }
            }
            return diff;
        }

        // Helper to parse expectation strings into structured layout
        function parseExpectation(exp) {
            const text = exp.expectation;
            const actual = exp.actual;
            const status = exp.result; // "passed" or "failed"
            
            let target = "Variable";
            let expected = text;
            
            if (text.toLowerCase().includes("says") || text.toLowerCase().includes("prompt") || text.toLowerCase().includes("greet") || text.toLowerCase().includes("welcome")) {
                target = "Transcript";
                const match = text.match(/['"](.*?)['"]/);
                if (match) {
                    expected = `Contains phrase: "${match[1]}"`;
                } else {
                    expected = text.replace(/^(Agent\\s+says\\s*:\\s*|Agent\\s+says\\s*)/i, "Agent says: ");
                }
            } else if (text.includes("=")) {
                const parts = text.split("=");
                const varName = parts[0].trim();
                target = `Variable (${varName})`;
                expected = parts[1].trim();
            } else if (text.toLowerCase().includes("counter") || text.toLowerCase().includes("should be")) {
                target = "Variable";
            }
            
            return {
                target: target,
                expected: expected,
                observed: actual || "Not returned or evaluated",
                status: status
            };
        }

        // Load and Render Detailed Test Case Report
        function loadTestCaseReport(tcid) {
            const tc = testCasesData.find(item => item.tcid === tcid);
            if (!tc) return;

            // Sync selector value
            document.getElementById('tcSelector').value = tcid;

            // Header & Banner
            document.getElementById('report-tcid-header').innerText = `QA Test Execution Report: TCID ${tc.tcid}`;
            document.getElementById('report-session-id').innerText = `Session ID: ${tc.session_id || 'N/A'}`;
            
            const banner = document.getElementById('report-banner');
            const stamp = document.getElementById('report-stamp');
            const bannerIconWrapper = document.querySelector('.status-banner-icon');
            
            if (tc.result === 'passed') {
                banner.className = 'status-banner status-banner-passed';
                stamp.innerText = "PASSED";
                bannerIconWrapper.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" style="width: 24px; height: 24px;">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                `;
            } else {
                banner.className = 'status-banner status-banner-failed';
                stamp.innerText = "FAILED";
                bannerIconWrapper.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" style="width: 24px; height: 24px;">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                `;
            }

            // Metadata
            document.getElementById('meta-tcid').innerText = tc.tcid;
            document.getElementById('meta-project-id').innerText = tc.project_id || '--';
            document.getElementById('meta-region').innerText = (tc.region || '--').toUpperCase();
            document.getElementById('meta-app-id').innerText = tc.app_id || '--';
            document.getElementById('meta-date').innerText = tc.timestamp || '--';

            // Objective & Scope
            const objective = tc.reasoning ? `This test case (TCID ${tc.tcid}) validates the Dialogflow CX Virtual Agent's dialog flows, intent routing, and session variable assignments during user-agent interactions. Specific focus is placed on assessing greeting phrases, multiple accounts disambiguation, ban info checks, and correct updates to key session variables.` : `No detailed objective available for TCID ${tc.tcid}.`;
            document.getElementById('report-objective').innerText = objective;

            // Full Transcript
            const transcriptBody = document.getElementById('transcriptTableBody');
            transcriptBody.innerHTML = '';
            
            let previousVars = null;
            if (tc.transcript && tc.transcript.length > 0) {
                tc.transcript.forEach(turn => {
                    const tr = document.createElement('tr');
                    
                    let speakerClass = 'speaker-system';
                    if (turn.speaker.toLowerCase() === 'caller' || turn.speaker.toLowerCase() === 'user') {
                        speakerClass = 'speaker-caller';
                    } else if (turn.speaker.toLowerCase() === 'agent') {
                        speakerClass = 'speaker-agent';
                    }

                    // Compute variable diff
                    const diffVars = getVariableDiff(turn.variables, previousVars);
                    previousVars = turn.variables;

                    let varsHtml = '<span class="variables-empty">No session variables set/changed</span>';
                    if (Object.keys(diffVars).length > 0) {
                        varsHtml = '<div class="variables-wrapper">';
                        for (const [k, v] of Object.entries(diffVars)) {
                            varsHtml += `
                                <div class="variable-pill">
                                    <span class="variable-name">${k}</span>
                                    <span class="variable-value">= ${v}</span>
                                </div>
                            `;
                        }
                        varsHtml += '</div>';
                    }

                    tr.innerHTML = `
                        <td>
                            <span class="speaker-badge ${speakerClass}">${turn.speaker}</span>
                        </td>
                        <td class="utterance-cell">${turn.utterance}</td>
                        <td>${varsHtml}</td>
                    `;
                    transcriptBody.appendChild(tr);
                });
            } else {
                transcriptBody.innerHTML = `
                    <tr>
                        <td colspan="3" style="text-align: center; color: var(--text-muted); font-style: italic;">
                            No transcript turns recorded for this test case.
                        </td>
                    </tr>
                `;
            }

            // Expectations Table
            const expectationsBody = document.getElementById('expectationsTableBody');
            expectationsBody.innerHTML = '';

            if (tc.expectations && tc.expectations.length > 0) {
                tc.expectations.forEach(exp => {
                    const parsed = parseExpectation(exp);
                    const tr = document.createElement('tr');
                    const badgeClass = parsed.status === 'passed' ? 'badge-pass' : 'badge-fail';
                    
                    tr.innerHTML = `
                        <td style="font-weight: 700; color: var(--text-primary); font-family: monospace; font-size: 0.85rem;">
                            ${parsed.target}
                        </td>
                        <td>${parsed.expected}</td>
                        <td style="font-family: monospace; font-size: 0.85rem;">${parsed.observed}</td>
                        <td style="text-align: center;">
                            <span class="badge ${badgeClass}">${parsed.status.toUpperCase()}</span>
                        </td>
                    `;
                    expectationsBody.appendChild(tr);
                });
            } else {
                expectationsBody.innerHTML = `
                    <tr>
                        <td colspan="4" style="text-align: center; color: var(--text-muted); font-style: italic;">
                            No expectations evaluated for this test case.
                        </td>
                    </tr>
                `;
            }

            // Conclusion Card
            const conclusionEl = document.getElementById('report-conclusion');
            conclusionEl.innerText = tc.reasoning || "No concluding remarks or reasoning recorded.";
            if (tc.result === 'passed') {
                conclusionEl.className = 'conclusion-card conclusion-card-passed';
            } else {
                conclusionEl.className = 'conclusion-card conclusion-card-failed';
            }
        }

        // Render Doughnut Chart
        function renderStatusChart() {
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            const textPrimary = isDark ? '#f9fafb' : '#0f172a';
            
            const passed = testCasesData.filter(tc => tc.result === 'passed').length;
            const failed = testCasesData.length - passed;

            if (statusChartInstance) {
                statusChartInstance.destroy();
            }

            const ctx = document.getElementById('statusChart').getContext('2d');
            statusChartInstance = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: ['Passed', 'Failed'],
                    datasets: [{
                        data: [passed, failed],
                        backgroundColor: ['#10b981', '#ef4444'],
                        borderWidth: isDark ? 2 : 1,
                        borderColor: isDark ? '#111827' : '#ffffff',
                        hoverOffset: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                color: textPrimary,
                                font: {
                                    family: 'Inter',
                                    size: 12,
                                    weight: '500'
                                }
                            }
                        }
                    },
                    cutout: '65%'
                }
            });
        }

        // Render Expectations Line Chart
        function renderTrendChart() {
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            const textPrimary = isDark ? '#f9fafb' : '#0f172a';
            const gridColor = isDark ? '#374151' : '#e2e8f0';

            // Get expectations data for each test case
            const labels = testCasesData.map(tc => `TC-${tc.tcid}`);
            const totalExpectations = testCasesData.map(tc => tc.expectations ? tc.expectations.length : 0);
            const passedExpectations = testCasesData.map(tc => tc.expectations ? tc.expectations.filter(e => e.result === 'passed').length : 0);

            if (trendChartInstance) {
                trendChartInstance.destroy();
            }

            const ctx = document.getElementById('trendChart').getContext('2d');
            trendChartInstance = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'Total Expectations',
                            data: totalExpectations,
                            borderColor: '#3b82f6',
                            backgroundColor: 'rgba(59, 130, 246, 0.1)',
                            borderWidth: 2.5,
                            fill: true,
                            tension: 0.3
                        },
                        {
                            label: 'Passed Expectations',
                            data: passedExpectations,
                            borderColor: '#10b981',
                            backgroundColor: 'rgba(16, 185, 129, 0.05)',
                            borderWidth: 2.5,
                            fill: false,
                            tension: 0.3
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'top',
                            labels: {
                                color: textPrimary,
                                font: {
                                    family: 'Inter',
                                    size: 11
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: {
                                color: gridColor
                            },
                            ticks: {
                                color: textPrimary
                            }
                        },
                        y: {
                            grid: {
                                color: gridColor
                            },
                            ticks: {
                                color: textPrimary,
                                stepSize: 1
                            },
                            beginAtZero: true
                        }
                    }
                }
            });
        }
    </script>
</body>
</html>
"""

def generate_report(results_file_path: str, output_html_path: str):
    print(f"Reading QA results from: {results_file_path}")
    if not os.path.exists(results_file_path):
        print(f"Error: Results file not found at '{results_file_path}'.")
        return False
        
    test_cases = []
    try:
        with open(results_file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    test_cases.append(json.loads(line))
                except json.JSONDecodeError as je:
                    print(f"Warning: Skipping malformed JSON line: {je}")
    except Exception as e:
        print(f"Error reading results file: {e}")
        return False
        
    if not test_cases:
        print("Error: No test cases found in the results file.")
        return False
        
    print(f"Loaded {len(test_cases)} test case results.")
    
    # Sort test cases by TC ID (numerical sort if possible)
    try:
        test_cases.sort(key=lambda x: int(x.get("tcid", 0)))
    except Exception:
        test_cases.sort(key=lambda x: str(x.get("tcid", "")))
        
    # Serialize the data to inject into the HTML template
    test_cases_json = json.dumps(test_cases, ensure_ascii=False)
    
    # Replace the placeholder in the template
    report_content = HTML_TEMPLATE.replace("##TEST_CASES_DATA##", test_cases_json)
    
    # Ensure the output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_html_path)), exist_ok=True)
    
    # Write the report to file
    try:
        with open(output_html_path, "w", encoding="utf-8") as f:
            f.write(report_content)
        print(f"Successfully generated HTML report at: {output_html_path}")
        return True
    except Exception as e:
        print(f"Error writing HTML report: {e}")
        return False

# =====================================================================

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
    parser.add_argument(
        "--no_report",
        action="store_false",
        dest="generate_report",
        help="Do not automatically generate the HTML report after the test run finishes"
    )
    parser.add_argument(
        "--report_html",
        type=str,
        default="",
        help="Custom path where the output HTML report should be saved (defaults to report.html in the output directory)"
    )
    parser.add_argument(
        "--project_id",
        type=str,
        default=PROJECT_ID,
        help="GCP Project ID for the agent under test (default: GCP_PROJECT_ID env var)"
    )
    parser.add_argument(
        "--region_id",
        type=str,
        default=REGION_ID,
        help="GCP Region ID for the agent under test (default: GCP_REGION_ID env var)"
    )
    parser.add_argument(
        "--app_id",
        type=str,
        default=APP_ID,
        help="Dialogflow CX Application/Agent ID (default: GCP_APP_ID env var)"
    )
    parser.add_argument(
        "--gemini_api_key",
        type=str,
        default=GEMINI_API_KEY,
        help="Gemini API Key for the ADK LLM agent (default: GEMINI_API_KEY env var)"
    )
    args = parser.parse_args()

    # Extract configuration
    gcp_project = args.project_id
    gcp_region = args.region_id
    gcp_app = args.app_id

    # Configure Gemini API Key if passed
    if args.gemini_api_key and args.gemini_api_key != "YOUR_GEMINI_API_KEY_HERE":
        os.environ["GEMINI_API_KEY"] = args.gemini_api_key

    # Validate that configuration has been provided
    if gcp_project == "YOUR_GCP_PROJECT_ID_HERE" or gcp_app == "YOUR_DIALOGFLOW_CX_APP_ID_HERE":
        print("Error: GCP Project ID and Dialogflow CX App ID must be configured.")
        print("Please set them as environment variables (GCP_PROJECT_ID, GCP_APP_ID) or pass them as CLI arguments:")
        print("  --project_id <GCP_PROJECT_ID> --app_id <DIALOGFLOW_CX_APP_ID>")
        sys.exit(1)

    input_file_path = os.path.abspath(args.input_file)
    output_file_path = os.path.abspath(args.output_result)

    print("=" * 60)
    print("QA Automation Test Runner Starting")
    print("=" * 60)
    print(f"Target Project ID: {gcp_project}")
    print(f"Target Region ID:  {gcp_region}")
    print(f"Target App ID:     {gcp_app}")
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
            prompt = format_test_case_prompt(row, gcp_project, gcp_region, gcp_app)
            
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
                    result_json["project_id"] = gcp_project
                if "region" not in result_json:
                    result_json["region"] = gcp_region
                if "app_id" not in result_json:
                    result_json["app_id"] = gcp_app
                
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
                    "project_id": gcp_project,
                    "region": gcp_region,
                    "app_id": gcp_app,
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

    # Generate the interactive HTML report
    if args.generate_report:
        try:
            if args.report_html:
                html_output_path = os.path.abspath(args.report_html)
            else:
                html_output_path = os.path.join(os.path.dirname(output_file_path), "report.html")
            print("\nGenerating interactive HTML report...")
            generate_report(output_file_path, html_output_path)
        except Exception as e:
            print(f"\nWarning: Could not generate HTML report: {e}")
    else:
        print("\nSkipped HTML report generation (run without --no_report to generate it).")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
