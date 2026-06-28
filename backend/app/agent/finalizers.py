from typing import Any, Dict, List, Optional

from app.agent.schemas import AgentToolCall, IotState, ToolEvent, VideoSearchResult


def can_finish_after_tool(tool_call: AgentToolCall, event: ToolEvent) -> bool:
    return False


def build_tool_final_message(
    tool_call: AgentToolCall,
    iot_state: IotState,
    video_results: List[VideoSearchResult],
    event: ToolEvent,
) -> str:
    if tool_call.tool_name == "video_search":
        return _build_video_search_message(video_results)
    if tool_call.tool_name == "web_search":
        return _build_web_search_message(event)
    if tool_call.tool_name != "iot_control":
        return "工具已执行完成。"

    if event.status != "success":
        return "IoT 模拟控制没有执行成功，请检查指令后重试。"

    target = _iot_target_label(iot_state.target)
    if iot_state.iot_action == "move":
        return "已完成模拟控制：摄像头已转向{}。".format(target)
    if iot_state.iot_action == "privacy_mask":
        return "已完成模拟控制：摄像头已开启隐私遮蔽。"
    if iot_state.target == "camera_on":
        return "已完成模拟控制：摄像头画面已恢复。"
    return "已完成 IoT 模拟控制。"


def _build_web_search_message(event: ToolEvent) -> str:
    output = event.output if isinstance(event.output, dict) else {}
    provider = str(output.get("provider") or "联网搜索")
    if event.status != "success":
        error = output.get("error") or "搜索服务暂不可用"
        return "联网搜索暂不可用（{}）：{}。".format(provider, error)

    results = output.get("results")
    if not isinstance(results, list) or not results:
        return "联网搜索完成，但没有检索到可展示的结果。"

    lines = [
        "联网搜索完成（{}），找到 {} 条结果：".format(
            provider,
            len(results),
        )
    ]
    for index, item in enumerate(results[:3], start=1):
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("title")) or "未命名结果"
        snippet = _clean_text(item.get("snippet"))
        url = _clean_text(item.get("url"))
        line = "{}. {}".format(index, title)
        if snippet:
            line = "{}：{}".format(line, snippet)
        if url:
            line = "{}（{}）".format(line, url)
        lines.append(line)
    return "\n".join(lines)


def _build_video_search_message(
    video_results: List[VideoSearchResult],
) -> str:
    if not video_results:
        return "没有检索到匹配的视频片段。"

    lines = [
        "已检索到 {} 条相关视频，优先展示前 {} 条：".format(
            len(video_results),
            min(5, len(video_results)),
        )
    ]
    for index, item in enumerate(video_results[:5], start=1):
        lines.append(
            "{}. {}：{}".format(
                index,
                item.f_id,
                _video_result_summary(item.f_text),
            )
        )
    return "\n".join(lines)


def _video_result_summary(text: str, limit: int = 96) -> str:
    parts = [
        part.strip()
        for part in str(text or "").split(";")
        if part.strip()
    ]
    summary = parts[1] if len(parts) > 1 else (parts[0] if parts else "无描述")
    if len(summary) <= limit:
        return summary
    return "{}...".format(summary[:limit])


def _iot_target_label(target: Optional[str]) -> str:
    labels = {
        "left": "左侧",
        "right": "右侧",
        "front_door": "门口",
        "balcony": "阳台",
        "window": "窗户",
        "garage": "车库",
        "camera_on": "摄像头画面",
    }
    if not target:
        return "目标方向"
    return labels.get(target, target)


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())
