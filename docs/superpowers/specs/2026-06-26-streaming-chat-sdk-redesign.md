# 对话流式交互与 Session 管理优化设计

## 1. 背景

当前项目已经具备安防 Agent 的核心能力：多轮对话、模型主导工具选择、联网搜索、VikingDB 视频搜索和 IoT 模拟控制。现有前端更像一个功能验证面板，聊天交互偏静态；后端通过 Ark CLI 获取完整 JSON 后一次性返回结果，无法复原参考项目 `Doubao-VolcEngine` 中的流式输出、思考过程展示和会话管理体验。

本轮优化目标是参考 `https://github.com/YuhaoYeSteve/Doubao-VolcEngine` 的对话体验，把本项目升级为更接近真实 App 的三栏式对话界面：左侧 session 管理，中间流式聊天，右侧保留 IoT 输出面板。

## 2. 已确认决策

| 决策项 | 结论 |
| --- | --- |
| 模型接入 | 对话主链路切到 Ark Python SDK，支持真流式输出 |
| CLI 兼容 | 保留现有 `ArkCLIModelClient`，不作为本轮主链路 |
| 前端重点 | 复原参考项目的 session、流式渲染、思考/状态展示、轻量豆包风格视觉 |
| IoT 面板 | 内容保留，视觉风格跟随新对话页调整 |
| 工具链路 | IoT、视频搜索、联网搜索仍由后端工具执行并做 Pydantic 校验 |
| 思考展示 | 优先展示 Ark SDK 返回的 reasoning summary；无 reasoning 时展示后端处理过程，不暴露隐藏推理链 |

## 3. 目标范围

### 3.1 必须完成

- 新增 Ark Python SDK 模型适配层，支持非流式 JSON 路由和流式文本回答。
- 新增 `POST /api/chat/stream`，通过 SSE 推送会话、状态、工具调用、思考摘要、回答增量和最终结构化结果。
- 调整 AgentLoop：工具路由保持结构化 JSON，最终自然语言回答改为 SDK 流式生成。
- 前端改用流式客户端，支持回答增量渲染、发送中占位、错误气泡和智能滚动。
- 新增 session 管理：新建、切换、删除、自动标题、本地持久化。
- 重构视觉布局：左侧 session 栏、中间聊天区、右侧 IoT 面板。
- 保留并展示 `iot_state`、`tool_events`、`video_results`，确保前端 IoT 高亮仍来自后端结构化 JSON。
- 更新 README 中“所有 LLM 调用必须走 CLI”的旧约束。

### 3.2 暂不完成

- 不做用户登录、云端会话数据库或多用户同步。
- 不接真实 IoT 设备协议。
- 不把 Ark 的内置 web_search 插件替代现有后端 `web_search` 工具。
- 不展示模型隐藏链路推理，只展示 SDK 提供的 reasoning summary 或后端可解释处理过程。
- 不实现完整参考项目的管理员后台、模型配置弹窗和监控页。

## 4. 后端设计

### 4.1 配置

在 `backend/app/core/config.py` 增加 SDK 配置：

- `ark_api_key`：优先读取 `ARK_API_KEY`。
- `ark_base_url`：默认 `https://ark.cn-beijing.volces.com/api/v3`。
- `ark_model`：继续沿用现有模型配置名称，默认值可保持当前项目模型。
- `ark_reasoning_effort`：可选，默认不强制下发。

保留 CLI 相关配置，避免破坏现有测试和回退路径。

### 4.2 SDK 模型适配层

新增 `backend/app/model/ark_sdk_client.py`：

- `generate_json(messages, schema_name)`：用于 Agent 工具路由，要求模型只返回 JSON。
- `stream_text(messages)`：用于最终回答，返回增量事件。
- 统一把 SDK 异常转为稳定错误码，例如 `ARK_SDK_NOT_CONFIGURED`、`ARK_SDK_FAILED`、`MODEL_JSON_PARSE_FAILED`。
- 兼容 Ark Responses API 的事件类型：
  - `response.output_text.delta` → `answer_delta`
  - `response.reasoning_summary_text.delta` → `reasoning_delta`
  - `response.completed` → 使用量、模型名等元信息
  - `response.failed` 或 `error` → 稳定错误事件

### 4.3 AgentLoop 流式流程

现有 `run()` 保留，用于兼容非流式接口。新增流式方法，核心流程如下：

```text
接收用户消息
  -> yield session/status
  -> 使用 SDK generate_json 做意图/工具路由
  -> 如果是 tool_call:
       yield tool_call
       后端执行工具
       yield tool_result
       把 observation 放回 messages
       继续路由
  -> 如果进入最终回答:
       使用 SDK stream_text 生成自然语言
       持续 yield reasoning_delta / answer_delta
       组装最终 ChatResponse
       yield final
```

工具调用仍最多执行 `max_steps` 次，避免循环。工具状态、IoT 状态和视频结果仍由后端结构化产出。

### 4.4 SSE 事件协议

`POST /api/chat/stream` 返回 `text/event-stream`，每条数据为 `data: <json>\n\n`。

事件类型：

| type | 用途 |
| --- | --- |
| `session` | 返回 `conversation_id` |
| `status` | 展示“正在分析意图 / 正在调用工具 / 正在生成回答” |
| `tool_call` | 展示工具名、参数、原因和 step |
| `tool_result` | 展示工具执行结果，并更新 IoT/视频状态 |
| `reasoning_delta` | 展示 SDK reasoning summary 增量 |
| `answer_delta` | 展示最终回答增量 |
| `final` | 返回完整 `ChatResponse` |
| `error` | 返回稳定错误码和错误消息 |
| `done` | 流结束 |

