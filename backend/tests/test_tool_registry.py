from types import SimpleNamespace

from app.agent.schemas import IotState, VideoSearchResult
from app.agent.tool_registry import (
    ToolRegistry,
    extract_iot_state,
    extract_video_results,
)
import app.tools.web_search as web_search_module
from app.tools.web_search import WebSearchTool


def test_tool_registry_calls_iot_control_move():
    result, event = ToolRegistry().run(
        "iot_control",
        {"device_id": "camera_living_room", "action": "move", "target": "front_door"},
        step=2,
    )

    assert isinstance(result, IotState)
    assert result.iot_action == "move"
    assert result.target == "front_door"
    assert event.tool_name == "iot_control"
    assert event.status == "success"


def test_tool_registry_unknown_tool_returns_failed_event():
    result, event = ToolRegistry().run("missing_tool", {"query": "x"}, step=3)

    assert result == {}
    assert event.status == "failed"
    assert event.output == {"error": "unknown tool: missing_tool"}
    assert event.input["tool_name"] == "missing_tool"


def test_extract_iot_state_returns_iot_state_or_default():
    state = IotState(iot_action="privacy_mask", status="simulated_success")

    assert extract_iot_state(state) is state
    assert extract_iot_state({"iot_action": "move"}).iot_action == "none"


def test_extract_video_results_returns_video_results_or_empty():
    results = [VideoSearchResult(f_id="clip_1", f_text="有人经过")]

    assert extract_video_results(results) == results
    assert extract_video_results([{"f_id": "clip_1"}]) == []
    assert extract_video_results({"results": []}) == []


def test_web_search_empty_query_fails_without_network(monkeypatch):
    tool = WebSearchTool()

    def fail_if_called(query, top_k, timeout):
        raise AssertionError("network search should not be called for empty query")

    monkeypatch.setattr(tool, "_search_duckduckgo", fail_if_called)

    output, event = tool.run({"query": "   ", "top_k": 3}, step=4)

    assert output == {"results": [], "error": "query is required"}
    assert event.tool_name == "web_search"
    assert event.status == "failed"


def test_web_search_disabled_is_skipped_without_network(monkeypatch):
    tool = WebSearchTool()
    monkeypatch.setattr(
        web_search_module,
        "get_settings",
        lambda: SimpleNamespace(
            web_search_enabled=False,
            web_search_timeout_seconds=1,
        ),
    )

    def fail_if_called(query, top_k, timeout):
        raise AssertionError("network search should not be called when disabled")

    monkeypatch.setattr(tool, "_search_duckduckgo", fail_if_called)

    output, event = tool.run({"query": "today news", "top_k": 3}, step=5)

    assert output == {"results": [], "error": "web search disabled"}
    assert event.status == "skipped"


def test_web_search_falls_back_to_bing_when_duckduckgo_unreachable(monkeypatch):
    tool = WebSearchTool()
    monkeypatch.setattr(
        web_search_module,
        "get_settings",
        lambda: SimpleNamespace(
            web_search_enabled=True,
            web_search_timeout_seconds=1,
        ),
    )
    calls = []

    def duckduckgo_unreachable(query, top_k, timeout):
        calls.append(("duckduckgo", query, top_k, timeout))
        return {
            "results": [],
            "error": "[Errno 65] No route to host",
            "provider": "duckduckgo",
        }

    def bing_success(query, top_k, timeout):
        calls.append(("bing", query, top_k, timeout))
        return {
            "results": [
                {
                    "title": "今日要闻",
                    "snippet": "今日新闻摘要。",
                    "url": "https://example.com/news",
                }
            ],
            "provider": "bing",
        }

    monkeypatch.setattr(tool, "_search_duckduckgo", duckduckgo_unreachable)
    monkeypatch.setattr(tool, "_search_bing", bing_success, raising=False)

    output, event = tool.run({"query": "今天新闻", "top_k": 5}, step=6)

    assert output == {
        "results": [
            {
                "title": "今日要闻",
                "snippet": "今日新闻摘要。",
                "url": "https://example.com/news",
            }
        ],
        "provider": "bing",
        "fallback_errors": {"duckduckgo": "[Errno 65] No route to host"},
    }
    assert event.status == "success"
    assert calls == [
        ("duckduckgo", "今天新闻", 5, 1),
        ("bing", "今天新闻", 5, 1),
    ]


