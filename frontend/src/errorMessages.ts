import type { ChatStreamEvent } from "./types";

type StreamErrorEvent = Extract<ChatStreamEvent, { type: "error" }>;

export function formatStreamErrorMessage(event: StreamErrorEvent): string {
  return event.code ? `${event.code}: ${event.message}` : event.message;
}
