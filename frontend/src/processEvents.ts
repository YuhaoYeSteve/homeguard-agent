import type { ChatProcessEvent, ChatStreamEvent } from "./types";
import { formatStreamErrorMessage } from "./errorMessages";

interface ProcessEventOptions {
  nextId: () => string;
  now: () => number;
}

type VisibleProcessStreamEvent = Extract<
  ChatStreamEvent,
  {
    type:
      | "model_input"
      | "model_output"
      | "status"
      | "policy_decision"
      | "history_trimmed"
      | "tool_call"
      | "tool_result"
      | "model_meta"
      | "error";
  }
>;

export function toProcessEvent(
  event: ChatStreamEvent,
  options: ProcessEventOptions,
): ChatProcessEvent | null {
  if (!isProcessEvent(event)) {
    return null;
  }

  if (isFrontendObservabilityStatus(event)) {
    return null;
  }

  const detailLabel = processEventDetailLabel(event);

  return {
    id: options.nextId(),
    type: event.type,
    label: processEventLabel(event),
    detail: processEventDetail(event),
    detailLabel,
    elapsedMs: streamEventElapsedMs(event),
    modelRound: processEventModelRound(event),
    createdAt: options.now(),
  };
}

function isProcessEvent(event: ChatStreamEvent): event is VisibleProcessStreamEvent {
  switch (event.type) {
    case "model_input":
    case "model_output":
    case "status":
    case "policy_decision":
    case "history_trimmed":
    case "tool_call":
    case "tool_result":
    case "model_meta":
    case "error":
      return true;
    default:
      return false;
  }
}

function isFrontendObservabilityStatus(
  event: VisibleProcessStreamEvent,
): boolean {
  return (
    event.type === "status" &&
    (event.status === "frontend_observability" ||
      event.architecture_step?.id === "08" ||
      event.architecture_step?.title === "前端可观测")
  );
}

function processEventLabel(event: VisibleProcessStreamEvent): string {
  switch (event.type) {
    case "model_input":
      return event.phase === "final_answer"
        ? "模型输入：最终自然语言生成"
        : "模型输入：决策调用";
    case "model_output":
      return event.phase === "final_answer"
        ? "模型输出：最终自然语言"
        : "模型输出：结构化决策";
    case "status": {
      const stage = event.architecture_step
        ? `${event.architecture_step.id} ${event.architecture_step.title}`
        : event.status;
      return `${stage}：${event.message}`;
    }
    case "policy_decision":
      return `策略判断：${event.action}（${event.category}）`;
    case "history_trimmed":
      return `上下文裁剪：保留 ${event.kept_count}/${event.original_count} 条历史，裁剪 ${event.dropped_count} 条`;
    case "tool_call":
      return `工具调用：${event.tool_name}`;
    case "tool_result":
      return `工具结果：${event.tool_name}（${event.event.status}）`;
    case "model_meta": {
      const tokenText = event.usage?.total_tokens
        ? `，${event.usage.total_tokens} tokens`
        : "";
      return `模型统计：${event.model ?? "未知模型"}${tokenText}`;
    }
    case "error":
      return `错误：${formatStreamErrorMessage(event)}`;
  }
}

function processEventDetail(event: VisibleProcessStreamEvent): unknown {
  switch (event.type) {
    case "model_input":
      return {
        schema_name: event.schema_name,
        messages: event.messages,
      };
    case "model_output":
      return event.output;
    case "status":
      return undefined;
    case "policy_decision":
      return {
        action: event.action,
        category: event.category,
        reason: event.reason,
        route_hints: event.route_hints,
        answer: event.answer,
      };
    case "history_trimmed":
      return {
        original_count: event.original_count,
        kept_count: event.kept_count,
        dropped_count: event.dropped_count,
      };
    case "tool_call":
      return {
        tool_name: event.tool_name,
        arguments: event.arguments,
        reason: event.reason,
      };
    case "tool_result":
      return event.event;
    case "model_meta":
      return {
        model: event.model,
        usage: event.usage,
      };
    case "error":
      return {
        code: event.code,
        message: event.message,
      };
  }
}

function processEventDetailLabel(
  event: VisibleProcessStreamEvent,
): string | undefined {
  switch (event.type) {
    case "model_input":
      return "查看模型输入";
    case "model_output":
      return "查看模型输出";
    case "status":
      return undefined;
    case "policy_decision":
      return "查看策略判断";
    case "history_trimmed":
      return "查看上下文裁剪";
    case "tool_call":
      return "查看工具调用参数";
    case "tool_result":
      return "查看工具执行结果";
    default:
      return undefined;
  }
}

function processEventModelRound(
  event: VisibleProcessStreamEvent,
): number | undefined {
  switch (event.type) {
    case "model_input":
    case "model_output":
    case "status":
    case "tool_call":
    case "tool_result":
      return event.model_round;
    default:
      return undefined;
  }
}

function streamEventElapsedMs(event: VisibleProcessStreamEvent): number | undefined {
  switch (event.type) {
    case "model_output":
      return event.elapsed_ms;
    case "status":
      return event.elapsed_ms;
    case "tool_call":
      return event.elapsed_ms;
    case "tool_result":
      return event.elapsed_ms ?? event.event.elapsed_ms;
    default:
      return undefined;
  }
}
