# 安防 C 端智能 Agent Web Demo 实施计划

> **面向 agentic workers:** REQUIRED SUB-SKILL: 使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务逐项实施。步骤使用 checkbox（`- [ ]`）语法跟踪。

**目标:** 构建一个可运行的安防 C 端 Agent Web Demo，支持多轮对话、模型主导工具选择、联网搜索、VikingDB 视频搜索接口和 IoT 摄像头模拟状态。

**架构:** 前端使用 React + Vite，左侧聊天、右侧 IoT 状态面板。后端使用 FastAPI，核心是模型主导的 AgentLoop：通过火山方舟 CLI 获取工具调用 JSON，后端校验后执行工具并返回结构化状态。

**技术栈:** Python + FastAPI + Pydantic + pytest；React 18 + TypeScript + Vite；VikingDB Data API；火山方舟 CLI。

---

## 当前约束

- 当前目录不是 Git 仓库，实施时不能强制 commit；每个任务完成后用文件清单和测试结果替代 commit 记录。
- 所有 LLM 调用只允许经过 `backend/app/model/ark_cli_client.py`。
- `demo.py` 中 VikingDB 检索逻辑可复用思路；DashScope、Voyage、Qwen rerank 不进入主链路。
- 第一版可在未配置真实方舟 CLI、联网搜索 provider 和 VikingDB 密钥时启动；对应工具返回清晰错误，不能影响 IoT 和前端演示。

## 文件结构

- 创建：`backend/requirements.txt`，后端依赖。
- 创建：`backend/app/main.py`，FastAPI 应用入口。
- 创建：`backend/app/api/chat.py`，聊天接口。
- 创建：`backend/app/api/health.py`，健康检查接口。
- 创建：`backend/app/agent/schemas.py`，Agent、工具、API 的 Pydantic schema。
- 创建：`backend/app/agent/prompts.py`，系统提示词和工具说明。
- 创建：`backend/app/agent/tool_registry.py`，工具注册与调用。
- 创建：`backend/app/agent/loop.py`，模型主导 AgentLoop。
- 创建：`backend/app/model/ark_cli_client.py`，火山方舟 CLI 调用封装。
- 创建：`backend/app/tools/iot_control.py`，IoT 模拟控制工具。
- 创建：`backend/app/tools/web_search.py`，联网搜索工具。
- 创建：`backend/app/tools/viking_video_search.py`，VikingDB 视频搜索工具。
- 创建：`backend/app/memory/session_store.py`，进程内会话存储。
- 创建：`backend/app/core/config.py`，环境配置。
- 创建：`backend/app/core/logging.py`，日志初始化。
- 创建：`backend/tests/test_iot_control.py`，IoT 工具测试。
- 创建：`backend/tests/test_agent_loop.py`，AgentLoop 测试。
- 创建：`backend/tests/test_chat_api.py`，聊天接口测试。
- 创建：`frontend/package.json`，前端依赖和脚本。
- 创建：`frontend/index.html`，Vite 入口 HTML。
- 创建：`frontend/src/main.tsx`，React 入口。
- 创建：`frontend/src/App.tsx`，页面组合。
- 创建：`frontend/src/types.ts`，前端类型。
- 创建：`frontend/src/api/chatClient.ts`，聊天 API 客户端。
- 创建：`frontend/src/components/ChatPane.tsx`，聊天窗口。
- 创建：`frontend/src/components/IotPanel.tsx`，IoT 状态面板。
- 创建：`frontend/src/components/ToolTrace.tsx`，工具轨迹折叠面板。
- 创建：`frontend/src/styles.css`，页面样式。

---

### 任务 1：创建后端工程骨架

**文件:**
- 创建：`backend/requirements.txt`
- 创建：`backend/app/__init__.py`
- 创建：`backend/app/main.py`
- 创建：`backend/app/api/__init__.py`
- 创建：`backend/app/api/health.py`
- 创建：`backend/app/core/__init__.py`
- 创建：`backend/app/core/config.py`
- 创建：`backend/app/core/logging.py`

- [ ] **步骤 1：写后端依赖文件**

写入 `backend/requirements.txt`：

```text
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
pydantic-settings==2.7.1
httpx==0.28.1
requests==2.32.3
pytest==8.3.4
pytest-asyncio==0.25.2
```

- [ ] **步骤 2：写配置模块**

写入 `backend/app/core/config.py`：

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Security Agent Web Demo"
    cors_origins: list[str] = ["http://localhost:5173"]

    ark_cli_bin: str = "ark"
    ark_model: str = "doubao-pro"
    ark_cli_timeout_seconds: int = 60
    ark_cli_max_retries: int = 1

    web_search_enabled: bool = True
    web_search_timeout_seconds: int = 10

    vikingdb_ak: str = ""
    vikingdb_sk: str = ""
    vikingdb_host: str = "api-vikingdb.vikingdb.ap-southeast-1.bytepluses.com"
    vikingdb_collection_name: str = "Yingshijy"
    vikingdb_index_name: str = "yingshi_en"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **步骤 3：写日志模块**

写入 `backend/app/core/logging.py`：

```python
import logging


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
```

- [ ] **步骤 4：写健康检查接口**

写入 `backend/app/api/health.py`：

```python
import shutil

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter()


@router.get("/health")
def health() -> dict[str, bool | str]:
    settings = get_settings()
    return {
        "status": "ok",
        "ark_cli_available": shutil.which(settings.ark_cli_bin) is not None,
        "vikingdb_configured": bool(settings.vikingdb_ak and settings.vikingdb_sk),
    }
```

- [ ] **步骤 5：写 FastAPI 入口**

写入 `backend/app/main.py`：

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.logging import setup_logging

