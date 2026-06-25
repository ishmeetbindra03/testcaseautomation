import os

# Set environment variable to force GenAI to use Vertex AI
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"

import json
import warnings
import html
# Import your agent from your agent.py file

warnings.filterwarnings("ignore")

def generate_individual_html(row_result: dict) -> str:
    row_index = row_result.get("row_index", 0)
    input_data = row_result.get("input_data", {})
    agent_output = row_result.get("agent_output", {})

    agent_config = html.escape(str({
        "project_id": agent_output.get("project_id", "N/A"),
        "region": agent_output.get("region", "N/A"),
        "app_id": agent_output.get("app_id", "N/A"),
    }))

    test_procedure = html.escape(str(agent_output.get("original_test_procedure", "N/A")))
    

    print(f"Agent Output: {agent_output}")


    tcid = html.escape(str(agent_output.get("tcid", "N/A")))
    is_error = "error" in agent_output or not isinstance(agent_output, dict)
    

    overall_result = agent_output.get("overall_result", "failed")
    project_id = html.escape(str(agent_output.get("project_id", "N/A")))
    region = html.escape(str(agent_output.get("region", "N/A")))
    app_id = html.escape(str(agent_output.get("app_id", "N/A")))
    session_id = html.escape(str(agent_output.get("session_id", "N/A")))
    modality = html.escape(str(agent_output.get("modality", "text")))
    timestamp = html.escape(str(agent_output.get("timestamp", "N/A")))
    
    # Build expectations HTML
    expectations = agent_output.get("expectations", [])
    expectations_html = ""
    if isinstance(expectations, list):
        for idx, exp in enumerate(expectations):
            if isinstance(exp, dict):
                exp_text = html.escape(str(exp.get("expectation", "")))
                exp_result = html.escape(str(exp.get("result", "")))
                exp_actual = html.escape(str(exp.get("actual", "")))
                
                if exp_result == "passed":
                    icon = "✔️"
                    border_color = "rgba(16, 185, 129, 0.25)"
                    bg_color = "rgba(16, 185, 129, 0.04)"
                    label_color = "var(--accent-success)"
                else:
                    icon = "❌"
                    border_color = "rgba(244, 63, 94, 0.25)"
                    bg_color = "rgba(244, 63, 94, 0.04)"
                    label_color = "var(--accent-fail)"
                    
                extra_info = ""
                if "action" in exp:
                    action_escaped = html.escape(str(exp["action"]))
                    extra_info += f'<div style="font-style: italic; color: var(--text-secondary); margin-top: 4px;">{action_escaped}</div>'
                    
                if "session_variables" in exp and isinstance(exp["session_variables"], list):
                    var_items = []
                    for var in exp["session_variables"]:
                        if isinstance(var, dict):
                            v_name = html.escape(str(var.get("variable_name", "")))
                            v_obs = html.escape(str(var.get("observed_value", "")))
                            v_exp = html.escape(str(var.get("expected_value", "")))
                            v_res = html.escape(str(var.get("result", "")))
                            
                            v_color = "var(--accent-success)" if v_res == "passed" else "var(--accent-fail)"
                            v_icon = "✔️" if v_res == "passed" else "❌"
                            var_items.append(
                                f'<span class="variable-pill" style="border-color: {v_color}; color: {v_color};">'
                                f'{v_icon} {v_name}: {v_obs} (expected {v_exp})'
                                f'</span>'
                            )
                        else:
                            v_str = html.escape(str(var))
                            var_items.append(
                                f'<span class="variable-pill" style="color: var(--text-secondary);">'
                                f'{v_str}'
                                f'</span>'
                            )
                    if var_items:
                        extra_info += f'<div class="variables-pill-list" style="margin-top: 8px;">{" ".join(var_items)}</div>'
                        
                expectations_html += f"""
                <div class="expectation-item" style="border-color: {border_color}; background-color: {bg_color};">
                    <span class="expectation-status-icon">{icon}</span>
                    <div class="expectation-content">
                        <div class="expectation-label" style="color: {label_color}; font-weight: 600;">Expectation #{idx+1}</div>
                        <div class="expectation-actual" style="color: var(--text-primary); font-weight: 500;">{exp_text}</div>
                        {f'<div class="expectation-actual" style="margin-top: 4px;"><strong>Actual:</strong> {exp_actual}</div>' if exp_actual else ''}
                        {extra_info}
                    </div>
                </div>
                """
            else:
                exp_text = html.escape(str(exp))
                expectations_html += f"""
                <div class="expectation-item" style="border-color: rgba(244, 63, 94, 0.15); background-color: rgba(244, 63, 94, 0.02);">
                    <span class="expectation-status-icon">❓</span>
                    <div class="expectation-content">
                        <div class="expectation-label" style="color: var(--text-secondary); font-weight: 600;">Expectation #{idx+1}</div>
                        <div class="expectation-actual" style="color: var(--text-primary); font-weight: 500;">{exp_text}</div>
                    </div>
                </div>
                """
            
        if not expectations_html:
            expectations_html = '<div style="color: var(--text-secondary); font-style: italic;">No expectations listed in the JSON output.</div>'
            
        # Build Transcript HTML
        transcript = agent_output.get("transcript", [])
        transcript_html = ""
        if isinstance(transcript, list):
            for turn in transcript:
                if not isinstance(turn, dict):
                    turn_str = html.escape(str(turn))
                    transcript_html += f"""
                    <div class="chat-bubble bubble-caller">
                        <div class="bubble-text">{turn_str}</div>
                    </div>
                    """
                    continue
                turn_timestamp = html.escape(str(turn.get("timestamp", "")))
                speaker = html.escape(str(turn.get("speaker", "")))
                observed = html.escape(str(turn.get("observed_utterance", "")))
                expected = html.escape(str(turn.get("expected_utterance", "")))
                exp_type = html.escape(str(turn.get("transcript_expectation", "")))
                exp_status = html.escape(str(turn.get("transcript_expectation_status", "")))
                variables = turn.get("variables", {})
                if not isinstance(variables, dict):
                    variables = {}
                
                turn_event = turn.get("event")
                turn_dtmf = turn.get("dtmf")

                event_html = ""
                if turn_event:
                    event_esc = html.escape(str(turn_event))
                    event_html = f"""
                    <div class="bubble-event" style="margin-top: 6px; display: inline-flex; align-items: center; gap: 6px; background-color: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.25); color: #93c5fd; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-family: 'Fira Code', monospace; font-weight: 500; align-self: flex-start;">
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: inline-block; vertical-align: middle;"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"></path></svg>
                        <span>Event: <strong>{event_esc}</strong></span>
                    </div>
                    """
                
                dtmf_html = ""
                if turn_dtmf:
                    dtmf_esc = html.escape(str(turn_dtmf))
                    dtmf_html = f"""
                    <div class="bubble-dtmf" style="margin-top: 6px; display: inline-flex; align-items: center; gap: 6px; background-color: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.25); color: #fde047; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-family: 'Fira Code', monospace; font-weight: 500; align-self: flex-start;">
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: inline-block; vertical-align: middle;"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="9" y1="9" x2="9.01" y2="9"></line><line x1="15" y1="9" x2="15.01" y2="9"></line><line x1="9" y1="15" x2="9.01" y2="15"></line><line x1="15" y1="15" x2="15.01" y2="15"></line></svg>
                        <span>DTMF: <strong>{dtmf_esc}</strong></span>
                    </div>
                    """
                
                is_agent = (speaker.lower() == "agent")
                bubble_class = "bubble-agent" if is_agent else "bubble-caller"
                
                expectation_block = ""
                if is_agent and exp_status:
                    status_class = "expectation-passed" if exp_status == "passed" else "expectation-failed"
                    status_text = "PASSED" if exp_status == "passed" else "FAILED"
                    status_icon = "✔️" if exp_status == "passed" else "❌"
                    expectation_block = f"""
                    <div class="bubble-expectation {status_class}">
                        <div style="font-weight: 600; display: flex; align-items: center; gap: 4px;">
                            <span>{status_icon} Turn Expectation ({status_text})</span>
                        </div>
                        <div style="margin-top: 2px;"><strong>Expected:</strong> {expected}</div>
                        <div><strong>Match Mode:</strong> {exp_type}</div>
                    </div>
                    """
                    
                vars_html = ""
                if variables:
                    pills = []
                    for k, v in variables.items():
                        k_esc = html.escape(str(k))
                        v_esc = html.escape(str(v))
                        pills.append(f'<span class="variable-pill">{k_esc}: {v_esc}</span>')
                    vars_html = f"""
                    <details style="margin-top: 8px; cursor: pointer;">
                        <summary style="font-size: 11px; color: var(--text-secondary); font-weight: 500; outline: none; user-select: none;">Variables ({len(variables)})</summary>
                        <div class="variables-pill-list" style="margin-top: 6px;">{" ".join(pills)}</div>
                    </details>
                    """
                    
                transcript_html += f"""
                <div class="chat-bubble {bubble_class}">
                    <div class="bubble-meta">
                        <span class="bubble-speaker">{speaker}</span>
                        <span>{turn_timestamp}</span>
                    </div>
                    <div class="bubble-text">{observed if observed else '<span style="font-style: italic; color: var(--text-secondary);">[Silent / Empty]</span>'}</div>
                    {event_html}
                    {dtmf_html}
                    {expectation_block}
                    {vars_html}
                </div>
                """
            
        if not transcript_html:
            transcript_html = '<div style="color: var(--text-secondary); font-style: italic;">No transcript conversational entries.</div>'

    badge_class = "badge-passed" if overall_result == "passed" else "badge-failed"
    overall_result_upper = overall_result.upper()
    raw_json_str = json.dumps(row_result, indent=4).replace("</script>", "<\\/script>")

    cx_insights_link = ""
    if not is_error and session_id != "N/A" and project_id != "N/A" and region != "N/A":
        raw_project_id = str(agent_output.get("project_id", ""))
        raw_region = str(agent_output.get("region", ""))
        raw_session_id = str(agent_output.get("session_id", ""))
        if raw_project_id and raw_region and raw_session_id:
            url = f"https://ccai.cloud.google.com/insights/projects/{raw_project_id}/locations/{raw_region}/quality/conversations/{raw_session_id}"
            cx_insights_link = f"""
            <a href="{url}" target="_blank" style="color: var(--accent-info); text-decoration: none; margin-left: 8px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px; border: 1px solid rgba(59, 130, 246, 0.3); background-color: rgba(59, 130, 246, 0.1); padding: 2px 8px; border-radius: 4px; font-family: sans-serif; transition: all var(--transition-speed);" title="View in CX Insights" onmouseover="this.style.backgroundColor='rgba(59, 130, 246, 0.2)'; this.style.borderColor='rgba(59, 130, 246, 0.5)';" onmouseout="this.style.backgroundColor='rgba(59, 130, 246, 0.1)'; this.style.borderColor='rgba(59, 130, 246, 0.3)';">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: inline-block; vertical-align: middle;"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
                <span style="font-weight: 500;">CX Insights</span>
            </a>
            """

    html_content = INDIVIDUAL_HTML_TEMPLATE
    html_content = html_content.replace("{row_index}", str(row_index))
    html_content = html_content.replace("{overall_result_upper}", overall_result_upper)
    html_content = html_content.replace("{badge_class}", badge_class)
    html_content = html_content.replace("{overall_result}", overall_result)
    html_content = html_content.replace("{tcid}", tcid)
    html_content = html_content.replace("{session_id}", session_id)
    html_content = html_content.replace("{cx_insights_link}", cx_insights_link)
    html_content = html_content.replace("{modality}", modality)
    html_content = html_content.replace("{project_id}", project_id)
    html_content = html_content.replace("{app_id}", app_id)
    html_content = html_content.replace("{timestamp}", timestamp)
    html_content = html_content.replace("{agent_config}", agent_config)
    html_content = html_content.replace("{test_procedure}", test_procedure)
    html_content = html_content.replace("{expectations_html}", expectations_html)
    html_content = html_content.replace("{transcript_html}", transcript_html)
    html_content = html_content.replace("{raw_json_str}", raw_json_str)
    
    return html_content

