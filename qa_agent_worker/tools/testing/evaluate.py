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
import uuid
import json
import time
import random
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List
from google.adk.tools import ToolContext
from google import genai
from google.genai import types

from ...models import (
    TestCase,
    ActualTurn,
    ActualMessage,
    MessageEvaluation,
    TestCaseResult,
    ExpectationType,
    VariableExpectation,
    TextExpectation,
    ConversationEvaluations,
    ActualTestProcedure,
    SimilarityEvaluation,
    TranscriptEvaluationResponse
)
from ...prompts import EVAL_SIMILARITY_PROMPT_TEMPLATE
from ..cxas import send_message_to_cx_agent

GEMINI_MODEL = os.getenv("EVALUATE_GEMINI_MODEL", "gemini-3.1-flash-lite")
SIMILARITY_THRESHOLD = os.getenv("SIMILARITY_THRESHOLD", 3)

def _generate_content_with_retry(
    client: genai.Client,
    model: str,
    contents: Any,
    config: Any,
    max_retries: int = 3
) -> Any:
    """Generates content using the Gemini client with exponential backoff retry."""
    delay = 1.0  # Initial delay of 1 second
    for attempt in range(max_retries + 1):
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config
            )
        except Exception as e:
            if attempt == max_retries:
                print(f"           [ERROR] Gemini generate_content call failed after {max_retries} retries: {str(e)}")
                raise e
            
            # Calculate sleep time with backoff and jitter
            sleep_time = delay * (2 ** attempt) + random.uniform(0.1, 0.5)
            print(f"           [WARNING] Gemini call failed: {str(e)}. Retrying in {sleep_time:.2f} seconds (Attempt {attempt + 1}/{max_retries})...")
            time.sleep(sleep_time)


def _evaluate_text_expectation(expected: Optional[TextExpectation], actual_text: str, client: genai.Client) -> Dict[str, Any]:
    """Evaluates actual text against a TextExpectation, returning a detailed result dict."""
    if expected is None:
        return {"passed": True}

    exp_type = expected.expectation_type
    exp_text = expected.text

    print(f"      - [EVALUATE] Checking text expectation (Type: {exp_type.value})")

    if exp_type == ExpectationType.OPTIONAL:
        print("        -> Optional text. Automatically PASS.")
        return {"passed": True}

    if exp_type == ExpectationType.ANY:
        passed = bool(actual_text and actual_text.strip() != "")
        print(f"        -> Any text check. Result: {'PASS' if passed else 'FAIL'} (Actual: '{actual_text}')")
        return {"passed": passed}

    if exp_type == ExpectationType.EXACT:
        clean_exp = exp_text.replace("\n", "").replace("\r", "").strip().lower()
        clean_act = actual_text.replace("\n", "").replace("\r", "").strip().lower()
        passed = (clean_exp == clean_act)
        print(f"        -> Exact match check. Result: {'PASS' if passed else 'FAIL'}")
        if not passed:
            print(f"           Expected: '{clean_exp}'")
            print(f"           Actual:   '{clean_act}'")
        return {"passed": passed}

    if exp_type == ExpectationType.SEMANTIC:
        # Optimization: Check for exact match first to bypass Gemini API call
        clean_exp = exp_text.replace("\n", "").replace("\r", "").strip().lower()
        clean_act = actual_text.replace("\n", "").replace("\r", "").strip().lower()
        if clean_exp == clean_act:
            print("        -> [OPTIMIZATION] Exact match found for semantic expectation. Short-circuited Gemini call.")
            return {"passed": True, "score": 5, "reasoning": "Optimized: Exact match found. Short-circuited Gemini call."}

        print("        -> Running semantic similarity check via Gemini...")
        prompt = EVAL_SIMILARITY_PROMPT_TEMPLATE.format(
            expected_text=exp_text,
            actual_text=actual_text
        )
        try:
            res = _generate_content_with_retry(
                client=client,
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type='application/json',
                    response_schema=SimilarityEvaluation,
                    thinking_config=types.ThinkingConfig(thinking_level="high")
                )
            )
            data = json.loads(res.text)
            score = data.get("score", 1)
            reasoning = data.get("reasoning", "")
            passed = (score >= SIMILARITY_THRESHOLD)
            print(f"           Gemini Similarity Score: {score}/5 - {'PASS' if passed else 'FAIL'}")
            print(f"           Gemini Reasoning: {reasoning}")
            return {"passed": passed, "score": score, "reasoning": reasoning}
        except Exception as e:
            print(f"           [ERROR] Gemini call failed: {str(e)}")
            return {"passed": False, "score": 1, "reasoning": f"Gemini call failed: {str(e)}"}

    return {"passed": True}