setup_logging()
settings = get_settings()

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
```

- [ ] **步骤 6：运行健康检查**

运行：

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另开终端运行：

```bash
curl http://127.0.0.1:8000/api/health
```

期望：返回 JSON，包含 `status`、`ark_cli_available`、`vikingdb_configured`。

---

### 任务 2：实现核心 Schema、会话存储和 IoT 工具

**文件:**
- 创建：`backend/app/agent/__init__.py`
- 创建：`backend/app/agent/schemas.py`
- 创建：`backend/app/memory/__init__.py`
- 创建：`backend/app/memory/session_store.py`
- 创建：`backend/app/tools/__init__.py`
- 创建：`backend/app/tools/iot_control.py`
- 创建：`backend/tests/test_iot_control.py`

- [ ] **步骤 1：写 Pydantic schema**

写入 `backend/app/agent/schemas.py`：

```python
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


ToolName = Literal["web_search", "video_search", "iot_control", "final_answer"]
IotAction = Literal["move", "privacy_mask", "none"]


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class AgentToolCall(BaseModel):
    type: Literal["tool_call"]
    tool_name: Literal["web_search", "video_search", "iot_control"]
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class AgentFinalAnswer(BaseModel):
    type: Literal["final_answer"]
    answer: str
    iot_action: IotAction = "none"


class IotControlCommand(BaseModel):
    tool: Literal["iot_control"] = "iot_control"
    device_id: str = "camera_living_room"
    action: IotAction
    target: str | None = None
    parameters: dict[str, str | int | float | bool] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str = ""


class IotState(BaseModel):
    iot_action: IotAction = "none"
    device_id: str | None = None
    target: str | None = None
    status: Literal["idle", "simulated_success", "validation_failed", "tool_error"] = "idle"
    raw_command: IotControlCommand | None = None


class VideoSearchResult(BaseModel):
    f_id: str
    f_text: str
    search_score: float | None = None
    ann_score: float | None = None
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class ToolEvent(BaseModel):
    step: int
    tool_name: ToolName
    input: dict[str, Any]
    output: dict[str, Any]
    status: Literal["success", "failed", "skipped"]
    elapsed_ms: int


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str
    debug: bool = False


class ChatResponse(BaseModel):
    conversation_id: str
    assistant_message: str
    iot_state: IotState = Field(default_factory=IotState)
    video_results: list[VideoSearchResult] = Field(default_factory=list)
    tool_events: list[ToolEvent] = Field(default_factory=list)
    error: dict[str, str] | None = None


def new_conversation_id() -> str:
    return f"conv_{uuid4().hex[:12]}"
```

- [ ] **步骤 2：写会话存储**

写入 `backend/app/memory/session_store.py`：

```python
from collections import defaultdict

from app.agent.schemas import ChatMessage, new_conversation_id


class InMemorySessionStore:
    def __init__(self) -> None:
        self._messages: dict[str, list[ChatMessage]] = defaultdict(list)

    def ensure_conversation(self, conversation_id: str | None) -> str:
        if conversation_id:
            self._messages.setdefault(conversation_id, [])
            return conversation_id
        conversation_id = new_conversation_id()
        self._messages[conversation_id] = []
        return conversation_id

    def append(self, conversation_id: str, message: ChatMessage) -> None:
        self._messages[conversation_id].append(message)

    def list_messages(self, conversation_id: str) -> list[ChatMessage]:
        return list(self._messages.get(conversation_id, []))


session_store = InMemorySessionStore()
```

- [ ] **步骤 3：写 IoT 工具**

写入 `backend/app/tools/iot_control.py`：

```python
import time
from typing import Any

from pydantic import ValidationError

from app.agent.schemas import IotControlCommand, IotState, ToolEvent


class IotControlTool:
    name = "iot_control"

    def run(self, arguments: dict[str, Any], step: int) -> tuple[IotState, ToolEvent]:
        started = time.perf_counter()
        try:
            command = IotControlCommand(action=arguments.get("action", "none"), **{
                key: value for key, value in arguments.items() if key != "action"
            })
            state = IotState(
                iot_action=command.action,
                device_id=command.device_id,
                target=command.target,
                status="simulated_success",
                raw_command=command,
            )
            status = "success"
            output = state.model_dump()
        except ValidationError as exc:
            state = IotState(iot_action="none", status="validation_failed")
            status = "failed"
            output = {"error": exc.errors()}

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return state, ToolEvent(
            step=step,
            tool_name="iot_control",
            input=arguments,
            output=output,
            status=status,
            elapsed_ms=elapsed_ms,
        )
```

- [ ] **步骤 4：写 IoT 单测**

写入 `backend/tests/test_iot_control.py`：

```python
from app.tools.iot_control import IotControlTool


def test_iot_move_returns_move_state():
    state, event = IotControlTool().run(
        {"device_id": "camera_living_room", "action": "move", "target": "front_door"},
        step=1,
    )
    assert state.iot_action == "move"
    assert state.status == "simulated_success"
    assert event.status == "success"


def test_iot_privacy_mask_returns_mask_state():
    state, event = IotControlTool().run(
        {"device_id": "camera_living_room", "action": "privacy_mask"},
        step=1,
    )
    assert state.iot_action == "privacy_mask"
    assert state.status == "simulated_success"
    assert event.status == "success"


def test_iot_invalid_action_is_rejected():
    state, event = IotControlTool().run(
        {"device_id": "camera_living_room", "action": "rotate_fast"},
        step=1,
    )
    assert state.iot_action == "none"
    assert state.status == "validation_failed"
    assert event.status == "failed"
