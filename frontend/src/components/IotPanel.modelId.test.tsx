import { renderToStaticMarkup } from "react-dom/server";

import { IotPanel } from "./IotPanel";
import type { IotState } from "../types";

function assertIncludes(actual: string, expected: string, message: string) {
  if (!actual.includes(expected)) {
    throw new Error(`${message}: expected markup to include ${expected}`);
  }
}

const idleState: IotState = {
  iot_action: "none",
  device_id: null,
  target: null,
  status: "idle",
  raw_command: null,
};

const markup = renderToStaticMarkup(
  <IotPanel
    modelId="ep-m-20260518145505-mt7gb"
    state={idleState}
    systemPrompt="系统提示词"
    systemPromptError={null}
  />,
);

assertIncludes(markup, "Model ID", "model label should render under the title");
assertIncludes(
  markup,
  "ep-m-20260518145505-mt7gb",
  "model id should render below the system prompt title",
);
