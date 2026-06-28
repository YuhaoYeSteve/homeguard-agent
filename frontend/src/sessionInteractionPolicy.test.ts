import {
  canCreateSession,
  canDeleteSession,
  canSelectSession,
} from "./sessionInteractionPolicy";

function assertEqual<T>(actual: T, expected: T, message: string) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${String(expected)}, got ${String(actual)}`);
  }
}

assertEqual(
  canCreateSession({ isStreaming: true }),
  true,
  "streaming should not block creating a new session",
);

assertEqual(
  canSelectSession({ isStreaming: true }),
  true,
  "streaming should not block switching sessions",
);

assertEqual(
  canDeleteSession({
    sessionCount: 3,
    sessionId: "conv_streaming",
    streamingSessionId: "conv_streaming",
  }),
  false,
  "the streaming session cannot be deleted",
);

assertEqual(
  canDeleteSession({
    sessionCount: 3,
    sessionId: "conv_other",
    streamingSessionId: "conv_streaming",
  }),
  true,
  "non-streaming sessions can be deleted while another session streams",
);

assertEqual(
  canDeleteSession({
    sessionCount: 1,
    sessionId: "conv_only",
    streamingSessionId: null,
  }),
  false,
  "the final remaining session cannot be deleted",
);
