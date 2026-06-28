import json
from typing import Any, Dict, Iterator, List, Optional

from app.agent.schemas import ChatMessage
from app.agent.structured_output import get_response_format
from app.core.config import get_settings


REASONING_EFFORTS = {"minimal", "low", "medium", "high"}


class ArkSDKError(RuntimeError):
    def __init__(self, code: str, message: str, stderr: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.stderr = stderr


class ArkSDKModelClient:
    def __init__(
        self,
        ark_api_key: Optional[str] = None,
        ark_base_url: Optional[str] = None,
        ark_model: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        ark_timeout_seconds: Optional[float] = None,
        ark_max_retries: Optional[int] = None,
        client: Optional[Any] = None,
    ):
        settings = get_settings()
        self.ark_api_key = (
            ark_api_key if ark_api_key is not None else settings.ark_api_key
        )
        self.ark_base_url = (
            ark_base_url if ark_base_url is not None else settings.ark_base_url
        )
        self.ark_model = ark_model if ark_model is not None else settings.ark_model
        self.reasoning_effort = (
            reasoning_effort
            if reasoning_effort is not None
            else settings.ark_reasoning_effort
        )
        self.ark_timeout_seconds = (
            ark_timeout_seconds
            if ark_timeout_seconds is not None
            else settings.agent_model_timeout_seconds
        )
        self.ark_max_retries = (
            ark_max_retries
            if ark_max_retries is not None
            else settings.ark_max_retries
        )
        self._client = client

    def generate_json(
        self, messages: List[ChatMessage], schema_name: str = "agent_step"
    ) -> Dict[str, Any]:
        client = self._client_or_create()
        kwargs = {
            "model": self.ark_model,
            "input": self._to_responses_input(messages, schema_name),
            "text": {"format": get_response_format(schema_name)},
        }
        reasoning = self._build_reasoning()
        if reasoning:
            kwargs["reasoning"] = reasoning

        try:
            response = client.responses.create(**kwargs)
        except ArkSDKError:
            raise
        except Exception as exc:
            if self._is_timeout_error(exc):
                raise ArkSDKError(
                    "ARK_SDK_TIMEOUT",
                    "Ark SDK request timed out",
                    stderr=str(exc),
                ) from exc
            raise ArkSDKError(
                "ARK_SDK_FAILED",
                "Ark SDK request failed",
                stderr=str(exc),
            ) from exc

        return self._parse_json(self._extract_response_text(response))

    def stream_text(self, messages: List[ChatMessage]) -> Iterator[Dict[str, Any]]:
        client = self._client_or_create()
        kwargs = {
            "model": self.ark_model,
            "input": self._to_responses_input(messages, "text"),
            "stream": True,
        }
        reasoning = self._build_reasoning()
        if reasoning:
            kwargs["reasoning"] = reasoning

        try:
            stream = client.responses.create(**kwargs)
            for chunk in self._iter_stream(stream):
                event = self._map_stream_chunk(chunk)
                if event is not None:
                    yield event
        except ArkSDKError:
            raise
        except Exception as exc:
            if self._is_timeout_error(exc):
                raise ArkSDKError(
                    "ARK_SDK_TIMEOUT",
                    "Ark SDK stream request timed out",
                    stderr=str(exc),
                ) from exc
            raise ArkSDKError(
                "ARK_SDK_FAILED",
                "Ark SDK stream request failed",
                stderr=str(exc),
            ) from exc

    def _client_or_create(self) -> Any:
        if self._client is not None:
            return self._client

        if not self.ark_api_key:
            raise ArkSDKError(
                "ARK_SDK_NOT_CONFIGURED",
                "Ark SDK API key is not configured",
            )

        try:
            from volcenginesdkarkruntime import Ark
        except ImportError as exc:
            raise ArkSDKError(
                "ARK_SDK_IMPORT_FAILED",
                "Ark SDK runtime package is not installed",
                stderr=str(exc),
            ) from exc

        kwargs = {"api_key": self.ark_api_key}
        if self.ark_base_url:
            kwargs["base_url"] = self.ark_base_url
        if self.ark_timeout_seconds and self.ark_timeout_seconds > 0:
            kwargs["timeout"] = self.ark_timeout_seconds
        if self.ark_max_retries >= 0:
            kwargs["max_retries"] = self.ark_max_retries

        try:
            self._client = Ark(**kwargs)
        except Exception as exc:
            raise ArkSDKError(
                "ARK_SDK_FAILED",
                "Ark SDK client initialization failed",
                stderr=str(exc),
            ) from exc

        return self._client

    def _format_messages(
        self, messages: List[ChatMessage], schema_name: str = "agent_step"
    ) -> str:
        payload = {
            "schema_name": schema_name,
            "messages": [self._message_to_dict(message) for message in messages],
        }
        return json.dumps(payload, ensure_ascii=False)

    def _to_responses_input(
        self, messages: List[ChatMessage], schema_name: str = "agent_step"
    ) -> List[Dict[str, str]]:
        return [
            {
                "role": "user",
                "content": self._format_messages(messages, schema_name),
            }
        ]

    def _build_reasoning(self) -> Dict[str, str]:
        if not self.reasoning_effort:
            return {}
        if self.reasoning_effort not in REASONING_EFFORTS:
            raise ArkSDKError(
                "ARK_SDK_INVALID_REASONING_EFFORT",
                "Invalid Ark reasoning effort: {}".format(self.reasoning_effort),
            )
        return {"effort": self.reasoning_effort}

    def _iter_stream(self, stream: Any) -> Iterator[Any]:
        if hasattr(stream, "__enter__") and hasattr(stream, "__exit__"):
            with stream:
                yield from stream
            return

        try:
            yield from stream
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()

    def _map_stream_chunk(self, chunk: Any) -> Optional[Dict[str, Any]]:
        chunk_type = self._get_value(chunk, "type")
        delta = self._get_value(chunk, "delta")

        if chunk_type == "response.output_text.delta" and delta is not None:
            return {"type": "answer_delta", "delta": delta}

        if (
            chunk_type == "response.reasoning_summary_text.delta"
            and delta is not None
        ):
            return {"type": "reasoning_delta", "delta": delta}

        if chunk_type == "response.completed":
            response = self._get_value(chunk, "response") or chunk
            event: Dict[str, Any] = {"type": "model_meta"}
            model = self._get_value(response, "model")
            usage = self._to_plain_data(self._get_value(response, "usage"))
            if model is not None:
                event["model"] = model
            if usage is not None:
                event["usage"] = usage
            return event

        if chunk_type == "response.incomplete":
            response = self._get_value(chunk, "response")
            details = self._get_value(response, "incomplete_details")
            reason = self._get_value(details, "reason") or "unknown"
            return {
                "type": "error",
                "code": "ARK_SDK_INCOMPLETE",
                "message": "Ark response incomplete: {}".format(reason),
            }

        if chunk_type in ("response.failed", "error"):
            error = self._get_value(chunk, "error")
            response = self._get_value(chunk, "response")
            if error is None and response is not None:
                error = self._get_value(response, "error")
            if error is None:
                error = chunk
            code = self._get_value(error, "code") or chunk_type
            message = self._get_value(error, "message") or str(error)
            return {"type": "error", "code": code, "message": message}

        return None

    def _extract_response_text(self, response: Any) -> str:
        output_text = self._get_value(response, "output_text")
        if isinstance(output_text, str):
            return output_text

        fragments = []  # type: List[str]
        output = self._get_value(response, "output")
        if isinstance(output, list):
            for item in output:
                content = self._get_value(item, "content")
                if not isinstance(content, list):
                    continue
                for content_item in content:
                    text = self._get_value(content_item, "text")
                    if isinstance(text, str):
                        fragments.append(text)

        return "".join(fragments)

    def _parse_json(self, raw: str) -> Dict[str, Any]:
        text = self._strip_json_fence(raw)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ArkSDKError(
                "MODEL_JSON_PARSE_FAILED",
                "Model output is not valid JSON",
                stderr=raw,
            ) from exc

        if not isinstance(parsed, dict):
            raise ArkSDKError(
                "MODEL_JSON_PARSE_FAILED",
                "Model output JSON top-level value must be an object",
                stderr=raw,
            )

        return parsed

    def _strip_json_fence(self, raw: str) -> str:
        text = raw.strip()
        if not text.startswith("```"):
            return text

        lines = text.splitlines()
        if len(lines) >= 2 and lines[0].strip().lower() in ("```json", "```"):
            if lines[-1].strip() == "```":
                return "\n".join(lines[1:-1]).strip()
        return text

    def _message_to_dict(self, message: ChatMessage) -> Dict[str, str]:
        if hasattr(message, "model_dump"):
            data = message.model_dump()
        else:
            data = message.dict()
        return {"role": data["role"], "content": data["content"]}

    def _get_value(self, value: Any, key: str) -> Any:
        if isinstance(value, dict):
            return value.get(key)
        return getattr(value, key, None)

    def _to_plain_data(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, list):
            return [self._to_plain_data(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): self._to_plain_data(item)
                for key, item in value.items()
            }
        if hasattr(value, "model_dump"):
            return self._to_plain_data(value.model_dump())
        if hasattr(value, "dict"):
            return self._to_plain_data(value.dict())
        if hasattr(value, "__dict__"):
            return self._to_plain_data(vars(value))
        return str(value)

    def _is_timeout_error(self, exc: Exception) -> bool:
        name = exc.__class__.__name__.lower()
        message = str(exc).lower()
        return (
            isinstance(exc, TimeoutError)
            or "timeout" in name
            or "timed out" in message
            or "timeout" in message
        )
