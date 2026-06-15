from typing import Optional, Any, Dict, List, Literal

from enum import Enum

from pydantic import BaseModel

class ExpectationType(Enum):
    """Expectation type enums"""
    ANY = "any"             # Not null
    EXACT = "exact"         # Must be exactly the same
    SEMANTIC = "semantic"   # Similar in meaning
    OPTIONAL = "optional"   # Can be null

class Expectation(BaseModel):
    """Defines the Expectation base class"""
    expectation_type: ExpectationType

class TextExpectation(Expectation):
    """Defines a text expectation"""
    expectation_type: ExpectationType = ExpectationType.SEMANTIC
    text: str

class VariableExpectation(Expectation):
    """Defines a variable expectation"""
    expectation_type: ExpectationType = ExpectationType.EXACT
    name: str
    value: str

class VariablesExpectation(Expectation):
    """Defines a list of variable expectations"""
    vars: List[VariableExpectation]

class UserMessage(BaseModel):
    """Defines a user/caller message expectations in a turn"""
    text: Optional[TextExpectation] = None
    vars: Optional[VariablesExpectation] = None

class AgentMessage(BaseModel):
    """Defines an agent message expectations in a turn"""
    text: Optional[TextExpectation] = None
    vars: Optional[VariablesExpectation] = None

class Turn(BaseModel):
    """Defines a turn in a test case, composed of a user message and an agent message"""
    turn_id: Optional[int] = None
    user_message: Optional[UserMessage] = None
    agent_message: Optional[AgentMessage] = None

class ActualMessage(BaseModel):
    """Defines an actual recorded message and variable state in a turn"""
    text: str = ""
    vars: Dict[str, Any] = {}

class ActualTurn(BaseModel):
    """Defines an actual executed turn, storing what both sides actually said and variable states"""
    turn_id: int
    user_message: Optional[ActualMessage] = None
    agent_message: Optional[ActualMessage] = None

class TestCaseResult(Enum):
    """Defines the TestCaseResult enum"""
    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"
    ERROR = "error"

class TestCase(BaseModel):
    """Defines a test case"""
    project_id: str
    region_id: str
    app_id: str
    start_time: str
    tcid: str
    initial_input_variables: Optional[Dict[str, Any]] = {}
    test_procedure: List[Turn]
    goal_expectations: Optional[List[str]] = []
    transcript_expectations: List[str]
    variable_expectations: Dict[str, str]
    overall_result: TestCaseResult
    
    # --- Actual Execution Results ---
    actual_test_procedure: List[ActualTurn] = []
    actual_transcript: List[str] = []
    actual_variables: Dict[str, Any] = {}