```

- [ ] **步骤 5：运行测试**

运行：

```bash
cd backend
PYTHONPATH=. pytest tests/test_iot_control.py -v
```

期望：3 个测试全部通过。

---

### 任务 3：实现火山方舟 CLI 客户端与 Agent 提示词

**文件:**
- 创建：`backend/app/model/__init__.py`
- 创建：`backend/app/model/ark_cli_client.py`
- 创建：`backend/app/agent/prompts.py`

- [ ] **步骤 1：写 Agent 系统提示词**

写入 `backend/app/agent/prompts.py`：

```python
SYSTEM_PROMPT = """你是安防 C 端 App 内的智能 Agent。
你必须根据用户意图选择下一步：
1. 如果只是闲聊或普通问答，输出 final_answer。
2. 如果需要实时网络信息，调用 web_search。
3. 如果用户要查监控视频内容，调用 video_search。
4. 如果用户要移动摄像头、转向、调整角度，调用 iot_control，action=move。
5. 如果用户要打开隐私遮蔽、遮挡、关闭画面，调用 iot_control，action=privacy_mask。

你必须只输出 JSON，不要输出 Markdown，不要输出解释文字。
工具调用格式：
{"type":"tool_call","tool_name":"iot_control","arguments":{"device_id":"camera_living_room","action":"move","target":"front_door"},"reason":"..."}

最终回答格式：
{"type":"final_answer","answer":"...","iot_action":"none"}
"""


TOOL_SPEC = """可用工具：
- web_search: 输入 {"query": "...", "top_k": 5}
- video_search: 输入 {"query": "...", "limit": 10}
- iot_control: 输入 {"device_id": "camera_living_room", "action": "move|privacy_mask|none", "target": "..."}
"""
```

- [ ] **步骤 2：写 Ark CLI 客户端**

写入 `backend/app/model/ark_cli_client.py`：

```python
import json
import logging
import subprocess
from typing import Any

from app.agent.schemas import ChatMessage
from app.core.config import get_settings

LOG = logging.getLogger(__name__)


