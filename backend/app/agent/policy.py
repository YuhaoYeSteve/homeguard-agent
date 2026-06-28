from typing import List, Literal

from pydantic import BaseModel, Field

from app.agent.schemas import ChatMessage


PolicyAction = Literal["continue", "refuse", "clarify"]


class PolicyDecision(BaseModel):
    action: PolicyAction = "continue"
    category: str = "normal"
    reason: str = ""
    answer: str = ""
    route_hints: List[str] = Field(default_factory=list)


class PolicyGuard:
    def evaluate(
        self,
        user_message: str,
        history: List[ChatMessage],
    ) -> PolicyDecision:
        text = self._normalize(user_message)

        if self._is_prompt_injection(text):
            return PolicyDecision(
                action="refuse",
                category="prompt_injection",
                reason="用户要求忽略规则、泄露提示词或直接输出工具调用 JSON。",
                answer=(
                    "不能执行这类请求：我不能忽略系统规则、泄露系统提示词，"
                    "也不能绕过后端安全校验直接输出或调用设备控制 JSON。"
                ),
            )

        if self._is_dangerous_iot(text):
            return PolicyDecision(
                action="refuse",
                category="dangerous_iot",
                reason="用户请求高危安防控制或破坏记录。",
                answer=(
                    "不能执行这个高风险安防操作。门锁、报警器、录像删除、"
                    "关闭所有摄像头等操作需要明确授权和更严格的安全确认。"
                ),
            )

        if self._is_privacy_violation(text):
            return PolicyDecision(
                action="refuse",
                category="privacy",
                reason="用户请求可能侵犯他人隐私或绕过授权。",
                answer="不能协助进行未经授权的隐私查看或偷偷开启摄像头。请确认设备和被查看对象都已获得授权。",
            )

        if self._is_ambiguous_shutdown(text, history):
            return PolicyDecision(
                action="clarify",
                category="clarification",
                reason="用户要求关闭不明确对象，直接执行会有误控风险。",
                answer="请明确你想关闭哪个设备或功能，例如隐私遮蔽、摄像头画面，还是其他安防设备。",
            )

        route_hints = []
        if self._is_video_search_query(text, history):
            route_hints.append(
                "用户要查监控视频内容，应优先调用 video_search，query 保留用户目标词。"
            )
        elif self._is_realtime_web_query(text):
            route_hints.append(
                "用户询问天气、气温、温度、新闻、预警或近期政策，应优先调用 web_search。"
            )

        return PolicyDecision(
            action="continue",
            category="normal",
            reason="未命中确定性拒绝或澄清策略，继续交给模型做语义决策。",
            route_hints=route_hints,
        )

    def to_event(self, decision: PolicyDecision) -> dict:
        return {
            "type": "policy_decision",
            "action": decision.action,
            "category": decision.category,
            "reason": decision.reason,
            "route_hints": list(decision.route_hints),
            "answer": decision.answer,
        }

    def _normalize(self, text: str) -> str:
        return str(text or "").lower().replace(" ", "")

    def _is_prompt_injection(self, text: str) -> bool:
        return any(
            token in text
            for token in (
                "忽略之前",
                "忽略所有",
                "系统提示词",
                "systemprompt",
                "直接输出",
                "不要解释",
                "tool_name",
                "iot_control",
            )
        ) and any(
            token in text
            for token in (
                "规则",
                "提示词",
                "json",
                "调用",
                "输出",
            )
        )

    def _is_dangerous_iot(self, text: str) -> bool:
        if "门锁" in text and any(token in text for token in ("打开", "解锁", "开锁")):
            return True
        if "报警器" in text and any(token in text for token in ("关", "关闭", "禁用", "停用")):
            return True
        if "删除" in text and any(token in text for token in ("录像", "记录", "视频")):
            return True
        if "所有摄像头" in text and any(token in text for token in ("关", "关闭", "停用")):
            return True
        if "关闭录像" in text:
            return True
        return False

    def _is_privacy_violation(self, text: str) -> bool:
        if "邻居" in text and any(token in text for token in ("谁经过", "查看", "查一下", "门口")):
            return True
        if "偷偷" in text and "摄像头" in text:
            return True
        if "卧室" in text and any(token in text for token in ("偷偷", "不要让", "打开摄像头")):
            return True
        return False

    def _is_ambiguous_shutdown(
        self,
        text: str,
        history: List[ChatMessage],
    ) -> bool:
        if not any(token in text for token in ("把它关", "把这个关", "把那个关", "关了")):
            return False
        if any(token in text for token in ("隐私遮蔽", "摄像头", "画面", "报警器", "门锁")):
            return False
        return not self._history_has_clear_shutdown_target(history)

    def _history_has_clear_shutdown_target(self, history: List[ChatMessage]) -> bool:
        recent_text = "\n".join(message.content for message in history[-4:]).lower()
        return any(token in recent_text for token in ("隐私遮蔽", "摄像头画面"))

    def _is_realtime_web_query(self, text: str) -> bool:
        return any(
            token in text
            for token in (
                "天气",
                "气温",
                "温度",
                "多少度",
                "几度",
                "新闻",
                "预警",
                "近期政策",
                "最近",
                "今天",
                "现在",
            )
        )

    def _is_video_search_query(
        self,
        text: str,
        history: List[ChatMessage],
    ) -> bool:
        if not text:
            return False

        video_tokens = ("视频", "录像", "监控", "片段", "回放", "画面")
        search_tokens = ("搜", "搜索", "查", "查找", "找", "检索", "看看")
        event_tokens = (
            "经过",
            "走过",
            "出现",
            "靠近",
            "进入",
            "离开",
            "移动",
            "跑过",
        )
        subject_tokens = (
            "猫",
            "狗",
            "老鼠",
            "鼠",
            "人",
            "人员",
            "小孩",
            "老人",
            "宠物",
            "快递",
            "车辆",
            "车",
        )

        has_video_token = any(token in text for token in video_tokens)
        has_search_token = any(token in text for token in search_tokens)
        has_event_token = any(token in text for token in event_tokens)
        has_subject_token = any(token in text for token in subject_tokens)

        if has_video_token and (
            has_search_token or has_event_token or has_subject_token
        ):
            return True
        if has_event_token:
            return True
        if has_search_token and has_subject_token:
            return True
        if len(text) <= 8 and has_subject_token:
            return True

        recent_text = "\n".join(message.content for message in history[-4:]).lower()
        return "视频" in recent_text and any(
            token in text for token in subject_tokens
        )
