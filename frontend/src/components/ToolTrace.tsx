import type { ToolEvent } from "../types";

interface ToolTraceProps {
  events: ToolEvent[];
}

export function ToolTrace({ events }: ToolTraceProps) {
  if (events.length === 0) {
    return null;
  }

  return (
    <details className="tool-trace">
      <summary>工具轨迹（{events.length}）</summary>
      <div className="tool-event-list">
        {events.map((event, index) => (
          <article
            className="tool-event"
            key={`${event.step}-${event.tool_name}-${index}`}
          >
            <div className="tool-event-meta">
              <span>step {event.step}</span>
              <strong>{event.tool_name}</strong>
              <span className={`tool-status tool-status-${event.status}`}>
                {event.status}
              </span>
              <span>{event.elapsed_ms}ms</span>
            </div>
            <div className="tool-event-json">
              <div>
                <span className="json-label">input</span>
                <pre>{JSON.stringify(event.input, null, 2)}</pre>
              </div>
              <div>
                <span className="json-label">output</span>
                <pre>{JSON.stringify(event.output, null, 2)}</pre>
              </div>
            </div>
          </article>
        ))}
      </div>
    </details>
  );
}