class ArkCLIError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ArkCLIModelClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def generate_json(self, messages: list[ChatMessage], schema_name: str = "agent_step") -> dict[str, Any]:
        prompt = self._format_messages(messages, schema_name)
        raw = self._run_cli(prompt)
        return self._parse_json(raw)

    def generate_text(self, messages: list[ChatMessage]) -> str:
        prompt = self._format_messages(messages, "text")
        return self._run_cli(prompt).strip()

    def _format_messages(self, messages: list[ChatMessage], schema_name: str) -> str:
        payload = {
            "schema_name": schema_name,
            "messages": [message.model_dump() for message in messages],
        }
        return json.dumps(payload, ensure_ascii=False)

    def _run_cli(self, prompt: str) -> str:
        command = [self.settings.ark_cli_bin, "chat", "--model", self.settings.ark_model]
        LOG.info("calling ark cli: command=%s model=%s", self.settings.ark_cli_bin, self.settings.ark_model)
        try:
            completed = subprocess.run(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=self.settings.ark_cli_timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ArkCLIError("ARK_CLI_NOT_FOUND", f"未找到火山方舟 CLI: {self.settings.ark_cli_bin}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ArkCLIError("ARK_CLI_TIMEOUT", "火山方舟 CLI 调用超时") from exc

        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            code = "ARK_AUTH_EXPIRED" if "auth" in stderr.lower() or "token" in stderr.lower() else "ARK_CLI_FAILED"
            raise ArkCLIError(code, stderr or "火山方舟 CLI 调用失败")
        return completed.stdout

    def _parse_json(self, raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ArkCLIError("MODEL_JSON_PARSE_FAILED", f"模型未返回合法 JSON: {raw[:300]}") from exc
        if not isinstance(result, dict):
            raise ArkCLIError("MODEL_JSON_PARSE_FAILED", "模型 JSON 顶层必须是对象")
        return result
```

- [ ] **步骤 3：验证 CLI 可用性**

运行：

```bash
which ark || true
ark --help | head -n 20
```

期望：如果本机安装了 `ark`，能看到帮助信息；如果没有安装，记录该事实，继续用 fake client 完成后续单测。

---

### 任务 4：实现 ToolRegistry、联网搜索和 VikingDB 工具

**文件:**
- 创建：`backend/app/agent/tool_registry.py`
- 创建：`backend/app/tools/web_search.py`
- 创建：`backend/app/tools/viking_video_search.py`

- [ ] **步骤 1：写联网搜索工具**

写入 `backend/app/tools/web_search.py`：

```python
import time
from typing import Any

import httpx

from app.agent.schemas import ToolEvent
from app.core.config import get_settings


class WebSearchTool:
    name = "web_search"

    def run(self, arguments: dict[str, Any], step: int) -> tuple[dict[str, Any], ToolEvent]:
        started = time.perf_counter()
        settings = get_settings()
        query = str(arguments.get("query", "")).strip()
        top_k = int(arguments.get("top_k", 5))
        if not query:
            output = {"results": [], "error": "query is required"}
            status = "failed"
        elif not settings.web_search_enabled:
            output = {"results": [], "error": "web search disabled"}
            status = "skipped"
        else:
            output = self._search_duckduckgo(query, top_k, settings.web_search_timeout_seconds)
            status = "success" if not output.get("error") else "failed"
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return output, ToolEvent(
            step=step,
            tool_name="web_search",
            input=arguments,
            output=output,
            status=status,
            elapsed_ms=elapsed_ms,
        )

    def _search_duckduckgo(self, query: str, top_k: int, timeout: int) -> dict[str, Any]:
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
        try:
            response = httpx.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            return {"results": [], "error": str(exc)}

        results = []
        abstract = data.get("AbstractText")
        if abstract:
            results.append({
                "title": data.get("Heading") or query,
                "snippet": abstract,
                "url": data.get("AbstractURL") or "",
            })
        for topic in data.get("RelatedTopics", [])[:top_k]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("Text", "")[:80],
                    "snippet": topic.get("Text", ""),
                    "url": topic.get("FirstURL", ""),
                })
        return {"results": results[:top_k]}
```

- [ ] **步骤 2：写 VikingDB 工具**

写入 `backend/app/tools/viking_video_search.py`：

```python
import json
import time
from typing import Any

import requests
from volcengine.Credentials import Credentials
from volcengine.auth.SignerV4 import SignerV4
from volcengine.base.Request import Request

from app.agent.schemas import ToolEvent, VideoSearchResult
from app.core.config import get_settings

SEARCH_PATH = "/api/vikingdb/data/search/multi_modal"
DEFAULT_SERVICE = "vikingdb"


class VikingVideoSearchTool:
    name = "video_search"

    def run(self, arguments: dict[str, Any], step: int) -> tuple[list[VideoSearchResult], ToolEvent]:
        started = time.perf_counter()
        query = str(arguments.get("query", "")).strip()
        limit = int(arguments.get("limit", 10))
        try:
            results = self.search(query=query, limit=limit)
            output = {"results": [item.model_dump() for item in results]}
            status = "success"
        except Exception as exc:
            results = []
            output = {"results": [], "error": str(exc)}
            status = "failed"
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return results, ToolEvent(
            step=step,
            tool_name="video_search",
            input=arguments,
            output=output,
            status=status,
            elapsed_ms=elapsed_ms,
        )

    def search(self, query: str, limit: int) -> list[VideoSearchResult]:
        settings = get_settings()
        if not query:
            return []
        if not settings.vikingdb_ak or not settings.vikingdb_sk:
            raise RuntimeError("VikingDB AK/SK 未配置")
        body = {
            "collection_name": settings.vikingdb_collection_name,
            "index_name": settings.vikingdb_index_name,
            "text": query,
            "instruction": {"auto_fill": True},
            "output_fields": ["f_id", "f_text"],
            "limit": limit,
        }
        req = self._prepare_request(settings.vikingdb_ak, settings.vikingdb_sk, settings.vikingdb_host, body)
        response = requests.request(
            method=req.method,
            url=f"https://{settings.vikingdb_host}{req.path}",
            headers=req.headers,
            data=req.body,
            timeout=30,
        )
        if response.status_code != 200:
            raise RuntimeError(f"VikingDB search failed: status={response.status_code}, body={response.text}")
        data = response.json()
        if data.get("code") != "Success":
            raise RuntimeError(f"VikingDB search api failed: {response.text}")
        return self._parse_results(data)

    def _prepare_request(self, ak: str, sk: str, host: str, body: dict[str, Any]) -> Request:
        req = Request()
        req.set_shema("https")
        req.set_method("POST")
        req.set_connection_timeout(10)
        req.set_socket_timeout(10)
        req.set_headers({"Accept": "application/json", "Content-Type": "application/json", "Host": host})
        req.set_host(host)
        req.set_path(SEARCH_PATH)
        req.set_body(json.dumps(body))
        SignerV4.sign(req, Credentials(ak, sk, DEFAULT_SERVICE, "cn-beijing"))
        return req

    def _parse_results(self, data: dict[str, Any]) -> list[VideoSearchResult]:
        results = []
        for item in data.get("result", {}).get("data", []):
            fields = item.get("fields") or {}
            f_id = fields.get("f_id") or item.get("id")
            if not f_id:
                continue
            results.append(VideoSearchResult(
                f_id=str(f_id),
                f_text=str(fields.get("f_text", "")),
                search_score=item.get("score"),
                ann_score=item.get("ann_score"),
            ))
        return results
```

- [ ] **步骤 3：把 volcengine 依赖加入 requirements**

修改 `backend/requirements.txt`，追加：

```text
volcengine==1.0.185
```

- [ ] **步骤 4：写 ToolRegistry**

写入 `backend/app/agent/tool_registry.py`：

```python
from typing import Any

from app.agent.schemas import IotState, ToolEvent, VideoSearchResult
from app.tools.iot_control import IotControlTool
from app.tools.viking_video_search import VikingVideoSearchTool
from app.tools.web_search import WebSearchTool


class ToolRegistry:
    def __init__(self) -> None:
        self.iot_tool = IotControlTool()
        self.web_tool = WebSearchTool()
        self.video_tool = VikingVideoSearchTool()

    def run(self, tool_name: str, arguments: dict[str, Any], step: int) -> tuple[Any, ToolEvent]:
        if tool_name == "iot_control":
            return self.iot_tool.run(arguments, step)
        if tool_name == "web_search":
            return self.web_tool.run(arguments, step)
        if tool_name == "video_search":
            return self.video_tool.run(arguments, step)
        return {}, ToolEvent(
            step=step,
            tool_name="final_answer",
            input={"tool_name": tool_name, "arguments": arguments},
            output={"error": f"unknown tool: {tool_name}"},
            status="failed",
            elapsed_ms=0,
        )


def extract_iot_state(result: Any) -> IotState:
    if isinstance(result, IotState):
        return result
    return IotState()


def extract_video_results(result: Any) -> list[VideoSearchResult]:
    if isinstance(result, list) and all(isinstance(item, VideoSearchResult) for item in result):
        return result
    return []
```

- [ ] **步骤 5：运行已有测试**

运行：

```bash
cd backend
PYTHONPATH=. pytest tests/test_iot_control.py -v
```

期望：IoT 测试仍然通过。

---

### 任务 5：实现 AgentLoop 和聊天 API

**文件:**
- 创建：`backend/app/agent/loop.py`
- 创建：`backend/app/api/chat.py`
- 修改：`backend/app/main.py`
- 创建：`backend/tests/test_agent_loop.py`
- 创建：`backend/tests/test_chat_api.py`

- [ ] **步骤 1：写 AgentLoop**

写入 `backend/app/agent/loop.py`：

```python
import json
import logging
from typing import Any

from pydantic import ValidationError

from app.agent.prompts import SYSTEM_PROMPT, TOOL_SPEC
from app.agent.schemas import (
    AgentFinalAnswer,
    AgentToolCall,
    ChatMessage,
    ChatResponse,
    IotState,
    ToolEvent,
    VideoSearchResult,
)
from app.agent.tool_registry import ToolRegistry, extract_iot_state, extract_video_results
from app.model.ark_cli_client import ArkCLIError, ArkCLIModelClient

LOG = logging.getLogger(__name__)


class AgentLoop:
    def __init__(self, model_client: ArkCLIModelClient, tool_registry: ToolRegistry | None = None) -> None:
        self.model_client = model_client
        self.tool_registry = tool_registry or ToolRegistry()
        self.max_steps = 3

    def run(self, conversation_id: str, history: list[ChatMessage], user_message: str) -> ChatResponse:
        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(role="system", content=TOOL_SPEC),
            *history,
            ChatMessage(role="user", content=user_message),
        ]
        tool_events: list[ToolEvent] = []
        iot_state = IotState()
        video_results: list[VideoSearchResult] = []

        try:
            for step in range(1, self.max_steps + 1):
                raw_step = self.model_client.generate_json(messages, schema_name="agent_step")
                if raw_step.get("type") == "final_answer":
                    final = AgentFinalAnswer.model_validate(raw_step)
                    if final.iot_action != "none":
                        iot_state.iot_action = final.iot_action
                    return ChatResponse(
                        conversation_id=conversation_id,
                        assistant_message=final.answer,
                        iot_state=iot_state,
                        video_results=video_results,
                        tool_events=tool_events,
                    )

                tool_call = AgentToolCall.model_validate(raw_step)
                result, event = self.tool_registry.run(tool_call.tool_name, tool_call.arguments, step)
                tool_events.append(event)
                if event.tool_name == "iot_control":
                    iot_state = extract_iot_state(result)
                if event.tool_name == "video_search":
                    video_results = extract_video_results(result)
                messages.append(ChatMessage(role="assistant", content=json.dumps(raw_step, ensure_ascii=False)))
                messages.append(ChatMessage(role="tool", content=json.dumps(event.output, ensure_ascii=False)))

            return ChatResponse(
                conversation_id=conversation_id,
                assistant_message="我已经完成工具调用，但还没有形成最终回答。请再问我一次或简化请求。",
                iot_state=iot_state,
                video_results=video_results,
                tool_events=tool_events,
            )
        except (ValidationError, ArkCLIError) as exc:
            LOG.exception("agent loop failed")
            return ChatResponse(
                conversation_id=conversation_id,
                assistant_message="这次我没有稳定理解你的请求，请换一种说法再试。",
                iot_state=iot_state,
                video_results=video_results,
                tool_events=tool_events,
                error={"code": getattr(exc, "code", "AGENT_LOOP_FAILED"), "message": str(exc)},
            )
