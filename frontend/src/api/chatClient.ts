import type {
  ChatStreamEvent,
  Message,
  SystemPromptResponse,
} from "../types";
import { isFrontendOnlyMessage } from "../frontendOnlyMessages";

const CHAT_STREAM_API_URL = "http://127.0.0.1:8000/api/chat/stream";
const SYSTEM_PROMPT_API_URL = "http://127.0.0.1:8000/api/system-prompt";
const CHAT_STREAM_TIMEOUT_MS = 90_000;

export async function fetchSystemPrompt(): Promise<SystemPromptResponse> {
  const response = await fetch(SYSTEM_PROMPT_API_URL);

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(
      `System prompt request failed with ${response.status} ${
        response.statusText
      }${errorBody ? `: ${errorBody}` : ""}`,
    );
  }

  return (await response.json()) as SystemPromptResponse;
}

function parseSseFrame(frame: string): ChatStreamEvent | null {
  const data = frame
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice("data:".length).trimStart())
    .join("\n");

  if (data.length === 0) {
    return null;
  }

  return JSON.parse(data) as ChatStreamEvent;
}

type ClientHistoryMessage = Message & { role: "user" | "assistant" };

function isClientHistoryMessage(
  message: Message,
): message is ClientHistoryMessage {
  return (
    (message.role === "user" || message.role === "assistant") &&
    message.content.trim().length > 0 &&
    !isFrontendOnlyMessage(message)
  );
}

export function toClientHistory(history: Message[]): Array<{
  role: "user" | "assistant";
  content: string;
}> {
  return history
    .filter(isClientHistoryMessage)
    .map((message) => ({
      role: message.role,
      content: message.content,
    }));
}

export async function streamChatMessage(params: {
  message: string;
  conversationId: string;
  history: Message[];
  onEvent: (event: ChatStreamEvent) => void;
}): Promise<void> {
  const controller = new AbortController();
  let didTimeout = false;
  const timeoutId = window.setTimeout(() => {
    didTimeout = true;
    controller.abort();
  }, CHAT_STREAM_TIMEOUT_MS);

  try {
    const response = await fetch(CHAT_STREAM_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        conversation_id: params.conversationId,
        message: params.message,
        debug: true,
        client_history: toClientHistory(params.history),
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      const errorBody = await response.text();
      throw new Error(
        `Chat stream request failed with ${response.status} ${response.statusText}${
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

    try {
      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          buffer += decoder.decode();
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split(/\r?\n\r?\n/);
        buffer = frames.pop() ?? "";

        for (const frame of frames) {
          const event = parseSseFrame(frame);
          if (event) {
            params.onEvent(event);
          }
        }
      }

      const tailEvent = parseSseFrame(buffer);
      if (tailEvent) {
        params.onEvent(tailEvent);
      }
    } finally {
      reader.releaseLock();
    }
  } catch (error) {
    if (didTimeout) {
      throw new Error(
        `Chat stream request timed out after ${
          CHAT_STREAM_TIMEOUT_MS / 1000
        } seconds`,
      );
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}
