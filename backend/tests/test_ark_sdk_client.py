import sys
from types import ModuleType, SimpleNamespace

import pytest

from app.agent.schemas import ChatMessage
from app.model.ark_sdk_client import ArkSDKError, ArkSDKModelClient


def test_parse_json_accepts_plain_object():
    client = ArkSDKModelClient(ark_api_key="test-key", client=object())

    result = client._parse_json('{"type":"final_answer","answer":"ok"}')

    assert result == {"type": "final_answer", "answer": "ok"}


def test_parse_json_accepts_json_fence():
    client = ArkSDKModelClient(ark_api_key="test-key", client=object())

    result = client._parse_json('```json\n{"type":"final_answer","answer":"ok"}\n```')

    assert result == {"type": "final_answer", "answer": "ok"}


def test_parse_json_rejects_non_object():
    client = ArkSDKModelClient(ark_api_key="test-key", client=object())

    with pytest.raises(ArkSDKError) as exc_info:
        client._parse_json("[]")

    assert exc_info.value.code == "MODEL_JSON_PARSE_FAILED"


def test_extract_response_text_from_responses_output():
    client = ArkSDKModelClient(ark_api_key="test-key", client=object())
    response = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="message",
                content=[
                    SimpleNamespace(type="output_text", text="hello"),
                    SimpleNamespace(type="text", text=" world"),
                ],
            )
        ]
    )

    assert client._extract_response_text(response) == "hello world"