```

- [ ] **步骤 2：写聊天 API**

写入 `backend/app/api/chat.py`：

```python
from fastapi import APIRouter

from app.agent.loop import AgentLoop
from app.agent.schemas import ChatMessage, ChatRequest, ChatResponse
from app.agent.tool_registry import ToolRegistry
from app.memory.session_store import session_store
from app.model.ark_cli_client import ArkCLIModelClient

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    conversation_id = session_store.ensure_conversation(request.conversation_id)
    history = session_store.list_messages(conversation_id)
    agent = AgentLoop(model_client=ArkCLIModelClient(), tool_registry=ToolRegistry())
    response = agent.run(conversation_id=conversation_id, history=history, user_message=request.message)
    session_store.append(conversation_id, ChatMessage(role="user", content=request.message))
    session_store.append(conversation_id, ChatMessage(role="assistant", content=response.assistant_message))
    return response
```

- [ ] **步骤 3：注册聊天路由**

修改 `backend/app/main.py`，增加 chat router：

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.logging import setup_logging

setup_logging()
settings = get_settings()

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
```

- [ ] **步骤 4：写 AgentLoop 测试**

写入 `backend/tests/test_agent_loop.py`：

```python
from app.agent.loop import AgentLoop
from app.agent.schemas import ChatMessage


class FakeModelClient:
    def __init__(self, outputs):
        self.outputs = list(outputs)

    def generate_json(self, messages, schema_name="agent_step"):
        return self.outputs.pop(0)


def test_agent_loop_runs_iot_tool_then_final_answer():
    model = FakeModelClient([
        {
            "type": "tool_call",
            "tool_name": "iot_control",
            "arguments": {"device_id": "camera_living_room", "action": "move", "target": "front_door"},
            "reason": "用户要求移动摄像头",
        },
        {
            "type": "final_answer",
            "answer": "好的，我已经模拟将摄像头转向门口。",
            "iot_action": "move",
        },
    ])
    response = AgentLoop(model_client=model).run("conv_test", [], "把摄像头转向门口")
    assert response.iot_state.iot_action == "move"
    assert response.assistant_message == "好的，我已经模拟将摄像头转向门口。"
    assert response.tool_events[0].tool_name == "iot_control"


def test_agent_loop_can_answer_without_tool():
    model = FakeModelClient([
        {
            "type": "final_answer",
            "answer": "你好，我可以帮你查视频和模拟控制摄像头。",
            "iot_action": "none",
        }
    ])
    response = AgentLoop(model_client=model).run("conv_test", [ChatMessage(role="user", content="你好")], "你能做什么")
    assert response.iot_state.iot_action == "none"
    assert "摄像头" in response.assistant_message
```

- [ ] **步骤 5：写聊天 API 测试**

写入 `backend/tests/test_chat_api.py`：

```python
from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

- [ ] **步骤 6：运行后端测试**

运行：

```bash
cd backend
PYTHONPATH=. pytest tests -v
```

期望：所有后端测试通过；真实 `/api/chat` 在未安装方舟 CLI 时会返回可读模型错误，这是可接受行为。

---

### 任务 6：创建前端工程和类型/API 客户端

**文件:**
- 创建：`frontend/package.json`
- 创建：`frontend/index.html`
- 创建：`frontend/src/main.tsx`
- 创建：`frontend/src/types.ts`
- 创建：`frontend/src/api/chatClient.ts`

- [ ] **步骤 1：写 package.json**

写入 `frontend/package.json`：

```json
{
  "scripts": {
    "dev": "vite --host 127.0.0.1 --port 5173",
    "build": "tsc && vite build",
    "preview": "vite preview --host 127.0.0.1 --port 4173"
  },
  "dependencies": {
    "@vitejs/plugin-react": "latest",
    "vite": "latest",
    "typescript": "latest",
    "react": "latest",
    "react-dom": "latest"
  },
  "devDependencies": {}
}
```

- [ ] **步骤 2：写 HTML 入口**

写入 `frontend/index.html`：

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>HomeGuard Agent</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **步骤 3：写前端类型**

写入 `frontend/src/types.ts`：

```ts
export type IotAction = 'move' | 'privacy_mask' | 'none';