def _evaluate_variable_expectation(expected: VariableExpectation, actual_vars: Dict[str, Any], client: genai.Client) -> Dict[str, Any]:
    """Evaluates actual variables against a VariableExpectation, returning a detailed result dict."""
    name = expected.name
    expected_val = expected.value
    exp_type = expected.expectation_type

    print(f"      - [EVALUATE] Checking variable expectation for '{name}' (Type: {exp_type.value})")

    if exp_type == ExpectationType.OPTIONAL:
        print(f"        -> Optional variable '{name}'. Automatically PASS.")
        return {"passed": True, "actual": actual_vars.get(name)}

    if name not in actual_vars:
        print(f"        -> Variable '{name}' missing from actual results. Result: FAIL")
        return {"passed": False, "actual": None, "reasoning": f"Variable '{name}' not found in actual variables."}

    actual_val = str(actual_vars[name])

    if exp_type == ExpectationType.ANY:
        passed = bool(actual_val and actual_val.strip() != "")
        print(f"        -> Any value check. Result: {'PASS' if passed else 'FAIL'} (Actual: '{actual_val}')")
        return {"passed": passed, "actual": actual_val}

    if exp_type == ExpectationType.EXACT:
        clean_exp = expected_val.replace("\n", "").replace("\r", "").strip().lower()
        clean_act = actual_val.replace("\n", "").replace("\r", "").strip().lower()
        passed = (clean_exp == clean_act)
        print(f"        -> Exact match check for '{name}'. Result: {'PASS' if passed else 'FAIL'}")
        if not passed:
            print(f"           Expected: '{clean_exp}'")
            print(f"           Actual:   '{clean_act}'")
        return {"passed": passed, "actual": actual_val}

    if exp_type == ExpectationType.SEMANTIC:
        # Optimization: Check for exact match first to bypass Gemini API call
        clean_exp = expected_val.replace("\n", "").replace("\r", "").strip().lower()
        clean_act = actual_val.replace("\n", "").replace("\r", "").strip().lower()
        if clean_exp == clean_act:
            print(f"        -> [OPTIMIZATION] Exact match found for semantic variable '{name}'. Short-circuited Gemini call.")
            return {"passed": True, "actual": actual_val, "score": 5, "reasoning": "Optimized: Exact match found. Short-circuited Gemini call."}

        print("        -> Running semantic variable similarity check via Gemini...")
        prompt = EVAL_SIMILARITY_PROMPT_TEMPLATE.format(
            expected_text=expected_val,
            actual_text=actual_val
        )
        try:
            res = _generate_content_with_retry(
                client=client,
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type='application/json',
                    response_schema=SimilarityEvaluation
                )
            )
            data = json.loads(res.text)
            score = data.get("score", 1)
            reasoning = data.get("reasoning", "")
            passed = (score >= SIMILARITY_THRESHOLD)
            print(f"           Gemini Similarity Score for '{name}': {score}/5 - {'PASS' if passed else 'FAIL'}")
            print(f"           Gemini Reasoning: {reasoning}")
            return {"passed": passed, "actual": actual_val, "score": score, "reasoning": reasoning}
        except Exception as e:
            print(f"           [ERROR] Gemini call failed: {str(e)}")
            return {"passed": False, "actual": actual_val, "score": 1, "reasoning": f"Gemini call failed: {str(e)}"}

    return {"passed": True, "actual": actual_val}


