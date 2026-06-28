#!/usr/bin/env python3
# Evaluate VikingDB retrieval, rerank, truncation, and threshold grid search on Yingshi q_to_c labels.
import argparse
import html
import json
import logging
import os
import time
from http import HTTPStatus
from pathlib import Path

import dashscope
import pandas as pd
import requests
import voyageai
from volcengine.Credentials import Credentials
from volcengine.auth.SignerV4 import SignerV4
from volcengine.base.Request import Request
from volcengine.viking_knowledgebase import VikingKnowledgeBaseService

DEFAULT_HOST = "api-vikingdb.vikingdb.ap-southeast-1.bytepluses.com"
DEFAULT_SERVICE = "vikingdb"
SEARCH_PATH = "/api/vikingdb/data/search/multi_modal"
AK = ""
SK = ""

DEFAULT_COLLECTION_NAME = "Yingshijy"
DEFAULT_INDEX_NAME = "yingshi_en"
DEFAULT_QUERY_PARQUET = "/Users/bytedance/Yingshi_search/2_en.parquet"
DEFAULT_EXTRA_INFO = "/Users/bytedance/Yingshi_search/extra_info.json"
DEFAULT_OUTPUT_JSON = "/Users/bytedance/Yingshi_search/eval_yingshi_retrieval_rerank_result.json"
DEFAULT_OUTPUT_CSV = "/Users/bytedance/Yingshi_search/eval_yingshi_retrieval_rerank_per_query.csv"
DEFAULT_OUTPUT_HTML = "/Users/bytedance/Yingshi_search/eval_yingshi_retrieval_rerank_visual.html"
DEFAULT_GRID_OUTPUT_CSV = "/Users/bytedance/Yingshi_search/eval_yingshi_threshold_grid.csv"
DEFAULT_GRID_OUTPUT_JSON = "/Users/bytedance/Yingshi_search/eval_yingshi_threshold_grid.json"

RERANK_HOST = "api-knowledgebase.mlp.cn-hongkong.bytepluses.com"
DEFAULT_RERANK_MODEL = "base-multilingual-rerank"
DEFAULT_RERANK_PROVIDER = "volc"
DEFAULT_QWEN_RERANK_MODEL = "qwen3-vl-rerank"
DEFAULT_VOYAGE_RERANK_MODEL = "rerank-2.5"
DEFAULT_KS = (1, 5, 10, 50)
STRATEGIES = (
    ("viking_only", "仅Viking召回"),
    ("viking_rerank", "Viking召回+Rerank"),
    ("viking_rerank_truncate", "Viking召回+Rerank+阈值截断"),
)

LOG = logging.getLogger("eval_yingshi")

class ClientForDataApi:
    def __init__(self, ak, sk, host):
        self.ak = ak
        self.sk = sk
        self.host = host

    def prepare_request(self, method, path, params=None, data=None):
        req = Request()
        req.set_shema("https")
        req.set_method(method)
        req.set_connection_timeout(10)
        req.set_socket_timeout(10)
        req.set_headers({"Accept": "application/json", "Content-Type": "application/json", "Host": self.host})
        if params:
            req.set_query(params)
        req.set_host(self.host)
        req.set_path(path)
        if data is not None:
            req.set_body(json.dumps(data))
        SignerV4.sign(req, Credentials(self.ak, self.sk, DEFAULT_SERVICE, "cn-beijing"))
        return req

    def do_req(self, method, path, body, params=None):
        req = self.prepare_request(method=method, path=path, params=params, data=body)
        return requests.request(
            method=req.method,
            url="http://{}{}".format(self.host, req.path),
            headers=req.headers,
            data=req.body,
            timeout=10000,
        )

def setup_logging(log_level):
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

def truncate_text(text, max_len=260):
    text = str(text)
    if len(text) <= max_len:
        return text
    return f"{text[:max_len]}...<truncated {len(text) - max_len} chars>"

