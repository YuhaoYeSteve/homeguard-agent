import { renderToStaticMarkup } from "react-dom/server";

import { ChatPane } from "./ChatPane";
import type { Message } from "../types";

function assertIncludes(actual: string, expected: string, message: string) {
  if (!actual.includes(expected)) {
    throw new Error(`${message}: expected markup to include ${expected}`);
  }
}

function assertNotIncludes(actual: string, unexpected: string, message: string) {
  if (actual.includes(unexpected)) {
    throw new Error(`${message}: expected markup not to include ${unexpected}`);
  }
}

const messages: Message[] = [
  {
    id: "msg_assistant",
    role: "assistant",
    content: "处理中",
    createdAt: 1,
    processEvents: [
      {
        id: "process_1",
        type: "status",
        label: "01 用户意图：已接收用户目标",
        createdAt: 1,
      },
      {
        id: "process_2",
        type: "model_input",
        label: "模型输入：决策",
        detailLabel: "查看模型输入",
        detail: {
          schema_name: "agent_step",
          messages: [{ role: "user", content: "你好" }],
        },
        modelRound: 1,
        createdAt: 1_000,
      },
      {
        id: "process_3",
        type: "model_output",
        label: "模型输出：final_answer",
        detailLabel: "查看模型输出",
        detail: {
          type: "final_answer",
          answer: "你好",
        },
        modelRound: 1,
        elapsedMs: 120,
        createdAt: 3,
      },
      {
        id: "process_5",
        type: "status",
        label:
          "08 前端可观测：完整处理轨迹、最终回复和业务状态已准备返回前端展示。",
        modelRound: 2,
        elapsedMs: 48_280,
        createdAt: 3_000,
      },
      {
        id: "process_4",
        type: "model_input",
        label: "模型输入：决策",
        detailLabel: "查看模型输入",
        detail: {
          schema_name: "agent_step",
          messages: [{ role: "user", content: "查一下今天北京天气" }],
        },
        modelRound: 2,
        createdAt: 1_000,
      },
    ],
  },
] as Message[];

const markup = renderToStaticMarkup(
  <ChatPane
    currentTimeMs={3_500}
    input=""
    loading={true}
    messages={messages}
    onInputChange={() => undefined}
    onSubmit={() => undefined}
  />,
);

assertIncludes(
  markup,
  '<details class="process-panel">',
  "process panel should render as a collapsible details element",
);
assertNotIncludes(
  markup,
  '<details class="process-panel" open="">',
  "process panel should be collapsed by default",
);
assertIncludes(
  markup,
  '<details class="process-round">',
  "process events should be grouped in collapsible round sections",
);
assertNotIncludes(
  markup,
  '<details class="process-round" open="">',
  "process round sections should be collapsed by default",
);
assertIncludes(
  markup,
  "准备阶段",
  "events without a model round should be grouped under preparation",
);
assertIncludes(
  markup,
  "模型调用轮次 1",
  "model events should show the model call round",
);
assertNotIncludes(
  markup,
  "查看原始事件 JSON",
  "status events should not force a generic JSON disclosure",
);
assertIncludes(
  markup,
  "查看模型输入",
  "model input should have a dedicated raw input disclosure",
);
assertIncludes(
  markup,
  "查看模型输出",
  "model output should have a dedicated raw output disclosure",
);
assertIncludes(
  markup,
  "耗时 120ms",
  "completed model outputs should show their measured duration",
);
assertIncludes(
  markup,
  "进行中 2.50s",
  "latest pending model events should show live elapsed time",
);
assertNotIncludes(
  markup,
  "前端可观测",
  "frontend observability status should not render in the visible process log",
);