def generate_index_html(all_results: list, timestamp: str, csv_basename: str) -> str:
    total_count = len(all_results)
    passed_count = sum(1 for res in all_results if res.get("agent_output", {}).get("overall_result", "") == "passed")
    failed_count = total_count - passed_count
    success_rate = (passed_count / total_count * 100) if total_count > 0 else 0.0
    
    run_status_text = "PASSED" if failed_count == 0 and total_count > 0 else "FAILED"
    run_badge_class = "badge-passed" if run_status_text == "PASSED" else "badge-failed"
    
    rows_html = ""
    for res in all_results:
        row_index = res.get("row_index", 0)
        agent_output = res.get("agent_output", {})
        tcid = html.escape(str(agent_output.get("tcid", "N/A")))
        
        is_error = "error" in agent_output or not isinstance(agent_output, dict)
        
        if is_error:
            status = "failed"
            project_id = "N/A"
            session_id = "N/A"
            region = "N/A"
        else:
            status = agent_output.get("overall_result", "failed")
            project_id = html.escape(str(agent_output.get("project_id", "N/A")))
            session_id = html.escape(str(agent_output.get("session_id", "N/A")))
            region = html.escape(str(agent_output.get("region", "N/A")))
            
        badge_class = "badge-passed" if status == "passed" else "badge-failed"
        detail_link = f"{csv_basename}_{row_index}.html"
        
        cx_link = ""
        if not is_error and session_id != "N/A" and project_id != "N/A" and region != "N/A":
            raw_project_id = str(agent_output.get("project_id", ""))
            raw_region = str(agent_output.get("region", ""))
            raw_session_id = str(agent_output.get("session_id", ""))
            if raw_project_id and raw_region and raw_session_id:
                url = f"https://ccai.cloud.google.com/insights/projects/{raw_project_id}/locations/{raw_region}/quality/conversations/{raw_session_id}"
                cx_link = f"""
                <a href="{url}" target="_blank" style="color: var(--accent-info); text-decoration: none; margin-left: 6px; display: inline-flex; align-items: center;" title="View in CX Insights">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: inline-block; vertical-align: middle;"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
                </a>
                """
        
        rows_html += f"""
        <tr data-status="{status}">
            <td style="font-weight: 600;">#{row_index}</td>
            <td style="font-family: 'Fira Code', monospace; color: var(--accent-info);">{tcid}</td>
            <td>{project_id}</td>
            <td style="font-family: 'Fira Code', monospace; font-size: 12px; color: var(--text-secondary);">
                <div style="display: flex; align-items: center; gap: 4px;">{session_id}{cx_link}</div>
            </td>
            <td><span class="badge {badge_class}">{status}</span></td>
            <td><a href="{detail_link}" class="action-link">View Details &rarr;</a></td>
        </tr>
        """
        
    index_content = INDEX_HTML_TEMPLATE
    index_content = index_content.replace("{timestamp}", timestamp)
    index_content = index_content.replace("{run_badge_class}", run_badge_class)
    index_content = index_content.replace("{run_status_text}", run_status_text)
    index_content = index_content.replace("{total_count}", str(total_count))
    index_content = index_content.replace("{passed_count}", str(passed_count))
    index_content = index_content.replace("{failed_count}", str(failed_count))
    index_content = index_content.replace("{success_rate}", f"{success_rate:.1f}")
    index_content = index_content.replace("{rows_html}", rows_html)
    
    return index_content