# 读取 q_to_c 标签，并从 parquet 中取 query 的英文 caption 作为检索输入。
def load_eval_data(extra_info_path, query_parquet_path):
    LOG.info("loading labels: %s", extra_info_path)
    with open(extra_info_path, "r", encoding="utf-8") as f:
        q_to_c = json.load(f)["q_to_c"]

    LOG.info("loading query captions: %s", query_parquet_path)
    query_df = pd.read_parquet(query_parquet_path)
    missing_columns = {"uniq_id", "caption"} - set(query_df.columns)
    if missing_columns:
        raise ValueError(f"{query_parquet_path} missing required columns: {sorted(missing_columns)}")

    query_df = query_df[query_df["uniq_id"].astype(str).str.contains("query", na=False)].copy()
    query_df["uniq_id"] = query_df["uniq_id"].astype(str)
    query_df["caption"] = query_df["caption"].fillna("").astype(str).str.strip()
    query_caption = dict(zip(query_df["uniq_id"], query_df["caption"]))

    eval_items = []
    missing_queries = []
    for query_id, corpus_ids in q_to_c.items():
        query_text = query_caption.get(query_id, "")
        if not query_text:
            missing_queries.append(query_id)
            continue
        eval_items.append(
            {
                "query_id": query_id,
                "query_text": query_text,
                "relevant_ids": sorted(set(map(str, corpus_ids))),
            }
        )

    if missing_queries:
        LOG.warning("missing query captions, skipped: %s", missing_queries)
    LOG.info("prepared eval queries: count=%s", len(eval_items))
    return eval_items

# 调 VikingDB multi_modal search，保留 f_id/f_text/score 供后续评估与可视化。
def search_vikingdb(client, collection_name, index_name, query_text, limit):
    req_body = {
        "collection_name": collection_name,
        "index_name": index_name,
        "text": query_text,
        "instruction": {"auto_fill": True},
        "output_fields": ["f_id", "f_text"],
        "limit": limit,
    }
    result = client.do_req(method="POST", path=SEARCH_PATH, body=req_body)
    if result.status_code != 200:
        raise RuntimeError(f"search failed: status={result.status_code}, body={result.text}")

    resp_json = result.json()
    if resp_json.get("code") != "Success":
        raise RuntimeError(f"search api failed: body={result.text}")

    search_results = []
    for item in resp_json.get("result", {}).get("data", []):
        fields = item.get("fields") or {}
        f_id = fields.get("f_id") or item.get("id")
        if not f_id:
            continue
        search_results.append(
            {
                "f_id": str(f_id),
                "f_text": str(fields.get("f_text", "")),
                "search_score": item.get("score"),
                "ann_score": item.get("ann_score"),
            }
        )
    return search_results, resp_json.get("result", {}).get("token_usage", {})

def build_rerank_service(rerank_provider):
    if rerank_provider == "qwen":
        return None
    if rerank_provider in {"voyage", "cohere"}:
        api_key = os.environ.get("VOYAGE_API_KEY")
        if not api_key:
            raise RuntimeError("VOYAGE_API_KEY is required when --rerank-provider voyage/cohere")
        return voyageai.Client(api_key=api_key)
    service = VikingKnowledgeBaseService(
        host=RERANK_HOST,
        scheme="https",
        connection_timeout=30,
        socket_timeout=30,
    )
    service.set_ak(AK)
    service.set_sk(SK)
    return service