def _evaluate_transcript_expectations(expectations: List[str], actual_transcript: List[str], client: genai.Client) -> tuple[Dict[str, bool], Dict[str, str]]:
    """Uses Gemini to evaluate high-level transcript expectations against the actual conversation transcript."""
    if not expectations:
        return {}, {}

    print(f"\n  [GEMINI] Evaluating {len(expectations)} transcript expectations using {GEMINI_MODEL}...")
    transcript_text = "\n".join(actual_transcript)
    expectations_json = json.dumps(expectations)

    prompt = f"""
    Evaluate the following conversation transcript against the list of high-level expectations.
    
    Conversation Transcript:
    ---
    {transcript_text}
    ---
    
    Expectations to verify:
    {expectations_json}
    
    For each expectation, determine if the conversation transcript satisfies it (passed: True or False) and provide a brief reasoning.
    """

    try:
        res = _generate_content_with_retry(
            client=client,
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type='application/json',
                response_schema=TranscriptEvaluationResponse
            )
        )
        data = json.loads(res.text)
        evaluations = data.get("evaluations", [])
        
        results = {}
        reasonings = {}
        for item in evaluations:
            exp = item.get("expectation", "")
            passed = item.get("passed", False)
            reasoning = item.get("reasoning", "")
            results[exp] = passed
            reasonings[exp] = reasoning
            print(f"    - Expectation: '{exp}' -> {'PASSED' if passed else 'FAILED'}")
            print(f"      Reasoning: {reasoning}")
        
        # Ensure all requested expectations are present in the final result dict
        for exp in expectations:
            if exp not in results:
                results[exp] = False
                reasonings[exp] = "No evaluation returned from Gemini"
                
        return results, reasonings
    except Exception as e:
        print(f"    [ERROR] Gemini transcript evaluation failed: {str(e)}. Falling back to exact substring match...")
        # Fallback to case-insensitive exact substring lookup in case of API failure
        results = {}
        reasonings = {}
        transcript_lower = transcript_text.lower()
        for exp in expectations:
            passed = exp.lower() in transcript_lower
            results[exp] = passed
            reasonings[exp] = f"Fallback exact match check. (Gemini call failed: {str(e)})"
            print(f"    - [FALLBACK] Expectation '{exp}': {'PASSED' if passed else 'FAILED'}")
        return results, reasonings


