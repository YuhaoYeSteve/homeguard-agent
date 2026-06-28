from types import SimpleNamespace

import pytest

import app.tools.viking_video_search as viking_module
from app.tools.viking_video_search import VikingVideoSearchTool


def test_parse_results_maps_fake_viking_response_to_video_results():
    data = {
        "code": "Success",
        "result": {
            "data": [
                {
                    "id": "fallback_id",
                    "fields": {"f_id": "clip_1", "f_text": "有人从门口经过"},
                    "score": 0.91,
                    "ann_score": 0.73,
                },
                {
                    "id": "clip_2",
                    "fields": {"f_text": "车辆停在车库前"},
                    "score": 0.82,
                },
                {
                    "fields": {"f_text": "缺少 ID 的结果应跳过"},
                    "score": 0.1,
                },
            ]
        },
    }

    results = VikingVideoSearchTool()._parse_results(data)

    assert len(results) == 2
    assert results[0].f_id == "clip_1"
    assert results[0].f_text == "有人从门口经过"
    assert results[0].search_score == 0.91
    assert results[0].ann_score == 0.73
    assert results[1].f_id == "clip_2"
    assert results[1].f_text == "车辆停在车库前"
    assert results[1].search_score == 0.82
    assert results[1].ann_score is None


def test_parse_results_maps_official_viking_fields_to_video_results():
    data = {
        "code": "Success",
        "result": {
            "data": [
                {
                    "id": "fallback_id",
                    "fields": {
                        "__AUTO_ID__": "auto_1",
                        "title_desc_obj_event": "门口有人经过",
                        "video_id": "video_123",
                    },
                    "score": 0.95,
                    "ann_score": 0.88,
                }
            ]
        },
    }

    results = VikingVideoSearchTool()._parse_results(data)

    assert len(results) == 1
    assert results[0].f_id == "video_123"
    assert results[0].f_text == "门口有人经过"
    assert results[0].search_score == 0.95
    assert results[0].ann_score == 0.88
    assert results[0].metadata == {
        "auto_id": "auto_1",
        "video_id": "video_123",
    }


def test_search_builds_request_body_from_official_viking_config(monkeypatch):
    captured = {}
    fake_request = SimpleNamespace(
        method="POST",
        path="/api/vikingdb/data/search/multi_modal",
        headers={},
        body="{}",
    )

    monkeypatch.setattr(
        viking_module,
        "get_settings",
        lambda: SimpleNamespace(
            vikingdb_ak="ak",
            vikingdb_sk="sk",
            vikingdb_host="api-vikingdb.vikingdb.ap-southeast-1.bytepluses.com",
            vikingdb_project_name="default",
            vikingdb_collection_name="yingshi_bp",
            vikingdb_index_name="yingshi_bp_index",
            vikingdb_region="ap-southeast-1",
        ),
    )

    tool = VikingVideoSearchTool()

    def fake_prepare_request(ak, sk, host, region, body):
        captured["ak"] = ak
        captured["sk"] = sk
        captured["host"] = host
        captured["region"] = region
        captured["body"] = body
        return fake_request

    class FakeResponse:
        status_code = 200
        text = '{"code":"Success","result":{"data":[]}}'

        @staticmethod
        def json():
            return {"code": "Success", "result": {"data": []}}

    monkeypatch.setattr(tool, "_prepare_request", fake_prepare_request)
    monkeypatch.setattr(viking_module.requests, "request", lambda **kwargs: FakeResponse())

    assert tool.search("门口有人经过", limit=99) == []
    assert captured == {
        "ak": "ak",
        "sk": "sk",
        "host": "api-vikingdb.vikingdb.ap-southeast-1.bytepluses.com",
        "region": "ap-southeast-1",
        "body": {
            "collection_name": "yingshi_bp",
            "index_name": "yingshi_bp_index",
            "project_name": "default",
            "text": "门口有人经过",
            "instruction": {"auto_fill": True},
            "output_fields": ["__AUTO_ID__", "title_desc_obj_event", "video_id"],
            "limit": 50,
        },
    }


def test_prepare_request_serializes_unicode_body_as_latin1_safe_ascii():
    request = VikingVideoSearchTool()._prepare_request(
        ak="ak",
        sk="sk",
        host="api-vikingdb.vikingdb.ap-southeast-1.bytepluses.com",
        region="ap-southeast-1",
        body={"text": "门口有人经过"},
    )

    request.body.encode("latin-1")
    assert "门口有人经过" not in request.body
    assert "\\u95e8" in request.body


def test_search_empty_query_returns_empty_without_request(monkeypatch):
    tool = VikingVideoSearchTool()

    def fail_if_called(ak, sk, host, body):
        raise AssertionError("VikingDB request should not be prepared for empty query")

    monkeypatch.setattr(tool, "_prepare_request", fail_if_called)

    assert tool.search("   ", limit=10) == []


def test_search_non_empty_query_requires_ak_sk(monkeypatch):
    monkeypatch.setattr(
        viking_module,
        "get_settings",
        lambda: SimpleNamespace(
            vikingdb_ak="",
            vikingdb_sk="",
            vikingdb_host="example.com",
            vikingdb_collection_name="collection",
            vikingdb_index_name="index",
        ),
    )

    with pytest.raises(RuntimeError, match="VikingDB AK/SK 未配置"):
        VikingVideoSearchTool().search("有人经过", limit=5)
