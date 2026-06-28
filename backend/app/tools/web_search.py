import time
from html.parser import HTMLParser
from typing import Any, Dict, List, Tuple
from urllib.parse import quote

import httpx

from app.agent.schemas import ToolEvent
from app.core.config import get_settings


class WebSearchTool:
    name = "web_search"

    def run(self, arguments: Dict[str, Any], step: int) -> Tuple[Dict[str, Any], ToolEvent]:
        started_at = time.monotonic()
        settings = get_settings()
        query = str(arguments.get("query") or "").strip()
        top_k = self._coerce_top_k(arguments.get("top_k", 5))

        if not query:
            output = {"results": [], "error": "query is required"}
            status = "failed"
        elif not settings.web_search_enabled:
            output = {"results": [], "error": "web search disabled"}
            status = "skipped"
        else:
            output = self._search_web(
                query,
                top_k,
                settings.web_search_timeout_seconds,
            )
            status = "failed" if output.get("error") else "success"

        event = ToolEvent(
            step=step,
            tool_name=self.name,
            input=arguments,
            output=output,
            status=status,
            elapsed_ms=self._elapsed_ms(started_at),
        )
        return output, event

    def _search_web(
        self,
        query: str,
        top_k: int,
        timeout: int,
    ) -> Dict[str, Any]:
        fallback_errors = {}
        if self._is_weather_query(query):
            output = self._search_weather(query, timeout)
            error = output.get("error")
            if not error:
                return output
            fallback_errors["wttr"] = str(error)

        for provider, search_fn in (
            ("duckduckgo", self._search_duckduckgo),
            ("bing", self._search_bing),
        ):
            output = search_fn(query, top_k, timeout)
            error = output.get("error")
            if error:
                fallback_errors[provider] = str(error)
                continue
            if fallback_errors:
                output["fallback_errors"] = fallback_errors
            return output

        return {
            "results": [],
            "error": "; ".join(
                "{}: {}".format(provider, error)
                for provider, error in fallback_errors.items()
            ),
            "fallback_errors": fallback_errors,
        }

    def _search_duckduckgo(
        self,
        query: str,
        top_k: int,
        timeout: int,
    ) -> Dict[str, Any]:
        try:
            response = httpx.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_html": 1,
                    "skip_disambig": 1,
                },
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            return {"results": [], "error": str(exc), "provider": "duckduckgo"}

        results = self._parse_duckduckgo_results(data, query, top_k)
        return {"results": results, "provider": "duckduckgo"}

    def _search_bing(
        self,
        query: str,
        top_k: int,
        timeout: int,
    ) -> Dict[str, Any]:
        try:
            response = httpx.get(
                "https://cn.bing.com/search",
                params={"q": query},
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0 Safari/537.36"
                    ),
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
                follow_redirects=True,
                timeout=timeout,
            )
            response.raise_for_status()
        except Exception as exc:
            return {"results": [], "error": str(exc), "provider": "bing"}

        results = self._parse_bing_results(response.text, top_k)
        if not results:
            return {"results": [], "error": "bing returned no results", "provider": "bing"}
        return {"results": results, "provider": "bing"}

    def _search_weather(self, query: str, timeout: int) -> Dict[str, Any]:
        location = self._weather_location_from_query(query)
        location_path = quote(location) if location else ""
        url = "https://wttr.in/{}".format(location_path)
        try:
            response = httpx.get(
                url,
                params={"format": "j1", "lang": "zh"},
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0 Safari/537.36"
                    ),
                },
                follow_redirects=True,
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            return {"results": [], "error": str(exc), "provider": "wttr"}
        return self._parse_weather_result(data, location)

    def _parse_duckduckgo_results(
        self,
        data: Dict[str, Any],
        query: str,
        top_k: int,
    ) -> List[Dict[str, str]]:
        results = []
        abstract = str(data.get("AbstractText") or "").strip()
        if abstract:
            results.append(
                {
                    "title": str(data.get("Heading") or query),
                    "snippet": abstract,
                    "url": str(data.get("AbstractURL") or ""),
                }
            )

        for topic in self._iter_related_topics(data.get("RelatedTopics", [])):
            text = str(topic.get("Text") or "").strip()
            if not text:
                continue
            results.append(
                {
                    "title": text[:80],
                    "snippet": text,
                    "url": str(topic.get("FirstURL") or ""),
                }
            )
            if len(results) >= top_k:
                break

        return results[:top_k]

    def _iter_related_topics(self, topics: Any) -> List[Dict[str, Any]]:
        flattened = []
        if not isinstance(topics, list):
            return flattened

        for topic in topics:
            if not isinstance(topic, dict):
                continue
            if isinstance(topic.get("Topics"), list):
                flattened.extend(self._iter_related_topics(topic.get("Topics")))
            else:
                flattened.append(topic)
        return flattened

    def _parse_bing_results(self, html: str, top_k: int) -> List[Dict[str, str]]:
        parser = _BingResultParser(limit=top_k)
        parser.feed(html)
        parser.close()
        return parser.results

    def _parse_weather_result(
        self,
        data: Dict[str, Any],
        location_query: str,
    ) -> Dict[str, Any]:
        current = self._first_item(data.get("current_condition"))
        forecast = self._first_item(data.get("weather"))
        area = self._first_item(data.get("nearest_area"))
        if not current:
            return {"results": [], "error": "weather data missing current condition", "provider": "wttr"}

        area_name = self._nested_text(area, "areaName")
        region = self._nested_text(area, "region")
        location_label = self._join_unique([region, area_name]) or location_query or "当前位置"
        description = (
            self._nested_text(current, "lang_zh")
            or self._nested_text(current, "weatherDesc")
            or "天气状况未知"
        )
        date = str(forecast.get("date") or "").strip() or "今日"
        temp = str(current.get("temp_C") or "").strip()
        feels_like = str(current.get("FeelsLikeC") or "").strip()
        humidity = str(current.get("humidity") or "").strip()
        wind_speed = str(current.get("windspeedKmph") or "").strip()
        min_temp = str(forecast.get("mintempC") or "").strip()
        max_temp = str(forecast.get("maxtempC") or "").strip()

        snippet = (
            "{} {}：{}，当前 {}℃，体感 {}℃，湿度 {}%，风速 {} km/h，今日 {}-{}℃。"
        ).format(
            date,
            location_label,
            description,
            temp or "未知",
            feels_like or "未知",
            humidity or "未知",
            wind_speed or "未知",
            min_temp or "未知",
            max_temp or "未知",
        )
        url = "https://wttr.in/{}".format(quote(location_query)) if location_query else "https://wttr.in/"
        return {
            "results": [
                {
                    "title": "{} 实时天气".format(location_label),
                    "snippet": snippet,
                    "url": url,
                }
            ],
            "provider": "wttr",
        }

    @staticmethod
    def _coerce_top_k(value: Any) -> int:
        try:
            top_k = int(value)
        except (TypeError, ValueError):
            return 5
        return max(1, min(top_k, 10))

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return int((time.monotonic() - started_at) * 1000)

    @staticmethod
    def _is_weather_query(query: str) -> bool:
        normalized = query.lower()
        return any(
            token in normalized
            for token in ("天气", "气温", "温度", "多少度", "几度", "weather")
        )

    @staticmethod
    def _weather_location_from_query(query: str) -> str:
        location = str(query or "").strip()
        for token in (
            "今天天气怎么样",
            "今天的天气怎么样",
            "天气怎么样",
            "天气预报",
            "今天天气",
            "今天的天气",
            "实时天气",
            "今天",
            "今日",
            "现在",
            "当前",
            "实时",
            "当地",
            "气温",
            "温度",
            "天气",
            "多少度",
            "几度",
            "是什么",
            "怎么样",
            "如何",
            "查询",
            "请问",
            "帮我查一下",
            "帮我查",
            "查一下",
            "一下",
            "的",
            "weather",
        ):
            location = location.replace(token, "")
        return location.strip(" \t\r\n，,。.?？!！")

    @staticmethod
    def _first_item(value: Any) -> Dict[str, Any]:
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value[0]
        return {}

    def _nested_text(self, data: Dict[str, Any], key: str) -> str:
        nested = self._first_item(data.get(key))
        return str(nested.get("value") or "").strip()

    @staticmethod
    def _join_unique(parts: List[str]) -> str:
        unique = []
        for part in parts:
            normalized = part.lower().replace(" ", "")
            if not normalized:
                continue
            redundant = False
            for existing in unique:
                existing_normalized = existing.lower().replace(" ", "")
                if (
                    normalized == existing_normalized
                    or normalized.startswith(existing_normalized)
                    or existing_normalized.startswith(normalized)
                ):
                    redundant = True
                    break
            if not redundant:
                unique.append(part)
        return " ".join(unique)


