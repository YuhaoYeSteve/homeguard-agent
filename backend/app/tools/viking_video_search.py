import json
import time
from typing import Any, Dict, List, Tuple

import requests

from app.agent.schemas import ToolEvent, VideoSearchResult
from app.core.config import get_settings


SEARCH_PATH = "/api/vikingdb/data/search/multi_modal"
DEFAULT_SERVICE = "vikingdb"
DEFAULT_REGION = "ap-southeast-1"
DEFAULT_PROJECT_NAME = "default"
OUTPUT_FIELDS = ["__AUTO_ID__", "title_desc_obj_event", "video_id"]


class VikingVideoSearchTool:
    name = "video_search"

    def run(
        self,
        arguments: Dict[str, Any],
        step: int,
    ) -> Tuple[List[VideoSearchResult], ToolEvent]:
        started_at = time.monotonic()
        query = str(arguments.get("query") or "").strip()
        limit = self._coerce_limit(arguments.get("limit", 10))

        try:
            results = self.search(query=query, limit=limit)
            output = {"results": [item.model_dump() for item in results]}
            status = "success"
        except Exception as exc:
            results = []
            output = {"results": [], "error": str(exc)}
            status = "failed"

        event = ToolEvent(
            step=step,
            tool_name=self.name,
            input=arguments,
            output=output,
            status=status,
            elapsed_ms=self._elapsed_ms(started_at),
        )
        return results, event

    def search(self, query: str, limit: int) -> List[VideoSearchResult]:
        query = str(query or "").strip()
        if not query:
            return []

        settings = get_settings()
        if not settings.vikingdb_ak or not settings.vikingdb_sk:
            raise RuntimeError("VikingDB AK/SK 未配置")

        body = {
            "collection_name": settings.vikingdb_collection_name,
            "index_name": settings.vikingdb_index_name,
            "project_name": getattr(settings, "vikingdb_project_name", DEFAULT_PROJECT_NAME),
            "text": query,
            "instruction": {"auto_fill": True},
            "output_fields": OUTPUT_FIELDS,
            "limit": self._coerce_limit(limit),
        }
        request = self._prepare_request(
            settings.vikingdb_ak,
            settings.vikingdb_sk,
            settings.vikingdb_host,
            getattr(settings, "vikingdb_region", DEFAULT_REGION),
            body,
        )
        response = requests.request(
            method=request.method,
            url="https://{}{}".format(settings.vikingdb_host, request.path),
            headers=request.headers,
            data=request.body,
            timeout=30,
        )
        if response.status_code != 200:
            raise RuntimeError(
                "VikingDB search failed: status={}, body={}".format(
                    response.status_code,
                    response.text,
                )
            )

        data = response.json()
        if data.get("code") != "Success":
            raise RuntimeError("VikingDB search api failed: {}".format(response.text))
        return self._parse_results(data)

    def _prepare_request(
        self,
        ak: str,
        sk: str,
        host: str,
        region: str,
        body: Dict[str, Any],
    ) -> Any:
        from volcengine.Credentials import Credentials
        from volcengine.auth.SignerV4 import SignerV4
        from volcengine.base.Request import Request

        request = Request()
        request.set_shema("https")
        request.set_method("POST")
        request.set_connection_timeout(10)
        request.set_socket_timeout(10)
        request.set_headers(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Host": host,
            }
        )
        request.set_host(host)
        request.set_path(SEARCH_PATH)
        request.set_body(json.dumps(body))
        SignerV4.sign(
            request,
            Credentials(ak, sk, DEFAULT_SERVICE, region),
        )
        return request

    def _parse_results(self, data: Dict[str, Any]) -> List[VideoSearchResult]:
        parsed = []
        result = data.get("result") or {}
        rows = result.get("data") or []
        if not isinstance(rows, list):
            return parsed

        for item in rows:
            if not isinstance(item, dict):
                continue
            fields = item.get("fields") or {}
            if not isinstance(fields, dict):
                fields = {}

            auto_id = fields.get("__AUTO_ID__")
            video_id = fields.get("video_id")
            f_id = video_id or fields.get("f_id") or auto_id or item.get("id")
            if not f_id:
                continue

            metadata = {}
            if auto_id:
                metadata["auto_id"] = str(auto_id)
            if video_id:
                metadata["video_id"] = str(video_id)

            parsed.append(
                VideoSearchResult(
                    f_id=str(f_id),
                    f_text=str(fields.get("title_desc_obj_event") or fields.get("f_text") or ""),
                    search_score=item.get("score"),
                    ann_score=item.get("ann_score"),
                    metadata=metadata,
                )
            )
        return parsed

    @staticmethod
    def _coerce_limit(value: Any) -> int:
        try:
            limit = int(value)
        except (TypeError, ValueError):
            return 10
        return max(1, min(limit, 50))

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return int((time.monotonic() - started_at) * 1000)
