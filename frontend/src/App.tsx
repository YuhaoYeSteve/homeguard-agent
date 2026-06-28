import { useEffect, useState } from "react";

import { fetchSystemPrompt, streamChatMessage } from "./api/chatClient";
import { ChatPane } from "./components/ChatPane";
import { IotPanel } from "./components/IotPanel";
import { SessionSidebar } from "./components/SessionSidebar";
import {
  canCreateSession,
  canDeleteSession,
  canSelectSession,
} from "./sessionInteractionPolicy";
import {
  FRONTEND_ONLY_WELCOME_MESSAGE,
  isFrontendOnlyMessage,
} from "./frontendOnlyMessages";
import { formatStreamErrorMessage } from "./errorMessages";
import { toProcessEvent } from "./processEvents";
import type {
  ChatProcessEvent,
  ChatSession,
  ChatStreamEvent,
  IotState,
  Message,
} from "./types";

const SESSION_STORAGE_KEY = "homeguard_chat_sessions";
const ACTIVE_SESSION_STORAGE_KEY = "homeguard_active_session_id";

const INITIAL_IOT_STATE: IotState = {
  iot_action: "none",
  device_id: null,
  target: null,
  status: "idle",
  raw_command: null,
};

interface SessionState {
  sessions: ChatSession[];
  activeSessionId: string;
}

function createId(prefix: string): string {
  const random =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `${Date.now()}_${Math.random().toString(36).slice(2)}`;

  return `${prefix}_${random}`;
}

function createInitialIotState(): IotState {
  return { ...INITIAL_IOT_STATE };
}

function createMessage(
  role: Message["role"],
  content: string,
  createdAt = Date.now(),
  error?: string,
): Message {
  return {
    id: createId("msg"),
    role,
    content,
    createdAt,
    ...(error ? { error } : {}),
  };
}

function createEmptySession(): ChatSession {
  const now = Date.now();

  return {
    id: createId("conv"),
    title: "新对话",
    messages: [],
    iotState: createInitialIotState(),
    toolEvents: [],
    videoResults: [],
    createdAt: now,
    updatedAt: now,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isMessageRole(value: unknown): value is Message["role"] {
  return (
    value === "system" ||
    value === "user" ||
    value === "assistant" ||
    value === "tool"
  );
}

function normalizeMessages(messages: unknown): Message[] {
  if (!Array.isArray(messages)) {
    return [];
  }

  const normalizedMessages = messages
    .filter(
      (message): message is Record<string, unknown> =>
        isRecord(message) &&
        isMessageRole(message.role) &&
        typeof message.content === "string",
    )
    .map((message): Message => ({
      ...message,
      role: message.role as Message["role"],
      content: message.content as string,
      id: typeof message.id === "string" ? message.id : createId("msg"),
      createdAt:
        typeof message.createdAt === "number" ? message.createdAt : Date.now(),
    }))
    .filter((message) => !isFrontendOnlyMessage(message)) as Message[];

  return normalizedMessages;
}

function normalizeSession(session: unknown): ChatSession | null {
  if (!isRecord(session)) {
    return null;
  }

  const now = Date.now();

  return {
    id: typeof session.id === "string" ? session.id : createId("conv"),
    title: typeof session.title === "string" ? session.title : "新对话",
    messages: normalizeMessages(session.messages),
    iotState: isRecord(session.iotState)
      ? (session.iotState as unknown as IotState)
      : createInitialIotState(),
    toolEvents: Array.isArray(session.toolEvents)
      ? (session.toolEvents as ChatSession["toolEvents"])
      : [],
    videoResults: Array.isArray(session.videoResults)
      ? (session.videoResults as ChatSession["videoResults"])
      : [],
    createdAt: typeof session.createdAt === "number" ? session.createdAt : now,
    updatedAt: typeof session.updatedAt === "number" ? session.updatedAt : now,
  };
}

function loadSessions(): ChatSession[] {
  try {
    const storedSessions = localStorage.getItem(SESSION_STORAGE_KEY);
    if (!storedSessions) {
      return [createEmptySession()];
    }

    const parsedSessions = JSON.parse(storedSessions) as unknown;
    if (!Array.isArray(parsedSessions)) {
      return [createEmptySession()];
    }

    const sessions = parsedSessions
      .map(normalizeSession)
      .filter((session): session is ChatSession => session !== null);

    return sessions.length > 0 ? sessions : [createEmptySession()];
  } catch {
    return [createEmptySession()];
  }
}

function saveSessions(sessions: ChatSession[]): void {
  try {
    localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(sessions));
  } catch {
    // Storage can fail in private mode or quota exhaustion; keep in-memory state.
  }
}

function titleFromMessage(message: string): string {
  const title = message.trim().replace(/\s+/g, " ");

  if (title.length === 0) {
    return "新对话";
  }

  return title.length > 24 ? `${title.slice(0, 24)}...` : title;
}

function loadSessionState(): SessionState {
  const sessions = loadSessions();
  let storedActiveSessionId: string | null = null;

  try {
    storedActiveSessionId = localStorage.getItem(ACTIVE_SESSION_STORAGE_KEY);
  } catch {
    storedActiveSessionId = null;
  }

  const activeSessionId =
    storedActiveSessionId &&
    sessions.some((session) => session.id === storedActiveSessionId)
      ? storedActiveSessionId
      : sessions[0].id;

  return {
    sessions,
    activeSessionId,
  };
}

function saveActiveSessionId(activeSessionId: string): void {
  try {
    localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, activeSessionId);
  } catch {
    // Storage can fail in private mode or quota exhaustion; keep in-memory state.
  }
}