def test_generate_json_sends_responses_json_schema_and_reasoning_kwargs():
    seen = {}

    class FakeResponses:
        def create(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(
                output_text='{"type":"final_answer","answer":"ok"}'
            )

    class FakeClient:
        responses = FakeResponses()

    client = ArkSDKModelClient(
        ark_api_key="test-key",
        ark_model="doubao-test",
        reasoning_effort="low",
        client=FakeClient(),
    )

    result = client.generate_json([ChatMessage(role="user", content="你好")])

    assert result == {"type": "final_answer", "answer": "ok"}
    assert seen["model"] == "doubao-test"
    response_format = seen["text"]["format"]
    assert response_format["type"] == "json_schema"
    assert response_format["name"] == "agent_step"
    assert response_format["strict"] is True
    assert response_format["schema"]["additionalProperties"] is False
    assert response_format["schema"]["properties"]["type"]["enum"] == [
        "tool_call",
        "final_answer",
    ]
    assert seen["reasoning"] == {"effort": "low"}
    assert "extra_body" not in seen
    assert seen["input"][0]["role"] == "user"
    assert '"schema_name": "agent_step"' in seen["input"][0]["content"]


def test_generate_json_wraps_sdk_errors():
    class FakeResponses:
        def create(self, **kwargs):
            raise RuntimeError("boom")

    class FakeClient:
        responses = FakeResponses()

    client = ArkSDKModelClient(ark_api_key="test-key", client=FakeClient())

    with pytest.raises(ArkSDKError) as exc_info:
        client.generate_json([ChatMessage(role="user", content="你好")])

    assert exc_info.value.code == "ARK_SDK_FAILED"
    assert exc_info.value.stderr == "boom"


def test_generate_json_maps_timeout_errors_to_stable_code():
    class FakeResponses:
        def create(self, **kwargs):
            raise TimeoutError("timed out after 25 seconds")

    class FakeClient:
        responses = FakeResponses()

    client = ArkSDKModelClient(ark_api_key="test-key", client=FakeClient())

    with pytest.raises(ArkSDKError) as exc_info:
        client.generate_json([ChatMessage(role="user", content="你好")])

    assert exc_info.value.code == "ARK_SDK_TIMEOUT"
    assert "timed out" in str(exc_info.value)


def test_generate_json_rejects_invalid_reasoning_effort():
    class FakeResponses:
        def create(self, **kwargs):
            raise AssertionError("responses.create should not be called")

    class FakeClient:
        responses = FakeResponses()

    client = ArkSDKModelClient(
        ark_api_key="test-key",
        reasoning_effort="very-high",
        client=FakeClient(),
    )

    with pytest.raises(ArkSDKError) as exc_info:
        client.generate_json([ChatMessage(role="user", content="你好")])

    assert exc_info.value.code == "ARK_SDK_INVALID_REASONING_EFFORT"


def test_client_initialization_passes_configured_timeout_to_ark_runtime(monkeypatch):
    seen = {}
    fake_module = ModuleType("volcenginesdkarkruntime")

    class FakeArk:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    fake_module.Ark = FakeArk
    monkeypatch.setitem(sys.modules, "volcenginesdkarkruntime", fake_module)

    client = ArkSDKModelClient(
        ark_api_key="test-key",
        ark_base_url="https://ark.example/api/v3",
        ark_timeout_seconds=12.5,
        ark_max_retries=0,
    )

    assert isinstance(client._client_or_create(), FakeArk)
    assert seen["api_key"] == "test-key"
    assert seen["base_url"] == "https://ark.example/api/v3"
    assert seen["timeout"] == 12.5
    assert seen["max_retries"] == 0


def test_stream_text_maps_answer_reasoning_and_meta_events():
    chunks = [
        SimpleNamespace(type="response.reasoning_summary_text.delta", delta="分析"),
        SimpleNamespace(type="response.output_text.delta", delta="你好"),
        SimpleNamespace(
            type="response.completed",
            response=SimpleNamespace(
                model="doubao-test",
                usage=SimpleNamespace(total_tokens=7),
            ),
        ),
    ]

    class FakeResponses:
        def create(self, **kwargs):
            return iter(chunks)

    class FakeClient:
        responses = FakeResponses()

    client = ArkSDKModelClient(
        ark_api_key="test-key",
        ark_model="doubao-test",
        client=FakeClient(),
    )

    events = list(client.stream_text([ChatMessage(role="user", content="你好")]))

    assert events == [
        {"type": "reasoning_delta", "delta": "分析"},
        {"type": "answer_delta", "delta": "你好"},
        {"type": "model_meta", "model": "doubao-test", "usage": {"total_tokens": 7}},
    ]


def test_stream_text_closes_plain_stream_objects():
    class FakeStream:
        def __init__(self):
            self.closed = False

        def __iter__(self):
            yield SimpleNamespace(type="response.output_text.delta", delta="你好")

        def close(self):
            self.closed = True

    stream = FakeStream()

    class FakeResponses:
        def create(self, **kwargs):
            return stream

    class FakeClient:
        responses = FakeResponses()

    client = ArkSDKModelClient(ark_api_key="test-key", client=FakeClient())

    events = list(client.stream_text([ChatMessage(role="user", content="你好")]))

    assert events == [{"type": "answer_delta", "delta": "你好"}]
    assert stream.closed is True


def test_stream_text_maps_failed_and_error_events():
    chunks = [
        SimpleNamespace(
            type="response.incomplete",
            response=SimpleNamespace(
                incomplete_details=SimpleNamespace(reason="max_output_tokens")
            ),
        ),
        SimpleNamespace(
            type="response.failed",
            response=SimpleNamespace(
                error=SimpleNamespace(code="bad_request", message="参数错误")
            ),
        ),
        SimpleNamespace(type="error", code="stream_error", message="流中断"),
    ]

    class FakeResponses:
        def create(self, **kwargs):
            return iter(chunks)

    class FakeClient:
        responses = FakeResponses()

    client = ArkSDKModelClient(
        ark_api_key="test-key",
        ark_model="doubao-test",
        client=FakeClient(),
    )

    events = list(client.stream_text([ChatMessage(role="user", content="你好")]))

    assert events == [
        {
            "type": "error",
            "code": "ARK_SDK_INCOMPLETE",
            "message": "Ark response incomplete: max_output_tokens",
        },
        {"type": "error", "code": "bad_request", "message": "参数错误"},
        {"type": "error", "code": "stream_error", "message": "流中断"},
    ]