export type IotState = {
  iot_action: IotAction;
  device_id?: string;
  target?: string;
  status: 'idle' | 'simulated_success' | 'validation_failed' | 'tool_error';
};

export type VideoSearchResult = {
  f_id: string;
  f_text: string;
  search_score?: number;
  ann_score?: number;
};

export type ToolEvent = {
  step: number;
  tool_name: 'web_search' | 'video_search' | 'iot_control' | 'final_answer';
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  status: 'success' | 'failed' | 'skipped';
  elapsed_ms: number;
};

export type ChatResponse = {
  conversation_id: string;
  assistant_message: string;
  iot_state: IotState;
  video_results: VideoSearchResult[];
  tool_events: ToolEvent[];
  error?: {
    code: string;
    message: string;
  };
};

export type Message = {
  role: 'user' | 'assistant';
  content: string;
};
```

- [ ] **步骤 4：写 API 客户端**

写入 `frontend/src/api/chatClient.ts`：

```ts
import type { ChatResponse } from '../types';

const API_BASE = 'http://127.0.0.1:8000/api';

export async function sendChatMessage(
  message: string,
  conversationId?: string,
): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      conversation_id: conversationId,
      message,
      debug: true,
    }),
  });
  if (!response.ok) {
    throw new Error(`聊天接口失败：${response.status}`);
  }
  return response.json();
}
```

- [ ] **步骤 5：写 React 入口**

写入 `frontend/src/main.tsx`：

```tsx
import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

---

### 任务 7：实现前端页面组件和摄像头 IoT 面板

**文件:**
- 创建：`frontend/src/App.tsx`
- 创建：`frontend/src/components/ChatPane.tsx`
- 创建：`frontend/src/components/IotPanel.tsx`
- 创建：`frontend/src/components/ToolTrace.tsx`
- 创建：`frontend/src/styles.css`

- [ ] **步骤 1：写 IoT 面板组件**

写入 `frontend/src/components/IotPanel.tsx`：

```tsx
import type { IotState } from '../types';

type Props = {
  state: IotState;
};

export default function IotPanel({ state }: Props) {
  return (
    <aside className="iot-pane">
      <div className="pane-title">
        <h2>IoT 输出面板</h2>
        <span>JSON 驱动</span>
      </div>
      <div className="camera-preview" aria-label="摄像头模拟预览">
        <div className="wall-mount" />
        <div className="mount-arm" />
        <div className="scan-cone" />
        <div className="camera-body">
          <div className="camera-face" />
          <div className="camera-glint" />
        </div>
        <div className="status-light">CAMERA ONLINE</div>
      </div>
      <StateButton title="移动" active={state.iot_action === 'move'} note="action = move 时点亮" />
      <StateButton title="遮蔽" active={state.iot_action === 'privacy_mask'} note="action = privacy_mask 时点亮" />
      <pre className="json-box">{JSON.stringify(state, null, 2)}</pre>
    </aside>
  );
}

function StateButton({ title, active, note }: { title: string; active: boolean; note: string }) {
  return (
    <div className={`state-button ${active ? 'active' : ''}`}>
      <div>
        <strong>{title}</strong>
        <small>{note}</small>
      </div>
      <span className="state-lamp" />
    </div>
  );
}
```

- [ ] **步骤 2：写工具轨迹组件**

写入 `frontend/src/components/ToolTrace.tsx`：

```tsx
import type { ToolEvent } from '../types';

type Props = {
  events: ToolEvent[];
};

export default function ToolTrace({ events }: Props) {
  if (events.length === 0) {
    return null;
  }
  return (
    <details className="tool-trace">
      <summary>工具轨迹（{events.length}）</summary>
      {events.map((event) => (
        <div className="tool-event" key={`${event.step}-${event.tool_name}`}>
          <div className="tool-event-title">
            Step {event.step} · {event.tool_name} · {event.status} · {event.elapsed_ms}ms
          </div>
          <pre>{JSON.stringify({ input: event.input, output: event.output }, null, 2)}</pre>
        </div>
      ))}
    </details>
  );
}
```

- [ ] **步骤 3：写聊天面板组件**

写入 `frontend/src/components/ChatPane.tsx`：

```tsx
import type { FormEvent } from 'react';
import type { Message, ToolEvent } from '../types';
import ToolTrace from './ToolTrace';

type Props = {
  messages: Message[];
  input: string;
  loading: boolean;
  toolEvents: ToolEvent[];
  onInputChange: (value: string) => void;
  onSubmit: () => void;
};

export default function ChatPane({ messages, input, loading, toolEvents, onInputChange, onSubmit }: Props) {
  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    onSubmit();
  }

  return (
    <section className="chat-pane">
      <div className="pane-title">
        <h2>用户对话</h2>
        <span>{loading ? 'Agent 思考中' : '多轮会话'}</span>
      </div>
      <div className="messages">
        {messages.map((message, index) => (
          <div className={`message ${message.role}`} key={`${message.role}-${index}`}>
            {message.content}
          </div>
        ))}
      </div>
      <ToolTrace events={toolEvents} />
      <form className="input-bar" onSubmit={handleSubmit}>
        <input
          value={input}
          onChange={(event) => onInputChange(event.target.value)}
          placeholder="例如：把客厅摄像头转向门口"
        />
        <button disabled={loading || input.trim().length === 0}>发送</button>
      </form>
    </section>
  );
}
```

