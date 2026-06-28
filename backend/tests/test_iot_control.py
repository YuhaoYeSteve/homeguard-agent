from app.tools.iot_control import IotControlTool
from app.agent.schemas import ChatResponse, IotState
from app.agent.prompts import SYSTEM_PROMPT, TOOL_SPEC


def test_iot_move_returns_move_state():
    state, event = IotControlTool().run(
        {"device_id": "camera_living_room", "action": "move", "target": "front_door"},
        step=1,
    )
    assert state.iot_action == "move"
    assert state.status == "simulated_success"
    assert event.status == "success"


def test_iot_privacy_mask_returns_mask_state():
    state, event = IotControlTool().run(
        {"device_id": "camera_living_room", "action": "privacy_mask"},
        step=1,
    )
    assert state.iot_action == "privacy_mask"
    assert state.status == "simulated_success"
    assert event.status == "success"


def test_iot_none_can_reopen_camera_after_privacy_mask():
    state, event = IotControlTool().run(
        {
            "device_id": "camera_living_room",
            "action": "none",
            "target": "camera_on",
            "reason": "用户要求打开摄像头",
        },
        step=1,
    )

    assert state.iot_action == "none"
    assert state.target == "camera_on"
    assert state.status == "simulated_success"
    assert event.status == "success"


def test_iot_normalizes_alias_target_before_validation():
    state, event = IotControlTool().run(
        {
            "device_id": "camera_living_room",
            "action": "move",
            "target": "garage_entrance",
        },
        step=1,
    )

    assert state.iot_action == "move"
    assert state.target == "garage"
    assert state.raw_command is not None
    assert state.raw_command.target == "garage"
    assert event.input["target"] == "garage"
    assert event.status == "success"


def test_iot_rejects_unknown_move_target():
    state, event = IotControlTool().run(
        {
            "device_id": "camera_living_room",
            "action": "move",
            "target": "left_of_unknown_place",
        },
        step=1,
    )

    assert state.iot_action == "none"
    assert state.status == "validation_failed"
    assert event.status == "failed"


def test_prompt_maps_camera_reopen_to_iot_none_action():
    assert "关闭隐私遮蔽" in SYSTEM_PROMPT
    assert "action=none" in SYSTEM_PROMPT
    assert "move|privacy_mask|none" in TOOL_SPEC
    assert '"tool_name":"video_search"' in SYSTEM_PROMPT
    assert "天气、气温、温度、新闻、预警、近期政策" in SYSTEM_PROMPT
    assert "不得调用工具" in SYSTEM_PROMPT
    assert "left|right|front_door|balcony|window|garage|camera_on" in TOOL_SPEC


def test_iot_invalid_action_is_rejected():
    state, event = IotControlTool().run(
        {"device_id": "camera_living_room", "action": "rotate_fast"},
        step=1,
    )
    assert state.iot_action == "none"
    assert state.status == "validation_failed"
    assert event.status == "failed"


def test_iot_state_has_idle_default():
    state = IotState()
    assert state.iot_action == "none"
    assert state.status == "idle"


def test_chat_response_accepts_assistant_message_text():
    response = ChatResponse(conversation_id="conv_test", assistant_message="好的")
    assert response.assistant_message == "好的"
    assert response.iot_state.iot_action == "none"
