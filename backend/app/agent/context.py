from typing import List, Optional

from app.agent.history import HistoryTrimResult, trim_history
from app.agent.prompts import SYSTEM_PROMPT, TOOL_SPEC
from app.agent.schemas import ChatMessage


FRONTEND_ONLY_ASSISTANT_INTRO = (
    "你好，我是 HomeGuard Agent，可以帮你查视频、联网搜索，"
    "也可以模拟控制摄像头。"
)


class ContextBuilder:
    def __init__(self, max_history_messages: int = 20) -> None:
        self.max_history_messages = max_history_messages

    def model_history_messages(
        self,
        history: List[ChatMessage],
    ) -> List[ChatMessage]:
        return [
            message
            for message in history
            if self._is_model_history_message(message)
        ]

    def trim_model_history(
        self,
        history: List[ChatMessage],
    ) -> HistoryTrimResult:
        return trim_history(
            self.model_history_messages(history),
            self.max_history_messages,
        )

    def build_initial_messages(
        self,
        history: List[ChatMessage],
        user_message: str,
        route_hints: Optional[List[str]] = None,
    ) -> List[ChatMessage]:
        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(role="system", content=TOOL_SPEC),
        ]
        hints = [hint for hint in (route_hints or []) if hint]
        if hints:
            messages.append(
                ChatMessage(
                    role="system",
                    content="后端策略提示：{}".format("；".join(hints)),
                )
            )
        messages.extend(history)
        messages.append(ChatMessage(role="user", content=user_message))
        return messages

    def _is_model_history_message(self, message: ChatMessage) -> bool:
        return not (
            message.role == "assistant"
            and message.content.strip() == FRONTEND_ONLY_ASSISTANT_INTRO
        )