function createProcessEvent(event: ChatStreamEvent): ChatProcessEvent | null {
  return toProcessEvent(event, {
    nextId: () => createId("process"),
    now: Date.now,
  });
}

function updateAssistantMessage(
  sessions: ChatSession[],
  sessionId: string,
  messageId: string,
  updateMessage: (message: Message) => Message,
  updateSession?: (session: ChatSession) => ChatSession,
): ChatSession[] {
  return sessions.map((session) => {
    if (session.id !== sessionId) {
      return session;
    }

    let didUpdateMessage = false;
    const messages = session.messages.map((message) => {
      if (message.id !== messageId) {
        return message;
      }

      didUpdateMessage = true;
      return updateMessage(message);
    });

    if (!didUpdateMessage) {
      return session;
    }

    const updatedSession = {
      ...session,
      messages,
      updatedAt: Date.now(),
    };

    return updateSession ? updateSession(updatedSession) : updatedSession;
  });
}

export default function App() {
  const [sessionState, setSessionState] =
    useState<SessionState>(loadSessionState);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [systemPrompt, setSystemPrompt] = useState<string | null>(null);
  const [modelId, setModelId] = useState<string | null>(null);
  const [systemPromptError, setSystemPromptError] = useState<string | null>(
    null,
  );
  const [streamingSessionId, setStreamingSessionId] = useState<string | null>(
    null,
  );

  const { activeSessionId, sessions } = sessionState;
  const activeSession =
    sessions.find((session) => session.id === activeSessionId) ?? sessions[0];

  useEffect(() => {
    saveSessions(sessions);
  }, [sessions]);

  useEffect(() => {
    saveActiveSessionId(activeSessionId);
  }, [activeSessionId]);

  useEffect(() => {
    let isActive = true;

    fetchSystemPrompt()
      .then((response) => {
        if (!isActive) {
          return;
        }

        setSystemPrompt(response.system_prompt);
        setModelId(response.model_id);
        setSystemPromptError(null);
      })
      .catch((error) => {
        if (!isActive) {
          return;
        }

        setSystemPromptError(
          error instanceof Error ? error.message : String(error),
        );
      });

    return () => {
      isActive = false;
    };
  }, []);

  const handleSubmit = async () => {
    const messageText = input.trim();
    if (messageText.length === 0 || loading || !activeSession) {
      return;
    }

    const sessionId = activeSession.id;
    let targetSessionId = sessionId;
    const historyBeforeSubmit = activeSession.messages;
    const userMessage = createMessage("user", messageText);
    const assistantMessage: Message = {
      ...createMessage("assistant", ""),
      statusText: "思考中...",
      processEvents: [],
    };

    const syncSessionId = (conversationId: string) => {
      if (conversationId === targetSessionId) {
        return;
      }

      const previousSessionId = targetSessionId;
      targetSessionId = conversationId;
        setStreamingSessionId((current) =>
          current === previousSessionId ? conversationId : current,
        );

      setSessionState((current) => ({
        activeSessionId:
          current.activeSessionId === previousSessionId
            ? conversationId
            : current.activeSessionId,
        sessions: current.sessions.map((session) =>
          session.id === previousSessionId
            ? {
                ...session,
                id: conversationId,
              }
            : session,
        ),
      }));
    };

    setLoading(true);
      setStreamingSessionId(sessionId);
    setInput("");
    setSessionState((current) => ({
      ...current,
      sessions: current.sessions.map((session) => {
        if (session.id !== sessionId) {
          return session;
        }

        const isFirstUserMessage = !session.messages.some(
          (message) => message.role === "user",
        );

        return {
          ...session,
          title: isFirstUserMessage
            ? titleFromMessage(messageText)
            : session.title,
          messages: [...session.messages, userMessage, assistantMessage],
          toolEvents: [],
          videoResults: [],
          updatedAt: assistantMessage.createdAt,
        };
      }),
    }));

    try {
      await streamChatMessage({
        message: messageText,
        conversationId: sessionId,
        history: historyBeforeSubmit,
        onEvent: (event) => {
          switch (event.type) {
            case "session":
              syncSessionId(event.conversation_id);
              return;

            case "answer_delta":
              setSessionState((current) => ({
                ...current,
                sessions: updateAssistantMessage(
                  current.sessions,
                  targetSessionId,
                  assistantMessage.id,
                  (message) => ({
                    ...message,
                    content: `${message.content}${event.delta}`,
                    statusText: undefined,
                  }),
                ),
              }));
              return;

            case "reasoning_delta":
              setSessionState((current) => ({
                ...current,
                sessions: updateAssistantMessage(
                  current.sessions,
                  targetSessionId,
                  assistantMessage.id,
                  (message) => ({
                    ...message,
                    reasoning: `${message.reasoning ?? ""}${event.delta}`,
                  }),
                ),
              }));
              return;

            case "status": {
              const processEvent = createProcessEvent(event);
              setSessionState((current) => ({
                ...current,
                sessions: updateAssistantMessage(
                  current.sessions,
                  targetSessionId,
                  assistantMessage.id,
                  (message) => ({
                    ...message,
                    statusText: event.message,
                    processEvents: processEvent
                      ? [...(message.processEvents ?? []), processEvent]
                      : message.processEvents,
                  }),
                ),
              }));
              return;
            }

            case "model_input":
            case "model_output":
            case "policy_decision":
            case "history_trimmed":
            case "tool_call":
            case "model_meta": {
              const processEvent = createProcessEvent(event);
              setSessionState((current) => ({
                ...current,
                sessions: updateAssistantMessage(
                  current.sessions,
                  targetSessionId,
                  assistantMessage.id,
                  (message) => ({
                    ...message,
                    processEvents: processEvent
                      ? [...(message.processEvents ?? []), processEvent]
                      : message.processEvents,
                  }),
                ),
              }));
              return;
            }

            case "tool_result": {
              const processEvent = createProcessEvent(event);
              setSessionState((current) => ({
                ...current,
                sessions: updateAssistantMessage(
                  current.sessions,
                  targetSessionId,
                  assistantMessage.id,
                  (message) => ({
                    ...message,
                    processEvents: processEvent
                      ? [...(message.processEvents ?? []), processEvent]
                      : message.processEvents,
                  }),
                  (session) => ({
                    ...session,
                    iotState: event.iot_state,
                    toolEvents: [...session.toolEvents, event.event],
                    videoResults: event.video_results,
                  }),
                ),
              }));
              return;
            }

            case "final": {
              syncSessionId(event.response.conversation_id);
              const processEvent = createProcessEvent(event);
              setSessionState((current) => ({
                ...current,
                sessions: updateAssistantMessage(
                  current.sessions,
                  targetSessionId,
                  assistantMessage.id,
                  (message) => ({
                    ...message,
                    content: event.response.assistant_message || message.content,
                    statusText: undefined,
                    processEvents: processEvent
                      ? [...(message.processEvents ?? []), processEvent]
                      : message.processEvents,
                  }),
                  (session) => ({
                    ...session,
                    iotState: event.response.iot_state,
                    toolEvents: event.response.tool_events,
                    videoResults: event.response.video_results,
                  }),
                ),
              }));
              return;
            }

            case "error": {
              const processEvent = createProcessEvent(event);
              setSessionState((current) => ({
                ...current,
                sessions: updateAssistantMessage(
                  current.sessions,
                  targetSessionId,
                  assistantMessage.id,
                  (message) => ({
                    ...message,
                    error: formatStreamErrorMessage(event),
                    statusText: undefined,
                    processEvents: processEvent
                      ? [...(message.processEvents ?? []), processEvent]
                      : message.processEvents,
                  }),
                ),
              }));
              return;
            }

            case "done":
              return;
          }
        },
      });
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : String(error);
      const processEvent = createProcessEvent({
        type: "error",
        message: errorMessage,
      });

      setSessionState((current) => ({
        ...current,
        sessions: updateAssistantMessage(
          current.sessions,
          targetSessionId,
          assistantMessage.id,
          (message) => ({
            ...message,
            content: message.content || `请求失败：${errorMessage}`,
            error: errorMessage,
            statusText: undefined,
            processEvents: processEvent
              ? [...(message.processEvents ?? []), processEvent]
              : message.processEvents,
          }),
        ),
      }));
    } finally {
      setLoading(false);
        setStreamingSessionId((current) =>
          current === targetSessionId ? null : current,
        );
    }
  };

  const handleCreateSession = () => {
      if (!canCreateSession({ isStreaming: loading })) {
      return;
    }

    const newSession = createEmptySession();
    setInput("");
    setSessionState((current) => ({
      activeSessionId: newSession.id,
      sessions: [newSession, ...current.sessions],
    }));
  };

  const handleSelectSession = (sessionId: string) => {
      if (!canSelectSession({ isStreaming: loading })) {
      return;
    }

    setInput("");
    setSessionState((current) => {
      if (
        current.activeSessionId === sessionId ||
        !current.sessions.some((session) => session.id === sessionId)
      ) {
        return current;
      }

      return {
        ...current,
        activeSessionId: sessionId,
      };
    });
  };

  const handleDeleteSession = (sessionId: string) => {
      if (
        !canDeleteSession({
          sessionCount: sessions.length,
          sessionId,
          streamingSessionId,
        })
      ) {
      return;
    }

    if (sessionId === activeSessionId) {
      setInput("");
    }

    setSessionState((current) => {
      if (current.sessions.length <= 1) {
        return current;
      }

      const remainingSessions = current.sessions.filter(
        (session) => session.id !== sessionId,
      );

      if (remainingSessions.length === current.sessions.length) {
        return current;
      }

      const activeSessionStillExists = remainingSessions.some(
        (session) => session.id === current.activeSessionId,
      );

      return {
        activeSessionId: activeSessionStillExists
          ? current.activeSessionId
          : remainingSessions[0].id,
        sessions: remainingSessions,
      };
    });
  };

  if (!activeSession) {
    return null;
  }

  return (
    <main className="app-shell">
      <SessionSidebar
        activeSessionId={activeSessionId}
        onCreateSession={handleCreateSession}
        onDeleteSession={handleDeleteSession}
        onSelectSession={handleSelectSession}
        sessions={sessions}
      />
      <div className="workspace">
        <ChatPane
          emptyMessage={FRONTEND_ONLY_WELCOME_MESSAGE}
          input={input}
          loading={loading}
          messages={activeSession.messages}
          onInputChange={setInput}
          onSubmit={handleSubmit}
        />
        <IotPanel
          modelId={modelId}
          state={activeSession.iotState}
          systemPrompt={systemPrompt}
          systemPromptError={systemPromptError}
        />
      </div>
    </main>
  );
}
