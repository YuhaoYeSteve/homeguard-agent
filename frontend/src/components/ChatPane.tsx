import { useEffect, useState, type FormEvent, type KeyboardEvent } from "react";

import type { ChatProcessEvent, Message } from "../types";

interface ChatPaneProps {
  messages: Message[];
  input: string;
  loading: boolean;
  emptyMessage?: string;
  currentTimeMs?: number;
  onInputChange: (value: string) => void;
  onSubmit: () => void;
}

const ROLE_LABELS: Record<Message["role"], string> = {
  assistant: "助手",
  user: "用户",
  system: "系统",
  tool: "工具",
};

function formatElapsedTime(elapsedMs: number): string {
  if (!Number.isFinite(elapsedMs)) {
    return "";
  }

  if (elapsedMs < 1000) {
    return `${Math.max(0, Math.round(elapsedMs))}ms`;
  }

  return `${(elapsedMs / 1000).toFixed(2)}s`;
}

function processElapsedLabel(
  event: ChatProcessEvent,
  latestPendingEventId: string | undefined,
  currentTimeMs: number,
): string | null {
  if (event.elapsedMs !== undefined) {
    return `耗时 ${formatElapsedTime(event.elapsedMs)}`;
  }

  if (event.id !== latestPendingEventId) {
    return null;
  }

  return `进行中 ${formatElapsedTime(currentTimeMs - event.createdAt)}`;
}

interface ProcessEventGroup {
  key: string;
  label: string;
  events: ChatProcessEvent[];
}

function groupProcessEvents(events: ChatProcessEvent[]): ProcessEventGroup[] {
  const groups: ProcessEventGroup[] = [];
  const groupByKey = new Map<string, ProcessEventGroup>();

  events.forEach((event) => {
    const key =
      event.modelRound === undefined ? "setup" : `round_${event.modelRound}`;
    let group = groupByKey.get(key);

    if (!group) {
      group = {
        key,
        label:
          event.modelRound === undefined
            ? "准备阶段"
            : `模型调用轮次 ${event.modelRound}`,
        events: [],
      };
      groupByKey.set(key, group);
      groups.push(group);
    }

    group.events.push(event);
  });

  return groups;
}

function isVisibleProcessEvent(event: ChatProcessEvent): boolean {
  return !event.label.includes("前端可观测");
}

function formatProcessDetail(detail: unknown): string {
  if (typeof detail === "string") {
    return detail;
  }

  return JSON.stringify(detail, null, 2);
}

export function ChatPane({
  messages,
  input,
  loading,
  emptyMessage,
  currentTimeMs,
  onInputChange,
  onSubmit,
}: ChatPaneProps) {
  const [liveTimeMs, setLiveTimeMs] = useState(() => Date.now());
  const displayTimeMs = currentTimeMs ?? liveTimeMs;

  useEffect(() => {
    if (!loading || currentTimeMs !== undefined) {
      return;
    }

    setLiveTimeMs(Date.now());
    const intervalId = window.setInterval(() => {
      setLiveTimeMs(Date.now());
    }, 500);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [currentTimeMs, loading]);

  const submitMessage = () => {
    if (loading || input.trim().length === 0) {
      return;
    }
    onSubmit();
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    submitMessage();
  };

  const handleInputKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      event.key !== "Enter" ||
      event.shiftKey ||
      event.nativeEvent.isComposing
    ) {
      return;
    }

    event.preventDefault();
    submitMessage();
  };

  return (
    <section className="chat-pane" aria-label="对话窗口">
      <div className="chat-header">
        <div>
          <p className="eyebrow">对话控制台</p>
          {emptyMessage && <p className="chat-intro">{emptyMessage}</p>}
        </div>
        <span className="chat-status">{loading ? "思考中" : "就绪"}</span>
      </div>

      <div className="message-list">
        {messages.map((message) => {
          const processEvents = (message.processEvents ?? []).filter(
            isVisibleProcessEvent,
          );
          const latestProcessEvent = processEvents[processEvents.length - 1];
          const latestPendingEventId =
            loading &&
            latestProcessEvent !== undefined &&
            latestProcessEvent.elapsedMs === undefined
              ? latestProcessEvent.id
              : undefined;

          return (
            <article
              className={`message-bubble message-${message.role}`}
              key={message.id}
            >
                <span className="message-role">{ROLE_LABELS[message.role]}</span>
                <p>{message.content}</p>
                {message.statusText && (
                  <p className="message-status">{message.statusText}</p>
                )}
                {message.reasoning && (
                  <details className="reasoning-panel">
                    <summary>思考摘要</summary>
                    <pre>{message.reasoning}</pre>
                  </details>
                )}
                {processEvents.length > 0 && (
                  <details className="process-panel">
                    <summary>处理过程</summary>
                    <div className="process-round-list">
                      {groupProcessEvents(processEvents).map((group) => (
                        <details className="process-round" key={group.key}>
                          <summary>
                            {group.label}
                            <span>{group.events.length} 个事件</span>
                          </summary>
                          <ol>
                            {group.events.map((event) => {
                              const elapsedLabel = processElapsedLabel(
                                event,
                                latestPendingEventId,
                                displayTimeMs,
                              );

                              return (
                                <li key={event.id}>
                                  <div className="process-event-heading">
                                    <span>{event.label}</span>
                                    {elapsedLabel && (
                                      <span className="process-elapsed">
                                        {elapsedLabel}
                                      </span>
                                    )}
                                  </div>
                                  {event.detail !== undefined && (
                                    <details className="process-event-detail">
                                      <summary>
                                        {event.detailLabel ?? "查看详情"}
                                      </summary>
                                      <pre>{formatProcessDetail(event.detail)}</pre>
                                    </details>
                                  )}
                                </li>
                              );
                            })}
                          </ol>
                        </details>
                      ))}
                    </div>
                  </details>
                )}
                {message.error && (
                  <p className="message-error">{message.error}</p>
                )}
            </article>
          );
        })}
      </div>

      <form className="chat-form" onSubmit={handleSubmit}>
        <textarea
          aria-label="输入消息"
          disabled={loading}
          onChange={(event) => onInputChange(event.target.value)}
          onKeyDown={handleInputKeyDown}
          placeholder="例如：把客厅摄像头转向门口"
          rows={3}
          value={input}
        />
        <button disabled={loading || input.trim().length === 0} type="submit">
          {loading ? "发送中..." : "发送"}
        </button>
      </form>
    </section>
  );
}
