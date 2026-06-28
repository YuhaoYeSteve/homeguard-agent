import type { ChatSession } from "../types";

interface SessionSidebarProps {
  sessions: ChatSession[];
  activeSessionId: string;
  onCreateSession: () => void;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
}

export function SessionSidebar({
  sessions,
  activeSessionId,
  onCreateSession,
  onSelectSession,
  onDeleteSession,
}: SessionSidebarProps) {
  return (
    <aside className="session-sidebar" aria-label="对话会话">
      <div className="sidebar-brand">
        <p className="brand-kicker">Home Security AI</p>
        <h1>HomeGuard Agent</h1>
      </div>

      <button
        className="new-session-button"
        onClick={onCreateSession}
        type="button"
      >
        新对话
      </button>

      <nav className="session-list" aria-label="历史对话">
        {sessions.map((session) => {
          const isActive = session.id === activeSessionId;

          return (
            <div
              className={`session-item ${isActive ? "active" : ""}`}
              key={session.id}
            >
              <button
                aria-current={isActive ? "page" : undefined}
                className="session-select-button"
                onClick={() => onSelectSession(session.id)}
                type="button"
              >
                <span className="session-title">{session.title}</span>
                <span className="session-meta">
                  {session.messages.length} 条消息
                </span>
              </button>

              {sessions.length > 1 && (
                <button
                  aria-label={`删除对话：${session.title}`}
                  className="session-delete-button"
                  onClick={(event) => {
                    event.stopPropagation();
                    onDeleteSession(session.id);
                  }}
                  type="button"
                >
                  删除
                </button>
              )}
            </div>
          );
        })}
      </nav>
    </aside>
  );
}
