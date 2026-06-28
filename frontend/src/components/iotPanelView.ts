import type { IotState, JsonScalar } from "../types";

export type IotPanelTag = "move_left" | "move_right" | "privacy_mask";
export type IotPanelMotion =
  | "idle"
  | "camera_on"
  | "move_left"
  | "move_right"
  | "move_generic"
  | "privacy_mask";

export interface IotPanelTagItem {
  key: IotPanelTag;
  label: string;
}

export interface IotPanelView {
  activeTag: IotPanelTag | null;
  motion: IotPanelMotion;
  motionLabel: string;
}

export const IOT_PANEL_TAGS: IotPanelTagItem[] = [
  { key: "move_left", label: "左移" },
  { key: "move_right", label: "右移" },
  { key: "privacy_mask", label: "遮蔽" },
];

const DIRECTION_PARAMETER_KEYS = [
  "direction",
  "pan",
  "orientation",
  "position",
  "target",
];

export function deriveIotPanelView(state: IotState): IotPanelView {
  if (state.iot_action === "privacy_mask") {
    return {
      activeTag: "privacy_mask",
      motion: "privacy_mask",
      motionLabel: "隐私遮蔽已开启",
    };
  }

  if (state.iot_action === "move") {
    const directionText = collectDirectionText(state);

    if (hasLeftSignal(directionText)) {
      return {
        activeTag: "move_left",
        motion: "move_left",
        motionLabel: "正在向左移动",
      };
    }

    if (hasRightSignal(directionText)) {
      return {
        activeTag: "move_right",
        motion: "move_right",
        motionLabel: "正在向右移动",
      };
    }

    return {
      activeTag: null,
      motion: "move_generic",
      motionLabel: "正在移动摄像头",
    };
  }

  if (isCameraOnCommand(state)) {
    return {
      activeTag: null,
      motion: "camera_on",
      motionLabel: "摄像头已打开",
    };
  }

  return {
    activeTag: null,
    motion: "idle",
    motionLabel: "等待 IoT 指令",
  };
}

function isCameraOnCommand(state: IotState) {
  if (state.iot_action !== "none" || state.status !== "simulated_success") {
    return false;
  }

  const target = [state.target, state.raw_command?.target]
    .filter(Boolean)
    .map(String)
    .join(" ")
    .toLowerCase();

  return /camera_on|open|unmask|解除|打开|恢复/.test(target);
}

function collectDirectionText(state: IotState) {
  const values: Array<JsonScalar | string | null | undefined> = [
    state.target,
    state.raw_command?.target,
  ];

  const parameters = state.raw_command?.parameters ?? {};
  for (const key of DIRECTION_PARAMETER_KEYS) {
    values.push(parameters[key]);
  }

  return values
    .filter((value): value is JsonScalar | string => value !== null && value !== undefined)
    .map(String)
    .join(" ")
    .toLowerCase();
}

function hasLeftSignal(value: string) {
  return /左|left|west/.test(value);
}

function hasRightSignal(value: string) {
  return /右|right|east/.test(value);
}
