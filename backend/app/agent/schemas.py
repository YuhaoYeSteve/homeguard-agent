from typing import Any, Dict, List, Literal, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field


ToolName = Literal["web_search", "video_search", "iot_control", "final_answer"]
IotAction = Literal["move", "privacy_mask", "none"]
IotTarget = Literal[
    "left",
    "right",
    "front_door",
    "balcony",
    "window",
    "garage",
    "camera_on",
]


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class AgentToolCall(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    tool_name: ToolName
    arguments: Dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class AgentFinalAnswer(BaseModel):
    type: Literal["final_answer"] = "final_answer"
    answer: str
    iot_action: IotAction = "none"


class IotControlCommand(BaseModel):
    tool: Literal["iot_control"] = "iot_control"
    device_id: str = "camera_living_room"
    action: IotAction
    target: Optional[IotTarget] = None
    parameters: Dict[str, Union[str, int, float, bool]] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str = ""


class IotState(BaseModel):
    iot_action: IotAction = "none"
    device_id: Optional[str] = None
    target: Optional[str] = None
    status: Literal["idle", "simulated_success", "validation_failed", "tool_error"] = "idle"
    raw_command: Optional[IotControlCommand] = None


class VideoSearchResult(BaseModel):
    f_id: str
    f_text: str
    search_score: Optional[float] = None
    ann_score: Optional[float] = None
    metadata: Dict[str, Union[str, int, float, bool]] = Field(default_factory=dict)


class ToolEvent(BaseModel):
    step: int
    tool_name: ToolName
    input: Dict[str, Any] = Field(default_factory=dict)
    output: Dict[str, Any] = Field(default_factory=dict)
    status: Literal["success", "failed", "skipped"]
    elapsed_ms: int


class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str
    client_history: Optional[List[ChatMessage]] = None
    debug: bool = False


class SystemPromptResponse(BaseModel):
    system_prompt: str
    model_id: str


class ChatResponse(BaseModel):
    conversation_id: str
    assistant_message: str
    iot_state: IotState = Field(default_factory=IotState)
    video_results: List[VideoSearchResult] = Field(default_factory=list)
    tool_events: List[ToolEvent] = Field(default_factory=list)
    error: Optional[Dict[str, str]] = None


def new_conversation_id() -> str:
    return "conv_" + uuid4().hex[:12]
