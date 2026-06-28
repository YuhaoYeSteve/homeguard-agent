export function canCreateSession(_state: { isStreaming: boolean }): boolean {
  return true;
}

export function canSelectSession(_state: { isStreaming: boolean }): boolean {
  return true;
}

export function canDeleteSession(state: {
  sessionCount: number;
  sessionId: string;
  streamingSessionId: string | null;
}): boolean {
  if (state.sessionCount <= 1) {
    return false;
  }

  return state.sessionId !== state.streamingSessionId;
}