def _evaluate_test_case_expectations(test_case: TestCase) -> TestCase:
    """Programmatically evaluates execution actuals against expected expectations, saving turn-level and overall evaluations."""
    print("\n========================================================")
    print(f"[EVALUATE] Starting Programmatic Evaluation for Test Case: {test_case.tcid}")
    print("========================================================")
    
    client = genai.Client(vertexai=True)
    all_passed = True

    expected_procedure = test_case.expected_test_procedure
    actual_procedure = test_case.actual_test_procedure or ActualTestProcedure()
    actual_turns = actual_procedure.actual_turns

    # 1. Verify expected Turn expectations
    for idx, expected_turn in enumerate(expected_procedure.turn_expectations):
        turn_id = expected_turn.turn_id if expected_turn.turn_id is not None else (idx + 1)
        print(f"\n--- [EVALUATE] Evaluating Turn {turn_id} ---")
        
        # Find corresponding actual turn in actual_turns
        actual_turn = None
        for at in actual_turns:
            if at.turn_id == turn_id:
                actual_turn = at
                break

        if not actual_turn:
            print(f"  [ERROR] Actual Turn {turn_id} is missing from executed turns! Fail.")
            all_passed = False
            continue

        turn_passed = True

        # Evaluate expected UserMessage
        if expected_turn.user_message:
            print("  - [EVALUATE] Evaluating UserMessage Expectations:")
            user_eval = MessageEvaluation(passed=True)
            actual_user = actual_turn.user_message or ActualMessage()
            
            # Text check
            if expected_turn.user_message.text:
                res = _evaluate_text_expectation(expected_turn.user_message.text, actual_user.text, client)
                user_eval.text_passed = res["passed"]
                user_eval.text_score = res.get("score")
                user_eval.text_reasoning = res.get("reasoning")
                if not res["passed"]:
                    user_eval.passed = False
                    turn_passed = False

            # Variables check
            if expected_turn.user_message.vars:
                user_eval.variables_passed = True
                for var_exp in expected_turn.user_message.vars.vars:
                    v_res = _evaluate_variable_expectation(var_exp, actual_user.vars, client)
                    user_eval.variable_details[var_exp.name] = v_res
                    if not v_res["passed"]:
                        user_eval.variables_passed = False
                        user_eval.passed = False
                        turn_passed = False

            actual_turn.user_message_evaluation = user_eval

        # Evaluate expected AgentMessage
        if expected_turn.agent_message:
            print("  - [EVALUATE] Evaluating AgentMessage Expectations:")
            agent_eval = MessageEvaluation(passed=True)
            actual_agent = actual_turn.agent_message or ActualMessage()
            
            # Text check
            if expected_turn.agent_message.text:
                res = _evaluate_text_expectation(expected_turn.agent_message.text, actual_agent.text, client)
                agent_eval.text_passed = res["passed"]
                agent_eval.text_score = res.get("score")
                agent_eval.text_reasoning = res.get("reasoning")
                if not res["passed"]:
                    agent_eval.passed = False
                    turn_passed = False

            # Variables check
            if expected_turn.agent_message.vars:
                agent_eval.variables_passed = True
                for var_exp in expected_turn.agent_message.vars.vars:
                    v_res = _evaluate_variable_expectation(var_exp, actual_agent.vars, client)
                    agent_eval.variable_details[var_exp.name] = v_res
                    if not v_res["passed"]:
                        agent_eval.variables_passed = False
                        agent_eval.passed = False
                        turn_passed = False

            actual_turn.agent_message_evaluation = agent_eval

        actual_turn.overall_turn_result = TestCaseResult.PASSED if turn_passed else TestCaseResult.FAILED
        print(f"  -> Turn {turn_id} Evaluation Result: {'PASSED' if turn_passed else 'FAILED'}")
        if not turn_passed:
            all_passed = False

    conv_expectations = expected_procedure.conversation_expectations

    # 2. Verify high-level transcript_expectations using Gemini LLM-as-judge
    print("\n--- [EVALUATE] Evaluating High-Level Transcript Expectations (via Gemini) ---")
    transcript_evals = {}
    transcript_reasonings = {}
    if conv_expectations.transcript_expectations:
        # Recreate transcript dynamically from actual turns
        actual_transcript = []
        for at in actual_turns:
            if at.user_message and at.user_message.text:
                actual_transcript.append(f"User: {at.user_message.text}")
            if at.agent_message and at.agent_message.text:
                actual_transcript.append(f"Agent: {at.agent_message.text}")

        transcript_evals, transcript_reasonings = _evaluate_transcript_expectations(
            conv_expectations.transcript_expectations,
            actual_transcript,
            client
        )
        # Check if any transcript evaluations failed
        for exp, passed in transcript_evals.items():
            if not passed:
                all_passed = False
    else:
        print("  - No transcript expectations defined.")

    # 3. Verify high-level variable_expectations
    print("\n--- [EVALUATE] Evaluating High-Level Variable Expectations ---")
    variable_evals = {}
    for name, expected_val in conv_expectations.variable_expectations.items():
        if name not in actual_procedure.actual_variables:
            variable_evals[name] = False
            print(f"  - [EVALUATE] Variable '{name}': FAILED (missing from final session variables)")
            all_passed = False
        else:
            clean_exp = expected_val.replace("\n", "").replace("\r", "").strip().lower()
            clean_act = str(actual_procedure.actual_variables[name]).replace("\n", "").replace("\r", "").strip().lower()
            passed = (clean_exp == clean_act)
            variable_evals[name] = passed
            print(f"  - [EVALUATE] Variable '{name}': {'PASSED' if passed else 'FAILED'} (Expected: '{clean_exp}', Actual: '{clean_act}')")
            if not passed:
                all_passed = False

    # Store conversation-level evaluation results
    actual_procedure.actual_conversation_evaluations = ConversationEvaluations(
        transcript_evaluations=transcript_evals,
        variable_evaluations=variable_evals,
        transcript_reasonings=transcript_reasonings
    )
    test_case.actual_test_procedure = actual_procedure

    # Update overall state
    test_case.overall_result = TestCaseResult.PASSED if all_passed else TestCaseResult.FAILED
    print("\n========================================================")
    print(f"[EVALUATE] Overall Test Case Result: {test_case.overall_result.value.upper()}")
    print("========================================================\n")
    return test_case

