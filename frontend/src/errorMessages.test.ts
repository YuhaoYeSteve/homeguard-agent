import { formatStreamErrorMessage } from "./errorMessages";

function assertEqual<T>(actual: T, expected: T, message: string) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${String(expected)}, got ${String(actual)}`);
  }
}

assertEqual(
  formatStreamErrorMessage({
    type: "error",
    code: "MODEL_VALIDATION_ERROR",
    message: "模型输出不合法",
  }),
  "MODEL_VALIDATION_ERROR: 模型输出不合法",
  "stream error messages should include stable error codes",
);

assertEqual(
  formatStreamErrorMessage({
    type: "error",
    message: "网络中断",
  }),
  "网络中断",
  "stream error messages without code should keep the original message",
);