- [ ] **步骤 4：写 App 组合逻辑**

写入 `frontend/src/App.tsx`：

```tsx
import { useState } from 'react';
import { sendChatMessage } from './api/chatClient';
import ChatPane from './components/ChatPane';
import IotPanel from './components/IotPanel';
import type { IotState, Message, ToolEvent } from './types';

const initialIotState: IotState = {
  iot_action: 'none',
  status: 'idle',
};

export default function App() {
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: '你好，我是 HomeGuard Agent，可以帮你查视频、联网搜索，也可以模拟控制摄像头。' },
  ]);
  const [input, setInput] = useState('');
  const [iotState, setIotState] = useState<IotState>(initialIotState);
  const [toolEvents, setToolEvents] = useState<ToolEvent[]>([]);
  const [loading, setLoading] = useState(false);

  async function handleSubmit() {
    const text = input.trim();
    if (!text || loading) return;
    setMessages((current) => [...current, { role: 'user', content: text }]);
    setInput('');
    setLoading(true);
    try {
      const response = await sendChatMessage(text, conversationId);
      setConversationId(response.conversation_id);
      setMessages((current) => [...current, { role: 'assistant', content: response.assistant_message }]);
      setIotState(response.iot_state);
      setToolEvents(response.tool_events);
    } catch (error) {
      setMessages((current) => [...current, { role: 'assistant', content: `请求失败：${String(error)}` }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>HomeGuard Agent</h1>
          <p>安防 C 端 App 智能助手 Web Demo</p>
        </div>
        <span>闲聊 · 联网搜索 · 视频搜索 · IoT 模拟</span>
      </header>
      <div className="workspace">
        <ChatPane
          messages={messages}
          input={input}
          loading={loading}
          toolEvents={toolEvents}
          onInputChange={setInput}
          onSubmit={handleSubmit}
        />
        <IotPanel state={iotState} />
      </div>
    </main>
  );
}
```

- [ ] **步骤 5：写样式**

写入 `frontend/src/styles.css`：

```css
* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-width: 1024px;
  color: #0f172a;
  background: #e2e8f0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}

button,
input {
  font: inherit;
}

.app-shell {
  min-height: 100vh;
  background: #f8fafc;
}

.topbar {
  height: 104px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 28px;
  color: #e5e7eb;
  background:
    radial-gradient(circle at 14% 0%, rgba(20, 184, 166, 0.18), transparent 28%),
    linear-gradient(90deg, #0f172a, #111827);
}

.topbar h1 {
  margin: 0;
  font-size: 28px;
  letter-spacing: -0.04em;
}

.topbar p {
  margin: 6px 0 0;
  color: #94a3b8;
}

.topbar span {
  color: #cbd5e1;
  font-size: 14px;
}

.workspace {
  display: grid;
  grid-template-columns: minmax(0, 1.65fr) 380px;
  min-height: calc(100vh - 104px);
}

.chat-pane {
  display: flex;
  flex-direction: column;
  gap: 18px;
  background: #ffffff;
  padding: 26px;
}

.pane-title {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  padding-bottom: 14px;
  border-bottom: 1px solid #e2e8f0;
}

.pane-title h2 {
  margin: 0;
  font-size: 20px;
}

.pane-title span {
  padding: 6px 10px;
  border-radius: 999px;
  color: #0f766e;
  background: #ecfeff;
  font-size: 12px;
  font-weight: 700;
}

.messages {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow-y: auto;
  padding-right: 4px;
}

.message {
  max-width: 76%;
  padding: 13px 15px;
  border-radius: 18px;
  line-height: 1.55;
  font-size: 14px;
}

.message.user {
  align-self: flex-end;
  color: #ffffff;
  background: #0f172a;
  border-bottom-right-radius: 6px;
}

.message.assistant {
  align-self: flex-start;
  color: #1e293b;
  background: #f1f5f9;
  border-bottom-left-radius: 6px;
}

.tool-trace {
  border: 1px solid #ccfbf1;
  border-radius: 18px;
  background: #f0fdfa;
  padding: 12px 14px;
}

.tool-trace summary {
  cursor: pointer;
  color: #115e59;
  font-weight: 800;
}

.tool-event {
  margin-top: 12px;
  border-top: 1px solid #99f6e4;
  padding-top: 12px;
}

.tool-event-title {
  color: #134e4a;
  font-size: 13px;
  font-weight: 800;
}

.tool-event pre,
.json-box {
  margin: 10px 0 0;
  overflow: auto;
  border-radius: 14px;
  background: #0f172a;
  color: #ccfbf1;
  padding: 12px;
  font-size: 12px;
  line-height: 1.5;
}

.input-bar {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  padding: 10px;
  border: 1px solid #e2e8f0;
  border-radius: 18px;
  background: #f8fafc;
}

.input-bar input {
  width: 100%;
  border: 0;
  outline: 0;
  background: transparent;
  color: #0f172a;
  padding: 11px 12px;
}

.input-bar button {
  border: 0;
  border-radius: 13px;
  padding: 0 18px;
  color: #ffffff;
  background: #0f172a;
  font-weight: 800;
  cursor: pointer;
}

.input-bar button:disabled {
  cursor: not-allowed;
  opacity: 0.48;
}

.iot-pane {
  display: flex;
  flex-direction: column;
  gap: 18px;
  background: #f1f5f9;
  border-left: 1px solid #e2e8f0;
  padding: 26px;
}

.camera-preview {
  height: 216px;
  border-radius: 24px;
  background:
    radial-gradient(circle at 50% 48%, rgba(45, 212, 191, 0.18), transparent 28%),
    radial-gradient(circle at 18% 20%, rgba(56, 189, 248, 0.16), transparent 24%),
    linear-gradient(135deg, #0f172a 0%, #111827 48%, #1e293b 100%);
  position: relative;
  overflow: hidden;
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.08);
}

.wall-mount {
  position: absolute;
  top: 28px;
  left: 36px;
  width: 72px;
  height: 22px;
  border-radius: 999px;
  background: linear-gradient(180deg, #dbeafe, #94a3b8);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.24);
}

.mount-arm {
  position: absolute;
  top: 39px;
  left: 88px;
  width: 72px;
  height: 12px;
  border-radius: 999px;
  background: linear-gradient(180deg, #cbd5e1, #64748b);
  transform: rotate(12deg);
  transform-origin: left center;
}

.camera-body {
  position: absolute;
  top: 54px;
  left: 132px;
  width: 154px;
  height: 88px;
  border-radius: 32px 44px 44px 32px;
  background:
    linear-gradient(90deg, rgba(255, 255, 255, 0.45), transparent 24%),
    linear-gradient(180deg, #f8fafc, #94a3b8 58%, #475569);
  box-shadow:
    0 24px 44px rgba(0, 0, 0, 0.36),
    inset 0 -10px 24px rgba(15, 23, 42, 0.24);
}

.camera-body::before {
  content: "";
  position: absolute;
  top: -10px;
  left: 22px;
  width: 88px;
  height: 18px;
  border-radius: 18px 18px 8px 8px;
  background: linear-gradient(180deg, #e2e8f0, #94a3b8);
}

.camera-face {
  position: absolute;
  right: -12px;
  top: 10px;
  width: 70px;
  height: 70px;
  border-radius: 999px;
  background:
    radial-gradient(circle at 50% 50%, #020617 0 23%, #0f172a 24% 43%, #38bdf8 44% 47%, #1e293b 48% 100%);
  box-shadow:
    inset 0 0 0 8px rgba(226, 232, 240, 0.38),
    0 0 34px rgba(45, 212, 191, 0.32);
}

.camera-glint {
  position: absolute;
  right: 30px;
  top: 24px;
  width: 13px;
  height: 13px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.84);
}

.status-light {
  position: absolute;
  left: 26px;
  bottom: 18px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #ccfbf1;
  font-size: 12px;
  letter-spacing: 0.04em;
}

.status-light::before {
  content: "";
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: #14b8a6;
  box-shadow: 0 0 0 7px rgba(20, 184, 166, 0.14), 0 0 24px rgba(20, 184, 166, 0.9);
}

.scan-cone {
  position: absolute;
  right: 8px;
  top: 75px;
  width: 108px;
  height: 56px;
  background: linear-gradient(90deg, rgba(45, 212, 191, 0.28), rgba(45, 212, 191, 0));
  clip-path: polygon(0 35%, 100% 0, 100% 100%, 0 65%);
}

.state-button {
  min-height: 82px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid #cbd5e1;
  border-radius: 20px;
  background: #ffffff;
  color: #334155;
  padding: 18px;
}

.state-button strong {
  display: block;
  color: #0f172a;
  font-size: 18px;
}

.state-button small {
  color: #64748b;
}

.state-button.active {
  border-color: #14b8a6;
  background: linear-gradient(135deg, #ccfbf1, #f0fdfa);
  box-shadow: 0 18px 42px rgba(20, 184, 166, 0.28);
}

.state-lamp {
  width: 18px;
  height: 18px;
  border-radius: 999px;
  background: #cbd5e1;
}

.state-button.active .state-lamp {
  background: #14b8a6;
  box-shadow: 0 0 0 8px rgba(20, 184, 166, 0.16), 0 0 26px rgba(20, 184, 166, 0.72);
}

@media (max-width: 900px) {
  body {
    min-width: 0;
  }

  .workspace {
    grid-template-columns: 1fr;
  }

  .iot-pane {
    border-left: 0;
    border-top: 1px solid #e2e8f0;
  }
}
```