INDIVIDUAL_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Case #{row_index} - {overall_result_upper}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0b0f19;
            --bg-secondary: #151d30;
            --bg-tertiary: #1f2b45;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-success: #10b981;
            --accent-success-glow: rgba(16, 185, 129, 0.15);
            --accent-fail: #f43f5e;
            --accent-fail-glow: rgba(244, 63, 94, 0.15);
            --accent-info: #3b82f6;
            --accent-info-glow: rgba(59, 130, 246, 0.15);
            --border-color: rgba(255, 255, 255, 0.08);
            --transition-speed: 0.2s;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            height: 100vh;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }

        /* App Layout */
        .app-header {
            background-color: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            padding: 12px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            z-index: 10;
            flex-shrink: 0;
        }

        .brand-section {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .back-btn {
            background-color: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            text-decoration: none;
            display: flex;
            align-items: center;
            gap: 6px;
            transition: all var(--transition-speed);
        }

        .back-btn:hover {
            background-color: #29395c;
            border-color: rgba(255, 255, 255, 0.2);
        }

        .header-title {
            font-size: 16px;
            font-weight: 600;
            letter-spacing: -0.01em;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .badge {
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }

        .badge-passed {
            background-color: var(--accent-success-glow);
            color: var(--accent-success);
            border: 1px solid rgba(16, 185, 129, 0.3);
        }

        .badge-failed {
            background-color: var(--accent-fail-glow);
            color: var(--accent-fail);
            border: 1px solid rgba(244, 63, 94, 0.3);
        }

        .main-container {
            display: flex;
            flex: 1;
            overflow: hidden;
        }

        /* Split Panes */
        .pane-left {
            width: 55%;
            height: 100%;
            overflow-y: auto;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        .pane-right {
            width: 45%;
            height: 100%;
            border-left: 1px solid var(--border-color);
            background-color: #0d1117; /* GitHub Dark style for code */
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        /* Cards and Sections */
        .section-card {
            background-color: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .section-title {
            font-size: 13px;
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 8px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        /* Key Value Grid */
        .kv-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
            gap: 16px;
        }

        .kv-item {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .kv-label {
            font-size: 11px;
            font-weight: 500;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.02em;
        }

        .kv-value {
            font-size: 13px;
            color: var(--text-primary);
            font-family: 'Fira Code', monospace;
            word-break: break-all;
        }

        /* Test Procedure & Config */
        .pre-container {
            background-color: var(--bg-primary);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px;
            font-family: 'Fira Code', monospace;
            font-size: 12px;
            line-height: 1.5;
            white-space: pre-wrap;
            color: #e2e8f0;
            max-height: 250px;
            overflow-y: auto;
        }

        /* Transcript Viewer */
        .transcript-container {
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .chat-bubble {
            max-width: 85%;
            border-radius: 12px;
            padding: 12px 16px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            position: relative;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06);
        }

        .bubble-caller {
            align-self: flex-start;
            background-color: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-bottom-left-radius: 2px;
        }

        .bubble-agent {
            align-self: flex-end;
            background-color: rgba(99, 102, 241, 0.12);
            border: 1px solid rgba(99, 102, 241, 0.25);
            border-bottom-right-radius: 2px;
        }

        .bubble-meta {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            font-size: 11px;
            font-weight: 500;
            color: var(--text-secondary);
        }

        .bubble-speaker {
            font-weight: 600;
            color: var(--text-primary);
        }

        .bubble-text {
            font-size: 13px;
            line-height: 1.5;
            word-break: break-word;
        }

        /* Expectations details inside bubbles */
        .bubble-expectation {
            font-size: 11.5px;
            padding: 8px 12px;
            border-radius: 6px;
            display: flex;
            flex-direction: column;
            gap: 4px;
            border-left: 3px solid;
            margin-top: 4px;
        }

        .expectation-passed {
            background-color: rgba(16, 185, 129, 0.08);
            border-left-color: var(--accent-success);
            color: #a7f3d0;
        }

        .expectation-failed {
            background-color: rgba(244, 63, 94, 0.08);
            border-left-color: var(--accent-fail);
            color: #fecdd3;
        }

        .variables-pill-list {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-top: 4px;
        }

        .variable-pill {
            font-family: 'Fira Code', monospace;
            font-size: 10px;
            padding: 2px 6px;
            border-radius: 4px;
            background-color: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.08);
            color: #cbd5e1;
        }

        /* Expectations checklist */
        .expectation-item {
            background-color: var(--bg-primary);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px;
            display: flex;
            gap: 12px;
            align-items: flex-start;
            transition: transform 0.2s;
        }

        .expectation-item:hover {
            transform: translateY(-1px);
            border-color: rgba(255, 255, 255, 0.15);
        }

        .expectation-status-icon {
            font-size: 16px;
            margin-top: 2px;
        }

        .expectation-content {
            display: flex;
            flex-direction: column;
            gap: 4px;
            flex: 1;
        }

        .expectation-label {
            font-size: 13px;
            font-weight: 500;
        }

        .expectation-actual {
            font-size: 12px;
            color: var(--text-secondary);
            line-height: 1.4;
        }

        /* Raw JSON Pane Right */
        .json-header {
            padding: 12px 20px;
            background-color: #161b22;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0;
        }

        .json-title {
            font-size: 13px;
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .copy-btn {
            background-color: #21262d;
            border: 1px solid #30363d;
            color: #c9d1d9;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 500;
            cursor: pointer;
            transition: all var(--transition-speed);
            display: flex;
            align-items: center;
            gap: 4px;
        }

        .copy-btn:hover {
            background-color: #30363d;
            border-color: #8b949e;
            color: #f0f6fc;
        }

        .pre-json {
            flex: 1;
            overflow: auto;
            padding: 20px;
            font-family: 'Fira Code', monospace;
            font-size: 12px;
            line-height: 1.5;
            color: #c9d1d9;
        }

        /* JSON Syntax Highlighting */
        .pre-json .key { color: #79c0ff; }
        .pre-json .string { color: #a5d6ff; }
        .pre-json .number { color: #ff7b72; }
        .pre-json .boolean { color: #ff7b72; }
        .pre-json .null { color: #8b949e; }

        /* Custom Scrollbars */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }

        ::-webkit-scrollbar-track {
            background: transparent;
        }

        ::-webkit-scrollbar-thumb {
            background: var(--bg-tertiary);
            border-radius: 4px;
        }

        ::-webkit-scrollbar-thumb:hover {
            background: #475569;
        }

        /* Responsive Mobile Layout */
        @media (max-width: 1024px) {
            body {
                overflow: auto;
                height: auto;
            }

            .main-container {
                flex-direction: column;
                height: auto;
                overflow: visible;
            }

            .pane-left, .pane-right {
                width: 100%;
                height: auto;
                overflow: visible;
            }

            .pane-right {
                border-left: none;
                border-top: 1px solid var(--border-color);
                height: 500px;
            }
        }
    </style>
</head>
<body>
    <header class="app-header">
        <div class="brand-section">
            <a href="index.html" class="back-btn">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"></line><polyline points="12 19 5 12 12 5"></polyline></svg>
                Dashboard
            </a>
            <div class="header-title">
                Row #{row_index} - Test Case Report
                <span class="badge {badge_class}">{overall_result}</span>
            </div>
        </div>
        <div style="font-size: 12px; color: var(--text-secondary);">
            Timestamp: {timestamp}
        </div>
    </header>

    <main class="main-container">
        <!-- LEFT PANEL: Visual Render -->
        <section class="pane-left">
            
            <!-- Metadata Card -->
            <div class="section-card">
                <h2 class="section-title">Session Metadata</h2>
                <div class="kv-grid">
                    <div class="kv-item">
                        <span class="kv-label">Test Case ID</span>
                        <span class="kv-value" style="color: var(--accent-info);">{tcid}</span>
                    </div>
                    <div class="kv-item">
                        <span class="kv-label">Session ID</span>
                        <span class="kv-value" style="display: flex; align-items: center; gap: 4px; flex-wrap: wrap;">{session_id}{cx_insights_link}</span>
                    </div>
                    <div class="kv-item">
                        <span class="kv-label">Modality</span>
                        <span class="kv-value" style="text-transform: capitalize;">{modality}</span>
                    </div>
                    <div class="kv-item">
                        <span class="kv-label">Project ID</span>
                        <span class="kv-value">{project_id}</span>
                    </div>
                    <div class="kv-item">
                        <span class="kv-label">App ID</span>
                        <span class="kv-value">{app_id}</span>
                    </div>
                </div>
            </div>

            <!-- Input Data & Config Card -->
            <div class="section-card">
                <h2 class="section-title">Test Settings & Procedure</h2>
                <div class="kv-grid" style="grid-template-columns: 1fr;">
                    <div class="kv-item">
                        <span class="kv-label">Agent Config</span>
                        <div class="pre-container">{agent_config}</div>
                    </div>
                    <div class="kv-item" style="margin-top: 10px;">
                        <span class="kv-label">Test Procedure</span>
                        <div class="pre-container" style="background-color: rgba(30, 41, 59, 0.4);">{test_procedure}</div>
                    </div>
                </div>
            </div>

            <!-- Expectations Checklist -->
            <div class="section-card">
                <h2 class="section-title">Evaluation Summary</h2>
                <div class="transcript-container">
                    {expectations_html}
                </div>
            </div>

            <!-- Conversation Transcript -->
            <div class="section-card">
                <h2 class="section-title">Conversation Transcript</h2>
                <div class="transcript-container">
                    {transcript_html}
                </div>
            </div>

        </section>

        <!-- RIGHT PANEL: Raw JSON Code View -->
        <section class="pane-right">
            <div class="json-header">
                <span class="json-title">Raw JSON Output</span>
                <button class="copy-btn" id="copy-btn" onclick="copyJsonToClipboard()">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="copy-icon"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                    <span>Copy JSON</span>
                </button>
            </div>
            <pre class="pre-json"><code id="raw-json-code"></code></pre>
        </section>
    </main>

    <!-- Hidden Raw JSON Data -->
    <script id="raw-json-data" type="application/json">
{raw_json_str}
    </script>

    <script>
        // Custom lightweight JSON Syntax Highlighter
        function syntaxHighlight(json) {
            if (typeof json !== 'string') {
                json = JSON.stringify(json, undefined, 2);
            }
            json = json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            return json.replace(/("(\\\\u[a-zA-Z0-9]{4}|\\\\[^u]|[^\\\\"])*"(\\\\s*):?|\\\\b(true|false|null)\\\\b|-\\\\d+(?:\\\\.\\\\d*)?(?:[eE][+-]?\\\\d+)?)/g, function (match) {
                let cls = 'number';
                if (/^"/.test(match)) {
                    if (/:$/.test(match)) {
                        cls = 'key';
                    } else {
                        cls = 'string';
                    }
                } else if (/true|false/.test(match)) {
                    cls = 'boolean';
                } else if (/null/.test(match)) {
                    cls = 'null';
                }
                return '<span class="' + cls + '">' + match + '</span>';
            });
        }

        // Run highlight on load
        document.addEventListener('DOMContentLoaded', () => {
            const rawJsonElement = document.getElementById('raw-json-data');
            const codeElement = document.getElementById('raw-json-code');
            try {
                const textVal = rawJsonElement.textContent.trim();
                const jsonObj = JSON.parse(textVal);
                codeElement.innerHTML = syntaxHighlight(jsonObj);
            } catch (e) {
                // fallback if parsing fails
                codeElement.textContent = rawJsonElement.textContent;
            }
        });

        function copyJsonToClipboard() {
            const rawJsonElement = document.getElementById('raw-json-data');
            const btn = document.getElementById('copy-btn');
            const btnText = btn.querySelector('span');
            
            navigator.clipboard.writeText(rawJsonElement.textContent.trim()).then(() => {
                btnText.textContent = 'Copied!';
                btn.style.borderColor = 'var(--accent-success)';
                btn.style.color = 'var(--accent-success)';
                setTimeout(() => {
                    btnText.textContent = 'Copy JSON';
                    btn.style.borderColor = '';
                    btn.style.color = '';
                }, 2000);
            }).catch(err => {
                console.error('Could not copy text: ', err);
            });
        }
    </script>
</body>
</html>
"""

INDEX_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QA Test Run Dashboard - {timestamp}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0b0f19;
            --bg-secondary: #151d30;
            --bg-tertiary: #1f2b45;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-success: #10b981;
            --accent-success-glow: rgba(16, 185, 129, 0.15);
            --accent-fail: #f43f5e;
            --accent-fail-glow: rgba(244, 63, 94, 0.15);
            --accent-info: #3b82f6;
            --border-color: rgba(255, 255, 255, 0.08);
            --transition-speed: 0.2s;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            padding: 40px 24px;
        }

        .dashboard-container {
            max-width: 1200px;
            width: 100%;
            margin: 0 auto;
            display: flex;
            flex-direction: column;
            gap: 32px;
        }

        .dashboard-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 20px;
        }

        .header-left h1 {
            font-size: 28px;
            font-weight: 700;
            letter-spacing: -0.02em;
            margin-bottom: 6px;
            background: linear-gradient(135deg, #fff 0%, #cbd5e1 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .header-left p {
            font-size: 14px;
            color: var(--text-secondary);
        }

        /* KPI Cards */
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
        }

        .kpi-card {
            background-color: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
        }

        .kpi-content {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .kpi-label {
            font-size: 12px;
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .kpi-value {
            font-size: 32px;
            font-weight: 700;
            color: var(--text-primary);
        }

        .kpi-icon-wrapper {
            width: 48px;
            height: 48px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
        }

        .icon-total {
            background-color: rgba(59, 130, 246, 0.1);
            color: var(--accent-info);
            border: 1px solid rgba(59, 130, 246, 0.2);
        }

        .icon-passed {
            background-color: var(--accent-success-glow);
            color: var(--accent-success);
            border: 1px solid rgba(16, 185, 129, 0.2);
        }

        .icon-failed {
            background-color: var(--accent-fail-glow);
            color: var(--accent-fail);
            border: 1px solid rgba(244, 63, 94, 0.2);
        }

        .icon-rate {
            background-color: rgba(139, 92, 246, 0.1);
            color: #a78bfa;
            border: 1px solid rgba(139, 92, 246, 0.2);
        }

        /* Table & Filters Section */
        .table-section {
            background-color: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        .filters-container {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
        }

        .filter-buttons {
            display: flex;
            gap: 8px;
            background-color: var(--bg-primary);
            padding: 4px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
        }

        .filter-btn {
            background: transparent;
            border: none;
            color: var(--text-secondary);
            padding: 6px 16px;
            font-size: 13px;
            font-weight: 600;
            border-radius: 6px;
            cursor: pointer;
            transition: all var(--transition-speed);
        }

        .filter-btn:hover {
            color: var(--text-primary);
        }

        .filter-btn.active {
            background-color: var(--bg-tertiary);
            color: var(--text-primary);
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }

        .search-input {
            background-color: var(--bg-primary);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 13px;
            width: 100%;
            max-width: 300px;
            transition: all var(--transition-speed);
        }

        .search-input:focus {
            outline: none;
            border-color: var(--accent-info);
            box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
        }

        /* Results Table */
        .results-table-container {
            width: 100%;
            overflow-x: auto;
        }

        .results-table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 14px;
        }

        .results-table th {
            color: var(--text-secondary);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.05em;
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-color);
        }

        .results-table td {
            padding: 16px;
            border-bottom: 1px solid var(--border-color);
            color: var(--text-primary);
        }

        .results-table tr {
            transition: background-color var(--transition-speed);
        }

        .results-table tbody tr:hover {
            background-color: rgba(255, 255, 255, 0.02);
        }

        .badge {
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }

        .badge-passed {
            background-color: var(--accent-success-glow);
            color: var(--accent-success);
            border: 1px solid rgba(16, 185, 129, 0.3);
        }

        .badge-failed {
            background-color: var(--accent-fail-glow);
            color: var(--accent-fail);
            border: 1px solid rgba(244, 63, 94, 0.3);
        }

        .action-link {
            color: var(--accent-info);
            text-decoration: none;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            transition: color var(--transition-speed);
        }

        .action-link:hover {
            color: #60a5fa;
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="dashboard-container">
        
        <header class="dashboard-header">
            <div class="header-left">
                <h1>QA Automation Test Run</h1>
                <p>Run timestamp: <strong>{timestamp}</strong></p>
            </div>
            <div class="header-right">
                <span class="badge {run_badge_class}">{run_status_text}</span>
            </div>
        </header>

        <!-- Stats Section -->
        <section class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-content">
                    <span class="kpi-label">Total Tests</span>
                    <span class="kpi-value">{total_count}</span>
                </div>
                <div class="kpi-icon-wrapper icon-total">📋</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-content">
                    <span class="kpi-label">Passed</span>
                    <span class="kpi-value" style="color: var(--accent-success);">{passed_count}</span>
                </div>
                <div class="kpi-icon-wrapper icon-passed">✔️</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-content">
                    <span class="kpi-label">Failed</span>
                    <span class="kpi-value" style="color: var(--accent-fail);">{failed_count}</span>
                </div>
                <div class="kpi-icon-wrapper icon-failed">❌</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-content">
                    <span class="kpi-label">Success Rate</span>
                    <span class="kpi-value" style="color: #cbd5e1;">{success_rate}%</span>
                </div>
                <div class="kpi-icon-wrapper icon-rate">⚡</div>
            </div>
        </section>

        <!-- Test Case Results Table -->
        <section class="table-section">
            <div class="filters-container">
                <div class="filter-buttons">
                    <button class="filter-btn active" onclick="filterResults('all')">All</button>
                    <button class="filter-btn" onclick="filterResults('passed')">Passed</button>
                    <button class="filter-btn" onclick="filterResults('failed')">Failed</button>
                </div>
                <input type="text" id="search-box" class="search-input" placeholder="Search test cases..." oninput="searchTable()">
            </div>

            <div class="results-table-container">
                <table class="results-table" id="results-table-el">
                    <thead>
                        <tr>
                            <th>Row Index</th>
                            <th>TCID</th>
                            <th>Project ID</th>
                            <th>Session ID</th>
                            <th>Status</th>
                            <th>Detail Report</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>
        </section>

    </div>

    <script>
        function filterResults(status) {
            const buttons = document.querySelectorAll('.filter-btn');
            buttons.forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');

            const table = document.getElementById('results-table-el');
            const rows = table.getElementsByTagName('tbody')[0].getElementsByTagName('tr');

            for (let i = 0; i < rows.length; i++) {
                const row = rows[i];
                const rowStatus = row.getAttribute('data-status');
                
                if (status === 'all' || rowStatus === status) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            }
            searchTable(false); // preserve status filter while searching
        }

        function searchTable(resetFilter = true) {
            const searchInput = document.getElementById('search-box');
            const filter = searchInput.value.toLowerCase();
            const table = document.getElementById('results-table-el');
            const tbody = table.getElementsByTagName('tbody')[0];
            const rows = tbody.getElementsByTagName('tr');
            
            // Get active status filter button
            const activeBtn = document.querySelector('.filter-btn.active');
            const activeStatus = activeBtn ? activeBtn.textContent.toLowerCase() : 'all';

            for (let i = 0; i < rows.length; i++) {
                const row = rows[i];
                const rowStatus = row.getAttribute('data-status');
                const cells = row.getElementsByTagName('td');
                let found = false;

                // Check search term matches any visible column
                for (let j = 0; j < cells.length - 1; j++) {
                    if (cells[j].textContent.toLowerCase().includes(filter)) {
                        found = true;
                        break;
                    }
                }

                // Check active status filter matches too
                const matchesStatus = (activeStatus === 'all' || rowStatus === activeStatus);

                if (found && matchesStatus) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            }
        }
    </script>
</body>
</html>
"""
