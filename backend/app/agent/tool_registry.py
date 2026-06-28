import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any, Dict, List, Optional, Tuple

from app.agent.schemas import IotState, ToolEvent, VideoSearchResult
from app.core.config import get_settings
from app.tools.iot_control import IotControlTool
from app.tools.viking_video_search import VikingVideoSearchTool
from app.tools.web_search import WebSearchTool


class ToolRegistry:
    def __init__(self, timeout_seconds: Optional[float] = None) -> None:
        settings = get_settings()
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.agent_tool_timeout_seconds
        )
        self.tools = {
            IotControlTool.name: IotControlTool(),
            WebSearchTool.name: WebSearchTool(),
            VikingVideoSearchTool.name: VikingVideoSearchTool(),
        }

    def run(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        step: int,
    ) -> Tuple[Any, ToolEvent]:
        tool = self.tools.get(tool_name)
        if tool is None:
            return {}, ToolEvent(
                step=step,
                tool_name="final_answer",
                input={"tool_name": tool_name, "arguments": arguments},
                output={"error": "unknown tool: {}".format(tool_name)},
                status="failed",
                elapsed_ms=0,
            )

        started_at = time.monotonic()
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(tool.run, arguments, step)
            return future.result(timeout=self.timeout_seconds)
        except TimeoutError:
            return {}, ToolEvent(
                step=step,
                tool_name=tool_name,
                input=arguments,
                output={
                    "error": "tool timed out after {} seconds".format(
                        self.timeout_seconds
                    )
                },
                status="failed",
                elapsed_ms=int((time.monotonic() - started_at) * 1000),
            )
        except Exception as exc:
            return {}, ToolEvent(
                step=step,
                tool_name=tool_name,
                input=arguments,
                output={"error": str(exc)},
                status="failed",
                elapsed_ms=int((time.monotonic() - started_at) * 1000),
            )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)


def extract_iot_state(result: Any) -> IotState:
    if isinstance(result, IotState):
        return result
    return IotState()


def extract_video_results(result: Any) -> List[VideoSearchResult]:
    if isinstance(result, list) and all(isinstance(item, VideoSearchResult) for item in result):
        return result
    return []
