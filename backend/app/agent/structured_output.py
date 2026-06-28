from copy import deepcopy
from typing import Any, Dict

from pydantic import ValidationError

from app.agent.schemas import AgentFinalAnswer, AgentToolCall


class AgentStepValidationError(ValueError):
    pass


AGENT_STEP_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": ["tool_call", "final_answer"],
            "description": "下一步动作类型。",
        },
        "tool_name": {
            "type": "string",
            "enum": ["web_search", "video_search", "iot_control"],
            "description": "type 为 tool_call 时要调用的后端白名单工具。",
        },
        "arguments": {
            "type": "object",
            "description": "工具调用参数。不同工具使用不同字段。",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                "device_id": {"type": "string"},
                "action": {
                    "type": "string",
                    "enum": ["move", "privacy_mask", "none"],
                },
                "target": {
                    "type": "string",
                    "enum": [
                        "left",
                        "right",
                        "front_door",
                        "balcony",
                        "window",
                        "garage",
                        "camera_on",
                    ],
                },
                "parameters": {
                    "type": "object",
                    "additionalProperties": True,
                },
            },
            "additionalProperties": True,
        },
        "reason": {
            "type": "string",
            "description": "选择该动作的简短原因。",
        },
        "answer": {
            "type": "string",
            "description": "type 为 final_answer 时返回给用户的自然语言答案。",
        },
        "iot_action": {
            "type": "string",
            "enum": ["move", "privacy_mask", "none"],
            "description": "最终回答关联的 IoT 动作状态。",
        },
    },
    "required": ["type"],
    "additionalProperties": False,
}


def get_response_format(schema_name: str) -> Dict[str, Any]:
    if schema_name != "agent_step":
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "name": "agent_step",
        "schema": deepcopy(AGENT_STEP_JSON_SCHEMA),
        "strict": True,
    }


def validate_agent_step(raw_step: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw_step, dict):
        raise AgentStepValidationError(
            "Model output JSON top-level value must be an object"
        )

    step_type = raw_step.get("type")
    if step_type == "tool_call":
        return _model_to_dict(_validate_tool_call(raw_step))
    if step_type == "final_answer":
        return _model_to_dict(AgentFinalAnswer(**raw_step))

    raise AgentStepValidationError(
        "Model output type must be final_answer or tool_call"
    )


def _validate_tool_call(raw_step: Dict[str, Any]) -> AgentToolCall:
    try:
        tool_call = AgentToolCall(**raw_step)
    except ValidationError:
        raise
    if tool_call.tool_name == "final_answer":
        raise AgentStepValidationError(
            "tool_call.tool_name must be web_search, video_search, or iot_control"
        )
    return tool_call


def _model_to_dict(value: Any) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value.dict()