### 4.5 会话历史

前端会把当前 session 的用户/助手消息作为 `client_history` 传给后端。后端优先使用 `client_history`，没有时回退 `session_store`。这样即使刷新页面，只要浏览器 localStorage 还在，就能继续保持上下文。

后端仍在 `session_store` 中记录请求结果，用于同一进程内的连续调用和测试兼容。

## 5. 前端设计

### 5.1 布局

新页面采用三栏结构：

```text
┌──────────────┬──────────────────────────┬──────────────────┐
│ Session 侧栏 │ 流式对话主区              │ IoT 输出面板      │
│ 新建/切换/删 │ 消息列表 + 思考过程 + 输入 │ 摄像头 + JSON     │
└──────────────┴──────────────────────────┴──────────────────┘
```

移动端降级为纵向布局，session 侧栏可收起。

### 5.2 Session 管理

新增本地 session 数据结构：

```ts
interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  iotState: IotState;
  toolEvents: ToolEvent[];
  videoResults: VideoSearchResult[];
  createdAt: number;
  updatedAt: number;
}
```

行为：

- 首次进入自动创建一个 session。
- 点击“新对话”创建空 session。
- 用户第一条消息生成标题，标题取前 18 个中文字符左右。
- 切换 session 时恢复消息、IoT 状态、工具轨迹和视频结果。
- 删除当前 session 后切换到最近 session；无 session 时重新创建。

### 5.3 消息与思考展示

消息结构扩展：

```ts
interface Message {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  reasoning?: string;
  statusText?: string;
  processEvents?: ChatProcessEvent[];
  createdAt: number;
  error?: string;
}
```

展示方式：

- 用户消息：浅蓝气泡，右侧对齐。
- 助手消息：透明文档式排版，左侧对齐。
- 发送后先显示“思考中”占位，收到首个有效事件后替换为助手消息。
- `reasoning_delta` 放入可折叠“思考摘要”。
- `status/tool_call/tool_result` 放入可折叠“处理过程”。
- `answer_delta` 逐步追加到助手消息正文。
- 错误显示为助手错误气泡，并恢复输入框。

### 5.4 输入区

参考项目的悬浮输入框：

- Enter 发送，Shift+Enter 换行。
- 请求中禁用输入和发送按钮。
- 底部保留能力提示标签，例如“联网搜索”“视频检索”“IoT 控制”，第一版只做状态提示，不额外改变工具路由。
- 智能滚动：用户在底部附近时自动跟随；用户上滑查看历史时不强行拉到底部。

### 5.5 IoT 面板

保留现有功能：

- 摄像头模拟预览。
- “移动”“遮蔽”状态按钮。
- 原始 JSON 输出。

视觉调整：

- 与参考项目一致的浅灰背景、白色卡片、轻边框和柔和阴影。
- 状态按钮高亮仍只根据 `iot_state.iot_action`。
- JSON 区默认折叠或高度收敛，避免压迫对话区域。

## 6. 错误处理

- SDK 未配置 API Key：返回 `ARK_SDK_NOT_CONFIGURED`，前端显示可读错误。
- SDK 调用失败：返回 `ARK_SDK_FAILED`，前端保留用户消息并显示失败气泡。
- 模型 JSON 解析失败：返回 `MODEL_JSON_PARSE_FAILED`，不执行工具。
- 工具失败：继续返回 `tool_result`，最终回答需要说明工具失败原因。
- SSE 中断：前端停止 loading，保留已收到的部分内容，并显示“连接中断”。

## 7. 测试计划

后端：

- 为 `ArkSDKModelClient` 增加 JSON 解析和事件映射测试。
- 为 `AgentLoop` 流式流程增加 fake model 测试：直答、IoT 工具、工具失败、模型错误。
- 为 `/api/chat/stream` 增加 TestClient 测试，验证 SSE 至少包含 `session`、`status`、`answer_delta`、`final`、`done`。
- 保留现有 `/api/chat` 测试，必要时改为 mock SDK。

前端：

- 运行 `npm run build` 验证 TypeScript 和 Vite 构建。
- 手动验证：新建 session、切换 session、删除 session、流式输出、思考摘要、IoT 高亮、错误恢复、移动端布局。

## 8. 风险与约束

- 旧文档要求所有 LLM 走 CLI，本轮会明确改成“对话主链路走 SDK，CLI 保留为兼容层”。
- Ark SDK 的 reasoning summary 是否返回取决于模型能力和请求参数；没有返回时，前端仍显示后端处理过程。
- 工具路由依然依赖模型 JSON 输出，必须继续保留 schema 校验和错误兜底。
- Session 只保存在浏览器 localStorage，不具备跨设备同步能力。
- 当前项目不是 Git 仓库，无法按标准流程提交 commit；完成后用文件清单和测试结果替代提交记录。

## 9. 验收标准

- 用户能在左侧创建、切换、删除 session。
- 中间对话区能边接收 SSE 边展示回答增量。
- 对话过程中能看到“思考摘要”或“处理过程”。
- 调用 IoT 工具后，右侧 IoT 状态按后端 JSON 正确高亮。
- 刷新页面后，浏览器 localStorage 内的 session 可恢复。
- `backend` 测试通过，`frontend` 构建通过。
- README 不再保留与 SDK 主链路冲突的 CLI 硬约束。