def test_web_search_uses_weather_provider_for_weather_query(monkeypatch):
    tool = WebSearchTool()
    monkeypatch.setattr(
        web_search_module,
        "get_settings",
        lambda: SimpleNamespace(
            web_search_enabled=True,
            web_search_timeout_seconds=1,
        ),
    )
    calls = []

    def weather_success(query, timeout):
        calls.append(("weather", query, timeout))
        return {
            "results": [
                {
                    "title": "上海实时天气",
                    "snippet": "2026-06-26 上海：晴，当前 27℃。",
                    "url": "https://wttr.in/Shanghai",
                }
            ],
            "provider": "wttr",
        }

    def fail_if_called(query, top_k, timeout):
        raise AssertionError("weather query should not call generic search first")

    monkeypatch.setattr(tool, "_search_weather", weather_success, raising=False)
    monkeypatch.setattr(tool, "_search_duckduckgo", fail_if_called)
    monkeypatch.setattr(tool, "_search_bing", fail_if_called, raising=False)

    output, event = tool.run({"query": "今天天气怎么样", "top_k": 5}, step=7)

    assert output["provider"] == "wttr"
    assert output["results"][0]["title"] == "上海实时天气"
    assert event.status == "success"
    assert calls == [("weather", "今天天气怎么样", 1)]


def test_web_search_uses_weather_provider_for_temperature_query(monkeypatch):
    tool = WebSearchTool()
    monkeypatch.setattr(
        web_search_module,
        "get_settings",
        lambda: SimpleNamespace(
            web_search_enabled=True,
            web_search_timeout_seconds=1,
        ),
    )
    calls = []

    def weather_success(query, timeout):
        calls.append(("weather", query, timeout))
        return {
            "results": [
                {
                    "title": "上海实时天气",
                    "snippet": "2026-06-28 上海：多云，当前 29℃。",
                    "url": "https://wttr.in/Shanghai",
                }
            ],
            "provider": "wttr",
        }

    def fail_if_called(query, top_k, timeout):
        raise AssertionError("temperature query should use weather provider")

    monkeypatch.setattr(tool, "_search_weather", weather_success, raising=False)
    monkeypatch.setattr(tool, "_search_duckduckgo", fail_if_called)
    monkeypatch.setattr(tool, "_search_bing", fail_if_called, raising=False)

    output, event = tool.run({"query": "上海的温度是什么？", "top_k": 5}, step=8)

    assert output["provider"] == "wttr"
    assert event.status == "success"
    assert calls == [("weather", "上海的温度是什么？", 1)]


def test_weather_location_from_temperature_query_uses_city_only():
    assert WebSearchTool._weather_location_from_query("上海的温度是什么？") == "上海"
    assert WebSearchTool._weather_location_from_query("上海今天气温如何") == "上海"
    assert WebSearchTool._weather_location_from_query("现在北京天气怎么样") == "北京"
    assert WebSearchTool._weather_location_from_query("深圳现在多少度") == "深圳"


def test_parse_weather_result_builds_current_weather_summary():
    data = {
        "current_condition": [
            {
                "temp_C": "27",
                "FeelsLikeC": "29",
                "humidity": "66",
                "weatherDesc": [{"value": "Partly Cloudy"}],
                "windspeedKmph": "14",
            }
        ],
        "nearest_area": [
            {
                "areaName": [{"value": "Pootung"}],
                "region": [{"value": "Shanghai"}],
                "country": [{"value": "China"}],
            }
        ],
        "weather": [
            {
                "date": "2026-06-26",
                "mintempC": "23",
                "maxtempC": "30",
            }
        ],
    }

    output = WebSearchTool()._parse_weather_result(data, location_query="")

    assert output == {
        "results": [
            {
                "title": "Shanghai Pootung 实时天气",
                "snippet": (
                    "2026-06-26 Shanghai Pootung：Partly Cloudy，"
                    "当前 27℃，体感 29℃，湿度 66%，风速 14 km/h，今日 23-30℃。"
                ),
                "url": "https://wttr.in/",
            }
        ],
        "provider": "wttr",
    }


def test_weather_location_label_skips_redundant_area_suffix():
    assert WebSearchTool._join_unique(["Shanghai", "Shanghaishih"]) == "Shanghai"
    assert WebSearchTool._join_unique(["Beijing", "Beijing"]) == "Beijing"
    assert WebSearchTool._join_unique(["Shanghai", "Pootung"]) == "Shanghai Pootung"


def test_parse_bing_results_extracts_titles_snippets_and_urls():
    html_doc = """
    <html><body>
      <li class="b_algo">
        <h2><a href="https://example.com/weather">北京天气预报</a></h2>
        <p>北京今日晴，气温 26 到 34 摄氏度。</p>
      </li>
      <li class="b_algo">
        <h2><a href="https://example.com/hourly">逐小时天气</a></h2>
        <p>未来 24 小时天气趋势。</p>
      </li>
    </body></html>
    """

    results = WebSearchTool()._parse_bing_results(html_doc, top_k=1)

    assert results == [
        {
            "title": "北京天气预报",
            "snippet": "北京今日晴，气温 26 到 34 摄氏度。",
            "url": "https://example.com/weather",
        }
    ]
