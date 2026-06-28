from typing import List

from pydantic import BaseModel

from app.agent.schemas import ChatMessage


class HistoryTrimResult(BaseModel):
    messages: List[ChatMessage]
    original_count: int
    kept_count: int
    dropped_count: int

    @property
    def was_trimmed(self) -> bool:
        return self.dropped_count > 0


def trim_history(
    history: List[ChatMessage],
    max_messages: int,
) -> HistoryTrimResult:
    original_count = len(history)
    if max_messages <= 0 or original_count <= max_messages:
        return HistoryTrimResult(
            messages=list(history),
            original_count=original_count,
            kept_count=original_count,
            dropped_count=0,
        )

    kept_messages = list(history[-max_messages:])
    return HistoryTrimResult(
        messages=kept_messages,
        original_count=original_count,
        kept_count=len(kept_messages),
        dropped_count=original_count - len(kept_messages),
    )
