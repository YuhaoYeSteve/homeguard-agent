import json
import logging
from typing import Any, Dict

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agent.loop import AgentLoop
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.schemas import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    SystemPromptResponse,
)
from app.agent.tool_registry import ToolRegistry
from app.core.config import get_settings
from app.memory.session_store import session_store
from app.model.ark_sdk_client import ArkSDKModelClient


router = APIRouter()
LOG = logging.getLogger(__name__)


def _sse_line(event: Dict[str, Any]) -> str:
    return "data: {}\n\n".format(json.dumps(event, ensure_ascii=False))


@router.get("/system-prompt", response_model=SystemPromptResponse)
def system_prompt() -> SystemPromptResponse:
    return SystemPromptResponse(
        system_prompt=SYSTEM_PROMPT,
        model_id=get_settings().ark_model,
    )


@router.post("/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    conversation_id = session_store.ensure_conversation(request.conversation_id)
    history = (
        list(request.client_history)
        if request.client_history is not None
        else session_store.list_messages(conversation_id)
    )

    loop = AgentLoop(
        model_client=ArkSDKModelClient(),
        tool_registry=ToolRegistry(),
    )

    def event_generator():
        persisted = False

        def persist(final_response: ChatResponse) -> None:
            nonlocal persisted
            if persisted:
                return
            session_store.append(
                conversation_id,
                ChatMessage(role="user", content=request.message),
            )
            session_store.append(
                conversation_id,
                ChatMessage(
                    role="assistant",
                    content=final_response.assistant_message,
                ),
            )
            persisted = True

        try:
            for event in loop.run_stream(
                conversation_id=conversation_id,
                history=history,
                user_message=request.message,
            ):
                if event.get("type") == "final" and isinstance(
                    event.get("response"), dict
                ):
                    persist(ChatResponse(**event["response"]))
                yield _sse_line(event)
        except Exception as exc:
            LOG.exception("chat stream failed")
            yield _sse_line(
                {
                    "type": "error",
                    "code": "AGENT_STREAM_ERROR",
                    "message": str(exc),
                }
            )
            yield _sse_line({"type": "done"})

    return StreamingResponse(event_generator(), media_type="text/event-stream")