class _BingResultParser(HTMLParser):
    def __init__(self, limit: int) -> None:
        super().__init__(convert_charrefs=True)
        self.limit = limit
        self.results = []  # type: List[Dict[str, str]]
        self._current = None  # type: Any
        self._depth = 0
        self._in_h2 = False
        self._capture = None  # type: Any

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Any]]) -> None:
        attr_map = {name: value for name, value in attrs}
        if self._current is None and tag == "li":
            class_name = str(attr_map.get("class") or "")
            if "b_algo" in class_name.split():
                self._current = {
                    "title": [],
                    "snippet": [],
                    "url": str(attr_map.get("href") or ""),
                }
                self._depth = 1
            return

        if self._current is None:
            return

        self._depth += 1
        if tag == "h2":
            self._in_h2 = True
        elif tag == "a" and self._in_h2:
            href = str(attr_map.get("href") or "").strip()
            if href and not self._current["url"]:
                self._current["url"] = href
            self._capture = "title"
        elif tag == "p":
            self._capture = "snippet"

    def handle_data(self, data: str) -> None:
        if self._current is None or self._capture is None:
            return
        text = data.strip()
        if text:
            self._current[self._capture].append(text)

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return

        if tag == "a" and self._capture == "title":
            self._capture = None
        elif tag == "p" and self._capture == "snippet":
            self._capture = None
        elif tag == "h2":
            self._in_h2 = False

        self._depth -= 1
        if self._depth == 0:
            self._append_current()

    def _append_current(self) -> None:
        title = self._normalize_text(self._current["title"])
        snippet = self._normalize_text(self._current["snippet"])
        url = str(self._current["url"]).strip()
        if title and url and len(self.results) < self.limit:
            self.results.append(
                {
                    "title": title,
                    "snippet": snippet,
                    "url": url,
                }
            )
        self._current = None
        self._depth = 0
        self._in_h2 = False
        self._capture = None

    @staticmethod
    def _normalize_text(parts: List[str]) -> str:
        return " ".join(" ".join(parts).split())
