from fastapi.testclient import TestClient

import app.api.chat as chat_module
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.schemas import ChatResponse
from app.core.config import get_settings
from app.main import app


def test_health_returns_ok():
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert set(payload) == {"status", "vikingdb_configured"}
    assert isinstance(payload["vikingdb_configured"], bool)


def test_system_prompt_endpoint_returns_agent_prompt():
    response = TestClient(app).get("/api/system-prompt")

    assert response.status_code == 200
    assert response.json() == {
        "system_prompt": SYSTEM_PROMPT,
        "model_id": get_settings().ark_model,
    }


def test_chat_endpoint_is_removed():
    response = TestClient(app).post(
        "/api/chat",
        json={"conversation_id": "conv_removed", "message": "你好"},
    )

    assert response.status_code == 404


def test_chat_stream_returns_sse_events(monkeypatch):
    chat_module.session_store._messages.clear()
    captured = {}

    class FakeArkSDKModelClient:
        pass

    class FakeToolRegistry:
        pass

    class FakeAgentLoop:
        def __init__(self, model_client, tool_registry):
            captured["model_client"] = model_client
            captured["tool_registry"] = tool_registry

        def run_stream(self, conversation_id, history, user_message):
            assert conversation_id == "conv_stream_test"
            assert history == []
            assert user_message == "你好"
            captured["stream_called"] = True
            yield {"type": "session", "conversation_id": conversation_id}
            yield {"type": "answer_delta", "delta": "流式"}
            yield {
                "type": "final",
                "response": {
                    "conversation_id": conversation_id,
                    "assistant_message": "流式回答",
                },
            }
            yield {"type": "done"}

    monkeypatch.setattr(chat_module, "ArkSDKModelClient", FakeArkSDKModelClient)
    monkeypatch.setattr(chat_module, "ToolRegistry", FakeToolRegistry)
    monkeypatch.setattr(chat_module, "AgentLoop", FakeAgentLoop)

    with TestClient(app).stream(
        "POST",
        "/api/chat/stream",
        json={"conversation_id": "conv_stream_test", "message": "你好"},
    ) as response:
        body = response.read().decode("utf-8")

    assert response.status_code == 200
    assert "data: " in body
    assert '"type": "answer_delta"' in body
    assert '"type": "done"' in body
    assert captured["stream_called"] is True
    assert isinstance(captured["model_client"], FakeArkSDKModelClient)
    assert isinstance(captured["tool_registry"], FakeToolRegistry)

    messages = chat_module.session_store.list_messages("conv_stream_test")
    assert [message.role for message in messages] == ["user", "assistant"]
    assert [message.content for message in messages] == ["你好", "流式回答"]


def test_chat_stream_converts_unexpected_errors_to_sse_error(monkeypatch):
    chat_module.session_store._messages.clear()

    class FakeArkSDKModelClient:
        pass

    class FakeToolRegistry:
        pass

    class FakeAgentLoop:
        def __init__(self, model_client, tool_registry):
            pass

        def run_stream(self, conversation_id, history, user_message):
            yield {"type": "session", "conversation_id": conversation_id}
            yield {
                "type": "status",
                "status": "analyzing",
                "message": "正在分析意图...",
                "step": 1,
            }
            raise RuntimeError("simulated stream crash")

    monkeypatch.setattr(chat_module, "ArkSDKModelClient", FakeArkSDKModelClient)
    monkeypatch.setattr(chat_module, "ToolRegistry", FakeToolRegistry)
    monkeypatch.setattr(chat_module, "AgentLoop", FakeAgentLoop)

    with TestClient(app, raise_server_exceptions=False).stream(
        "POST",
        "/api/chat/stream",
        json={"conversation_id": "conv_stream_crash", "message": "你好"},
    ) as response:
        body = response.read().decode("utf-8")

    assert response.status_code == 200
    assert '"type": "session"' in body
    assert '"type": "error"' in body
    assert '"code": "AGENT_STREAM_ERROR"' in body
    assert "simulated stream crash" in body
    assert '"type": "done"' in body


def test_chat_stream_uses_empty_client_history(monkeypatch):
    chat_module.session_store._messages.clear()
    chat_module.session_store.append(
        "conv_stream_empty_history",
        {"role": "assistant", "content": "服务端旧历史"},
    )
    captured = {}

    class FakeArkSDKModelClient:
        pass

    class FakeToolRegistry:
        pass

    class FakeAgentLoop:
        def __init__(self, model_client, tool_registry):
            pass

        def run_stream(self, conversation_id, history, user_message):
            captured["conversation_id"] = conversation_id
            captured["history"] = history
            captured["user_message"] = user_message
            yield {"type": "session", "conversation_id": conversation_id}
            yield {
                "type": "final",
                "response": {
                    "conversation_id": conversation_id,
                    "assistant_message": "重新开始后的回答",
                },
            }
            yield {"type": "done"}

    monkeypatch.setattr(chat_module, "ArkSDKModelClient", FakeArkSDKModelClient)
    monkeypatch.setattr(chat_module, "ToolRegistry", FakeToolRegistry)
    monkeypatch.setattr(chat_module, "AgentLoop", FakeAgentLoop)

    with TestClient(app).stream(
        "POST",
        "/api/chat/stream",
        json={
            "conversation_id": "conv_stream_empty_history",
            "message": "重新开始",
            "client_history": [],
        },
    ) as response:
        response.read()

    assert response.status_code == 200
    assert captured["conversation_id"] == "conv_stream_empty_history"
    assert captured["history"] == []
    assert captured["user_message"] == "重新开始"


def test_chat_stream_error_without_final_does_not_persist_messages(monkeypatch):
    chat_module.session_store._messages.clear()

    class FakeArkSDKModelClient:
        pass

    class FakeToolRegistry:
        pass

    class FakeAgentLoop:
        def __init__(self, model_client, tool_registry):
            pass

        def run_stream(self, conversation_id, history, user_message):
            yield {"type": "session", "conversation_id": conversation_id}
            yield {
                "type": "error",
                "code": "ARK_SDK_FAILED",
                "message": "流式失败",
            }
            yield {"type": "done"}

    monkeypatch.setattr(chat_module, "ArkSDKModelClient", FakeArkSDKModelClient)
    monkeypatch.setattr(chat_module, "ToolRegistry", FakeToolRegistry)
    monkeypatch.setattr(chat_module, "AgentLoop", FakeAgentLoop)

    with TestClient(app).stream(
        "POST",
        "/api/chat/stream",
        json={"conversation_id": "conv_stream_error", "message": "你好"},
    ) as response:
        body = response.read().decode("utf-8")

    assert response.status_code == 200
    assert '"type": "error"' in body
    assert '"type": "done"' in body
    assert chat_module.session_store.list_messages("conv_stream_error") == []
