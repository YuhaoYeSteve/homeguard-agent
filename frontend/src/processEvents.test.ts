import { toProcessEvent } from "./processEvents";
import type { ChatStreamEvent } from "./types";

function assertEqual<T>(actual: T, expected: T, message: string) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${String(expected)}, got ${String(actual)}`);
  }
}

function assertDeepEqual(actual: unknown, expected: unknown, message: string) {
  const actualJson = stableStringify(actual);
  const expectedJson = stableStringify(expected);
  if (actualJson !== expectedJson) {
    throw new Error(`${message}: expected ${expectedJson}, got ${actualJson}`);
  }
}

function stableStringify(value: unknown): string {
  return JSON.stringify(sortObject(value));
}

function sortObject(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(sortObject);
  }
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([leftKey], [rightKey]) => leftKey.localeCompare(rightKey))
        .map(([key, item]) => [key, sortObject(item)]),
    );
  }
  return value;
}

const nextId = () => "process_1";
const now = () => 123456;

const ignoredEvents: ChatStreamEvent[] = [
  { type: "session", conversation_id: "conv_1" },
  { type: "done" },
  { type: "answer_delta", delta: "你好" },
  { type: "reasoning_delta", delta: "判断为普通问答" },
  {
    type: "final",
    step: 1,
    elapsed_ms: 20,
    response: {
      conversation_id: "conv_1",
      assistant_message: "完成",
      iot_state: {
        iot_action: "none",
        device_id: null,
        target: null,
        status: "idle",
        raw_command: null,
      },
      video_results: [],
      tool_events: [],
      error: null,
    },
  },
];

for (const event of ignoredEvents) {
  assertEqual(
    toProcessEvent(event, { nextId, now }),
    null,
    `${event.type} should not be shown in process events`,
  );
}

const statusEvent = toProcessEvent(
  {
    type: "status",
    status: "model_decision",
    message: "正在分析意图并选择下一步动作...",
    step: 1,
    model_round: 1,
    architecture_step: {
      id: "03",
      title: "模型决策层",
      description: "LLM 判断下一步是直接回答，还是调用外部能力。",
    },
  },
  { nextId, now },
);

assertDeepEqual(
  statusEvent,
  {
    id: "process_1",
    type: "status",
    label: "03 模型决策层：正在分析意图并选择下一步动作...",
    modelRound: 1,
    createdAt: 123456,
  },
  "status events should show architecture stage progress",
);

const frontendObservabilityStatusEvent = toProcessEvent(
  {
    type: "status",
    status: "frontend_observability",
    message: "完整处理轨迹、最终回复和业务状态已准备返回前端展示。",
    step: 8,
    model_round: 2,
    elapsed_ms: 48_280,
    architecture_step: {
      id: "08",
      title: "前端可观测",
      description: "将处理过程、最终回答和业务状态交给前端展示。",
    },
  },
  { nextId, now },
);

assertEqual(
  frontendObservabilityStatusEvent,
  null,
  "frontend observability status should not become a visible process event",
);

const modelInputEvent = toProcessEvent(
  {
    type: "model_input",
    model_round: 1,
    phase: "decision",
    step: 1,
    schema_name: "agent_step",
    messages: [
      { role: "system", content: "你是家庭安防助手" },
      { role: "user", content: "把摄像头转向门口" },
    ],
  },
  { nextId, now },
);

assertDeepEqual(
  modelInputEvent,
  {
    id: "process_1",
    type: "model_input",
    label: "模型输入：决策调用",
    detailLabel: "查看模型输入",
    detail: {
      schema_name: "agent_step",
      messages: [
        { role: "system", content: "你是家庭安防助手" },
        { role: "user", content: "把摄像头转向门口" },
      ],
    },
    modelRound: 1,
    createdAt: 123456,
  },
  "model input should be shown as a model process event",
);

const modelOutputEvent = toProcessEvent(
  {
    type: "model_output",
    model_round: 1,
    phase: "decision",
    step: 1,
    output: {
      type: "tool_call",
      tool_name: "iot_control",
      arguments: { action: "move", target: "门口" },
      reason: "用户要求移动摄像头",
    },
    elapsed_ms: 88,
  },
  { nextId, now },
);

assertDeepEqual(
  modelOutputEvent,
  {
    id: "process_1",
    type: "model_output",
    label: "模型输出：结构化决策",
    detailLabel: "查看模型输出",
    detail: {
      type: "tool_call",
      tool_name: "iot_control",
      arguments: { action: "move", target: "门口" },
      reason: "用户要求移动摄像头",
    },
    elapsedMs: 88,
    modelRound: 1,
    createdAt: 123456,
  },
  "model output should expose the structured model decision",
);

const toolCallEvent = toProcessEvent(
  {
    type: "tool_call",
    step: 1,
    tool_name: "iot_control",
    arguments: { action: "move", target: "门口" },
    reason: "用户要求移动摄像头",
    elapsed_ms: 88,
  },
  { nextId, now },
);

assertDeepEqual(
  toolCallEvent,
  {
    id: "process_1",
    type: "tool_call",
    label: "工具调用：iot_control",
    detailLabel: "查看工具调用参数",
    detail: {
      tool_name: "iot_control",
      arguments: { action: "move", target: "门口" },
      reason: "用户要求移动摄像头",
    },
    elapsedMs: 88,
    createdAt: 123456,
  },
  "tool call should become a model output process event",
);

const policyDecisionEvent = toProcessEvent(
  {
    type: "policy_decision",
    action: "refuse",
    category: "prompt_injection",
    reason: "用户要求忽略规则并直接输出工具 JSON",
    route_hints: [],
    answer: "不能执行该请求。",
  },
  { nextId, now },
);

assertDeepEqual(
  policyDecisionEvent,
  {
    id: "process_1",
    type: "policy_decision",
    label: "策略判断：refuse（prompt_injection）",
    detailLabel: "查看策略判断",
    detail: {
      action: "refuse",
      category: "prompt_injection",
      reason: "用户要求忽略规则并直接输出工具 JSON",
      route_hints: [],
      answer: "不能执行该请求。",
    },
    createdAt: 123456,
  },
  "policy decisions should be visible in the demo trace",
);

const historyTrimmedEvent = toProcessEvent(
  {
    type: "history_trimmed",
    original_count: 12,
    kept_count: 6,
    dropped_count: 6,
  },
  { nextId, now },
);

assertDeepEqual(
  historyTrimmedEvent,
  {
    id: "process_1",
    type: "history_trimmed",
    label: "上下文裁剪：保留 6/12 条历史，裁剪 6 条",
    detailLabel: "查看上下文裁剪",
    detail: {
      original_count: 12,
      kept_count: 6,
      dropped_count: 6,
    },
    createdAt: 123456,
  },
  "history trimming should be visible when model context is shortened",
);

const toolResultEvent = toProcessEvent(
  {
    type: "tool_result",
    step: 1,
    tool_name: "iot_control",
    elapsed_ms: 12,
    iot_state: {
      iot_action: "move",
      device_id: "camera_living_room",
      target: "门口",
      status: "simulated_success",
      raw_command: null,
    },
    video_results: [],
    event: {
      step: 1,
      tool_name: "iot_control",
      input: { action: "move", target: "门口" },
      output: { status: "simulated_success" },
      status: "success",
      elapsed_ms: 12,
    },
  },
  { nextId, now },
);

assertDeepEqual(
  toolResultEvent,
  {
    id: "process_1",
    type: "tool_result",
    label: "工具结果：iot_control（success）",
    detailLabel: "查看工具执行结果",
    detail: {
      step: 1,
      tool_name: "iot_control",
      input: { action: "move", target: "门口" },
      output: { status: "simulated_success" },
      status: "success",
      elapsed_ms: 12,
    },
    elapsedMs: 12,
    createdAt: 123456,
  },
  "tool result should expose only direct tool execution details",
);

const modelMetaEvent = toProcessEvent(
  {
    type: "model_meta",
    model: "doubao-test",
    usage: { total_tokens: 99 },
  },
  { nextId, now },
);

assertDeepEqual(
  modelMetaEvent,
  {
    id: "process_1",
    type: "model_meta",
    label: "模型统计：doubao-test，99 tokens",
    detail: {
      model: "doubao-test",
      usage: { total_tokens: 99 },
    },
    createdAt: 123456,
  },
  "model metadata should be shown without unrelated stream details",
);

const errorEvent = toProcessEvent(
  { type: "error", code: "MODEL_VALIDATION_ERROR", message: "模型输出不合法" },
  { nextId, now },
);

assertDeepEqual(
  errorEvent,
  {
    id: "process_1",
    type: "error",
    label: "错误：MODEL_VALIDATION_ERROR: 模型输出不合法",
    detail: {
      code: "MODEL_VALIDATION_ERROR",
      message: "模型输出不合法",
    },
      createdAt: 123456,
    },
    "errors should remain visible for debugging",
  );