def _get_final_output(tcid: str, context: ToolContext) -> Dict[str, Any]:
    """Loads the test case from the agent's context state and formats it according to the requested schema.

    Args:
        tcid: The unique test case ID.
        context: The ADK ToolContext injected by the agent runtime. Do not pass this manually.

    Returns:
        A dictionary containing the formatted test case details.
    """
    if tcid not in context.state["test_cases"]:
        return {"error": f"Test case ID {tcid} not found in state."}

    try:
        test_case = TestCase.model_validate(context.state["test_cases"][tcid])
    except Exception as e:
        return {"error": f"Failed to validate test case {tcid}: {str(e)}"}

    expected_procedure = test_case.expected_test_procedure
    actual_procedure = test_case.actual_test_procedure or ActualTestProcedure()
    actual_turns = actual_procedure.actual_turns or []

    # 1. Map transcript
    transcript = []
    matched_actual_ids = set()
    for idx, expected_turn in enumerate(expected_procedure.turn_expectations):
        turn_id = expected_turn.turn_id if expected_turn.turn_id is not None else (idx + 1)
        actual_turn = None
        for at in actual_turns:
            if at.turn_id == turn_id:
                actual_turn = at
                matched_actual_ids.add(at.turn_id)
                break
        
        # Add Caller Message (UserMessage)
        if expected_turn.user_message or (actual_turn and actual_turn.user_message):
            user_exp_type = "any"
            expected_text = ""
            if expected_turn.user_message and expected_turn.user_message.text:
                expected_text = expected_turn.user_message.text.text or ""
                et = expected_turn.user_message.text.expectation_type
                user_exp_type = "similar" if (et == "semantic" or et == ExpectationType.SEMANTIC) else (et.value if hasattr(et, "value") else str(et))
            
            observed_text = ""
            vars_dict = {}
            if actual_turn and actual_turn.user_message:
                observed_text = actual_turn.user_message.text or ""
                vars_dict = actual_turn.user_message.vars or {}
                
            status = "passed"
            reasoning = ""
            if actual_turn:
                if actual_turn.user_message_evaluation:
                    reasoning = actual_turn.user_message_evaluation.text_reasoning or ""
                    if actual_turn.user_message_evaluation.text_passed is False or actual_turn.user_message_evaluation.passed is False:
                        status = "failed"
            else:
                status = "pending" if test_case.overall_result == TestCaseResult.PENDING else "passed"
                
            timestamp = (actual_turn.timestamp if (actual_turn and actual_turn.timestamp) else test_case.start_time) or ""
            
            transcript.append({
                "timestamp": timestamp,
                "speaker": "Caller",
                "observed_utterance": observed_text,
                "expected_utterance": expected_text,
                "transcript_expectation": user_exp_type,
                "transcript_expectation_status": status,
                "variables": vars_dict,
                "reasoning": reasoning
            })
            
        # Add Agent Message (AgentMessage)
        if expected_turn.agent_message or (actual_turn and actual_turn.agent_message):
            agent_exp_type = "any"
            expected_text = ""
            if expected_turn.agent_message and expected_turn.agent_message.text:
                expected_text = expected_turn.agent_message.text.text or ""
                et = expected_turn.agent_message.text.expectation_type
                agent_exp_type = "similar" if (et == "semantic" or et == ExpectationType.SEMANTIC) else (et.value if hasattr(et, "value") else str(et))
            
            observed_text = ""
            vars_dict = {}
            if actual_turn and actual_turn.agent_message:
                observed_text = actual_turn.agent_message.text or ""
                vars_dict = actual_turn.agent_message.vars or {}
                
            status = "passed"
            reasoning = ""
            if actual_turn:
                if actual_turn.agent_message_evaluation:
                    reasoning = actual_turn.agent_message_evaluation.text_reasoning or ""
                    if actual_turn.agent_message_evaluation.text_passed is False or actual_turn.agent_message_evaluation.passed is False:
                        status = "failed"
            else:
                status = "pending" if test_case.overall_result == TestCaseResult.PENDING else "passed"
                
            timestamp = (actual_turn.timestamp if (actual_turn and actual_turn.timestamp) else test_case.start_time) or ""
            
            transcript.append({
                "timestamp": timestamp,
                "speaker": "Agent",
                "observed_utterance": observed_text,
                "expected_utterance": expected_text,
                "transcript_expectation": agent_exp_type,
                "transcript_expectation_status": status,
                "variables": vars_dict,
                "reasoning": reasoning
            })
            
    # Handle any actual turns that didn't match an expected turn
    for at in actual_turns:
        if at.turn_id not in matched_actual_ids:
            # Caller
            if at.user_message:
                transcript.append({
                    "timestamp": at.timestamp or test_case.start_time or "",
                    "speaker": "Caller",
                    "observed_utterance": at.user_message.text or "",
                    "expected_utterance": "",
                    "transcript_expectation": "any",
                    "transcript_expectation_status": "passed",
                    "variables": at.user_message.vars or {},
                    "reasoning": ""
                })
            # Agent
            if at.agent_message:
                transcript.append({
                    "timestamp": at.timestamp or test_case.start_time or "",
                    "speaker": "Agent",
                    "observed_utterance": at.agent_message.text or "",
                    "expected_utterance": "",
                    "transcript_expectation": "any",
                    "transcript_expectation_status": "passed",
                    "variables": at.agent_message.vars or {},
                    "reasoning": ""
                })

    # 2. Map expectations
    expectations = []
    
    # 2a. Turn procedure expectation
    # Check if there are any failed turns
    failed_turns = []
    for at in actual_turns:
        if at.overall_turn_result == TestCaseResult.FAILED:
            # Gather details of what failed in this turn
            reasons = []
            if at.user_message_evaluation and not at.user_message_evaluation.passed:
                if at.user_message_evaluation.text_passed is False:
                    reasons.append("user text did not match expectations")
                if at.user_message_evaluation.variables_passed is False:
                    reasons.append("user variables did not match expectations")
            if at.agent_message_evaluation and not at.agent_message_evaluation.passed:
                if at.agent_message_evaluation.text_passed is False:
                    if at.agent_message_evaluation.text_reasoning:
                        reasons.append(f"agent response failed: {at.agent_message_evaluation.text_reasoning}")
                    else:
                        reasons.append("agent response did not meet semantic or exact expectations")
                if at.agent_message_evaluation.variables_passed is False:
                    reasons.append("agent variables did not match expectations")
            
            reason_str = ", ".join(reasons) or "turn expectations were not met"
            failed_turns.append(f"on Turn {at.turn_id}, {reason_str}")

    turn_exp_status = "passed"
    if test_case.overall_result == TestCaseResult.PENDING:
        turn_exp_status = "pending"
        turn_exp_actual = "The test case has not been executed yet."
    elif failed_turns:
        turn_exp_status = "failed"
        turn_exp_actual = "The agent did not follow the exact procedure expectations: " + "; ".join(failed_turns) + "."
    else:
        turn_exp_actual = "The agent followed the test procedure expectations perfectly."

    expectations.append({
        "expectation": "The [Agent] followed the test procedure expectations.",
        "actual": turn_exp_actual,
        "result": turn_exp_status
    })

    # 2b. Variable expectation
    var_expectations = expected_procedure.conversation_expectations.variable_expectations or {}
    session_variables_list = []
    all_vars_passed = True
    
    actual_conv_evals = actual_procedure.actual_conversation_evaluations
    var_evals_map = actual_conv_evals.variable_evaluations if actual_conv_evals else {}
    
    for name, expected_val in var_expectations.items():
        observed_val = str(actual_procedure.actual_variables.get(name, "")) if actual_procedure.actual_variables else ""
        passed = var_evals_map.get(name, False) if var_evals_map else False
        if not passed:
            all_vars_passed = False
            
        session_variables_list.append({
            "variable_name": name,
            "observed_value": observed_val,
            "expected_value": expected_val,
            "result": "passed" if passed else ("pending" if test_case.overall_result == TestCaseResult.PENDING else "failed")
        })

    var_exp_status = "passed"
    if test_case.overall_result == TestCaseResult.PENDING:
        var_exp_status = "pending"
        var_exp_action = "The test case has not been executed yet."
    elif not all_vars_passed:
        var_exp_status = "failed"
        var_exp_action = "The session variables were not set correctly."
    else:
        var_exp_action = "The session variables were set correctly."

    expectations.append({
        "expectation": "The [Agent] set the correct variables exactly as expected.",
        "action": var_exp_action,
        "session_variables": session_variables_list
    })

    # 2c. Transcript expectations (High level)
    transcript_exps = expected_procedure.conversation_expectations.transcript_expectations or []
    transcript_evals_map = actual_conv_evals.transcript_evaluations if actual_conv_evals else {}
    transcript_reasonings_map = getattr(actual_conv_evals, "transcript_reasonings", {}) if actual_conv_evals else {}
    
    for exp in transcript_exps:
        passed = transcript_evals_map.get(exp, False) if transcript_evals_map else False
        reasoning = transcript_reasonings_map.get(exp, "") if transcript_reasonings_map else ""
        
        if "professional" in exp.lower():
            actual_text = "The agent remained professional throughout the entire conversation." if passed else "The agent did not remain professional."
        else:
            actual_text = f"The agent satisfied the expectation: '{exp}'" if passed else f"The agent failed to satisfy the expectation: '{exp}'"
            
        if test_case.overall_result == TestCaseResult.PENDING:
            status = "pending"
            actual_text = "The test case has not been executed yet."
        else:
            status = "passed" if passed else "failed"
            
        expectations.append({
            "expectation": exp,
            "actual": actual_text,
            "result": status,
            "reasoning": reasoning
        })

    final_output = {
        "project_id": test_case.project_id,
        "region": test_case.region_id,
        "app_id": test_case.app_id,
        "session_id": test_case.session_id or "",
        "modality": test_case.modality,
        "timestamp": test_case.start_time,
        "tcid": test_case.tcid,
        "initial_input_variables": test_case.initial_input_variables or {},
        "transcript": transcript,
        "expectations": expectations,
        "overall_result": test_case.overall_result.value if hasattr(test_case.overall_result, "value") else str(test_case.overall_result)
    }

    # 3. Assemble and return final dictionary (skipping reasoning)
    return final_output

