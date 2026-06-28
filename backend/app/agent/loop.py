import json
from time import perf_counter
from typing import Any, Dict, Iterator, List, Optional

from pydantic import BaseModel, ValidationError

from app.agent.context import ContextBuilder
from app.agent.events import (
    ARCHITECTURE_STEPS,
    architecture_status_event,
    error_event,
    history_trimmed_event,
    model_input_event,
    model_output_event,
    redact_sensitive_text,
)
from app.agent.finalizers import (
    build_tool_final_message,
    can_finish_after_tool,
)
from app.agent.policy import PolicyGuard
from app.agent.schemas import (
    AgentFinalAnswer,
    AgentToolCall,
    ChatMessage,
    ChatResponse,
    IotState,
    ToolEvent,
    VideoSearchResult,
)
from app.agent.structured_output import (
    AgentStepValidationError,
    validate_agent_step,
)
from app.agent.tool_registry import (
    ToolRegistry,
    extract_iot_state,
    extract_video_results,
)
from app.core.config import get_settings
from app.model.ark_sdk_client import ArkSDKError


class AgentLoop:
    max_steps = 3

    def __init__(
        self,
        model_client: Any,
        tool_registry: Optional[ToolRegistry] = None,
        context_builder: Optional[ContextBuilder] = None,
        policy_guard: Optional[PolicyGuard] = None,
    ) -> None:
        settings = get_settings()
        self.model_client = model_client
        self.tool_registry = tool_registry or ToolRegistry()
        self.context_builder = context_builder or ContextBuilder(
            max_history_messages=settings.agent_history_max_messages
        )
        self.policy_guard = policy_guard or PolicyGuard()

    def run(
        self,
        conversation_id: str,
        history: List[ChatMessage],
        user_message: str,
    ) -> ChatResponse:
        iot_state = IotState()
        video_results = []  # type: List[VideoSearchResult]
        tool_events = []  # type: List[ToolEvent]

        for event in self.iter_agent_events(
            conversation_id=conversation_id,
            history=history,
            user_message=user_message,
            stream_final_answer=False,
        ):
            if event.get("type") == "tool_result":
                iot_state = IotState(**event.get("iot_state", {}))
                video_results = [
                    VideoSearchResult(**item)
                    for item in event.get("video_results", [])
                ]
                tool_events.append(ToolEvent(**event["event"]))
                continue

            if event.get("type") == "final" and isinstance(
                event.get("response"), dict
            ):
                return ChatResponse(**event["response"])

            if event.get("type") == "error":
                return self._error_response(
                    conversation_id,
                    str(event.get("code") or "AGENT_LOOP_ERROR"),
                    str(event.get("message") or "Unknown agent loop error"),
                    iot_state,
                    video_results,
                    tool_events,
                )

        return ChatResponse(
            conversation_id=conversation_id,
            assistant_message=(
                "我已经尝试处理你的请求，但还没有得到稳定的最终回答。"
                "请稍后重试，或换一种方式描述需求。"
            ),
            iot_state=iot_state,
            video_results=video_results,
            tool_events=tool_events,
        )

    def run_stream(
        self,
        conversation_id: str,
        history: List[ChatMessage],
        user_message: str,
        debug: bool = True,
    ) -> Iterator[Dict[str, Any]]:
        yield from self.iter_agent_events(
            conversation_id=conversation_id,
            history=history,
            user_message=user_message,
            stream_final_answer=True,
            debug=debug,
        )

    def iter_agent_events(
        self,
        conversation_id: str,
        history: List[ChatMessage],
        user_message: str,
        stream_final_answer: bool = True,
        debug: bool = True,
    ) -> Iterator[Dict[str, Any]]:
        yield {"type": "session", "conversation_id": conversation_id}

        model_round = 0
        yield self._architecture_status_event(
            "01",
            "user_intent",
            "已接收用户目标：{}".format(self._preview(user_message)),
        )
        policy_decision = self.policy_guard.evaluate(user_message, history)
        yield self.policy_guard.to_event(policy_decision)
        if policy_decision.action in ("refuse", "clarify"):
            yield self._architecture_status_event(
                "07",
                "final_response",
                "已由后端确定性策略生成{}。".format(
                    "拒绝回复"
                    if policy_decision.action == "refuse"
                    else "澄清问题"
                ),
            )
            response = ChatResponse(
                conversation_id=conversation_id,
                assistant_message=policy_decision.answer,
                iot_state=IotState(),
                video_results=[],
                tool_events=[],
            )
            if stream_final_answer and policy_decision.answer:
                yield {"type": "answer_delta", "delta": policy_decision.answer}
            yield self._architecture_status_event(
                "08",
                "frontend_observable",
                "策略判断、最终回复和业务状态已准备返回前端展示。",
            )
            yield {
                "type": "final",
                "response": self._jsonable(response),
                "elapsed_ms": 0,
            }
            yield {"type": "done"}
            return

        context_started_at = perf_counter()
        trim_result = self.context_builder.trim_model_history(history)
        if trim_result.was_trimmed:
            yield history_trimmed_event(
                trim_result.original_count,
                trim_result.kept_count,
                trim_result.dropped_count,
            )
        messages = self.context_builder.build_initial_messages(
            trim_result.messages,
            user_message,
            route_hints=policy_decision.route_hints,
        )
        context_elapsed_ms = self._elapsed_ms(context_started_at)
        yield self._architecture_status_event(
            "02",
            "context_packing",
            "已打包系统角色、工具说明、{} 条历史消息和当前用户消息。".format(
                len(trim_result.messages)
            ),
            elapsed_ms=context_elapsed_ms,
        )
        iot_state = IotState()
        video_results = []  # type: List[VideoSearchResult]
        tool_events = []  # type: List[ToolEvent]

        try:
            for step in range(1, self.max_steps + 1):
                step_result = yield from self._generate_valid_agent_step(
                    messages,
                    policy_decision,
                    user_message,
                    step,
                    model_round + 1,
                )
                raw_step = step_result["raw_step"]
                decision_elapsed_ms = step_result["elapsed_ms"]
                decision_model_round = step_result["model_round"]
                model_round = decision_model_round
                step_type = raw_step.get("type")

                if step_type == "tool_call":
                    tool_call = AgentToolCall(**raw_step)
                    yield self._architecture_status_event(
                        "04",
                        "action_protocol",
                        "模型按 JSON 协议选择调用工具：{}。".format(
                            tool_call.tool_name
                        ),
                        step,
                        model_round=decision_model_round,
                    )
                    yield {
                        "type": "tool_call",
                        "step": step,
                        "model_round": decision_model_round,
                        "tool_name": tool_call.tool_name,
                        "arguments": self._jsonable(tool_call.arguments),
                        "reason": tool_call.reason,
                        "elapsed_ms": decision_elapsed_ms,
                    }

                    yield self._architecture_status_event(
                        "05",
                        "tool_execution",
                        "后端正在执行白名单工具：{}。".format(
                            tool_call.tool_name
                        ),
                        step,
                        model_round=decision_model_round,
                    )
                    result, event = self.tool_registry.run(
                        tool_call.tool_name,
                        tool_call.arguments,
                        step,
                    )
                    tool_events.append(event)

                    if tool_call.tool_name == "iot_control":
                        iot_state = extract_iot_state(result)
                    elif tool_call.tool_name == "video_search":
                        video_results = extract_video_results(result)

                    yield {
                        "type": "tool_result",
                        "step": step,
                        "model_round": decision_model_round,
                        "tool_name": tool_call.tool_name,
                        "event": self._jsonable(event),
                        "elapsed_ms": event.elapsed_ms,
                        "iot_state": self._jsonable(iot_state),
                        "video_results": self._jsonable(video_results),
                    }
                    observation_started_at = perf_counter()
                    self._append_tool_observation(messages, tool_call, result, event)
                    observation_elapsed_ms = self._elapsed_ms(observation_started_at)
                    yield self._architecture_status_event(
                        "06",
                        "observation_feedback",
                        "已将 {} 的执行结果作为 observation 回填给模型，状态：{}。".format(
                            tool_call.tool_name,
                            event.status,
                        ),
                        step,
                        model_round=decision_model_round,
                        elapsed_ms=observation_elapsed_ms,
                    )
                    if self._can_finish_after_tool(tool_call, event):
                        assistant_message = self._build_tool_final_message(
                            tool_call,
                            iot_state,
                            video_results,
                            event,
                        )
                        yield self._architecture_status_event(
                            "07",
                            "final_response",
                            "已基于工具执行结果生成最终回复。",
                            step,
                            model_round=decision_model_round,
                        )
                        response = ChatResponse(
                            conversation_id=conversation_id,
                            assistant_message=assistant_message,
                            iot_state=iot_state,
                            video_results=video_results,
                            tool_events=tool_events,
                        )
                        yield self._architecture_status_event(
                            "08",
                            "frontend_observable",
                            "完整处理轨迹、最终回复和业务状态已准备返回前端展示。",
                            step,
                            model_round=decision_model_round,
                        )
                        yield {
                            "type": "final",
                            "step": step,
                            "model_round": decision_model_round,
                            "response": self._jsonable(response),
                            "elapsed_ms": 0,
                        }
                        yield {"type": "done"}
                        return
                    continue

                if step_type == "final_answer":
                    final_answer = AgentFinalAnswer(**raw_step)
                    yield self._architecture_status_event(
                        "04",
                        "action_protocol",
                        "模型按 JSON 协议选择 final_answer，本轮无需新的工具调用。",
                        step,
                        model_round=decision_model_round,
                    )
                    yield self._architecture_status_event(
                        "05",
                        "tool_execution_skipped",
                        "无需调用外部工具，跳过工具能力层。",
                        step,
                        model_round=decision_model_round,
                    )
                    yield self._architecture_status_event(
                        "06",
                        "observation_skipped",
                        "没有新的工具 observation，沿用当前上下文和已有工具结果。",
                        step,
                        model_round=decision_model_round,
                    )

                    yield self._architecture_status_event(
                        "07",
                        "final_response",
                        "已基于结构化决策生成最终回答。",
                        step,
                        model_round=decision_model_round,
                    )

                    assistant_message = final_answer.answer
                    final_elapsed_ms = 0
                    if stream_final_answer and assistant_message:
                        yield {
                            "type": "answer_delta",
                            "delta": assistant_message,
                        }

                    response = ChatResponse(
                        conversation_id=conversation_id,
                        assistant_message=assistant_message,
                        iot_state=iot_state,
                        video_results=video_results,
                        tool_events=tool_events,
                    )
                    yield self._architecture_status_event(
                        "08",
                        "frontend_observable",
                        "完整处理轨迹、最终回复和业务状态已准备返回前端展示。",
                        step,
                        model_round=decision_model_round,
                    )
                    yield {
                        "type": "final",
                        "step": step,
                        "model_round": decision_model_round,
                        "response": self._jsonable(response),
                        "elapsed_ms": final_elapsed_ms,
                    }
                    yield {"type": "done"}
                    return

                yield self._error_event(
                    "MODEL_VALIDATION_ERROR",
                    "Model output type must be final_answer or tool_call",
                )
                yield {"type": "done"}
                return

            response = ChatResponse(
                conversation_id=conversation_id,
                assistant_message=(
                    "我已经尝试处理你的请求，但还没有得到稳定的最终回答。"
                    "请稍后重试，或换一种方式描述需求。"
                ),
                iot_state=iot_state,
                video_results=video_results,
                tool_events=tool_events,
            )
            yield {"type": "final", "response": self._jsonable(response)}
            yield {"type": "done"}
        except (ValidationError, AgentStepValidationError) as exc:
            yield self._error_event("MODEL_VALIDATION_ERROR", str(exc))
            yield {"type": "done"}
        except ArkSDKError as exc:
            yield self._error_event(exc.code, str(exc))
            yield {"type": "done"}

    def _architecture_status_event(
        self,
        architecture_step_id: str,
        status: str,
        message: str,
        step: Optional[int] = None,
        model_round: Optional[int] = None,
        elapsed_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        return architecture_status_event(
            architecture_step_id,
            status,
            message,
            step=step,
            model_round=model_round,
            elapsed_ms=elapsed_ms,
        )

    def _model_input_event(
        self,
        model_round: int,
        phase: str,
        schema_name: str,
        messages: List[ChatMessage],
        step: int,
    ) -> Dict[str, Any]:
        return model_input_event(
            model_round,
            phase,
            schema_name,
            messages,
            step,
            self._jsonable,
        )

    def _model_output_event(
        self,
        model_round: int,
        phase: str,
        output: Any,
        elapsed_ms: int,
        step: int,
    ) -> Dict[str, Any]:
        return model_output_event(
            model_round,
            phase,
            output,
            elapsed_ms,
            step,
            self._jsonable,
        )

    def _generate_valid_agent_step(
        self,
        messages: List[ChatMessage],
        policy_decision: Any,
        user_message: str,
        step: int,
        initial_model_round: int,
    ) -> Iterator[Dict[str, Any]]:
        model_round = initial_model_round
        retry_error = None  # type: Optional[Dict[str, str]]

        for attempt in range(2):
            attempt_messages = messages
            if attempt > 0:
                attempt_messages = self._build_protocol_retry_messages(
                    messages,
                    retry_error or {},
                )
                yield self._architecture_status_event(
                    "03",
                    "model_protocol_retry",
                    "模型输出不符合 agent_step JSON 协议，正在进行第 1 次修正重试。",
                    step,
                    model_round=model_round,
                )

            yield self._architecture_status_event(
                "03",
                "model_decision",
                "正在分析意图并选择下一步动作...",
                step,
                model_round=model_round,
            )
            yield self._model_input_event(
                model_round,
                "decision",
                "agent_step",
                attempt_messages,
                step,
            )

            decision_started_at = perf_counter()
            try:
                raw_step = self.model_client.generate_json(
                    attempt_messages,
                    schema_name="agent_step",
                )
            except ArkSDKError as exc:
                if attempt == 0 and self._is_retryable_protocol_error(exc):
                    retry_error = self._protocol_error_payload(
                        exc.code,
                        str(exc),
                        getattr(exc, "stderr", None),
                    )
                    model_round += 1
                    continue
                raise

            decision_elapsed_ms = self._elapsed_ms(decision_started_at)
            raw_step = self._apply_policy_tool_fallback(
                raw_step,
                policy_decision,
                user_message,
                step,
            )

            try:
                validated_step = validate_agent_step(raw_step)
            except (ValidationError, AgentStepValidationError) as exc:
                yield self._model_output_event(
                    model_round,
                    "decision",
                    raw_step,
                    decision_elapsed_ms,
                    step,
                )
                if attempt == 0 and self._is_retryable_protocol_error(exc):
                    retry_error = self._protocol_error_payload(
                        "MODEL_VALIDATION_ERROR",
                        str(exc),
                        self._to_json(self._jsonable(raw_step)),
                    )
                    model_round += 1
                    continue
                raise

            yield self._model_output_event(
                model_round,
                "decision",
                validated_step,
                decision_elapsed_ms,
                step,
            )
            return {
                "raw_step": validated_step,
                "elapsed_ms": decision_elapsed_ms,
                "model_round": model_round,
            }

        raise AgentStepValidationError("Model output failed protocol retry")

    def _build_protocol_retry_messages(
        self,
        messages: List[ChatMessage],
        retry_error: Dict[str, str],
    ) -> List[ChatMessage]:
        code = retry_error.get("code") or "MODEL_VALIDATION_ERROR"
        message = redact_sensitive_text(
            retry_error.get("message") or "模型输出不符合 JSON 协议"
        )
        raw_output = self._preview(
            redact_sensitive_text(retry_error.get("raw_output") or ""),
            limit=240,
        )
        correction = (
            "上一轮模型输出违反 agent_step JSON 协议，错误码：{code}。"
            "错误摘要：{message}。"
            "请只重新输出一个合法 JSON object，不要输出 Markdown 或解释文字。"
            "合法 type 只能是 tool_call 或 final_answer；"
            "tool_call 的 tool_name 只能是 web_search、video_search、iot_control；"
            "final_answer 必须包含 answer 和 iot_action。"
        ).format(code=code, message=message)
        if raw_output:
            correction = "{} 原始输出预览：{}。".format(correction, raw_output)

        return list(messages) + [ChatMessage(role="user", content=correction)]

    def _is_retryable_protocol_error(self, error: Any) -> bool:
        if isinstance(error, ArkSDKError):
            return error.code == "MODEL_JSON_PARSE_FAILED"
        return isinstance(error, (ValidationError, AgentStepValidationError))

    def _protocol_error_payload(
        self,
        code: str,
        message: str,
        raw_output: Optional[str] = None,
    ) -> Dict[str, str]:
        payload = {
            "code": code,
            "message": redact_sensitive_text(message),
        }
        if raw_output:
            payload["raw_output"] = redact_sensitive_text(raw_output)
        return payload

    def _build_initial_messages(
        self,
        history: List[ChatMessage],
        user_message: str,
    ) -> List[ChatMessage]:
        return self.context_builder.build_initial_messages(history, user_message)

    def _model_history_messages(
        self,
        history: List[ChatMessage],
    ) -> List[ChatMessage]:
        return self.context_builder.model_history_messages(history)

    def _is_model_history_message(self, message: ChatMessage) -> bool:
        return message in self.context_builder.model_history_messages([message])

    def _append_tool_observation(
        self,
        messages: List[ChatMessage],
        tool_call: AgentToolCall,
        result: Any,
        event: ToolEvent,
    ) -> None:
        messages.append(
            ChatMessage(
                role="assistant",
                content=self._to_json(self._model_to_dict(tool_call)),
            )
        )
        messages.append(
            ChatMessage(
                role="tool",
                content=self._to_json(
                    {
                        "tool_name": tool_call.tool_name,
                        "status": event.status,
                        "result": self._jsonable(result),
                        "event": self._jsonable(event),
                    }
                ),
            )
        )

    def _can_finish_after_tool(
        self,
        tool_call: AgentToolCall,
        event: ToolEvent,
    ) -> bool:
        return (
            can_finish_after_tool(tool_call, event)
        )

    def _apply_policy_tool_fallback(
        self,
        raw_step: Dict[str, Any],
        policy_decision: Any,
        user_message: str,
        step: int,
    ) -> Dict[str, Any]:
        if step != 1:
            return raw_step
        if raw_step.get("type") != "final_answer":
            return raw_step
        if not self._has_route_hint(policy_decision, "video_search"):
            return raw_step

        tool_call = AgentToolCall(
            tool_name="video_search",
            arguments={
                "query": self._video_search_query_from_message(user_message),
                "limit": 10,
            },
            reason="后端策略识别为视频检索请求，使用用户查询触发 video_search。",
        )
        return self._model_to_dict(tool_call)

    def _has_route_hint(self, policy_decision: Any, tool_name: str) -> bool:
        route_hints = getattr(policy_decision, "route_hints", [])
        return any(tool_name in hint for hint in route_hints)

    def _video_search_query_from_message(self, text: str) -> str:
        query = " ".join(str(text or "").split())
        if not query:
            return ""

        for prefix in (
            "请帮我搜索",
            "请帮我查找",
            "请帮我查看",
            "请帮我查",
            "请帮我找",
            "帮我搜索",
            "帮我查找",
            "帮我查看",
            "帮我查",
            "帮我找",
            "给我搜索",
            "给我查找",
            "给我查看",
            "给我查",
            "给我找",
            "搜索",
            "查找",
            "查看",
            "查一下",
            "找一下",
            "检索",
            "搜",
            "查",
            "找",
        ):
            if query.startswith(prefix):
                query = query[len(prefix):].strip()
                break

        for suffix in (
            "相关的视频片段",
            "相关视频片段",
            "相关的视频",
            "相关录像",
            "相关视频",
            "的视频片段",
            "的录像",
            "的监控",
            "的视频",
            "视频片段",
            "录像片段",
            "监控片段",
            "视频",
            "录像",
            "监控",
            "片段",
            "回放",
            "画面",
        ):
            if query.endswith(suffix):
                query = query[:-len(suffix)].strip()
                break

        for filler in ("相关", "一下"):
            query = query.replace(filler, "").strip()
        return query or " ".join(str(text or "").split())

    def _build_tool_final_message(
        self,
        tool_call: AgentToolCall,
        iot_state: IotState,
        video_results: List[VideoSearchResult],
        event: ToolEvent,
    ) -> str:
        return build_tool_final_message(tool_call, iot_state, video_results, event)

    def _build_video_search_message(
        self,
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
                    self._video_result_summary(item.f_text),
                )
            )
        return "\n".join(lines)

    def _video_result_summary(self, text: str, limit: int = 96) -> str:
        parts = [
            part.strip()
            for part in str(text or "").split(";")
            if part.strip()
        ]
        summary = parts[1] if len(parts) > 1 else (parts[0] if parts else "无描述")
        if len(summary) <= limit:
            return summary
        return "{}...".format(summary[:limit])

    def _iot_target_label(self, target: Optional[str]) -> str:
        labels = {
            "left": "左侧",
            "right": "右侧",
            "front_door": "门口",
            "balcony": "阳台",
            "window": "窗户",
            "garage": "车库",
            "garage_entrance": "车库入口",
        }
        if not target:
            return "目标方向"
        return labels.get(target, target)

    def _error_event(self, code: str, message: str) -> Dict[str, str]:
        return error_event(code, message)

    def _error_response(
        self,
        conversation_id: str,
        code: str,
        message: str,
        iot_state: IotState,
        video_results: List[VideoSearchResult],
        tool_events: List[ToolEvent],
    ) -> ChatResponse:
        return ChatResponse(
            conversation_id=conversation_id,
            assistant_message="模型处理请求时出现问题：{}".format(
                redact_sensitive_text(message)
            ),
            iot_state=iot_state,
            video_results=video_results,
            tool_events=tool_events,
            error={"code": code, "message": redact_sensitive_text(message)},
        )

    def _to_json(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    def _jsonable(self, value: Any) -> Any:
        if isinstance(value, BaseModel):
            return self._model_to_dict(value)
        if isinstance(value, list):
            return [self._jsonable(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): self._jsonable(item)
                for key, item in value.items()
            }
        return value

    def _model_to_dict(self, value: BaseModel) -> Dict[str, Any]:
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return value.dict()

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, round((perf_counter() - started_at) * 1000))

    def _preview(self, text: str, limit: int = 48) -> str:
        normalized = " ".join(str(text or "").split())
        if len(normalized) <= limit:
            return normalized
        return "{}...".format(normalized[:limit])