- [ ] **步骤 6：安装并构建前端**

运行：

```bash
cd frontend
npm install
npm run build
```

期望：TypeScript 和 Vite 构建成功。

---

### 任务 8：端到端运行和验收

**文件:**
- 修改：`README.md`

- [ ] **步骤 1：写 README**

写入 `README.md`：

````markdown
# 安防 C 端智能 Agent Web Demo

## 启动后端

```bash
cd backend
python -m pip install -r requirements.txt
PYTHONPATH=. python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 `http://127.0.0.1:5173`。

## 模型接入约束

所有 LLM 调用统一经过 `backend/app/model/ark_cli_client.py`。业务代码不得直接调用其他模型 SDK。

## VikingDB

视频搜索读取已有 VikingDB collection/index。建库、视频切片、向量写入由人工完成。
````

- [ ] **步骤 2：运行后端测试**

运行：

```bash
cd backend
PYTHONPATH=. pytest tests -v
```

期望：所有后端测试通过。

- [ ] **步骤 3：运行前端构建**

运行：

```bash
cd frontend
npm run build
```

期望：构建成功。

- [ ] **步骤 4：启动服务并手动验收**

启动后端：

```bash
cd backend
PYTHONPATH=. python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动前端：

```bash
cd frontend
npm run dev
```

验收输入：

```text
帮我把客厅摄像头转向门口
```

期望：

- 左侧出现用户消息和 Agent 回复。
- 如果方舟 CLI 可用，后端通过模型选择 `iot_control`。
- 右侧 `iot_action` 为 `move` 时，“移动”按钮高亮。
- 工具轨迹中出现 `iot_control`。

验收输入：

```text
帮我打开隐私遮蔽
```

期望：

- 右侧 `iot_action` 为 `privacy_mask`。
- “遮蔽”按钮高亮。

## 计划自审

- 覆盖 PRD 中的 Web 页面、Agent 后端、火山方舟 CLI、IoT JSON、联网搜索和 VikingDB 视频搜索。
- 没有把关键词规则路由作为主链路。
- 测试使用 fake model client 验证 AgentLoop，避免依赖短期 SSO token。
- 当前目录非 Git 仓库，计划未包含强制 commit 步骤。
