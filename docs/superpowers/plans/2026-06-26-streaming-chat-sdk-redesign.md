# Streaming Chat SDK Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有安防 Agent 对话页升级为 Ark Python SDK 真流式输出、可展示思考/处理过程、支持 session 管理，并保留 IoT 输出面板。

**Architecture:** 后端新增 Ark SDK 模型适配层和 `/api/chat/stream` SSE 接口；Agent 工具路由继续使用结构化 JSON，最终自然语言回答通过 SDK 流式生成。前端重构为左侧 session 管理、中间流式对话、右侧 IoT 面板的三栏布局，session 数据保存在 localStorage。

**Tech Stack:** Python 3.12, FastAPI, Pydantic, Volcengine Ark Python SDK, pytest, React 18, TypeScript, Vite, CSS。

---

## 当前约束

- 当前目录不是 Git 仓库，计划中的 commit 步骤改为“记录变更文件和验证结果”。
- 现有 `ArkCLIModelClient` 保留，新的对话主链路使用 `ArkSDKModelClient`。
- 前端 IoT 高亮必须继续来自后端 `iot_state`，不能从自然语言回复推断。
- 不展示模型隐藏链路推理，只展示 Ark reasoning summary 或后端处理过程。

## 文件结构

- 修改：`backend/requirements.txt`，加入 Ark SDK 依赖。
- 修改：`backend/app/core/config.py`，加入 SDK 配置。
- 创建：`backend/app/model/ark_sdk_client.py`，封装 Ark SDK JSON 调用与流式事件。
- 修改：`backend/app/model/__init__.py`，导出 SDK client。
- 修改：`backend/app/agent/prompts.py`，新增最终回答流式生成提示词。
- 修改：`backend/app/agent/schemas.py`，扩展 `ChatRequest`，增加流式事件相关类型别名。
- 修改：`backend/app/agent/loop.py`，新增 `run_stream`，保留 `run`。
- 修改：`backend/app/api/chat.py`，新增 `/chat/stream` SSE 接口。
- 创建：`backend/tests/test_ark_sdk_client.py`，覆盖 SDK JSON 解析和事件映射。
- 修改：`backend/tests/test_agent_loop.py`，增加流式 AgentLoop 测试。
- 修改：`backend/tests/test_chat_api.py`，增加 SSE 接口测试。
- 修改：`frontend/src/types.ts`，扩展 session、流式事件、消息类型。
- 修改：`frontend/src/api/chatClient.ts`，新增 POST SSE 流式客户端。
- 修改：`frontend/src/App.tsx`，接入 session 管理和流式状态。
- 修改：`frontend/src/components/ChatPane.tsx`，重构消息、思考摘要、处理过程、输入区。
- 创建：`frontend/src/components/SessionSidebar.tsx`，左侧 session 管理。
- 修改：`frontend/src/components/IotPanel.tsx`，保留功能并调整 JSON 区展示。
- 修改：`frontend/src/styles.css`，整体改为参考项目的浅灰/白色三栏视觉。
- 修改：`README.md`，更新模型接入说明和环境变量。

---

### Task 1: 后端 SDK 配置与模型适配层

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/core/config.py`
- Create: `backend/app/model/ark_sdk_client.py`
- Modify: `backend/app/model/__init__.py`
- Create: `backend/tests/test_ark_sdk_client.py`

- [ ] **Step 1: 写 SDK client 的失败测试**

写入 `backend/tests/test_ark_sdk_client.py`：

```python
from types import SimpleNamespace

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
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd backend
PYTHONPATH=. python3 -m pytest tests/test_ark_sdk_client.py -v
```

Expected: 失败，原因是 `app.model.ark_sdk_client` 尚不存在。

- [ ] **Step 3: 增加依赖和配置**

修改 `backend/requirements.txt`，加入：

```text
volcengine-python-sdk[ark]==1.0.185
```

修改 `backend/app/core/config.py`，在 `Settings` 中加入：

```python
    ark_api_key: str = ""
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_reasoning_effort: str = ""
```

保留现有 `ark_cli_*` 和 `ark_model` 字段。

- [ ] **Step 4: 实现 SDK client**

创建 `backend/app/model/ark_sdk_client.py`：

```python
import json
from typing import Any, Dict, Iterable, Iterator, List, Optional

from app.agent.schemas import ChatMessage
from app.core.config import get_settings