def execute_test_case(
    tcid: str,
    context: ToolContext,
) -> str:
    """Reads a TestCase from state, executes it against CX Agent, programmatically checks all expectations, and updates overall_result.

    This tool sends the user messages specified in each turn of the test_procedure to the
    CX Agent agent under test, captures the agent's actual responses and cumulative 
    session variables, and programmatically evaluates them using exact matching and LLM-as-judge semantic similarity.

    Args:
        tcid: The unique test case identifier (e.g., "tc_001") whose TestCase is stored in context.state.
        context: The ADK ToolContext (automatically injected).

    Returns:
        dict: The result of the test case    
    """
    if tcid not in context.state["test_cases"]:
        return f"Test case id {tcid} not found in state."

    print("\n========================================================")
    print(f"[EXECUTE] Initializing Test Case Run: {tcid}")
    print("========================================================")

    try:
        test_case = TestCase.model_validate(context.state["test_cases"][tcid])
    except Exception as e:
        print(f"[ERROR] Failed to validate test case {tcid}: {str(e)}")
        return f"Failed to validate test case {tcid}: {str(e)}"

    session_id = str(uuid.uuid4())
    test_case.session_id = session_id
    print(f"[EXECUTE] Started CX Agent conversation session: {session_id}")

    actual_turns: List[ActualTurn] = []
    current_vars: Dict[str, Any] = dict(test_case.initial_input_variables or {})

    # Execute the test case sequential conversation
    for idx, turn in enumerate(test_case.expected_test_procedure.turn_expectations):
        turn_id = turn.turn_id if turn.turn_id is not None else (idx + 1)
        print(f"\n--- [EXECUTE] Executing Turn {turn_id} ---")

        user_text = ""
        if turn.user_message and turn.user_message.text:
            user_text = turn.user_message.text.text

        send_vars = {}
        if idx == 0 and test_case.initial_input_variables:
            send_vars.update(test_case.initial_input_variables)

        actual_user = ActualMessage(text=user_text, vars=dict(send_vars))
        if user_text:
            print(f"  User:  {user_text}")

        # Send utterance to CX Agent
        print("  [EXECUTE] Sending request to CX Agent agent...")
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
            context.state["test_cases"][tcid] = test_case.model_dump(mode='json')
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

        print(f"  [EXECUTE] Updated variables after Turn {turn_id}: {updated_vars_this_turn}")

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

    print(f"\n[EXECUTE] Conversation finished. Saved {len(actual_turns)} turns.")

    # Programmatically evaluate actuals against expectations
    try:
        print("\n========================================================")
        print("Starting Test Case Expectations Evaluations")
        test_case = _evaluate_test_case_expectations(test_case)
    except Exception as e:
        print(f"[ERROR] Evaluation failed: {str(e)}")
        test_case.overall_result = TestCaseResult.ERROR
        context.state["test_cases"][tcid] = test_case.model_dump(mode='json')
        return f"Execution succeeded, but programmatic evaluation failed: {str(e)}"

    # Save back to context state
    print("Savings to context state")
    context.state["test_cases"][tcid] = test_case.model_dump(mode='json')
    context.state["final_output"] = _get_final_output(tcid, context)

    # Return structured test execution summary report
    status_emoji = "✅ PASSED" if test_case.overall_result == TestCaseResult.PASSED else "❌ FAILED"
    return f"Test Case {tcid} Execution Report:\nResult: {status_emoji}\nTurns Evaluated: {len(actual_turns)}"


