# 对话步骤实际耗时显示设计

## 背景

对话页当前已经在助手消息中展示“处理过程”，后端 SSE 事件也按 `step` 输出状态、工具调用、工具结果和最终响应。工具结果已有 `elapsed_ms`，但模型分析和回答生成阶段没有统一的实际耗时字段，前端无法展示每个步骤的完整耗时。

## 目标

在对话页面的“处理过程”中展示每个步骤的实际耗时。这里的耗时是执行完成后的最终耗时，不做超时阈值、倒计时或前端估算。

## 方案

后端 `AgentLoop.iter_agent_events()` 负责记录真实执行耗时，并在 SSE 事件上补充 `elapsed_ms`：

- `tool_call`：表示模型完成本轮意图分析并决定调用工具，携带本轮模型决策耗时。
- `tool_result`：复用工具 `ToolEvent.elapsed_ms`，表示工具执行耗时。
- `final`：携带最终回答所在 `step` 与生成耗时，流式回答时统计 `_stream_final_answer()` 消费完成的耗时；非流式时为 0。
- `status`：仍作为开始状态提示，不强行补完成耗时，避免开始事件与完成事件语义混淆。

前端类型 `ChatStreamEvent` 增加可选 `elapsed_ms` 字段，并在 `ChatPane` 的处理过程列表中用统一格式展示，例如 `耗时 1.24s`。工具结果事件优先读取 `event.event.elapsed_ms`，其他事件读取顶层 `elapsed_ms`。

## 测试

- 后端补充 AgentLoop 单元测试，验证 `tool_call`、`tool_result`、`final` 事件都包含实际耗时字段。
- 前端通过 `npm run build` 验证 TypeScript 类型和构建。
