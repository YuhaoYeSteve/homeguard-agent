import type { IotState } from "../types";
import { deriveIotPanelView, IOT_PANEL_TAGS } from "./iotPanelView";

interface IotPanelProps {
  modelId: string | null;
  state: IotState;
  systemPrompt: string | null;
  systemPromptError: string | null;
}

export function IotPanel({
  modelId,
  state,
  systemPrompt,
  systemPromptError,
}: IotPanelProps) {
  const view = deriveIotPanelView(state);

  return (
    <aside className="iot-pane">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">JSON 驱动</p>
          <h2>IoT 输出面板</h2>
        </div>
        <span className={`device-status device-status-${state.status}`}>
          {state.status}
        </span>
      </div>

      <div
        className={`camera-preview camera-motion-${view.motion}`}
        aria-label="摄像头模拟预览"
      >
        <div className="wall-mount" />
        <div className="camera-head">
          <div className="mount-arm" />
          <div className="scan-cone" />
          <div className="camera-body">
            <div className="camera-face">
              <div className="camera-lens">
                <div className="camera-glint" />
              </div>
              <span className="privacy-shutter" />
              <span className="status-light" />
            </div>
          </div>
        </div>
        <span className="motion-caption">{view.motionLabel}</span>
      </div>

      <div className="state-buttons" aria-label="摄像头状态">
        {IOT_PANEL_TAGS.map((tag) => (
          <button
            aria-pressed={view.activeTag === tag.key}
            className={`state-button ${
              view.activeTag === tag.key ? "active" : ""
            }`}
            key={tag.key}
            type="button"
          >
            <span className="state-lamp" />
            {tag.label}
          </button>
        ))}
      </div>

      <details className="iot-json-panel">
        <summary>结构化 JSON</summary>
        <pre className="json-box">{JSON.stringify(state, null, 2)}</pre>
      </details>

      <section className="system-prompt-panel" aria-label="应用系统提示词">
        <div className="system-prompt-heading">
          <div>
            <p className="eyebrow">Agent Prompt</p>
            <h3>System Prompt</h3>
            <p className="system-model-id">
              <span>Model ID</span>
              <code>{modelId ?? "正在加载模型信息..."}</code>
            </p>
          </div>
          <span>debug</span>
        </div>
        {systemPromptError ? (
          <p className="system-prompt-error">
            System Prompt 加载失败：{systemPromptError}
          </p>
        ) : (
          <pre className="system-prompt-box">
            {systemPrompt ?? "正在加载系统提示词..."}
          </pre>
        )}
      </section>
    </aside>
  );
}
