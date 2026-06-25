from typing import List, Optional, Dict, Any
from google.adk.tools import ToolContext
import io
import csv

def create_test_case(
        tcid: str,
        test_repository_path: Optional[str],
        summary: Optional[str],
        test_type: Optional[str],
        test_case_class: Optional[str],
        reporter: Optional[str],
        priority: Optional[str],
        single_application: Optional[str],
        test_data_pre_conditions: Optional[str],
        pre_agent_procedure: Optional[str],
        required_variables: Dict[str, Any],
        agent_test_procedure: List[str],
        expectation_goal: List[str],
        expectation_transcript: List[str],
        expectation_variables: Dict[str, Any],
        context: ToolContext
) -> Dict[str, Any]:
    """Create a standardized test case.

    Args:
        tcid: The test case ID.
        test_repository_path: The path to the test repository.
        summary: The summary of the test case.
        test_type: The type of the test case.
        test_case_class: The class of the test case.
        reporter: The reporter of the test case.
        priority: The priority of the test case.
        single_application: Whether the test case is single application.
        test_data_pre_conditions: The test data pre-conditions.
        pre_agent_procedure: The pre-agent procedure.
        required_variables: The required variables.
        agent_test_procedure: The agent test procedure.
        expectation_goal: The expectation goal.
        expectation_transcript: The expectation transcript.
        expectation_variables: The expectation variables.
        context: The tool context that is automatically passed. Do not mannually input anything.
    """

    test_case = {
        "tcid": tcid,
        "Test Repository path": test_repository_path,
        "Summary": summary,
        "Test Type": test_type,
        "Test Case Class": test_case_class,
        "Reporter": reporter,
        "Priority": priority,
        "Single Application": single_application,
        "Test Data Pre-Conditions": test_data_pre_conditions,
        "Pre-Agent Procedure": pre_agent_procedure,
        "Required Variables": required_variables,
        "Agent Test Procedure": agent_test_procedure,
        "Expectation_Goal": expectation_goal,
        "Expectation_Transcript": expectation_transcript,
        "Expectations_Variables": expectation_variables,
    }

    if "test_cases" not in context.state:
        context.state["test_cases"] = []
    
    context.state["test_cases"].append(test_case)

    return context.state["test_cases"]

def get_test_cases_csv(context: ToolContext) -> str:
    """Returns test cases as a CSV

    Args:
        context: The tool context that is automatically passed. Do not manually input anything. 

    Returns:
        str: The CSV of test cases
    """

    test_cases = context.state.get("test_cases")
    if not test_cases:
        return "No test cases found."

    # Use an in-memory string buffer to build the CSV
    output = io.StringIO()
    
    # The header of the CSV will be the keys of the first test case dictionary
    fieldnames = test_cases[0].keys()
    writer = csv.DictWriter(output, fieldnames=fieldnames)

    # Write the header row and then all the test case data
    writer.writeheader()
    writer.writerows(test_cases)

    # Return the CSV string from the buffer
    return output.getvalue()


