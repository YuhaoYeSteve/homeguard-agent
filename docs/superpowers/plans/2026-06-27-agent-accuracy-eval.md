# Agent Accuracy Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为当前安防 Agent 增加一套可重复运行的准确性评测框架，第一版排除视频搜索，覆盖 IoT、联网搜索、闲聊、多轮上下文和安全边界。

**Architecture:** 评测核心放在 `backend/app/evaluation/agent_accuracy.py`，负责读取 JSONL 样例、调用响应提供者、对 `ChatResponse` 做规则评分。CLI 放在 `backend/scripts/evaluate_agent_accuracy.py`，默认调用本地 `/api/chat`，也支持通过参数指定 case 文件、API 地址和报告输出路径。

**Tech Stack:** Python 3、Pydantic 模型、httpx、pytest。

---

### Task 1: 评测核心规则

**Files:**
- Create: `backend/tests/test_agent_accuracy_eval.py`
- Create: `backend/app/evaluation/__init__.py`
- Create: `backend/app/evaluation/agent_accuracy.py`

- [ ] **Step 1: Write failing tests**

验证三类核心评分行为：正常 IoT 参数命中、安全边界禁止工具调用、报告汇总指标。

- [ ] **Step 2: Run red test**

Run: `cd backend && PYTHONPATH=. python3 -m pytest tests/test_agent_accuracy_eval.py -v`

Expected: FAIL，因为 `app.evaluation.agent_accuracy` 尚不存在。

- [ ] **Step 3: Implement scoring**

实现 `EvaluationCase`、`CaseResult`、`score_case()`、`summarize_results()`、`load_cases()`。

- [ ] **Step 4: Run green test**

Run: `cd backend && PYTHONPATH=. python3 -m pytest tests/test_agent_accuracy_eval.py -v`

Expected: PASS。

### Task 2: 评测样例集

**Files:**
- Create: `backend/evals/agent_accuracy_cases.jsonl`

- [ ] **Step 1: Add cases**

写入 35 条样例：10 条 IoT、6 条多轮上下文、5 条联网搜索、4 条闲聊、10 条安全边界。所有样例 `expected_route` 均不使用 `video_search`。

- [ ] **Step 2: Validate cases**

Run: `cd backend && PYTHONPATH=. python3 -m pytest tests/test_agent_accuracy_eval.py -v`

Expected: PASS，JSONL 可被加载且不含视频搜索样例。

### Task 3: CLI 和报告

**Files:**
- Create: `backend/scripts/evaluate_agent_accuracy.py`

- [ ] **Step 1: Add CLI**

实现参数：`--cases`、`--base-url`、`--output`、`--timeout`。运行后逐条调用 `/api/chat`，生成 Markdown 报告。

- [ ] **Step 2: Verify CLI help**

Run: `cd backend && PYTHONPATH=. python3 scripts/evaluate_agent_accuracy.py --help`

Expected: exit 0，并展示参数说明。

### Task 4: Full verification

**Files:**
- No additional files.

- [ ] **Step 1: Run focused tests**

Run: `cd backend && PYTHONPATH=. python3 -m pytest tests/test_agent_accuracy_eval.py -v`

Expected: PASS。

- [ ] **Step 2: Run backend regression tests**

Run: `cd backend && PYTHONPATH=. python3 -m pytest tests -v`

Expected: PASS。

- [ ] **Step 3: Run dry evaluation**

Run: `cd backend && PYTHONPATH=. python3 scripts/evaluate_agent_accuracy.py --help`

Expected: PASS。真实准确率评测需要本地后端和模型凭证可用后再运行。
