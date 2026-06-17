from typing import Optional, Any, Dict, List
from enum import Enum
from pydantic import BaseModel, Field

class TestCaseResult(Enum):
    """Defines the TestCaseResult enum"""
    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"
    ERROR = "error"

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

class MessageEvaluation(BaseModel):
    """Stores the detailed evaluation of a message (text and/or variables)"""
    passed: bool = True
    text_passed: Optional[bool] = None
    text_score: Optional[int] = None      # For semantic expectations
    text_reasoning: Optional[str] = None  # Reasoning from Gemini
    variables_passed: Optional[bool] = None
    variable_details: Dict[str, Any] = {} # Detail per variable (passed, actual, expected, score, etc.)

class ActualTurn(BaseModel):
    """Defines an actual executed turn, storing what both sides actually said, variable states, and evaluation results"""
    turn_id: int
    timestamp: Optional[str] = None
    user_message: Optional[ActualMessage] = None
    agent_message: Optional[ActualMessage] = None
    user_message_evaluation: Optional[MessageEvaluation] = None
    agent_message_evaluation: Optional[MessageEvaluation] = None
    overall_turn_result: Optional[TestCaseResult] = None

# --- New Reorganized Structures ---

class ConversationExpectations(BaseModel):
    """Expectations at the conversation level, checking global traits after session completes"""
    goal_expectations: Optional[List[str]] = []
    transcript_expectations: List[str] = []
    variable_expectations: Dict[str, str] = {}

class ExpectedTestProcedure(BaseModel):
    """The full test plan including sequential turns and conversation-level expectations"""
    turn_expectations: List[Turn]
    conversation_expectations: ConversationExpectations

class ConversationEvaluations(BaseModel):
    """The result of evaluating conversation level expectations"""
    transcript_evaluations: Dict[str, bool] = {}
    variable_evaluations: Dict[str, bool] = {}

class ActualTestProcedure(BaseModel):
    """The recorded procedure of actual execution and the resulting evaluations"""
    actual_turns: List[ActualTurn] = []
    actual_conversation_evaluations: Optional[ConversationEvaluations] = None
    actual_variables: Dict[str, Any] = {}

class TestCase(BaseModel):
    """Defines a test case with expectations and execution/evaluation actuals"""
    project_id: str
    region_id: str
    app_id: str
    session_id: Optional[str] = None
    start_time: str
    tcid: str
    initial_input_variables: Optional[Dict[str, Any]] = {}
    overall_result: TestCaseResult = TestCaseResult.PENDING

    expected_test_procedure: ExpectedTestProcedure
    actual_test_procedure: Optional[ActualTestProcedure] = None

class SimilarityEvaluation(BaseModel):
    """Pydantic model for structured Gemini similarity evaluations."""
    score: int = Field(description="Similarity score between 1 (Not similar) and 5 (Very strongly similar)")
    reasoning: str = Field(description="A brief rationale for the assigned score")

class TranscriptExpectationEvaluation(BaseModel):
    """Evaluation result for a single transcript expectation."""
    expectation: str = Field(description="The high-level transcript expectation that was checked")
    passed: bool = Field(description="Whether the transcript met the expectation")
    reasoning: str = Field(description="A brief rationale for the decision")

class TranscriptEvaluationResponse(BaseModel):
    """Pydantic model for bulk transcript expectation checking."""
    evaluations: List[TranscriptExpectationEvaluation]
