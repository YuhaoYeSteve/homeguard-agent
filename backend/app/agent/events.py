import re
from typing import Any, Dict, List, Optional

from app.agent.schemas import ChatMessage


ARCHITECTURE_STEPS = {
    "01": {
        "id": "01",
        "title": "用户意图",
        "description": "用户用自然语言表达目标，不需要知道底层工具。",
    },
    "02": {
        "id": "02",
        "title": "上下文打包",
        "description": "系统合并角色约束、工具规格、历史对话和当前消息。",
    },
    "03": {
        "id": "03",
        "title": "模型决策层",
        "description": "LLM 判断下一步是直接回答，还是调用外部能力。",
    },
    "04": {
        "id": "04",
        "title": "动作协议",
        "description": "模型输出受约束 JSON 决策，不能用自由文本驱动业务动作。",
    },
    "05": {
        "id": "05",
        "title": "工具能力层",
        "description": "后端按白名单执行联网搜索、视频检索或 IoT 模拟控制。",
    },
    "06": {
        "id": "06",
        "title": "Observation 回填",
        "description": "工具结果、状态和耗时作为事实依据回填给模型。",
    },
    "07": {
        "id": "07",
        "title": "最终回复",
        "description": "模型基于上下文和 observation 生成自然语言回复。",
    },
    "08": {
        "id": "08",
        "title": "前端可观测",
        "description": "前端展示回答、工具轨迹、IoT 状态和视频结果。",
    },
}


SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|ak|sk|token|authorization|cookie)\s*[:=]\s*[^,\s;]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"),
]


def architecture_status_event(
    architecture_step_id: str,
    status: str,
    message: str,
    step: Optional[int] = None,
    model_round: Optional[int] = None,
    elapsed_ms: Optional[int] = None,
) -> Dict[str, Any]:
    event = {
        "type": "status",
        "status": status,
        "message": redact_sensitive_text(message),
        "architecture_step": ARCHITECTURE_STEPS[architecture_step_id],
    }  # type: Dict[str, Any]
    if step is not None:
        event["step"] = step
    if model_round is not None:
        event["model_round"] = model_round
    if elapsed_ms is not None:
        event["elapsed_ms"] = elapsed_ms
    return event


def model_input_event(
    model_round: int,
    phase: str,
    schema_name: str,
    messages: List[ChatMessage],
    step: int,
    jsonable,
) -> Dict[str, Any]:
    return {
        "type": "model_input",
        "model_round": model_round,
        "phase": phase,
        "step": step,
        "schema_name": schema_name,
        "messages": jsonable(messages),
    }


def model_output_event(
    model_round: int,
    phase: str,
    output: Any,
    elapsed_ms: int,
    step: int,
    jsonable,
) -> Dict[str, Any]:
    return {
        "type": "model_output",
        "model_round": model_round,
        "phase": phase,
        "step": step,
        "output": jsonable(output),
        "elapsed_ms": elapsed_ms,
    }


def history_trimmed_event(
    original_count: int,
    kept_count: int,
    dropped_count: int,
) -> Dict[str, Any]:
    return {
        "type": "history_trimmed",
        "original_count": original_count,
        "kept_count": kept_count,
        "dropped_count": dropped_count,
    }


def error_event(code: str, message: str) -> Dict[str, str]:
    return {
        "type": "error",
        "code": code,
        "message": redact_sensitive_text(message),
    }


def redact_sensitive_text(text: str) -> str:
    redacted = str(text)
    for pattern in SENSITIVE_PATTERNS:
        redacted = pattern.sub(lambda match: _redact_match(match.group(0)), redacted)
    return redacted


def _redact_match(value: str) -> str:
    if "=" in value:
        return "{}=[REDACTED]".format(value.split("=", 1)[0])
    if ":" in value:
        return "{}:[REDACTED]".format(value.split(":", 1)[0])
    if value.lower().startswith("bearer "):
        return "Bearer [REDACTED]"
    return "[REDACTED]"
