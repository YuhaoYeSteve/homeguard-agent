from typing import Dict, List, Optional, Union

from app.agent.schemas import ChatMessage, new_conversation_id


class InMemorySessionStore:
    def __init__(self) -> None:
        self._messages: Dict[str, List[ChatMessage]] = {}

    def ensure_conversation(self, conversation_id: Optional[str]) -> str:
        if not conversation_id:
            conversation_id = new_conversation_id()

        if conversation_id not in self._messages:
            self._messages[conversation_id] = []

        return conversation_id

    def append(
        self, conversation_id: str, message: Union[ChatMessage, Dict[str, str]]
    ) -> ChatMessage:
        conversation_id = self.ensure_conversation(conversation_id)
        chat_message = (
            message if isinstance(message, ChatMessage) else ChatMessage(**message)
        )
        self._messages[conversation_id].append(chat_message)
        return chat_message

    def list_messages(self, conversation_id: str) -> List[ChatMessage]:
        conversation_id = self.ensure_conversation(conversation_id)
        return list(self._messages[conversation_id])


session_store = InMemorySessionStore()
