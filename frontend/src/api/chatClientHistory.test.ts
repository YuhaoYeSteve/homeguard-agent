import { toClientHistory } from "./chatClient";
import type { Message } from "../types";

function assertEqual<T>(actual: T, expected: T, message: string) {
  const actualJson = JSON.stringify(actual);
  const expectedJson = JSON.stringify(expected);

  if (actualJson !== expectedJson) {
    throw new Error(
      `${message}: expected ${expectedJson}, got ${actualJson}`,
    );
  }
}

const frontendOnlyWelcome =
  "你好，我是 HomeGuard Agent，可以帮你查视频、联网搜索，也可以模拟控制摄像头。";

const history: Message[] = [
  {
    id: "msg_welcome",
    role: "assistant",
    content: frontendOnlyWelcome,
    createdAt: 1,
  },
  {
    id: "msg_user",
    role: "user",
    content: "上一轮真实问题",
    createdAt: 2,
  },
  {
    id: "msg_assistant",
    role: "assistant",
    content: "上一轮真实回答",
    createdAt: 3,
  },
  {
    id: "msg_pending",
    role: "assistant",
    content: "   ",
    createdAt: 4,
  },
];

assertEqual(
  toClientHistory(history),
  [
    {
      role: "user",
      content: "上一轮真实问题",
    },
    {
      role: "assistant",
      content: "上一轮真实回答",
    },
  ],
  "frontend-only welcome should not be sent as client history",
);
