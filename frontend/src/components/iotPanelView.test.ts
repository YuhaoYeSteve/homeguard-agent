import type { IotState } from "../types";
import { deriveIotPanelView } from "./iotPanelView";

function assertEqual<T>(actual: T, expected: T, message: string) {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${expected}, got ${actual}`);
  }
}

function createState(state: Partial<IotState>): IotState {
  return {
    iot_action: "none",
    device_id: null,
    target: null,
    status: "idle",
    raw_command: null,
    ...state,
  };
}

const leftMove = deriveIotPanelView(
  createState({
    iot_action: "move",
    target: "向左移动",
    status: "simulated_success",
  }),
);
assertEqual(leftMove.activeTag, "move_left", "left target activates left tag");
assertEqual(leftMove.motion, "move_left", "left target drives left motion");

const rightMove = deriveIotPanelView(
  createState({
    iot_action: "move",
    raw_command: {
      tool: "iot_control",
      device_id: "camera_living_room",
      action: "move",
      target: null,
      parameters: { direction: "right" },
      confidence: 1,
      reason: "用户要求摄像头向右移动",
    },
  }),
);
assertEqual(rightMove.activeTag, "move_right", "right parameter activates right tag");
assertEqual(rightMove.motion, "move_right", "right parameter drives right motion");

const masked = deriveIotPanelView(
  createState({
    iot_action: "privacy_mask",
    status: "simulated_success",
  }),
);
assertEqual(masked.activeTag, "privacy_mask", "privacy action activates mask tag");
assertEqual(masked.motion, "privacy_mask", "privacy action drives mask motion");

const genericMove = deriveIotPanelView(
  createState({
    iot_action: "move",
    target: "front_door",
    status: "simulated_success",
  }),
);
assertEqual(genericMove.activeTag, null, "generic move does not guess left or right");
assertEqual(genericMove.motion, "move_generic", "generic move still has motion feedback");

const cameraOn = deriveIotPanelView(
  createState({
    iot_action: "none",
    status: "simulated_success",
    raw_command: {
      tool: "iot_control",
      device_id: "camera_living_room",
      action: "none",
      target: "camera_on",
      parameters: {},
      confidence: 1,
      reason: "用户要求打开摄像头",
    },
  }),
);
assertEqual(cameraOn.activeTag, null, "camera-on does not activate action tags");
assertEqual(cameraOn.motion, "camera_on", "camera-on drives reopen feedback");
assertEqual(cameraOn.motionLabel, "摄像头已打开", "camera-on label is explicit");
