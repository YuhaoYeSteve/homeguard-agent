export type IotAction = "move" | "privacy_mask" | "none";

export type ToolName =
  | "web_search"
  | "video_search"
  | "iot_control"
  | "final_answer";

export type IotStatus =
  | "idle"
  | "simulated_success"
  | "validation_failed"
  | "tool_error";

export type ToolEventStatus = "success" | "failed" | "skipped";

export type MessageRole = "system" | "user" | "assistant" | "tool";

export type JsonScalar = string | number | boolean;

export type JsonObject = Record<string, JsonScalar>;

export interface IotControlCommand {
  tool: "iot_control";
  device_id: string;
  action: IotAction;
  target: string | null;
  parameters: JsonObject;
  confidence: number;
  reason: string;
}

export interface IotState {
  iot_action: IotAction;
  device_id: string | null;
  target: string | null;
  status: IotStatus;
  raw_command: IotControlCommand | null;
}

export interface VideoSearchResult {
  f_id: string;
  f_text: string;
  search_score: number | null;
  ann_score: number | null;
  metadata: JsonObject;
}

export interface ToolEvent {
  step: number;
  tool_name: ToolName;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  status: ToolEventStatus;
  elapsed_ms: number;
}

export interface ChatResponse {
  conversation_id: string;
  assistant_message: string;
  iot_state: IotState;
  video_results: VideoSearchResult[];
  tool_events: ToolEvent[];
  error: Record<string, string> | null;
}

export interface SystemPromptResponse {
  system_prompt: string;
  model_id: string;
}

export interface ChatProcessEvent {
  id: string;
  type:
    | "status"
    | "policy_decision"
    | "history_trimmed"
    | "model_input"
    | "model_output"
    | "tool_call"
    | "tool_result"
    | "model_meta"
    | "final"
    | "error";
  label: string;
  detail?: unknown;
  detailLabel?: string;
  elapsedMs?: number;
  modelRound?: number;
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

export interface AgentArchitectureStep {
  id: string;
  title: string;
  description: string;
}

export type ChatStreamEvent =
  | { type: "session"; conversation_id: string }
  | {
      type: "status";
      status: string;
      message: string;
      step?: number;
      model_round?: number;
      elapsed_ms?: number;
      architecture_step?: AgentArchitectureStep;
    }
  | {
      type: "policy_decision";
      action: "continue" | "refuse" | "clarify";
      category: string;
      reason: string;
      route_hints: string[];
      answer: string;
    }
  | {
      type: "history_trimmed";
      original_count: number;
      kept_count: number;
      dropped_count: number;
    }
  | {
      type: "model_input";
      model_round: number;
      phase: "decision" | "final_answer";
      step: number;
      schema_name: string;
      messages: Array<{ role: MessageRole; content: string }>;
    }
  | {
      type: "model_output";
      model_round: number;
      phase: "decision" | "final_answer";
      step: number;
      output: unknown;
      elapsed_ms: number;
    }
  | {
      type: "tool_call";
      step: number;
      model_round?: number;
      tool_name: ToolName;
      arguments: Record<string, unknown>;
      reason: string;
      elapsed_ms?: number;
    }
  | {
      type: "tool_result";
      step: number;
      model_round?: number;
      tool_name: ToolName;
      event: ToolEvent;
      elapsed_ms?: number;
      iot_state: IotState;
      video_results: VideoSearchResult[];
    }
  | { type: "reasoning_delta"; delta: string }
  | { type: "answer_delta"; delta: string }
  | {
      type: "model_meta";
      model?: string | null;
      usage?: { total_tokens?: number };
    }
  | {
      type: "final";
      step?: number;
      model_round?: number;
      response: ChatResponse;
      elapsed_ms?: number;
    }
  | { type: "error"; code?: string; message: string }
  | { type: "done" };