class ArkSDKError(RuntimeError):
    def __init__(self, code: str, message: str, stderr: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.stderr = stderr


class ArkSDKModelClient:
    def __init__(
        self,
        ark_api_key: Optional[str] = None,
        ark_base_url: Optional[str] = None,
        ark_model: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        client: Any = None,
    ) -> None:
        settings = get_settings()
        self.ark_api_key = ark_api_key if ark_api_key is not None else settings.ark_api_key
        self.ark_base_url = ark_base_url or settings.ark_base_url
        self.ark_model = ark_model or settings.ark_model
        self.reasoning_effort = (
            reasoning_effort
            if reasoning_effort is not None
            else settings.ark_reasoning_effort
        )
        self._client = client

    def generate_json(
        self, messages: List[ChatMessage], schema_name: str = "agent_step"
    ) -> Dict[str, Any]:
        prompt = self._format_messages(messages, schema_name)
        response = self._client_or_create().responses.create(
            model=self.ark_model,
            input=[
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                }
            ],
        )
        return self._parse_json(self._extract_response_text(response))

    def stream_text(self, messages: List[ChatMessage]) -> Iterator[Dict[str, Any]]:
        extra_body = self._build_extra_body()
        try:
            stream = self._client_or_create().responses.create(
                model=self.ark_model,
                input=self._to_responses_input(messages),
                stream=True,
                extra_body=extra_body or None,
            )
            for chunk in stream:
                yield from self._map_stream_chunk(chunk)
        except ArkSDKError:
            raise
        except Exception as exc:
            raise ArkSDKError("ARK_SDK_FAILED", str(exc)) from exc

    def _client_or_create(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.ark_api_key:
            raise ArkSDKError(
                "ARK_SDK_NOT_CONFIGURED",
                "Missing ARK_API_KEY. Please set it in backend/.env or environment.",
            )
        try:
            from volcenginesdkarkruntime import Ark
        except Exception as exc:
            raise ArkSDKError(
                "ARK_SDK_IMPORT_FAILED",
                "volcenginesdkarkruntime is not installed",
            ) from exc
        self._client = Ark(base_url=self.ark_base_url, api_key=self.ark_api_key)
        return self._client

    def _format_messages(
        self, messages: List[ChatMessage], schema_name: str = "agent_step"
    ) -> str:
        payload = {
            "schema_name": schema_name,
            "messages": [self._message_to_dict(message) for message in messages],
        }
        return json.dumps(payload, ensure_ascii=False)

    def _to_responses_input(self, messages: List[ChatMessage]) -> List[Dict[str, Any]]:
        responses_input = []
        for message in messages:
            role = message.role if message.role in ("system", "user", "assistant") else "user"
            text = message.content
            if message.role == "tool":
                text = "工具返回：{}".format(message.content)
            responses_input.append(
                {
                    "role": role,
                    "content": [{"type": "input_text", "text": text}],
                }
            )
        return responses_input

    def _build_extra_body(self) -> Dict[str, Any]:
        if self.reasoning_effort in ("minimal", "low", "medium", "high"):
            return {"reasoning_effort": self.reasoning_effort}
        return {}

    def _map_stream_chunk(self, chunk: Any) -> Iterable[Dict[str, Any]]:
        chunk_type = getattr(chunk, "type", "")
        if chunk_type == "response.output_text.delta":
            yield {"type": "answer_delta", "delta": getattr(chunk, "delta", "")}
        elif chunk_type == "response.reasoning_summary_text.delta":
            yield {"type": "reasoning_delta", "delta": getattr(chunk, "delta", "")}
        elif chunk_type == "response.completed":
            response = getattr(chunk, "response", None)
            usage = getattr(response, "usage", None)
            event = {
                "type": "model_meta",
                "model": getattr(response, "model", None),
                "usage": {
                    "total_tokens": getattr(usage, "total_tokens", 0),
                },
            }
            yield event
        elif chunk_type == "response.failed":
            response = getattr(chunk, "response", None)
            error = getattr(response, "error", None)
            message = getattr(error, "message", "Ark response failed")
            yield {"type": "error", "code": "ARK_SDK_FAILED", "message": message}
        elif chunk_type == "error":
            yield {
                "type": "error",
                "code": "ARK_SDK_FAILED",
                "message": getattr(chunk, "message", "Ark stream error"),
            }

    def _extract_response_text(self, response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str):
            return output_text

        parts = []
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", "") != "message":
                continue
            for content in getattr(item, "content", []) or []:
                content_type = getattr(content, "type", "")
                if content_type in ("output_text", "text"):
                    parts.append(str(getattr(content, "text", "")))
        return "".join(parts)

    def _parse_json(self, raw: str) -> Dict[str, Any]:
        text = self._strip_json_fence(raw)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ArkSDKError(
                "MODEL_JSON_PARSE_FAILED",
                "Model output is not valid JSON",
                stderr=raw,
            ) from exc
        if not isinstance(parsed, dict):
            raise ArkSDKError(
                "MODEL_JSON_PARSE_FAILED",
                "Model output JSON top-level value must be an object",
                stderr=raw,
            )
        return parsed

    def _strip_json_fence(self, raw: str) -> str:
        text = raw.strip()
        if not text.startswith("```"):
            return text
        lines = text.splitlines()
        if len(lines) >= 2 and lines[0].strip().lower() in ("```json", "```"):
            if lines[-1].strip() == "```":
                return "\n".join(lines[1:-1]).strip()
        return text

    def _message_to_dict(self, message: ChatMessage) -> Dict[str, str]:
        if hasattr(message, "model_dump"):
            data = message.model_dump()
        else:
            data = message.dict()
        return {"role": data["role"], "content": data["content"]}
```

- [ ] **Step 5: 导出 SDK client**

修改 `backend/app/model/__init__.py`：

```python
from app.model.ark_cli_client import ArkCLIError, ArkCLIModelClient
from app.model.ark_sdk_client import ArkSDKError, ArkSDKModelClient

__all__ = [
    "ArkCLIError",
    "ArkCLIModelClient",
    "ArkSDKError",
    "ArkSDKModelClient",
]
```

- [ ] **Step 6: 运行 SDK client 测试**

Run:

```bash
cd backend
PYTHONPATH=. python3 -m pytest tests/test_ark_sdk_client.py -v
```

Expected: `5 passed`。

---

### Task 2: 流式 AgentLoop

**Files:**
- Modify: `backend/app/agent/prompts.py`
- Modify: `backend/app/agent/schemas.py`
- Modify: `backend/app/agent/loop.py`
- Modify: `backend/tests/test_agent_loop.py`

- [ ] **Step 1: 写 AgentLoop 流式失败测试**

追加到 `backend/tests/test_agent_loop.py`：

```python
class FakeStreamingModelClient(FakeModelClient):
    def __init__(self, outputs, stream_events):
        super().__init__(outputs)
        self.stream_events = list(stream_events)
        self.stream_calls = []

    def stream_text(self, messages):
        self.stream_calls.append(list(messages))
        yield from self.stream_events


def test_agent_loop_streams_direct_final_answer():
    model = FakeStreamingModelClient(
        [
            {
                "type": "final_answer",
                "answer": "你好，我可以帮你查看监控。",
                "iot_action": "none",
            }
        ],
        [
            {"type": "reasoning_delta", "delta": "判断为普通问候。"},
            {"type": "answer_delta", "delta": "你好，"},
            {"type": "answer_delta", "delta": "我可以帮你查看监控。"},
        ],
    )

    events = list(
        AgentLoop(model_client=model, tool_registry=FakeToolRegistry()).run_stream(
            conversation_id="conv_stream",
            history=[],
            user_message="你好",
        )
    )

    assert [event["type"] for event in events] == [
        "session",
        "status",
        "status",
        "reasoning_delta",
        "answer_delta",
        "answer_delta",
        "final",
        "done",
    ]
    final_event = events[-2]
    assert final_event["response"]["assistant_message"] == "你好，我可以帮你查看监控。"
    assert final_event["response"]["conversation_id"] == "conv_stream"
    assert model.stream_calls


def test_agent_loop_streams_tool_call_and_updates_iot_state():
    model = FakeStreamingModelClient(
        [
            {
                "type": "tool_call",
                "tool_name": "iot_control",
                "arguments": {
                    "device_id": "camera_living_room",
                    "action": "move",
                    "target": "front_door",
                },
                "reason": "用户要求摄像头转向门口",
            },
            {
                "type": "final_answer",
                "answer": "摄像头已转向门口。",
                "iot_action": "move",
            },
        ],
        [
            {"type": "answer_delta", "delta": "摄像头已"},
            {"type": "answer_delta", "delta": "转向门口。"},
        ],
    )

    events = list(
        AgentLoop(model_client=model, tool_registry=FakeToolRegistry()).run_stream(
            conversation_id="conv_iot_stream",
            history=[],
            user_message="把摄像头转向门口",
        )
    )

    event_types = [event["type"] for event in events]
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    final_event = [event for event in events if event["type"] == "final"][0]
    assert final_event["response"]["assistant_message"] == "摄像头已转向门口。"
    assert final_event["response"]["iot_state"]["iot_action"] == "move"
    assert final_event["response"]["iot_state"]["target"] == "front_door"
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd backend
PYTHONPATH=. python3 -m pytest tests/test_agent_loop.py::test_agent_loop_streams_direct_final_answer tests/test_agent_loop.py::test_agent_loop_streams_tool_call_and_updates_iot_state -v
```

Expected: 失败，原因是 `AgentLoop.run_stream` 尚不存在。

- [ ] **Step 3: 新增最终回答提示词**

追加到 `backend/app/agent/prompts.py`：

```python
FINAL_ANSWER_PROMPT = """你是安防 C 端 App 内的智能 Agent。
你现在要根据用户问题、会话历史和工具返回结果生成最终自然语言回复。

要求：
1. 用中文回答，语气清晰、简洁、适合 C 端用户。
2. 不输出 JSON，不输出 Markdown 标题。
3. 如果工具执行失败，要说明失败原因和用户可以怎么重试。
4. 如果涉及 IoT 控制，只描述后端已经校验并模拟执行的结果，不编造真实设备状态。
5. 如果涉及视频搜索，优先引用工具返回的视频片段描述。
"""
```

- [ ] **Step 4: 扩展 ChatRequest**

修改 `backend/app/agent/schemas.py` 中的 `ChatRequest`：

```python
class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str
    debug: bool = False
    client_history: List[ChatMessage] = Field(default_factory=list)
```

- [ ] **Step 5: 实现 `run_stream`**

在 `backend/app/agent/loop.py` 中增加导入：

```python
from app.agent.prompts import FINAL_ANSWER_PROMPT, SYSTEM_PROMPT, TOOL_SPEC
from app.model.ark_sdk_client import ArkSDKError
```

在 `AgentLoop` 类中增加：

```python
    def run_stream(
        self,
        conversation_id: str,
        history: List[ChatMessage],
        user_message: str,
    ):
        messages = self._build_initial_messages(history, user_message)
        iot_state = IotState()
        video_results = []  # type: List[VideoSearchResult]
        tool_events = []  # type: List[ToolEvent]

        yield {"type": "session", "conversation_id": conversation_id}

        try:
            for step in range(1, self.max_steps + 1):
                yield {
                    "type": "status",
                    "status": "analyzing",
                    "message": "正在分析意图...",
                    "step": step,
                }
                raw_step = self.model_client.generate_json(
                    messages,
                    schema_name="agent_step",
                )
                step_type = raw_step.get("type")

                if step_type == "final_answer":
                    final_answer = AgentFinalAnswer(**raw_step)
                    yield {
                        "type": "status",
                        "status": "answering",
                        "message": "正在生成回答...",
                        "step": step,
                    }
                    assistant_message = yield from self._stream_final_answer(
                        history=history,
                        user_message=user_message,
                        working_messages=messages,
                        draft_answer=final_answer.answer,
                    )
                    if not assistant_message:
                        assistant_message = final_answer.answer
                    response = ChatResponse(
                        conversation_id=conversation_id,
                        assistant_message=assistant_message,
                        iot_state=iot_state,
                        video_results=video_results,
                        tool_events=tool_events,
                    )
                    yield {"type": "final", "response": self._jsonable(response)}
                    yield {"type": "done"}
                    return

                if step_type == "tool_call":
                    tool_call = AgentToolCall(**raw_step)
                    yield {
                        "type": "tool_call",
                        "step": step,
                        "tool_name": tool_call.tool_name,
                        "arguments": tool_call.arguments,
                        "reason": tool_call.reason,
                    }
                    result, event = self.tool_registry.run(
                        tool_call.tool_name,
                        tool_call.arguments,
                        step,
                    )
                    tool_events.append(event)

                    if tool_call.tool_name == "iot_control":
                        iot_state = extract_iot_state(result)
                    elif tool_call.tool_name == "video_search":
                        video_results = extract_video_results(result)

                    yield {
                        "type": "tool_result",
                        "step": step,
                        "tool_name": tool_call.tool_name,
                        "event": self._jsonable(event),
                        "iot_state": self._jsonable(iot_state),
                        "video_results": self._jsonable(video_results),
                    }
                    self._append_tool_observation(messages, tool_call, result, event)
                    continue

                yield {
                    "type": "error",
                    "code": "MODEL_VALIDATION_ERROR",
                    "message": "Model output type must be final_answer or tool_call",
                }
                yield {"type": "done"}
                return

            response = ChatResponse(
                conversation_id=conversation_id,
                assistant_message=(
                    "我已经尝试处理你的请求，但还没有得到稳定的最终回答。"
                    "请稍后重试，或换一种方式描述需求。"
                ),
                iot_state=iot_state,
                video_results=video_results,
                tool_events=tool_events,
            )
            yield {"type": "final", "response": self._jsonable(response)}
            yield {"type": "done"}
        except ValidationError as exc:
            yield {
                "type": "error",
                "code": "MODEL_VALIDATION_ERROR",
                "message": str(exc),
            }
            yield {"type": "done"}
        except (ArkCLIError, ArkSDKError) as exc:
            yield {"type": "error", "code": exc.code, "message": str(exc)}
            yield {"type": "done"}

    def _stream_final_answer(
        self,
        history: List[ChatMessage],
        user_message: str,
        working_messages: List[ChatMessage],
        draft_answer: str,
    ):
        final_messages = [
            ChatMessage(role="system", content=FINAL_ANSWER_PROMPT),
        ]
        final_messages.extend(history)
        final_messages.append(ChatMessage(role="user", content=user_message))
        final_messages.append(
            ChatMessage(
                role="assistant",
                content="结构化决策给出的回答初稿：{}".format(draft_answer),
            )
        )
        for message in working_messages:
            if message.role == "tool":
                final_messages.append(message)

        chunks = []
        for event in self.model_client.stream_text(final_messages):
            if event.get("type") == "answer_delta":
                chunks.append(str(event.get("delta") or ""))
            yield event
        return "".join(chunks).strip()
```

- [ ] **Step 6: 运行 AgentLoop 测试**

Run:

```bash
cd backend
PYTHONPATH=. python3 -m pytest tests/test_agent_loop.py -v
```

Expected: 现有测试和新增流式测试全部通过。

---

### Task 3: SSE Chat API

**Files:**
- Modify: `backend/app/api/chat.py`
- Modify: `backend/tests/test_chat_api.py`

- [ ] **Step 1: 写 SSE API 失败测试**

追加到 `backend/tests/test_chat_api.py`：

```python
def test_chat_stream_returns_sse_events(monkeypatch):
    chat_module.session_store._messages.clear()

    class FakeArkSDKModelClient:
        pass

    class FakeToolRegistry:
        pass

    class FakeAgentLoop:
        def __init__(self, model_client, tool_registry):
            assert isinstance(model_client, FakeArkSDKModelClient)
            assert isinstance(tool_registry, FakeToolRegistry)

        def run_stream(self, conversation_id, history, user_message):
            assert conversation_id == "conv_stream_api"
            assert history == []
            assert user_message == "你好"
            yield {"type": "session", "conversation_id": conversation_id}
            yield {"type": "answer_delta", "delta": "你好"}
            yield {
                "type": "final",
                "response": {
                    "conversation_id": conversation_id,
                    "assistant_message": "你好",
                    "iot_state": {
                        "iot_action": "none",
                        "device_id": None,
                        "target": None,
                        "status": "idle",
                        "raw_command": None,
                    },
                    "video_results": [],
                    "tool_events": [],
                    "error": None,
                },
            }
            yield {"type": "done"}

    monkeypatch.setattr(chat_module, "ArkSDKModelClient", FakeArkSDKModelClient)
    monkeypatch.setattr(chat_module, "ToolRegistry", FakeToolRegistry)
    monkeypatch.setattr(chat_module, "AgentLoop", FakeAgentLoop)

    with TestClient(app).stream(
        "POST",
        "/api/chat/stream",
        json={"conversation_id": "conv_stream_api", "message": "你好"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "data: " in body
    assert '"type": "answer_delta"' in body
    assert '"type": "done"' in body

    messages = chat_module.session_store.list_messages("conv_stream_api")
    assert [message.role for message in messages] == ["user", "assistant"]
    assert [message.content for message in messages] == ["你好", "你好"]
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd backend
PYTHONPATH=. python3 -m pytest tests/test_chat_api.py::test_chat_stream_returns_sse_events -v
```

Expected: 失败，原因是 `/api/chat/stream` 或 `ArkSDKModelClient` 导入尚未接入。

- [ ] **Step 3: 实现 SSE 接口**

修改 `backend/app/api/chat.py`：

```python
import json
from typing import Any, Dict, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agent.loop import AgentLoop
from app.agent.schemas import ChatMessage, ChatRequest, ChatResponse
from app.agent.tool_registry import ToolRegistry
from app.memory.session_store import session_store
from app.model.ark_cli_client import ArkCLIModelClient
from app.model.ark_sdk_client import ArkSDKModelClient
```

在原 `/chat` 下面增加：

```python
@router.post("/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    conversation_id = session_store.ensure_conversation(request.conversation_id)
    history = (
        list(request.client_history)
        if request.client_history
        else session_store.list_messages(conversation_id)
    )

    loop = AgentLoop(
        model_client=ArkSDKModelClient(),
        tool_registry=ToolRegistry(),
    )

    def event_generator():
        final_response: Optional[ChatResponse] = None
        for event in loop.run_stream(
            conversation_id=conversation_id,
            history=history,
            user_message=request.message,
        ):
            if event.get("type") == "final" and isinstance(event.get("response"), dict):
                final_response = ChatResponse(**event["response"])
            yield _sse_line(event)

        if final_response is not None:
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

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _sse_line(event: Dict[str, Any]) -> str:
    return "data: {}\n\n".format(json.dumps(event, ensure_ascii=False))
```

- [ ] **Step 4: 运行 API 测试**

Run:

```bash
cd backend
PYTHONPATH=. python3 -m pytest tests/test_chat_api.py -v
```

Expected: `test_chat_stream_returns_sse_events` 和现有 API 测试通过。

---

### Task 4: 前端类型、流式客户端与 Session 数据模型

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/chatClient.ts`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 扩展前端类型**

修改 `frontend/src/types.ts`，保留现有类型并增加：

```ts
export interface ChatProcessEvent {
  id: string;
  type: "status" | "tool_call" | "tool_result" | "model_meta" | "error";
  label: string;
  detail?: unknown;
  createdAt: number;
}

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  reasoning?: string;
  statusText?: string;
  processEvents?: ChatProcessEvent[];
  createdAt: number;
  error?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  iotState: IotState;
  toolEvents: ToolEvent[];
  videoResults: VideoSearchResult[];
  createdAt: number;
  updatedAt: number;
}

export type ChatStreamEvent =
  | { type: "session"; conversation_id: string }
  | { type: "status"; status: string; message: string; step?: number }
  | {
      type: "tool_call";
      step: number;
      tool_name: ToolName;
      arguments: Record<string, unknown>;
      reason: string;
    }
  | {
      type: "tool_result";
      step: number;
      tool_name: ToolName;
      event: ToolEvent;
      iot_state: IotState;
      video_results: VideoSearchResult[];
    }
  | { type: "reasoning_delta"; delta: string }
  | { type: "answer_delta"; delta: string }
  | { type: "model_meta"; model?: string | null; usage?: { total_tokens?: number } }
  | { type: "final"; response: ChatResponse }
  | { type: "error"; code?: string; message: string }
  | { type: "done" };
```

- [ ] **Step 2: 实现 POST SSE 流式客户端**

修改 `frontend/src/api/chatClient.ts`，保留 `sendChatMessage`，增加：

```ts
import type { ChatResponse, ChatStreamEvent, Message } from "../types";

const CHAT_STREAM_API_URL = "http://127.0.0.1:8000/api/chat/stream";

export async function streamChatMessage(params: {
  message: string;
  conversationId: string;
  history: Message[];
  onEvent: (event: ChatStreamEvent) => void;
}): Promise<void> {
  const response = await fetch(CHAT_STREAM_API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      conversation_id: params.conversationId,
      message: params.message,
      debug: true,
      client_history: params.history
        .filter((message) => message.role === "user" || message.role === "assistant")
        .map((message) => ({
          role: message.role,
          content: message.content,
        })),
    }),
  });

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(
      `Chat stream failed with ${response.status} ${response.statusText}${
        errorBody ? `: ${errorBody}` : ""
      }`,
    );
  }

  if (!response.body) {
    throw new Error("Chat stream response body is empty");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      const line = frame
        .split("\n")
        .find((item) => item.startsWith("data: "));
      if (!line) {
        continue;
      }
      const jsonText = line.slice("data: ".length);
      params.onEvent(JSON.parse(jsonText) as ChatStreamEvent);
    }
  }
}
```

- [ ] **Step 3: 重写 App 的 session 状态骨架**

修改 `frontend/src/App.tsx`，建立这些 helper：

```ts
const SESSION_STORAGE_KEY = "homeguard_chat_sessions";

function createId(prefix: string) {
  return `${prefix}_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
}

function createEmptySession(): ChatSession {
  const now = Date.now();
  return {
    id: createId("conv"),
    title: "新会话",
    messages: [
      {
        id: createId("msg"),
        role: "assistant",
        content:
          "你好，我是 HomeGuard Agent，可以帮你查视频、联网搜索，也可以模拟控制摄像头。",
        createdAt: now,
      },
    ],
    iotState: INITIAL_IOT_STATE,
    toolEvents: [],
    videoResults: [],
    createdAt: now,
    updatedAt: now,
  };
}

function loadSessions(): ChatSession[] {
  try {
    const raw = localStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) {
      return [createEmptySession()];
    }
    const parsed = JSON.parse(raw) as ChatSession[];
    return Array.isArray(parsed) && parsed.length > 0 ? parsed : [createEmptySession()];
  } catch {
    return [createEmptySession()];
  }
}

function saveSessions(sessions: ChatSession[]) {
  localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(sessions));
}

function titleFromMessage(message: string) {
  const normalized = message.replace(/\s+/g, " ").trim();
  return normalized.length > 18 ? `${normalized.slice(0, 18)}...` : normalized || "新会话";
}
```

- [ ] **Step 4: 运行前端类型检查确认当前重构点**

Run:

```bash
cd frontend
npm run build
```

Expected: 这里可能失败，因为 `App.tsx` 还没有完成流式事件接入；错误应集中在未使用或组件 props 不匹配，下一任务修复。

---

### Task 5: 前端流式交互与组件重构

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/components/SessionSidebar.tsx`
- Modify: `frontend/src/components/ChatPane.tsx`
- Modify: `frontend/src/components/IotPanel.tsx`

- [ ] **Step 1: 创建 SessionSidebar**

创建 `frontend/src/components/SessionSidebar.tsx`：

```tsx
import type { ChatSession } from "../types";

interface SessionSidebarProps {
  sessions: ChatSession[];
  activeSessionId: string;
  onCreateSession: () => void;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
}

export function SessionSidebar({
  sessions,
  activeSessionId,
  onCreateSession,
  onSelectSession,
  onDeleteSession,
}: SessionSidebarProps) {
  return (
    <aside className="session-sidebar" aria-label="会话列表">
      <div className="session-brand">
        <div className="brand-dot">H</div>
        <div>
          <strong>HomeGuard</strong>
          <span>Security Agent</span>
        </div>
      </div>

      <button className="new-session-button" onClick={onCreateSession} type="button">
        + 新对话
      </button>

      <div className="session-list">
        {sessions.map((session) => (
          <div
            className={`session-item ${
              session.id === activeSessionId ? "active" : ""
            }`}
            key={session.id}
          >
            <button onClick={() => onSelectSession(session.id)} type="button">
              <span>{session.title}</span>
              <small>{new Date(session.updatedAt).toLocaleTimeString()}</small>
            </button>
            {sessions.length > 1 ? (
              <button
                aria-label={`删除 ${session.title}`}
                className="delete-session-button"
                onClick={() => onDeleteSession(session.id)}
                type="button"
              >
                ×
              </button>
            ) : null}
          </div>
        ))}
      </div>
    </aside>
  );
}
```

- [ ] **Step 2: 重构 ChatPane props 和消息展示**

修改 `frontend/src/components/ChatPane.tsx` 的 props：

```tsx
interface ChatPaneProps {
  title: string;
  messages: Message[];
  input: string;
  loading: boolean;
  onInputChange: (value: string) => void;
  onSubmit: () => void;
}
```

在消息循环中渲染：

```tsx
{messages.map((message) => (
  <article
    className={`message-row message-${message.role}`}
    key={message.id}
  >
    <div className="message-content">
      <span className="message-role">{ROLE_LABELS[message.role]}</span>
      {message.statusText ? (
        <div className="message-status">{message.statusText}</div>
      ) : null}
      {message.reasoning ? (
        <details className="reasoning-panel">
          <summary>思考摘要</summary>
          <p>{message.reasoning}</p>
        </details>
      ) : null}
      {message.processEvents?.length ? (
        <details className="process-panel">
          <summary>处理过程</summary>
          <ol>
            {message.processEvents.map((event) => (
              <li key={event.id}>
                <strong>{event.label}</strong>
                {event.detail ? (
                  <pre>{JSON.stringify(event.detail, null, 2)}</pre>
                ) : null}
              </li>
            ))}
          </ol>
        </details>
      ) : null}
      <p>{message.content}</p>
      {message.error ? <p className="message-error">{message.error}</p> : null}
    </div>
  </article>
))}
```

保留 Enter 发送和 Shift+Enter 换行逻辑。

- [ ] **Step 3: 在 App 中接入流式事件**

在 `frontend/src/App.tsx` 中实现：

```ts
function processEventLabel(event: ChatStreamEvent) {
  if (event.type === "status") {
    return event.message;
  }
  if (event.type === "tool_call") {
    return `调用工具：${event.tool_name}`;
  }
  if (event.type === "tool_result") {
    return `工具完成：${event.tool_name}`;
  }
  if (event.type === "model_meta") {
    return event.model ? `模型：${event.model}` : "模型返回完成";
  }
  if (event.type === "error") {
    return `错误：${event.message}`;
  }
  return event.type;
}

function toProcessEvent(event: ChatStreamEvent): ChatProcessEvent | null {
  if (!["status", "tool_call", "tool_result", "model_meta", "error"].includes(event.type)) {
    return null;
  }
  return {
    id: createId("process"),
    type: event.type as ChatProcessEvent["type"],
    label: processEventLabel(event),
    detail: event,
    createdAt: Date.now(),
  };
}
```

`handleSubmit` 逻辑使用 `streamChatMessage`：

```ts
const handleSubmit = async () => {
  const messageText = input.trim();
  const activeSession = sessions.find((session) => session.id === activeSessionId);
  if (!activeSession || messageText.length === 0 || loading) {
    return;
  }

  const userMessage: Message = {
    id: createId("msg"),
    role: "user",
    content: messageText,
    createdAt: Date.now(),
  };
  const assistantMessage: Message = {
    id: createId("msg"),
    role: "assistant",
    content: "",
    statusText: "思考中...",
    processEvents: [],
    createdAt: Date.now(),
  };

  setLoading(true);
  setInput("");
  setSessions((current) =>
    current.map((session) =>
      session.id === activeSessionId
        ? {
            ...session,
            title: session.title === "新会话" ? titleFromMessage(messageText) : session.title,
            messages: [...session.messages, userMessage, assistantMessage],
            updatedAt: Date.now(),
          }
        : session,
    ),
  );

  try {
    await streamChatMessage({
      message: messageText,
      conversationId: activeSession.id,
      history: activeSession.messages,
      onEvent: (event) => {
        setSessions((current) =>
          current.map((session) => {
            if (session.id !== activeSessionId) {
              return session;
            }
            const messages = session.messages.map((message) => {
              if (message.id !== assistantMessage.id) {
                return message;
              }
              if (event.type === "answer_delta") {
                return {
                  ...message,
                  statusText: undefined,
                  content: `${message.content}${event.delta}`,
                };
              }
              if (event.type === "reasoning_delta") {
                return {
                  ...message,
                  reasoning: `${message.reasoning ?? ""}${event.delta}`,
                };
              }
              const processEvent = toProcessEvent(event);
              if (processEvent) {
                return {
                  ...message,
                  statusText: event.type === "status" ? event.message : message.statusText,
                  processEvents: [...(message.processEvents ?? []), processEvent],
                };
              }
              if (event.type === "error") {
                return {
                  ...message,
                  statusText: undefined,
                  error: event.message,
                };
              }
              return message;
            });

            if (event.type === "tool_result") {
              return {
                ...session,
                messages,
                iotState: event.iot_state,
                toolEvents: [...session.toolEvents, event.event],
                videoResults: event.video_results,
                updatedAt: Date.now(),
              };
            }
            if (event.type === "final") {
              return {
                ...session,
                messages: messages.map((message) =>
                  message.id === assistantMessage.id
                    ? {
                        ...message,
                        content: event.response.assistant_message || message.content,
                        statusText: undefined,
                      }
                    : message,
                ),
                iotState: event.response.iot_state,
                toolEvents: event.response.tool_events,
                videoResults: event.response.video_results,
                updatedAt: Date.now(),
              };
            }
            return { ...session, messages, updatedAt: Date.now() };
          }),
        );
      },
    });
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    setSessions((current) =>
      current.map((session) =>
        session.id === activeSessionId
          ? {
              ...session,
              messages: session.messages.map((message) =>
                message.id === assistantMessage.id
                  ? {
                      ...message,
                      statusText: undefined,
                      error: `请求失败：${errorMessage}`,
                    }
                  : message,
              ),
              updatedAt: Date.now(),
            }
          : session,
      ),
    );
  } finally {
    setLoading(false);
  }
};
```

- [ ] **Step 4: 调整 IotPanel JSON 展示**

修改 `frontend/src/components/IotPanel.tsx` 中 JSON 区：

```tsx
<details className="iot-json-panel">
  <summary>结构化 JSON</summary>
  <pre className="json-box">{JSON.stringify(state, null, 2)}</pre>
</details>
```

- [ ] **Step 5: 运行前端构建**

Run:

```bash
cd frontend
npm run build
```

Expected: TypeScript 编译通过，Vite 构建成功。

---

### Task 6: 参考视觉重构与 README 更新

**Files:**
- Modify: `frontend/src/styles.css`
- Modify: `README.md`

- [ ] **Step 1: 重写页面整体布局样式**

修改 `frontend/src/styles.css`，使用这些核心布局样式：

```css
.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 248px minmax(0, 1fr) 380px;
  background: #f7f8fa;
  color: #111827;
}

.session-sidebar {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 100vh;
  padding: 18px 14px;
  background: #f7f8fa;
  border-right: 1px solid #eceff3;
}

.chat-pane {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border-left: 1px solid #f1f5f9;
  border-right: 1px solid #f1f5f9;
}

.iot-pane {
  min-height: 100vh;
  overflow-y: auto;
  padding: 22px;
  background: #f7f8fa;
  border-left: 1px solid #eceff3;
}
```

- [ ] **Step 2: 写消息和输入框样式**

追加或替换消息相关样式：

```css
.message-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 24px;
  overflow-y: auto;
  padding: 84px clamp(18px, 5vw, 72px) 24px;
}

.message-row {
  display: flex;
  width: 100%;
}

.message-row.message-user {
  justify-content: flex-end;
}

.message-row.message-assistant {
  justify-content: flex-start;
}

.message-content {
  max-width: min(760px, 88%);
  line-height: 1.75;
}

.message-user .message-content {
  padding: 12px 16px;
  background: #ebf5ff;
  border-radius: 18px 18px 4px 18px;
}

.message-assistant .message-content {
  padding: 0;
  background: transparent;
}

.chat-form {
  margin: 0 auto 28px;
  width: min(820px, calc(100% - 36px));
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  padding: 12px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 24px;
  box-shadow: 0 12px 34px rgba(15, 23, 42, 0.08);
}
```

- [ ] **Step 3: 写 session 和过程面板样式**

加入：

```css
.session-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  border-radius: 12px;
}

.session-item.active {
  background: #e9edf3;
}

.reasoning-panel,
.process-panel,
.iot-json-panel {
  margin: 10px 0;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
}

.reasoning-panel summary,
.process-panel summary,
.iot-json-panel summary {
  padding: 9px 12px;
  color: #6b7280;
  font-size: 13px;
  cursor: pointer;
}

.process-panel pre,
.json-box {
  overflow: auto;
  max-height: 220px;
  margin: 0;
  padding: 12px;
  color: #dbeafe;
  background: #111827;
  border-radius: 0 0 12px 12px;
}
```

- [ ] **Step 4: 写响应式样式**

加入：

```css
@media (max-width: 1180px) {
  .app-shell {
    grid-template-columns: 220px minmax(0, 1fr);
  }

  .iot-pane {
    grid-column: 1 / -1;
    min-height: auto;
    border-left: 0;
    border-top: 1px solid #eceff3;
  }
}

@media (max-width: 760px) {
  .app-shell {
    grid-template-columns: 1fr;
  }

  .session-sidebar,
  .chat-pane,
  .iot-pane {
    min-height: auto;
  }

  .message-list {
    padding: 24px 16px;
  }

  .chat-form {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 5: 更新 README 模型接入说明**

替换 README 的“模型接入约束”段落为：

````markdown
## 模型接入

对话主链路使用火山方舟 Ark Python SDK，以支持流式输出和思考摘要展示。旧的 `ArkCLIModelClient` 仍保留作为兼容层和回退参考，但新对话接口 `/api/chat/stream` 默认使用 SDK。

当前后端从 `backend/.env` 或环境变量读取以下配置：

```text
ARK_API_KEY=你的方舟 API Key
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_MODEL=doubao-seed-1-6-250615
ARK_REASONING_EFFORT=
```

如果未配置 `ARK_API_KEY`，流式对话会返回可读错误，不会影响前端启动。
````

- [ ] **Step 6: 运行构建**

Run:

```bash
cd frontend
npm run build
```

Expected: 构建成功。

---

### Task 7: 全量验证

**Files:**
- No code changes.

- [ ] **Step 1: 运行后端测试**

Run:

```bash
cd backend
PYTHONPATH=. python3 -m pytest tests -v
```

Expected: 所有后端测试通过。

- [ ] **Step 2: 运行前端构建**

Run:

```bash
cd frontend
npm run build
```

Expected: TypeScript 和 Vite 构建通过。

- [ ] **Step 3: 启动后端做本地冒烟**

Run:

```bash
cd backend
PYTHONPATH=. python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Expected: 服务监听 `http://127.0.0.1:8000`，无启动异常。

- [ ] **Step 4: 启动前端做本地冒烟**

Run:

```bash
cd frontend
npm run dev
```

Expected: Vite 服务监听 `http://127.0.0.1:5173`。

- [ ] **Step 5: 手动验证关键路径**

在浏览器打开 `http://127.0.0.1:5173`，验证：

```text
1. 左侧能新建、切换、删除 session。
2. 发送“你好”后，中间出现思考中占位，并流式显示回复或可读 SDK 配置错误。
3. 发送“把客厅摄像头转向门口”后，右侧 IoT 面板根据后端 JSON 高亮“移动”。
4. 刷新页面后，session 列表和历史消息仍保留。
5. 请求失败后输入框恢复可用。
```

- [ ] **Step 6: 记录变更文件和验证结果**

由于当前目录不是 Git 仓库，在最终回复中列出：

```text
修改/新增的后端文件
修改/新增的前端文件
README 更新
后端测试结果
前端构建结果
未完成或受环境限制的真实 Ark SDK 验证
```
