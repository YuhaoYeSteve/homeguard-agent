import time
from typing import Any, Dict, Tuple

from pydantic import ValidationError

from app.agent.schemas import IotControlCommand, IotState, ToolEvent


class IotControlTool:
    name = "iot_control"
    TARGET_ALIASES = {
        "garage_entrance": "garage",
        "garage entrance": "garage",
        "车库入口": "garage",
        "车库": "garage",
        "left_of_front_door": "left",
        "left": "left",
        "左": "left",
        "左侧": "left",
        "right": "right",
        "右": "right",
        "右侧": "right",
        "front door": "front_door",
        "front_door": "front_door",
        "door": "front_door",
        "门口": "front_door",
        "balcony": "balcony",
        "阳台": "balcony",
        "window": "window",
        "窗户": "window",
        "camera_on": "camera_on",
        "摄像头画面": "camera_on",
        "恢复画面": "camera_on",
    }
    MOVE_TARGETS = {"left", "right", "front_door", "balcony", "window", "garage"}

    def run(self, arguments: Dict[str, Any], step: int) -> Tuple[IotState, ToolEvent]:
        started_at = time.monotonic()
        normalized_arguments = dict(arguments)
        validation_error = self._normalize_arguments(normalized_arguments)
        if validation_error:
            elapsed_ms = self._elapsed_ms(started_at)
            state = IotState(
                iot_action="none",
                device_id=normalized_arguments.get("device_id"),
                target=normalized_arguments.get("target"),
                status="validation_failed",
            )
            event = ToolEvent(
                step=step,
                tool_name=self.name,
                input=normalized_arguments,
                output={"error": validation_error},
                status="failed",
                elapsed_ms=elapsed_ms,
            )
            return state, event

        try:
            command = IotControlCommand(**normalized_arguments)
        except ValidationError as exc:
            elapsed_ms = self._elapsed_ms(started_at)
            state = IotState(
                iot_action="none",
                device_id=normalized_arguments.get("device_id"),
                target=normalized_arguments.get("target"),
                status="validation_failed",
            )
            event = ToolEvent(
                step=step,
                tool_name=self.name,
                input=normalized_arguments,
                output={"error": exc.errors()},
                status="failed",
                elapsed_ms=elapsed_ms,
            )
            return state, event

        elapsed_ms = self._elapsed_ms(started_at)
        state = IotState(
            iot_action=command.action,
            device_id=command.device_id,
            target=command.target,
            status="simulated_success",
            raw_command=command,
        )
        event = ToolEvent(
            step=step,
            tool_name=self.name,
            input=normalized_arguments,
            output=state.model_dump(),
            status="success",
            elapsed_ms=elapsed_ms,
        )
        return state, event

    def _normalize_arguments(self, arguments: Dict[str, Any]) -> Any:
        target = arguments.get("target")
        if target is not None:
            normalized_target = self._normalize_target(target)
            if normalized_target is None:
                return [
                    {
                        "loc": ["target"],
                        "msg": "unknown iot target: {}".format(target),
                        "type": "value_error",
                    }
                ]
            arguments["target"] = normalized_target

        action = arguments.get("action")
        normalized_target = arguments.get("target")
        if action == "move" and normalized_target not in self.MOVE_TARGETS:
            return [
                {
                    "loc": ["target"],
                    "msg": "move action requires one of {}".format(
                        sorted(self.MOVE_TARGETS)
                    ),
                    "type": "value_error",
                }
            ]
        if action == "none" and normalized_target not in (None, "camera_on"):
            return [
                {
                    "loc": ["target"],
                    "msg": "none action only supports camera_on target",
                    "type": "value_error",
                }
            ]
        return None

    def _normalize_target(self, target: Any) -> Any:
        key = str(target or "").strip().lower()
        return self.TARGET_ALIASES.get(key)

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return int((time.monotonic() - started_at) * 1000)