def get_response_field(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

def rerank_scores_with_volc(rerank_service, query_text, search_results, rerank_model):
    rerank_input = [{"query": query_text, "content": item["f_text"]} for item in search_results]
    rerank_res = rerank_service.rerank(datas=rerank_input, rerank_model=rerank_model)
    scores = rerank_res.get("data", {}).get("scores")
    if scores is None:
        raise RuntimeError(f"invalid rerank response: {rerank_res}")
    return [float(score) for score in scores]

def rerank_scores_with_qwen(query_text, search_results, rerank_model):
    documents = [{"text": item["f_text"]} for item in search_results]
    response = dashscope.TextReRank.call(
        model=rerank_model,
        query={"text": query_text},
        documents=documents,
        top_n=len(documents),
        return_documents=True,
    )
    status_code = get_response_field(response, "status_code")
    if status_code != HTTPStatus.OK:
        raise RuntimeError(f"qwen rerank failed: status={status_code}, response={response}")

    output = get_response_field(response, "output", {})
    results = get_response_field(output, "results", [])
    scores_by_index = {}
    for result in results:
        index = get_response_field(result, "index")
        score = get_response_field(result, "relevance_score", get_response_field(result, "score"))
        if index is None or score is None:
            raise RuntimeError(f"invalid qwen rerank result item: {result}")
        scores_by_index[int(index)] = float(score)

    if len(scores_by_index) != len(search_results):
        raise RuntimeError(f"qwen score count mismatch: scores={len(scores_by_index)} results={len(search_results)}")
    return [scores_by_index[i] for i in range(len(search_results))]

def rerank_scores_with_voyage(rerank_service, query_text, search_results, rerank_model):
    documents = [item["f_text"] for item in search_results]
    reranking = rerank_service.rerank(query_text, documents, model=rerank_model, top_k=len(documents))
    scores_by_index = {}
    for result in reranking.results:
        index = get_response_field(result, "index")
        score = get_response_field(result, "relevance_score")
        if index is None or score is None:
            raise RuntimeError(f"invalid voyage rerank result item: {result}")
        scores_by_index[int(index)] = float(score)

    if len(scores_by_index) != len(search_results):
        raise RuntimeError(f"voyage score count mismatch: scores={len(scores_by_index)} results={len(search_results)}")
    return [scores_by_index[i] for i in range(len(search_results))]

# 对 Viking 召回结果进行 rerank，并按 rerank_score 降序排序。
def rerank_results(rerank_service, query_text, search_results, rerank_provider, rerank_model):
    if not search_results:
        return []

    if rerank_provider == "qwen":
        scores = rerank_scores_with_qwen(query_text, search_results, rerank_model)
    elif rerank_provider in {"voyage", "cohere"}:
        scores = rerank_scores_with_voyage(rerank_service, query_text, search_results, rerank_model)
    else:
        scores = rerank_scores_with_volc(rerank_service, query_text, search_results, rerank_model)
    if len(scores) != len(search_results):
        raise RuntimeError(f"rerank score count mismatch: scores={len(scores)} results={len(search_results)}")

    reranked = []
    for item, score in zip(search_results, scores):
        new_item = dict(item)
        new_item["rerank_score"] = float(score)
        reranked.append(new_item)
    reranked.sort(key=lambda x: x["rerank_score"], reverse=True)
    return reranked

# 先按阈值过滤，再按相邻分数比例 step_beta 截断尾部结果。
def postprocess_truncate(reranked_results, threshold, step_beta):
    threshold_results = [item for item in reranked_results if item["rerank_score"] >= threshold]
    if not threshold_results:
        return []

    kept = [threshold_results[0]]
    for item in threshold_results[1:]:
        prev_score = kept[-1]["rerank_score"]
        current_score = item["rerank_score"]
        keep = current_score >= prev_score if prev_score <= 0 else current_score >= prev_score * step_beta
        if not keep:
            break
        kept.append(item)
    return kept

# Recall@K 使用 hit_count@K / min(G_i, K)，Precision@K 使用 hit_count@K / returned_count@K，MAP@K 使用标准 AP@K。
def hit_count_at_k(ranked_ids, relevant_ids, k):
    return len(set(ranked_ids[:k]) & relevant_ids)

def precision_at_k(ranked_ids, relevant_ids, k):
    returned_count = len(ranked_ids[:k])
    if returned_count == 0:
        return 0.0
    return hit_count_at_k(ranked_ids, relevant_ids, k) / returned_count

def ap_at_k(ranked_ids, relevant_ids, k):
    if not relevant_ids:
        return 0.0
    score_sum = 0.0
    hit_count = 0
    seen = set()
    for rank, doc_id in enumerate(ranked_ids[:k], start=1):
        if doc_id in seen:
            continue
        seen.add(doc_id)
        if doc_id in relevant_ids:
            hit_count += 1
            score_sum += hit_count / rank
    return score_sum / min(len(relevant_ids), k)

def compute_metrics(ranked_ids, relevant_ids, ks):
    metrics = {}
    for k in ks:
        denominator = min(len(relevant_ids), k)
        hits = hit_count_at_k(ranked_ids, relevant_ids, k)
        returned_count = len(ranked_ids[:k])
        metrics[f"recall@{k}"] = hits / denominator if denominator else 0.0
        metrics[f"precision@{k}"] = hits / returned_count if returned_count else 0.0
        metrics[f"map@{k}"] = ap_at_k(ranked_ids, relevant_ids, k)
        metrics[f"hit_count@{k}"] = hits
        metrics[f"possible_hit_count@{k}"] = denominator
        metrics[f"returned_count@{k}"] = returned_count
    return metrics

def compact_result(item):
    return {
        "f_id": item["f_id"],
        "f_text": item.get("f_text", ""),
        "search_score": item.get("search_score"),
        "ann_score": item.get("ann_score"),
        "rerank_score": item.get("rerank_score"),
    }

def build_view(results, relevant_ids, top_n):
    view = []
    for rank, item in enumerate(results[:top_n], start=1):
        row = compact_result(item)
        row["rank"] = rank
        row["is_hit"] = item["f_id"] in relevant_ids
        view.append(row)
    return view

# 单 query 只调用一次检索和 rerank，然后派生三套策略结果。
def evaluate_one_query(item, client, rerank_service, args):
    start = time.perf_counter()
    relevant_ids = set(item["relevant_ids"])

    search_results, token_usage = search_vikingdb(
        client=client,
        collection_name=args.collection_name,
        index_name=args.index_name,
        query_text=item["query_text"],
        limit=args.search_limit,
    )
    reranked_results = rerank_results(rerank_service, item["query_text"], search_results, args.rerank_provider, args.rerank_model)
    truncated_results = postprocess_truncate(reranked_results, args.threshold, args.step_beta)

    strategy_results = {
        "viking_only": search_results,
        "viking_rerank": reranked_results,
        "viking_rerank_truncate": truncated_results,
    }
    strategy_metrics = {
        name: compute_metrics([x["f_id"] for x in results], relevant_ids, args.ks)
        for name, results in strategy_results.items()
    }

    row = {
        "query_id": item["query_id"],
        "query_text": item["query_text"],
        "relevant_ids": sorted(relevant_ids),
        "relevant_count": len(relevant_ids),
        "elapsed_sec": round(time.perf_counter() - start, 4),
        "token_usage": token_usage,
        "result_counts": {name: len(results) for name, results in strategy_results.items()},
        "strategy_metrics": strategy_metrics,
        "reranked_full_results": [compact_result(x) for x in reranked_results],
        "views": {name: build_view(results, relevant_ids, args.viz_top_n) for name, results in strategy_results.items()},
    }
    LOG.info(
        "query done: query_id=%s search=%s rerank=%s truncate=%s elapsed=%.2fs",
        row["query_id"],
        row["result_counts"]["viking_only"],
        row["result_counts"]["viking_rerank"],
        row["result_counts"]["viking_rerank_truncate"],
        row["elapsed_sec"],
    )
    return row

# 汇总每个策略的 query 平均指标和命中计数。
def evaluate_queries(eval_items, client, rerank_service, args):
    rows = []
    for index, item in enumerate(eval_items, start=1):
        rows.append(evaluate_one_query(item, client, rerank_service, args))
        if args.rerank_sleep_seconds > 0 and index < len(eval_items):
            LOG.info("sleeping between rerank calls: seconds=%s", args.rerank_sleep_seconds)
            time.sleep(args.rerank_sleep_seconds)
    return rows

def summarize_strategy(per_query_rows, ks, strategy_name):
    summary = {
        "query_count": len(per_query_rows),
        "total_relevant_count": sum(row["relevant_count"] for row in per_query_rows),
    }
    for k in ks:
        recall_key = f"recall@{k}"
        precision_key = f"precision@{k}"
        map_key = f"map@{k}"
        hit_key = f"hit_count@{k}"
        possible_key = f"possible_hit_count@{k}"
        returned_key = f"returned_count@{k}"
        summary[recall_key] = sum(row["strategy_metrics"][strategy_name][recall_key] for row in per_query_rows) / len(per_query_rows)
        summary[precision_key] = sum(row["strategy_metrics"][strategy_name][precision_key] for row in per_query_rows) / len(per_query_rows)
        summary[map_key] = sum(row["strategy_metrics"][strategy_name][map_key] for row in per_query_rows) / len(per_query_rows)
        summary[f"total_{hit_key}"] = sum(row["strategy_metrics"][strategy_name][hit_key] for row in per_query_rows)
        summary[f"total_{possible_key}"] = sum(row["strategy_metrics"][strategy_name][possible_key] for row in per_query_rows)
        summary[f"total_{returned_key}"] = sum(row["strategy_metrics"][strategy_name][returned_key] for row in per_query_rows)
    return summary

def summarize_all(per_query_rows, ks):
    return {name: summarize_strategy(per_query_rows, ks, name) for name, _ in STRATEGIES}

def frange_int(start, end, step):
    scale = 100
    start_i = int(round(start * scale))
    end_i = int(round(end * scale))
    step_i = int(round(step * scale))
    return [i / scale for i in range(start_i, end_i + 1, step_i)]

# 网格搜索只复用已 rerank 的分数，不重复调用线上接口。
def run_grid_search(per_query_rows, ks, args):
    thresholds = frange_int(args.grid_threshold_min, args.grid_threshold_max, args.grid_threshold_step)
    step_betas = frange_int(args.grid_step_beta_min, args.grid_step_beta_max, args.grid_step_beta_step)
    rows = []

    LOG.info("grid search started: thresholds=%s step_betas=%s objective=%s", len(thresholds), len(step_betas), args.grid_objective)
    for threshold in thresholds:
        for step_beta in step_betas:
            pseudo_rows = []
            final_counts = []
            for row in per_query_rows:
                relevant_ids = set(row["relevant_ids"])
                truncated = postprocess_truncate(row["reranked_full_results"], threshold, step_beta)
                final_counts.append(len(truncated))
                pseudo_rows.append(
                    {
                        "relevant_count": row["relevant_count"],
                        "strategy_metrics": {
                            "grid": compute_metrics([x["f_id"] for x in truncated], relevant_ids, ks)
                        },
                    }
                )
            combo = summarize_strategy(pseudo_rows, ks, "grid")
            combo.update(
                {
                    "threshold": threshold,
                    "step_beta": step_beta,
                    "avg_final_count": sum(final_counts) / len(final_counts) if final_counts else 0.0,
                    "min_final_count": min(final_counts) if final_counts else 0,
                    "max_final_count": max(final_counts) if final_counts else 0,
                }
            )
            if args.grid_objective not in combo:
                raise ValueError(f"unknown grid objective: {args.grid_objective}")
            rows.append(combo)

    rows.sort(key=lambda x: (x[args.grid_objective], x.get("map@10", 0.0), x.get("recall@10", 0.0)), reverse=True)
    best = rows[0] if rows else {}
    LOG.info("grid search best: %s", json.dumps(best, ensure_ascii=False))

    if args.grid_output_csv:
        pd.DataFrame(rows).to_csv(args.grid_output_csv, index=False)
        LOG.info("saved grid csv: %s", args.grid_output_csv)
    if args.grid_output_json:
        payload = {"objective": args.grid_objective, "best": best, "top10": rows[:10], "all_results": rows}
        Path(args.grid_output_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        LOG.info("saved grid json: %s", args.grid_output_json)

    return {
        "objective": args.grid_objective,
        "combo_count": len(rows),
        "best": best,
        "top10": rows[:10],
        "output_csv": args.grid_output_csv,
        "output_json": args.grid_output_json,
    }

def fmt_score(value):
    if value is None:
        return ""
    try:
        return f"{float(value):.6f}"
    except (TypeError, ValueError):
        return str(value)

def render_result_table(title, results):
    rows = []
    for item in results:
        hit_class = "hit" if item["is_hit"] else "miss"
        hit_text = "YES" if item["is_hit"] else "NO"
        rows.append(
            "<tr>"
            f"<td>{item['rank']}</td>"
            f"<td class='{hit_class}'>{hit_text}</td>"
            f"<td>{html.escape(item['f_id'])}</td>"
            f"<td>{html.escape(fmt_score(item.get('search_score')))}</td>"
            f"<td>{html.escape(fmt_score(item.get('ann_score')))}</td>"
            f"<td>{html.escape(fmt_score(item.get('rerank_score')))}</td>"
            f"<td>{html.escape(truncate_text(item.get('f_text', '')))}</td>"
            "</tr>"
        )
    if not rows:
        rows.append("<tr><td colspan='7'>No results</td></tr>")
    return (
        f"<h4>{html.escape(title)}</h4>"
        "<table><thead><tr><th>rank</th><th>hit</th><th>f_id</th>"
        "<th>search_score</th><th>ann_score</th><th>rerank_score</th><th>f_text</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )

# 生成 HTML，便于肉眼对比 Viking、rerank、截断三套排序。
def save_html_visualization(per_query_rows, strategy_summary, output_html, args):
    if not output_html:
        return

    summary_tables = []
    for strategy_name, strategy_label in STRATEGIES:
        rows = []
        for key, value in strategy_summary[strategy_name].items():
            value = f"{value:.6f}" if isinstance(value, float) else value
            rows.append(f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(str(value))}</td></tr>")
        summary_tables.append(f"<div><h3>{html.escape(strategy_label)}</h3><table><tbody>{''.join(rows)}</tbody></table></div>")

    query_blocks = []
    for row in per_query_rows:
        metric_lines = []
        for strategy_name, strategy_label in STRATEGIES:
            metrics = row["strategy_metrics"][strategy_name]
            parts = [
                f"R@{k}={metrics[f'recall@{k}']:.4f}, P@{k}={metrics[f'precision@{k}']:.4f}, "
                f"MAP@{k}={metrics[f'map@{k}']:.4f}, "
                f"hit={metrics[f'hit_count@{k}']}/{metrics[f'possible_hit_count@{k}']}, "
                f"returned={metrics[f'returned_count@{k}']}"
                for k in args.ks
            ]
            metric_lines.append(f"<li><b>{html.escape(strategy_label)}:</b> {html.escape(' | '.join(parts))}</li>")

        relevant_preview = ", ".join(row["relevant_ids"][:20])
        if len(row["relevant_ids"]) > 20:
            relevant_preview += f" ... (+{len(row['relevant_ids']) - 20})"
        query_blocks.append(
            "<section>"
            f"<h3>{html.escape(row['query_id'])}</h3>"
            f"<p><b>query_text:</b> {html.escape(row['query_text'])}</p>"
            f"<ul class='metrics'>{''.join(metric_lines)}</ul>"
            f"<p><b>GroundTruth({row['relevant_count']}):</b> {html.escape(relevant_preview)}</p>"
            "<div class='grid'>"
            f"<div>{render_result_table('Viking raw search topN', row['views']['viking_only'])}</div>"
            f"<div>{render_result_table('Rerank sorted topN', row['views']['viking_rerank'])}</div>"
            f"<div>{render_result_table('After threshold + step_beta topN', row['views']['viking_rerank_truncate'])}</div>"
            "</div></section>"
        )

    content = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Yingshi Retrieval Rerank Visualization</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #222; }}
    section {{ border-top: 2px solid #ddd; padding-top: 18px; margin-top: 28px; }}
    table {{ border-collapse: collapse; width: 100%; table-layout: fixed; font-size: 12px; }}
    th, td {{ border: 1px solid #ddd; padding: 6px; vertical-align: top; word-break: break-all; }}
    th {{ background: #f6f8fa; }}
    .grid {{ display: grid; grid-template-columns: 1fr; gap: 18px; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }}
    .hit {{ color: #0a7f26; font-weight: 700; }}
    .miss {{ color: #b42318; font-weight: 700; }}
    .note {{ background: #fff8db; border: 1px solid #f0d36b; padding: 10px; border-radius: 6px; }}
    .metrics {{ line-height: 1.8; }}
  </style>
</head>
<body>
  <h1>Yingshi Retrieval + Rerank Visualization</h1>
  <p class="note">Recall@K = hit_count@K / min(G_i, K)；Precision@K = hit_count@K / returned_count@K。截断参数：threshold={args.threshold}, step_beta={args.step_beta}</p>
  <h2>Args</h2>
  <pre>{html.escape(json.dumps(vars(args), ensure_ascii=False, indent=2))}</pre>
  <h2>Strategy Summary</h2>
  <div class="summary-grid">{''.join(summary_tables)}</div>
  <h2>Per Query Visualization</h2>
  {''.join(query_blocks)}
</body>
</html>
"""
    Path(output_html).write_text(content, encoding="utf-8")
    LOG.info("saved html visualization: %s", output_html)

# 保存 JSON/CSV/HTML 三类产物；CSV 中嵌套字段以 JSON 字符串存储。
def save_outputs(per_query_rows, summary, args):
    result = {"args": vars(args), "summary": summary, "per_query": per_query_rows}
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        LOG.info("saved json result: %s", args.output_json)
    if args.output_csv:
        csv_rows = []
        for row in per_query_rows:
            csv_row = dict(row)
            for field in ["relevant_ids", "result_counts", "strategy_metrics", "reranked_full_results", "views", "token_usage"]:
                csv_row[field] = json.dumps(csv_row[field], ensure_ascii=False)
            csv_rows.append(csv_row)
        pd.DataFrame(csv_rows).to_csv(args.output_csv, index=False)
        LOG.info("saved csv result: %s", args.output_csv)
    save_html_visualization(per_query_rows, summary["strategy_summary"], args.output_html, args)

def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate VikingDB retrieval + KB rerank + truncation on Yingshi labels.")
    parser.add_argument("--collection-name", default=DEFAULT_COLLECTION_NAME)
    parser.add_argument("--index-name", default=DEFAULT_INDEX_NAME)
    parser.add_argument("--query-parquet", default=DEFAULT_QUERY_PARQUET)
    parser.add_argument("--extra-info", default=DEFAULT_EXTRA_INFO)
    parser.add_argument("--search-limit", type=int, default=50)
    parser.add_argument("--threshold", type=float, default=0.0, help="Truncation threshold.")
    parser.add_argument("--step-beta", type=float, default=0.8, help="Truncation ratio in [0, 1].")
    parser.add_argument("--rerank-provider", default=DEFAULT_RERANK_PROVIDER, choices=["volc", "qwen", "voyage", "cohere"])
    parser.add_argument("--rerank-model", default=DEFAULT_RERANK_MODEL)
    parser.add_argument("--rerank-sleep-seconds", type=float, default=0.0, help="Sleep seconds between rerank calls, useful for low RPM providers.")
    parser.add_argument("--ks", nargs="+", type=int, default=list(DEFAULT_KS))
    parser.add_argument("--max-queries", type=int, default=0, help="Debug only: evaluate first N queries.")
    parser.add_argument("--output-json", default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-csv", default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--output-html", default=DEFAULT_OUTPUT_HTML)
    parser.add_argument("--viz-top-n", type=int, default=10)
    parser.add_argument("--grid-search", action="store_true")
    parser.add_argument("--grid-objective", default="map@10")
    parser.add_argument("--grid-output-csv", default=DEFAULT_GRID_OUTPUT_CSV)
    parser.add_argument("--grid-output-json", default=DEFAULT_GRID_OUTPUT_JSON)
    parser.add_argument("--grid-threshold-min", type=float, default=0.0)
    parser.add_argument("--grid-threshold-max", type=float, default=0.2)
    parser.add_argument("--grid-threshold-step", type=float, default=0.01)
    parser.add_argument("--grid-step-beta-min", type=float, default=0.1)
    parser.add_argument("--grid-step-beta-max", type=float, default=0.9)
    parser.add_argument("--grid-step-beta-step", type=float, default=0.05)
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args()

def main():
    args = parse_args()
    setup_logging(args.log_level)
    if not 0 <= args.step_beta <= 1:
        raise ValueError("--step-beta must be between 0 and 1")
    if args.search_limit <= 0:
        raise ValueError("--search-limit must be greater than 0")
    if not args.ks:
        raise ValueError("--ks must not be empty")

    if args.rerank_provider == "qwen" and args.rerank_model == DEFAULT_RERANK_MODEL:
        args.rerank_model = DEFAULT_QWEN_RERANK_MODEL
    if args.rerank_provider in {"voyage", "cohere"} and args.rerank_model == DEFAULT_RERANK_MODEL:
        args.rerank_model = DEFAULT_VOYAGE_RERANK_MODEL
    if args.rerank_provider in {"voyage", "cohere"} and args.rerank_sleep_seconds <= 0:
        args.rerank_sleep_seconds = 21.0
    LOG.info(
        "start eval: collection=%s index=%s search_limit=%s threshold=%s step_beta=%s rerank_provider=%s rerank_model=%s ks=%s",
        args.collection_name,
        args.index_name,
        args.search_limit,
        args.threshold,
        args.step_beta,
        args.rerank_provider,
        args.rerank_model,
        args.ks,
    )
    start = time.perf_counter()

    eval_items = load_eval_data(args.extra_info, args.query_parquet)
    if args.max_queries > 0:
        eval_items = eval_items[: args.max_queries]
        LOG.warning("max_queries enabled, only evaluate first %s queries", len(eval_items))

    client = ClientForDataApi(ak=AK, sk=SK, host=DEFAULT_HOST)
    rerank_service = build_rerank_service(args.rerank_provider)
    per_query_rows = evaluate_queries(eval_items, client, rerank_service, args)

    strategy_summary = summarize_all(per_query_rows, args.ks)
    summary = {
        "strategy_summary": strategy_summary,
        "selected_strategy": "viking_rerank_truncate",
        "selected_strategy_summary": strategy_summary["viking_rerank_truncate"],
    }
    if args.grid_search:
        summary["grid_search"] = run_grid_search(per_query_rows, args.ks, args)

    LOG.info("summary: %s", json.dumps(summary, ensure_ascii=False))
    save_outputs(per_query_rows, summary, args)
    LOG.info("eval finished: elapsed=%.2fs", time.perf_counter() - start)

if __name__ == "__main__":
    main()
