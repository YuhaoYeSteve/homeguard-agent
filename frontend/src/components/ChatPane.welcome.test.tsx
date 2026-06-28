import { renderToStaticMarkup } from "react-dom/server";

import { ChatPane } from "./ChatPane";

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

const welcomeMessage =
  "你好，我是 HomeGuard Agent，可以帮你查视频、联网搜索，也可以模拟控制摄像头。";

const markup = renderToStaticMarkup(
  <ChatPane
    emptyMessage={welcomeMessage}
    input=""
    loading={false}
    messages={[]}
    onInputChange={() => undefined}
    onSubmit={() => undefined}
  />,
);

assertIncludes(
  markup,
  '<p class="chat-intro">',
  "empty-session welcome should render as a header intro",
);
assertIncludes(
  markup,
  welcomeMessage,
  "empty-session welcome should remain visible",
);
assertNotIncludes(
  markup,
  'aria-label="欢迎语"',
  "empty-session welcome should not render as a chat message",
);
assertNotIncludes(
  markup,
  "多轮对话",
  "capability tags should not render in the chat header",
);
assertNotIncludes(
  markup,
  "<h2",
  "chat header should not render a large session heading",
);
