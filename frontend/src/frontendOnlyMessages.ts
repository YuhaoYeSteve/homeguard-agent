import type { Message } from "./types";

export const FRONTEND_ONLY_WELCOME_MESSAGE =
  "你好，我是 HomeGuard Agent，可以帮你查视频、联网搜索，也可以模拟控制摄像头。";

export function isFrontendOnlyMessage(
  message: Pick<Message, "role" | "content">,
): boolean {
  return (
    message.role === "assistant" &&
    message.content.trim() === FRONTEND_ONLY_WELCOME_MESSAGE
  );
}
